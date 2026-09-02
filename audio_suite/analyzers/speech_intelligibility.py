"""Speech intelligibility analyzer — STOI proxy for accessibility (Fase 2.5).

Per the roadmap (Fase 2.5 Acessibilidade): STOI/PESQ focused on accessibility.
This is a no-reference proxy that estimates intelligibility from objective
signal features (SNR, spectral clarity, transient preservation).

For full-reference STOI, use ref_quality with mode=speech-full-ref.

This analyzer is for accessibility auditing — does the signal meet minimum
intelligibility thresholds for hard-of-hearing listeners?
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..models import PCM, Profile, Status
from . import register
from .base import AudioAnalyzer


def _snr_db(x: np.ndarray, frame_ms: float, sr: int) -> float:
    """Estimate SNR via envelope analysis: signal vs silence floor."""
    if len(x) == 0:
        return 0.0
    frame = int(sr * frame_ms / 1000)
    if frame < 1:
        frame = 1
    # Compute per-frame RMS
    n_frames = len(x) // frame
    if n_frames < 2:
        return 0.0
    rms = np.array([np.sqrt(np.mean(x[i * frame : (i + 1) * frame] ** 2)) for i in range(n_frames)])
    # Silence floor = 10th percentile of RMS
    silence = np.percentile(rms, 10)
    if silence < 1e-8:
        silence = 1e-8
    signal = np.percentile(rms, 90)
    if signal < silence:
        return 0.0
    return float(20 * np.log10(signal / silence))


def _spectral_clarity(x: np.ndarray, sr: int) -> float:
    """Ratio of energy in speech-critical band (300-3400 Hz) to total.

    Higher = more intelligible (energy concentrated where speech matters).
    """
    if len(x) < 256:
        return 0.0
    n_fft = 2048
    if len(x) < n_fft:
        n_fft = 512
    win = np.hanning(n_fft)
    X = np.abs(np.fft.rfft(x[:n_fft] * win)) ** 2
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
    speech_band = (freqs >= 300) & (freqs <= 3400)
    if not speech_band.any():
        return 0.0
    e_speech = float(np.sum(X[speech_band]))
    e_total = float(np.sum(X)) + 1e-12
    return e_speech / e_total


def _stoi_proxy_no_ref(x: np.ndarray, sr: int) -> float:
    """No-reference STOI proxy: combination of SNR and spectral clarity.

    Returns a value in [0, 1] where >0.6 is considered acceptable for
    accessibility. This is NOT the reference STOI algorithm — it is a
    heuristic proxy for CI gating.
    """
    snr = _snr_db(x, frame_ms=100, sr=sr)
    clarity = _spectral_clarity(x, sr)
    # Map SNR: 0 dB -> 0, 20 dB -> 1
    snr_score = max(0.0, min(1.0, snr / 20.0))
    # Clarity is already [0, 1]
    # Weighted combination
    return float(0.6 * snr_score + 0.4 * clarity)


@register
class SpeechIntelligibilityAnalyzer(AudioAnalyzer):
    ID = "speech_intelligibility"
    NAME = "Speech Intelligibility (STOI proxy, no-reference)"
    VERSION = "1.0.0"
    METHOD = "SNR + spectral clarity heuristic for accessibility"
    DEFAULT_LIMITATIONS = [
        "No-reference heuristic; not the reference STOI algorithm",
        "Calibrated against synthetic speech; corpus needed for production (A2)",
        "For full-reference STOI, use ref_quality with mode=speech-full-ref",
        "Accessibility threshold (0.6) is a heuristic; adjust per use case",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        return audio.n_frames >= 2048

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        min_score = float(params.get("min_score", 0.6))
        x = audio.mono_mix().astype(np.float64)
        score = _stoi_proxy_no_ref(x, audio.sample_rate)
        if not np.isfinite(score):
            score = 0.0
            status = Status.INDETERMINATE
            msg = "score was non-finite"
        elif score < min_score:
            status = Status.WARNING
            msg = f"intelligibility proxy {score:.3f} below {min_score} (accessibility)"
        else:
            status = Status.PASS
            msg = f"intelligibility proxy {score:.3f} >= {min_score}"

        return [
            self._finding(
                check_id="speech_intelligibility.proxy",
                metric="stoi_proxy_no_ref",
                value=round(float(score), 4),
                unit="0-1",
                status=status,
                confidence=0.7,
                message=msg,
                evidence={
                    "min_score": min_score,
                    "snr_db": round(_snr_db(x, 100, audio.sample_rate), 2),
                    "spectral_clarity": round(_spectral_clarity(x, audio.sample_rate), 4),
                },
            )
        ]

    def profile_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "min_score": {"type": "number", "minimum": 0.0, "maximum": 1.0, "default": 0.6},
            },
            "additionalProperties": False,
        }
