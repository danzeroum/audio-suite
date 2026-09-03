"""Glitch analyzer v1 — detects objective digital discontinuities.

Per the roadmap (Fase 1 GLITCH v1), this version detects:
  - Click / pop: single-sample or very short impulsive discontinuity
  - Dropout: abrupt silence in an otherwise non-silent signal
  - Short digital repetition: same N samples repeated (buffer stutter)

Advanced glitch types (zipper noise, buffer underrun, stitching artifacts)
are deferred to Fase 2/3 and require a labeled corpus per the calibração
policy (A2).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..models import PCM, Profile, Status
from . import register
from .base import AudioAnalyzer


@register
class GlitchAnalyzer(AudioAnalyzer):
    ID = "glitch"
    NAME = "Glitch Detector v1"
    VERSION = "1.0.0"
    METHOD = "derivative spike + zero-run + repetition scan"
    DEFAULT_LIMITATIONS = [
        "Detects clicks/dropouts/repetition only; zipper noise is Fase 2+",
        "Percussive onsets may false-trigger if sensitivity is too high",
        "Recommended corpus calibration before production use (A2)",
        "Per-channel detection; cross-channel glitches are not correlated",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        return audio.n_frames >= 16

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        click_sensitivity = float(params.get("click_sensitivity", 6.0))
        dropout_min_ms = float(params.get("dropout_min_ms", 10.0))
        dropout_threshold = float(params.get("dropout_threshold", 0.001))
        repeat_min_samples = int(params.get("repeat_min_samples", 32))
        min_severity_for_warning = int(params.get("min_events_for_warning", 1))

        findings: list = []
        total_events = 0

        for c in range(audio.channels):
            x = audio.samples[c].astype(np.float64)
            events: list[dict[str, Any]] = []

            # 1. Click / pop detection via 2nd derivative
            d2 = np.diff(x, n=2)
            if len(d2) > 0:
                rms_d2 = float(np.sqrt(np.mean(d2**2))) + 1e-12
                clicks = np.abs(d2) > click_sensitivity * rms_d2
                # Group adjacent click samples
                click_ranges = self._runs_bool(clicks, min_run=1)
                for s, e in click_ranges:
                    # Translate back to original index (diff shifted by 1)
                    t_start_ms = 1000.0 * max(s - 1, 0) / audio.sample_rate
                    t_end_ms = 1000.0 * e / audio.sample_rate
                    events.append(
                        {
                            "type": "click",
                            "time_range_ms": [round(t_start_ms, 3), round(t_end_ms, 3)],
                            "channel": c,
                            "amplitude": round(float(np.abs(x[max(s, 0)])), 4),
                        }
                    )

            # 2. Dropout detection
            abs_x = np.abs(x)
            silent = abs_x < dropout_threshold
            min_samples = int(audio.sample_rate * dropout_min_ms / 1000)
            min_samples = max(min_samples, 1)
            drop_ranges = self._runs_bool(silent, min_run=min_samples)
            # Only flag dropouts inside non-silent regions
            for s, e in drop_ranges:
                # Check that there's actual signal around the dropout
                ctx_start = max(0, s - min_samples * 4)
                ctx_end = min(audio.n_frames, e + min_samples * 4)
                if ctx_end - ctx_start <= (e - s):
                    continue  # No context — likely overall silence, skip
                ctx_rms = float(np.sqrt(np.mean(x[ctx_start:ctx_end] ** 2)))
                if ctx_rms < 10 * dropout_threshold:
                    continue
                events.append(
                    {
                        "type": "dropout",
                        "time_range_ms": [
                            round(1000.0 * s / audio.sample_rate, 3),
                            round(1000.0 * e / audio.sample_rate, 3),
                        ],
                        "channel": c,
                        "duration_ms": round(1000.0 * (e - s) / audio.sample_rate, 3),
                    }
                )

            # 3. Short digital repetition (buffer stutter)
            rep_events = self._detect_repetition(x, repeat_min_samples)
            for s, length in rep_events:
                events.append(
                    {
                        "type": "repetition",
                        "time_range_ms": [
                            round(1000.0 * s / audio.sample_rate, 3),
                            round(1000.0 * (s + length) / audio.sample_rate, 3),
                        ],
                        "channel": c,
                        "repeat_length_samples": length,
                    }
                )

            total_events += len(events)
            if events:
                findings.append(
                    self._finding(
                        check_id=f"glitch.channel_{c}",
                        metric="glitch_event_count",
                        value=float(len(events)),
                        unit="events",
                        status=Status.WARNING,
                        confidence=0.85,
                        message=f"{len(events)} glitch events on channel {c}",
                        time_range_ms=None,
                        evidence={"events": events[:50]},  # cap to avoid bloat
                    )
                )

        if total_events == 0:
            findings.append(
                self._finding(
                    check_id="glitch.summary",
                    metric="glitch_event_count",
                    value=0.0,
                    unit="events",
                    status=Status.PASS,
                    confidence=0.95,
                    message="no glitches detected",
                    evidence={"channels_scanned": audio.channels},
                )
            )
        elif total_events >= min_severity_for_warning:
            # Already have per-channel warnings; this is a summary
            pass

        return findings

    def profile_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "click_sensitivity": {"type": "number", "minimum": 1.0, "default": 6.0},
                "dropout_min_ms": {"type": "number", "minimum": 1.0, "default": 10.0},
                "dropout_threshold": {"type": "number", "minimum": 0.0, "maximum": 0.1, "default": 0.001},
                "repeat_min_samples": {"type": "integer", "minimum": 4, "default": 32},
                "min_events_for_warning": {"type": "integer", "minimum": 1, "default": 1},
            },
            "additionalProperties": False,
        }

    @staticmethod
    def _runs_bool(mask: np.ndarray, min_run: int) -> list[tuple[int, int]]:
        if not mask.any():
            return []
        diff = np.diff(mask.astype(np.int8), prepend=0, append=0)
        starts = np.where(diff == 1)[0]
        ends = np.where(diff == -1)[0]
        return [(int(s), int(e)) for s, e in zip(starts, ends) if e - s >= min_run]

    @staticmethod
    def _detect_repetition(x: np.ndarray, min_len: int) -> list[tuple[int, int]]:
        """Detect blocks where a sub-block of length L is repeated immediately.

        Returns list of (start, repeat_length).

        Equivalência exata com o scan original (CORP-04, custo O(n) por L):
        d[i] = max|x[i:i+L] - x[i+L:i+2L]| < 1e-6 é verdadeiro se e somente se
        TODO par elementar satisfaz |x[i+j] - x[i+L+j]| < 1e-6. Um somatório
        deslizante (cumsum) sobre o vetor booleano de igualdades reproduz o
        match por janela sem materializar d[i] — de ~4,6 s/fixture (loop
        Python) para milissegundos, sem mudar nenhum resultado.
        """
        events: list[tuple[int, int]] = []
        n = len(x)
        # Scan candidate repeat lengths (powers of 2 from min_len up to 4096)
        L = min_len
        while min(4096, n // 2) >= L:
            n_windows = n - 2 * L + 1
            if n_windows > 0:
                eq = (np.abs(x[: n - L] - x[L:]) < 1e-6).astype(np.int64)
                cum = np.concatenate(([0], np.cumsum(eq)))
                window_true = cum[np.arange(n_windows) + L] - cum[np.arange(n_windows)]
                match = window_true == L  # d[i] < 1e-6 para toda a janela
                # Replay do scan original: avança 2L em match, 1 caso contrário.
                # Equivalente a emitir cada posição de match (em ordem) que seja
                # >= cursor (= início do último evento + 2L), O(nº de matches).
                cursor = 0
                for i in np.flatnonzero(match):
                    i = int(i)
                    if i >= cursor:
                        events.append((i, L))
                        cursor = i + 2 * L
            L *= 2
        return events
