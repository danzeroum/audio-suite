"""Channel balance analyzer — L/R loudness and RMS difference."""

from __future__ import annotations

from typing import Any

import numpy as np

from ..models import PCM, Profile, Status
from . import register
from .base import AudioAnalyzer


def _rms_db(x: np.ndarray) -> float:
    if len(x) == 0:
        return -120.0
    rms = float(np.sqrt(np.mean(x**2))) + 1e-12
    return 20 * np.log10(rms)


def _lufs_short(x: np.ndarray, sr: int) -> float:
    """Short-form LUFS approximation (no gating) for a single channel."""
    if len(x) == 0:
        return -70.0
    from scipy.signal import lfilter

    # K-weighting (simplified)
    b1 = np.array([1.53512485958697, -2.69169618940638, 1.19839281085285])
    a1 = np.array([1.0, -1.69065929318241, 0.73248077421585])
    b2 = np.array([1.0, -2.0, 1.0])
    a2 = np.array([1.0, -1.99004745483398, 0.99007225036621])
    y = lfilter(b2, a2, lfilter(b1, a1, x.astype(np.float64)))
    z = float(np.mean(y**2))
    if z <= 0:
        return -70.0
    return -0.691 + 10 * np.log10(z)


@register
class ChannelBalanceAnalyzer(AudioAnalyzer):
    ID = "channel_balance"
    NAME = "Channel Balance (L/R LUFS+RMS)"
    VERSION = "1.0.0"
    METHOD = "per-channel short-term LUFS and RMS, |Δ| reported"
    DEFAULT_LIMITATIONS = [
        "Stereo only; multichannel uses spatial_coherence (Fase 4)",
        "LUFS is ungated short-term; not a substitute for full integrated LUFS",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        return audio.channels == 2

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        max_delta_lufs = float(params.get("max_delta_lufs", 1.0))
        max_delta_rms = float(params.get("max_delta_rms_db", 2.0))

        L = audio.samples[0]
        R = audio.samples[1]
        lufs_L = _lufs_short(L, audio.sample_rate)
        lufs_R = _lufs_short(R, audio.sample_rate)
        rms_L = _rms_db(L.astype(np.float64))
        rms_R = _rms_db(R.astype(np.float64))

        d_lufs = abs(lufs_L - lufs_R)
        d_rms = abs(rms_L - rms_R)

        if d_lufs > max_delta_lufs or d_rms > max_delta_rms:
            status = Status.WARNING
            msg = f"channel imbalance: ΔLUFS={d_lufs:.2f} ΔRMS={d_rms:.2f} dB"
        else:
            status = Status.PASS
            msg = f"channels balanced: ΔLUFS={d_lufs:.2f} ΔRMS={d_rms:.2f} dB"

        return [
            self._finding(
                check_id="channel_balance.lr",
                metric="delta_lufs",
                value=round(d_lufs, 3),
                unit="LUFS",
                status=status,
                confidence=0.92,
                message=msg,
                evidence={
                    "lufs_L": round(lufs_L, 2),
                    "lufs_R": round(lufs_R, 2),
                    "rms_L_db": round(rms_L, 2),
                    "rms_R_db": round(rms_R, 2),
                    "delta_rms_db": round(d_rms, 3),
                    "max_delta_lufs": max_delta_lufs,
                    "max_delta_rms_db": max_delta_rms,
                },
            )
        ]

    def profile_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "max_delta_lufs": {"type": "number", "default": 1.0},
                "max_delta_rms_db": {"type": "number", "default": 2.0},
            },
            "additionalProperties": False,
        }
