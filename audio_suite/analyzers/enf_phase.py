"""ENF (Electrical Network Frequency) phase analyzer — experimental forensic (Fase 3).

Per the roadmap (Fase 3 ENF_PHASE): "Continuidade da fase da rede elétrica."
Marked as **extensão forense experimental**.

CRITICAL (rule 8 — Regra da Inferência):
  - This analyzer NEVER returns "authentic" or "tampered".
  - It returns `needs_review` with documented limitations.
  - Requires minimum duration (>= 60s recommended) and ENF SNR.
  - Requires a reference ENF database for true authentication.

What this analyzer DOES:
  - Detects the mains hum frequency (50 Hz or 60 Hz)
  - Tracks its phase over time
  - Flags discontinuities as potential edit points (needs_review)

What it does NOT do:
  - Authenticate recordings
  - Match against a grid reference
  - Conclude tampering
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..models import PCM, Profile, Status
from . import register
from .base import AudioAnalyzer


def _detect_mains_freq(x: np.ndarray, sr: int) -> tuple[float, float]:
    """Detect mains frequency (50 or 60 Hz) via spectral peak.

    Returns (freq, snr_db). SNR is peak-to-floor ratio.
    """
    if len(x) < sr:
        return 0.0, 0.0
    # FFT around 50/60 Hz
    n_fft = min(len(x), 65536)
    if n_fft < 2048:
        return 0.0, 0.0
    win = np.hanning(n_fft)
    X = np.abs(np.fft.rfft(x[:n_fft] * win)) ** 2
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
    # Search in 45-65 Hz
    band = (freqs >= 45) & (freqs <= 65)
    if not band.any():
        return 0.0, 0.0
    band_X = X[band]
    band_f = freqs[band]
    peak_idx = int(np.argmax(band_X))
    peak_freq = float(band_f[peak_idx])
    # SNR: peak vs median of band
    floor = float(np.median(band_X))
    peak = float(band_X[peak_idx])
    if floor <= 0:
        return peak_freq, 0.0
    snr = 10 * np.log10(peak / floor)
    return peak_freq, float(snr)


def _track_enf_phase(
    x: np.ndarray, sr: int, enf_freq: float, frame_ms: float = 1000.0, hop_ms: float = 500.0
) -> np.ndarray:
    """Track instantaneous ENF phase per frame via DFT bin.

    Returns array of phase values (radians) per frame. NaN where SNR too low.
    """
    frame = int(sr * frame_ms / 1000)
    hop = int(sr * hop_ms / 1000)
    n_frames = max(0, (len(x) - frame) // hop + 1)
    phases = np.full(n_frames, np.nan)
    if enf_freq <= 0 or frame < 4:
        return phases
    for i in range(n_frames):
        seg = x[i * hop : i * hop + frame]
        # DFT at exactly enf_freq
        t = np.arange(len(seg)) / sr
        c = np.sum(seg * np.exp(-2j * np.pi * enf_freq * t))
        phases[i] = float(np.angle(c))
    return phases


def _detect_phase_discontinuities(phases: np.ndarray, threshold_rad: float = 1.0) -> list[dict[str, Any]]:
    """Detect sudden phase jumps (potential edit points)."""
    if len(phases) < 2:
        return []
    # Unwrap phase
    unwrapped = np.unwrap(phases[np.isfinite(phases)])
    if len(unwrapped) < 2:
        return []
    # First derivative
    d = np.diff(unwrapped)
    # Large jumps
    events = []
    for i in np.where(np.abs(d) > threshold_rad)[0]:
        events.append(
            {
                "frame_index": int(i),
                "phase_jump_rad": round(float(d[i]), 4),
            }
        )
    return events


@register
class EnfPhaseAnalyzer(AudioAnalyzer):
    ID = "enf_phase"
    NAME = "ENF Phase Continuity (experimental forensic)"
    VERSION = "0.1.0"  # 0.x = experimental
    METHOD = "spectral mains detection + per-frame DFT phase tracking"
    DEFAULT_LIMITATIONS = [
        "EXPERIMENTAL forensic extension; do not use for authentication",
        "Never returns 'authentic' or 'tampered' — only needs_review",
        "Requires >= 60s duration and ENF SNR >= 10 dB for meaningful results",
        "No reference grid matching; phase discontinuities are not proof of editing",
        "Calibration against a known ENF database is required for forensic use (A2)",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        params = profile.analyzer_params(self.ID)
        # Opt-in: must be explicitly enabled in profile
        return bool(params.get("enabled", False)) and audio.n_frames >= audio.sample_rate

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        min_duration_s = float(params.get("min_duration_s", 60.0))
        min_snr_db = float(params.get("min_snr_db", 10.0))
        phase_threshold_rad = float(params.get("phase_threshold_rad", 1.0))

        x = audio.mono_mix().astype(np.float64)

        # Check duration
        if audio.duration_s < min_duration_s:
            return [
                self._finding(
                    check_id="enf_phase.applicability",
                    metric="enf_status",
                    value=None,
                    unit="enum",
                    status=Status.NEEDS_REVIEW,
                    message=(
                        f"duration {audio.duration_s:.1f}s < {min_duration_s}s required; "
                        "ENF analysis inconclusive"
                    ),
                    evidence={"duration_s": round(audio.duration_s, 2), "min_duration_s": min_duration_s},
                )
            ]

        mains_freq, snr = _detect_mains_freq(x, audio.sample_rate)

        if snr < min_snr_db:
            return [
                self._finding(
                    check_id="enf_phase.snr",
                    metric="enf_snr_db",
                    value=round(float(snr), 2),
                    unit="dB",
                    status=Status.NEEDS_REVIEW,
                    message=(
                        f"ENF SNR {snr:.1f} dB < {min_snr_db} dB; "
                        "no reliable mains hum detected, analysis inconclusive"
                    ),
                    evidence={
                        "detected_mains_freq_hz": round(mains_freq, 2),
                        "snr_db": round(snr, 2),
                        "min_snr_db": min_snr_db,
                    },
                )
            ]

        phases = _track_enf_phase(x, audio.sample_rate, mains_freq)
        events = _detect_phase_discontinuities(phases, phase_threshold_rad)

        # NEVER conclude "authentic" or "tampered"
        if events:
            msg = (
                f"{len(events)} phase discontinuities detected — POTENTIAL edit points; "
                "REQUIRES HUMAN REVIEW. Not proof of tampering."
            )
        else:
            msg = (
                "no phase discontinuities detected; this does NOT prove authenticity — "
                "requires reference grid comparison for forensic conclusion"
            )

        return [
            self._finding(
                check_id="enf_phase.continuity",
                metric="phase_discontinuity_count",
                value=float(len(events)),
                unit="events",
                status=Status.NEEDS_REVIEW,  # ALWAYS needs_review, per rule 8
                confidence=0.5,
                message=msg,
                evidence={
                    "detected_mains_freq_hz": round(mains_freq, 2),
                    "snr_db": round(snr, 2),
                    "n_frames_analyzed": len(phases),
                    "phase_discontinuities": events[:20],
                    "phase_threshold_rad": phase_threshold_rad,
                    "forensic_warning": (
                        "This result is experimental and does NOT constitute a forensic "
                        "conclusion. Reference grid matching and human review are required."
                    ),
                },
            )
        ]

    def profile_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean", "default": False},
                "min_duration_s": {"type": "number", "minimum": 1.0, "default": 60.0},
                "min_snr_db": {"type": "number", "default": 10.0},
                "phase_threshold_rad": {"type": "number", "minimum": 0.1, "default": 1.0},
            },
            "required": ["enabled"],
            "additionalProperties": False,
        }
