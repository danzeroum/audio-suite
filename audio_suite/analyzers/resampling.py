"""Resampling artifact analyzer — detects aliasing and abnormal spectral cutoff.

Per Fase 2 RESAMPLING: distinguishes:
  - aliasing (mirror images of high content around Nyquist/2)
  - effective bandwidth (where energy drops below threshold)
  - transcode loss indicators (sharp low-pass below codec Nyquist)

IMPORTANT (rule from the roadmap): does NOT conclude "originally from MP3"
just because of a spectral cutoff. Such inference requires corpus calibration.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from ..models import PCM, Profile, Status
from . import register
from .base import AudioAnalyzer


def _power_spectrum(x: np.ndarray, sr: int, n_fft: int = 4096) -> tuple[np.ndarray, np.ndarray]:
    if len(x) < n_fft:
        x = np.pad(x, (0, n_fft - len(x)))
    win = np.hanning(n_fft)
    X = np.abs(np.fft.rfft(x[:n_fft] * win)) ** 2
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
    return X, freqs


@register
class ResamplingAnalyzer(AudioAnalyzer):
    ID = "resampling"
    NAME = "Resampling Artifact Detector"
    VERSION = "1.0.0"
    METHOD = "spectral energy distribution + aliasing mirror scan"
    DEFAULT_LIMITATIONS = [
        "Cannot infer source codec from cutoff alone (rule 1)",
        "Aliasing detection is heuristic; false positives on bright content",
        "Requires corpus calibration for production use (A2)",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        return audio.n_frames >= 1024

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        alias_thr = float(params.get("aliasing_threshold_db", -60.0))
        bw_drop_thr = float(params.get("bandwidth_drop_db", -30.0))

        x = audio.mono_mix().astype(np.float64)
        X, freqs = _power_spectrum(x, audio.sample_rate)
        nyq = audio.sample_rate / 2.0

        # Effective bandwidth: highest freq above -40 dBFS threshold
        db = 10 * np.log10(X + 1e-12)
        bw_mask = db > bw_drop_thr
        if bw_mask.any():
            effective_bw_hz = float(freqs[bw_mask].max())
        else:
            effective_bw_hz = 0.0

        # Aliasing: look for spectral energy mirror around sr/4 (typical of
        # bad resampling). Energy near sr/4 should not exceed energy below.
        quarter = nyq / 2.0
        below_mask = freqs < quarter * 0.5
        mirror_mask = (freqs > quarter * 0.9) & (freqs < quarter * 1.1)
        if below_mask.any() and mirror_mask.any():
            e_below = float(np.mean(X[below_mask]))
            e_mirror = float(np.mean(X[mirror_mask]))
            alias_db = 10 * np.log10((e_mirror + 1e-12) / (e_below + 1e-12))
        else:
            alias_db = -120.0

        aliasing_bands: list[dict[str, Any]] = []
        if alias_db > alias_thr:
            aliasing_bands.append({
                "center_hz": round(quarter, 1),
                "level_db": round(alias_db, 2),
            })

        if alias_db > alias_thr:
            status = Status.WARNING
            msg = f"possible aliasing at {quarter:.0f}Hz ({alias_db:.1f}dB)"
        else:
            status = Status.PASS
            msg = f"no significant aliasing (effective BW {effective_bw_hz:.0f}Hz)"

        return [self._finding(
            check_id="resampling.artifacts",
            metric="aliasing_level_db",
            value=round(float(alias_db), 2),
            unit="dB",
            status=status,
            confidence=0.7,
            message=msg,
            evidence={
                "effective_bandwidth_hz": round(effective_bw_hz, 1),
                "nyquist_hz": nyq,
                "aliasing_bands": aliasing_bands,
                "aliasing_threshold_db": alias_thr,
                "bandwidth_drop_db": bw_drop_thr,
            },
            extra_limitations=[
                "result is observation-level; not a forensic codec identification",
            ],
        )]

    def profile_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "aliasing_threshold_db": {"type": "number", "default": -60.0},
                "bandwidth_drop_db": {"type": "number", "default": -30.0},
            },
            "additionalProperties": False,
        }
