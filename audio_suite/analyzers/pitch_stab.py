"""Pitch stability analyzer — drift, wow, flutter (Fase 3).

Detects:
  - Pitch drift: slow deviation of fundamental frequency over time
  - Wow: low-frequency modulation (0.1-10 Hz) of pitch
  - Flutter: higher-frequency modulation (10-200 Hz) of pitch

Uses autocorrelation-based pitch tracking on short frames, then analyzes
the pitch contour for instability.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..models import PCM, Profile, Status
from . import register
from .base import AudioAnalyzer


def _pitch_track_autocorr(
    x: np.ndarray, sr: int, frame_ms: float = 50, hop_ms: float = 25, fmin: float = 50.0, fmax: float = 2000.0
) -> np.ndarray:
    """Track pitch via autocorrelation. Returns array of f0 estimates (Hz).

    NaN where unvoiced or untrackable.
    """
    frame = int(sr * frame_ms / 1000)
    hop = int(sr * hop_ms / 1000)
    lag_min = int(sr / fmax)
    lag_max = int(sr / fmin)
    if lag_max >= frame:
        lag_max = frame - 1
    if lag_min < 1:
        lag_min = 1

    n_frames = max(0, (len(x) - frame) // hop + 1)
    f0 = np.full(n_frames, np.nan)
    for i in range(n_frames):
        seg = x[i * hop : i * hop + frame]
        seg = seg - np.mean(seg)
        if np.max(np.abs(seg)) < 1e-6:
            continue
        # Autocorrelation
        corr = np.correlate(seg, seg, mode="full")[frame - 1 :]
        corr = corr / (corr[0] + 1e-12)
        # Search in valid lag range
        if lag_max < lag_min or lag_max >= len(corr):
            continue
        search = corr[lag_min : lag_max + 1]
        if len(search) == 0:
            continue
        peak = int(np.argmax(search))
        # Parabolic interpolation
        if 0 < peak < len(search) - 1:
            a, b, c = search[peak - 1], search[peak], search[peak + 1]
            denom = a - 2 * b + c
            if abs(denom) > 1e-12:
                peak = peak + 0.5 * (a - c) / denom
        lag = lag_min + peak
        if lag > 0:
            f0[i] = sr / lag
    return f0


def _cents_drift(f0: np.ndarray) -> float:
    """Total pitch drift in cents (100 cents = 1 semitone).

    Computed as the range of median-smoothed f0, in cents relative to mean.
    """
    valid = f0[np.isfinite(f0)]
    if len(valid) < 4:
        return 0.0
    mean_f = float(np.mean(valid))
    if mean_f <= 0:
        return 0.0
    # Median filter to remove octave errors
    from scipy.signal import medfilt

    try:
        smoothed = medfilt(valid, kernel_size=5)
    except Exception:
        smoothed = valid
    # Drift = max deviation from mean in cents
    cents = 1200 * np.log2(smoothed / mean_f)
    return float(np.max(cents) - np.min(cents))


def _wow_flutter_db(f0: np.ndarray, sr_frame: float) -> tuple[float, float]:
    """Estimate wow (0.1-10 Hz) and flutter (10-200 Hz) modulation depth in dB."""
    valid = f0[np.isfinite(f0)]
    if len(valid) < 8:
        return 0.0, 0.0
    mean_f = float(np.mean(valid))
    if mean_f <= 0:
        return 0.0, 0.0
    # Deviation in cents
    cents = 1200 * np.log2(valid / mean_f)
    # FFT of the cents contour
    spectrum = np.abs(np.fft.rfft(cents - np.mean(cents)))
    freqs = np.fft.rfftfreq(len(cents), d=1.0 / sr_frame)
    wow_band = (freqs >= 0.1) & (freqs <= 10.0)
    flutter_band = (freqs >= 10.0) & (freqs <= 200.0)
    wow_energy = float(np.sum(spectrum[wow_band] ** 2)) if wow_band.any() else 0.0
    flutter_energy = float(np.sum(spectrum[flutter_band] ** 2)) if flutter_band.any() else 0.0
    total = float(np.sum(spectrum**2)) + 1e-12
    # Convert ratio to dB
    wow_db = 10 * np.log10((wow_energy / total) + 1e-12)
    flutter_db = 10 * np.log10((flutter_energy / total) + 1e-12)
    return float(wow_db), float(flutter_db)


@register
class PitchStabilityAnalyzer(AudioAnalyzer):
    ID = "pitch_stab"
    NAME = "Pitch Stability (drift, wow, flutter)"
    VERSION = "1.0.0"
    METHOD = "autocorrelation pitch tracking + cents contour FFT"
    DEFAULT_LIMITATIONS = [
        "Autocorrelation pitch tracking; errors on polyphonic content",
        "Optimized for monophonic voice/instruments; corpus needed (A2)",
        "Wow/flutter bands are heuristic; not ITU-R BS.1116 compliant",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        return audio.n_frames >= audio.sample_rate  # at least 1 second

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        max_drift_cents = float(params.get("max_drift_cents", 50.0))
        x = audio.mono_mix().astype(np.float64)
        f0 = _pitch_track_autocorr(x, audio.sample_rate)
        n_voiced = int(np.sum(np.isfinite(f0)))
        if n_voiced < 4:
            return [
                self._finding(
                    check_id="pitch_stab.drift",
                    metric="pitch_drift_cents",
                    value=None,
                    unit="cents",
                    status=Status.NOT_APPLICABLE,
                    message="not enough voiced frames to track pitch",
                    evidence={"n_voiced_frames": n_voiced},
                )
            ]

        drift = _cents_drift(f0)
        frame_rate = 1000.0 / 25.0  # hop_ms=25 -> 40 Hz frame rate
        wow, flutter = _wow_flutter_db(f0, frame_rate)

        if drift > max_drift_cents:
            status = Status.WARNING
            msg = f"pitch drift {drift:.1f} cents exceeds {max_drift_cents}"
        else:
            status = Status.PASS
            msg = f"pitch drift {drift:.1f} cents within {max_drift_cents}"

        return [
            self._finding(
                check_id="pitch_stab.drift",
                metric="pitch_drift_cents",
                value=round(float(drift), 2),
                unit="cents",
                status=status,
                confidence=0.7,
                message=msg,
                evidence={
                    "n_voiced_frames": n_voiced,
                    "n_total_frames": len(f0),
                    "wow_modulation_db": round(float(wow), 3),
                    "flutter_modulation_db": round(float(flutter), 3),
                    "max_drift_cents": max_drift_cents,
                },
            )
        ]

    def profile_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "max_drift_cents": {"type": "number", "minimum": 0.0, "default": 50.0},
            },
            "additionalProperties": False,
        }
