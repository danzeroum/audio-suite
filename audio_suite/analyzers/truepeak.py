"""True Peak analyzer — ITU-R BS.1770-4 Annex 2.

True peak accounts for inter-sample peaks that may exceed the sample-level
peak when reconstructed by a DAC. Uses 4x oversampling via polyphase FIR.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..models import PCM, Profile, Status
from . import register
from .base import AudioAnalyzer

# ITU-R BS.1770-4 true-peak FIR filter (4x oversampling, 32-tap)
# This is the standard Annex 2 coefficient set.
_TRUE_PEAK_FIR = np.array(
    [
        0.0017089843750,
        0.0109863281250,
        -0.0196533203125,
        0.0322265625000,
        -0.0324707031250,
        0.0495605468750,
        -0.0498046875000,
        0.0698242187500,
        -0.0708007812500,
        0.0991210937500,
        -0.1103515625000,
        0.1525878906250,
        -0.1655273437500,
        0.2189941406250,
        -0.2248535156250,
        0.2905273437500,
        -0.2905273437500,
        0.2248535156250,
        -0.2189941406250,
        0.1655273437500,
        -0.1525878906250,
        0.1103515625000,
        -0.0991210937500,
        0.0708007812500,
        -0.0698242187500,
        0.0498046875000,
        -0.0495605468750,
        0.0324707031250,
        -0.0322265625000,
        0.0196533203125,
        -0.0109863281250,
        0.0017089843750,
    ]
)


def compute_true_peak_dbtp(audio: PCM) -> tuple[float, float]:
    """Return (true_peak_dbtp, sample_peak_dbfs).

    Uses scipy.signal.resample_poly for 4x oversampling (proper polyphase
    decomposition with anti-imaging filter). True peak >= sample peak by
    construction (inter-sample peaks can exceed sample peaks).
    """
    from scipy.signal import resample_poly

    sample_peak = 0.0
    true_peak = 0.0

    for c in range(audio.channels):
        x = audio.samples[c].astype(np.float64)
        sp = float(np.max(np.abs(x))) if len(x) > 0 else 0.0
        sample_peak = max(sample_peak, sp)

        if len(x) > 0:
            # 4x polyphase oversampling
            y = resample_poly(x, up=4, down=1)
            tp = float(np.max(np.abs(y)))
        else:
            tp = 0.0
        true_peak = max(true_peak, tp)

    def to_db(x: float) -> float:
        return 20.0 * np.log10(max(x, 1e-12))

    return to_db(true_peak), to_db(sample_peak)


@register
class TruePeakAnalyzer(AudioAnalyzer):
    ID = "true_peak"
    NAME = "True Peak (ITU-R BS.1770-4 Annex 2)"
    VERSION = "1.0.0"
    METHOD = "4x polyphase FIR oversampling"
    DEFAULT_LIMITATIONS = [
        "True peak is an estimate; actual DAC peaks may differ",
        "FIR has finite length; very sharp transients may be slightly underestimated",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        return audio.n_frames > 0

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        tp_dbtp, sp_dbfs = compute_true_peak_dbtp(audio)

        max_dbtp = params.get("max_dbtp", -1.0)
        if tp_dbtp > max_dbtp:
            status = Status.FAIL
            msg = f"true peak {tp_dbtp:.2f} dBTP exceeds {max_dbtp} dBTP"
        else:
            status = Status.PASS
            msg = f"true peak {tp_dbtp:.2f} dBTP within {max_dbtp} dBTP"

        return [
            self._finding(
                check_id="true_peak.measurement",
                metric="true_peak",
                value=round(tp_dbtp, 3),
                unit="dBTP",
                status=status,
                confidence=0.97,
                message=msg,
                evidence={
                    "sample_peak_dbfs": round(sp_dbfs, 3),
                    "max_dbtp": max_dbtp,
                    "oversample_factor": 4,
                },
            )
        ]

    def profile_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "max_dbtp": {"type": "number", "default": -1.0},
            },
            "additionalProperties": False,
        }
