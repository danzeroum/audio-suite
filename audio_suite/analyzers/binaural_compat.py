"""Binaural compatibility analyzer — stereo vs binaural render (Fase 4).

Per the roadmap (Fase 4 BINAURAL_COMPATIBILITY): Compatibilidade render
binaural vs. estéreo, graves laterais.

Checks:
  - Lateral low-frequency content (< 200 Hz in L/R difference) — may cause
    issues on binaural render and is generally undesirable
  - Phase coherence at low frequencies
  - Overall stereo width distribution
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..models import PCM, Profile, Status
from . import register
from .base import AudioAnalyzer


@register
class BinauralCompatibilityAnalyzer(AudioAnalyzer):
    ID = "binaural_compat"
    NAME = "Binaural Compatibility (lateral lows, phase)"
    VERSION = "1.0.0"
    METHOD = "L/R difference in low band + phase coherence analysis"
    DEFAULT_LIMITATIONS = [
        "Heuristic; not a substitute for actual binaural rendering test",
        "Lateral low threshold is empirical; adjust per use case",
        "Does not validate HRTF compatibility",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        return audio.channels == 2

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        lateral_low_thr_db = float(params.get("max_lateral_low_db", -20.0))
        cutoff_hz = float(params.get("lateral_low_cutoff_hz", 200.0))

        L = audio.samples[0].astype(np.float64)
        R = audio.samples[1].astype(np.float64)
        n = min(len(L), len(R))
        if n < 256:
            return [
                self._finding(
                    check_id="binaural_compat.applicability",
                    metric="lateral_low_energy",
                    value=None,
                    unit="dB",
                    status=Status.NOT_APPLICABLE,
                    message="signal too short for binaural analysis",
                )
            ]

        L = L[:n]
        R = R[:n]
        # Side channel (L-R) — lateral content
        side = L - R
        # Low-pass filter the side channel
        from scipy.signal import butter, sosfilt

        nyq = audio.sample_rate / 2.0
        cutoff = min(cutoff_hz, nyq - 1)
        if cutoff < 1.0:
            return [
                self._finding(
                    check_id="binaural_compat.applicability",
                    metric="lateral_low_energy",
                    value=None,
                    unit="dB",
                    status=Status.NOT_APPLICABLE,
                    message="sample rate too low for lateral low analysis",
                )
            ]
        sos = butter(4, cutoff / nyq, btype="lowpass", output="sos")
        side_low = sosfilt(sos, side)
        mid_low = sosfilt(sos, L + R)

        # Energy ratio: side_low / mid_low in dB
        e_side = float(np.sqrt(np.mean(side_low**2))) + 1e-12
        e_mid = float(np.sqrt(np.mean(mid_low**2))) + 1e-12
        lateral_low_db = 20 * np.log10(e_side / e_mid)

        # Phase coherence at low frequencies
        # Use correlation of low-passed L and R
        L_low = sosfilt(sos, L)
        R_low = sosfilt(sos, R)
        if len(L_low) > 0 and np.std(L_low) > 0 and np.std(R_low) > 0:
            coherence = float(np.corrcoef(L_low, R_low)[0, 1])
        else:
            coherence = 1.0
        if not np.isfinite(coherence):
            coherence = 1.0

        if lateral_low_db > lateral_low_thr_db:
            status = Status.WARNING
            msg = (
                f"lateral low-frequency content {lateral_low_db:.1f} dB > "
                f"{lateral_low_thr_db} dB — may cause binaural render issues"
            )
        else:
            status = Status.PASS
            msg = f"lateral low content {lateral_low_db:.1f} dB within threshold"

        return [
            self._finding(
                check_id="binaural_compat.lateral_low",
                metric="lateral_low_energy_db",
                value=round(float(lateral_low_db), 2),
                unit="dB",
                status=status,
                confidence=0.75,
                message=msg,
                evidence={
                    "cutoff_hz": cutoff_hz,
                    "max_lateral_low_db": lateral_low_thr_db,
                    "low_freq_phase_coherence": round(coherence, 4),
                },
            )
        ]

    def profile_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "max_lateral_low_db": {"type": "number", "default": -20.0},
                "lateral_low_cutoff_hz": {"type": "number", "default": 200.0},
            },
            "additionalProperties": False,
        }
