"""Mono compatibility analyzer — detects phase cancellation when summing L/R.

Per Fase 1: measures per-band energy loss when downmixing to mono.
Does NOT treat negative correlation as automatic failure — that's a profile
decision. The analyzer reports the measurement.

Uses the profile's downmix matrix if provided; defaults to (L+R)/2.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from ..models import PCM, Profile, Status
from . import register
from .base import AudioAnalyzer

# Standard frequency bands (Hz) for per-band analysis
DEFAULT_BANDS_HZ = [
    (20, 120),     # sub bass
    (120, 400),    # bass
    (400, 1200),   # low mid
    (1200, 4000),  # mid
    (4000, 12000), # high mid
    (12000, 20000),# high
]


def _band_energy_db(x: np.ndarray, sr: int, f_lo: float, f_hi: float) -> float:
    """RMS energy in dB within a frequency band."""
    if len(x) == 0:
        return -120.0
    from scipy.signal import butter, sosfilt
    nyq = sr / 2.0
    f_hi = min(f_hi, nyq - 1)
    if f_lo >= f_hi:
        return -120.0
    sos = butter(4, [f_lo / nyq, f_hi / nyq], btype="bandpass", output="sos")
    y = sosfilt(sos, x)
    rms = float(np.sqrt(np.mean(y ** 2))) + 1e-12
    return 20 * np.log10(rms)


@register
class MonoCompatAnalyzer(AudioAnalyzer):
    ID = "mono_compat"
    NAME = "Mono Compatibility (Phase/Loss)"
    VERSION = "1.0.0"
    METHOD = "per-band energy loss in L+R vs L,R"
    DEFAULT_LIMITATIONS = [
        "Per-band loss is heuristic; ear perception varies",
        "Negative correlation is reported, not auto-failed",
        "Default downmix is (L+R)/2; profile can override",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        return audio.channels >= 2

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        bands = params.get("bands_hz", DEFAULT_BANDS_HZ)
        max_loss_db = float(params.get("max_loss_db", 6.0))
        downmix = params.get("downmix_matrix", [0.5, 0.5])

        L = audio.samples[0].astype(np.float64)
        R = audio.samples[1].astype(np.float64)
        mono = downmix[0] * L + downmix[1] * R

        # Overall correlation
        if len(L) > 0:
            corr = float(np.corrcoef(L, R)[0, 1])
        else:
            corr = 0.0
        if not np.isfinite(corr):
            corr = 0.0

        band_results: list[dict[str, Any]] = []
        worst_loss = 0.0
        for f_lo, f_hi in bands:
            eL = _band_energy_db(L, audio.sample_rate, f_lo, f_hi)
            eR = _band_energy_db(R, audio.sample_rate, f_lo, f_hi)
            eM = _band_energy_db(mono, audio.sample_rate, f_lo, f_hi)
            ref = max(eL, eR)
            loss = ref - eM  # positive = loss
            if not np.isfinite(loss):
                loss = 0.0
            band_results.append({
                "band_hz": [f_lo, f_hi],
                "loss_db": round(loss, 2),
                "mono_energy_db": round(eM, 2),
            })
            worst_loss = max(worst_loss, loss)

        critical_windows = [b for b in band_results if b["loss_db"] >= max_loss_db]

        if worst_loss >= max_loss_db:
            status = Status.WARNING
            msg = f"mono downmix loses {worst_loss:.1f} dB in worst band"
        else:
            status = Status.PASS
            msg = f"mono downmix loss <= {worst_loss:.1f} dB"

        return [
            self._finding(
                check_id="mono_compat.band_loss",
                metric="max_band_loss",
                value=round(worst_loss, 2),
                unit="dB",
                status=status,
                confidence=0.9,
                message=msg,
                evidence={
                    "downmix_matrix": downmix,
                    "lr_correlation": round(corr, 4),
                    "bands": band_results,
                    "critical_windows": critical_windows,
                    "max_loss_db_threshold": max_loss_db,
                },
            )
        ]

    def profile_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "bands_hz": {
                    "type": "array",
                    "items": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2,
                    },
                },
                "max_loss_db": {"type": "number", "default": 6.0},
                "downmix_matrix": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 8,
                },
            },
            "additionalProperties": False,
        }
