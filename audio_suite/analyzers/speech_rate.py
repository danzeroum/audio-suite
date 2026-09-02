"""Speech rate analyzer — detects excessive speaking rate (Fase 2.5).

Per the roadmap: detection of excessive speech velocity. This is a
heuristic based on syllable-like onset detection. Not a substitute for
ASR-based word-per-minute measurement.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..models import PCM, Profile, Status
from . import register
from .base import AudioAnalyzer


def _detect_syllable_rate(x: np.ndarray, sr: int) -> tuple[float, int]:
    """Estimate syllable rate via envelope fluctuation in 2-7 Hz band.

    Returns (syllables_per_second, n_syllables_detected).
    """
    if len(x) < sr:
        return 0.0, 0
    # Envelope via Hilbert
    from scipy.signal import butter, hilbert, sosfilt

    env = np.abs(hilbert(x))
    # Bandpass filter envelope to syllable rate (2-7 Hz)
    nyq = sr / 2.0
    sos = butter(4, [2.0 / nyq, 7.0 / nyq], btype="bandpass", output="sos")
    env_filt = sosfilt(sos, env)
    # Count peaks above threshold
    threshold = 0.3 * np.max(np.abs(env_filt)) if len(env_filt) > 0 else 0
    if threshold <= 0:
        return 0.0, 0
    # Simple peak detection
    above = np.abs(env_filt) > threshold
    # Count rising edges
    rising = np.diff(above.astype(np.int8))
    n_peaks = int(np.sum(rising == 1))
    duration = len(x) / sr
    rate = n_peaks / duration if duration > 0 else 0.0
    return float(rate), n_peaks


@register
class SpeechRateAnalyzer(AudioAnalyzer):
    ID = "speech_rate"
    NAME = "Speech Rate Detector (syllable proxy)"
    VERSION = "1.0.0"
    METHOD = "envelope bandpass 2-7 Hz + peak counting"
    DEFAULT_LIMITATIONS = [
        "Heuristic syllable detection; not ASR-based word count",
        "Language-dependent; calibration needed per language (A2)",
        "Music and noise may inflate the count",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        return audio.n_frames >= audio.sample_rate  # at least 1 second

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        max_syl_per_sec = float(params.get("max_syllables_per_sec", 7.0))
        x = audio.mono_mix().astype(np.float64)
        rate, n_syl = _detect_syllable_rate(x, audio.sample_rate)
        if not np.isfinite(rate):
            rate = 0.0

        if rate > max_syl_per_sec:
            status = Status.WARNING
            msg = f"speech rate {rate:.1f} syl/s exceeds {max_syl_per_sec} (accessibility)"
        else:
            status = Status.PASS
            msg = f"speech rate {rate:.1f} syl/s within {max_syl_per_sec}"

        return [
            self._finding(
                check_id="speech_rate.syllables",
                metric="syllables_per_second",
                value=round(float(rate), 2),
                unit="syl/s",
                status=status,
                confidence=0.6,
                message=msg,
                evidence={
                    "n_syllables_detected": n_syl,
                    "duration_s": round(audio.duration_s, 2),
                    "max_syllables_per_sec": max_syl_per_sec,
                },
            )
        ]

    def profile_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "max_syllables_per_sec": {"type": "number", "minimum": 1.0, "default": 7.0},
            },
            "additionalProperties": False,
        }
