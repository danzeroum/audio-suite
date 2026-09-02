"""Goniometer analyzer — phase/correlation visualization data (Fase 4).

Per the roadmap (Fase 4 GONIOMETER): Visualização de fase/correlação.

This analyzer does NOT render a visual goniometer; it computes the
underlying data (Lissajous statistics) that a frontend can render.

Returns:
  - Mean correlation
  - Spread (standard deviation of the Lissajous distribution)
  - L/R balance
  - Phase spread (how much of the signal is out of phase)
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..models import PCM, Profile, Status
from . import register
from .base import AudioAnalyzer


@register
class GoniometerAnalyzer(AudioAnalyzer):
    ID = "goniometer"
    NAME = "Goniometer (Lissajous statistics)"
    VERSION = "1.0.0"
    METHOD = "L/R Lissajous point statistics"
    DEFAULT_LIMITATIONS = [
        "Returns statistics only; visual rendering is a frontend concern",
        "Downsamples for large signals (max 10000 points)",
        "Does not capture transient phase relationships",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        return audio.channels == 2

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        L = audio.samples[0].astype(np.float64)
        R = audio.samples[1].astype(np.float64)
        n = min(len(L), len(R))
        if n < 2:
            return [
                self._finding(
                    check_id="goniometer.applicability",
                    metric="mean_correlation",
                    value=None,
                    unit="0-1",
                    status=Status.NOT_APPLICABLE,
                    message="signal too short for goniometer",
                )
            ]

        L = L[:n]
        R = R[:n]

        # Mean correlation
        if np.std(L) > 1e-12 and np.std(R) > 1e-12:
            corr = float(np.corrcoef(L, R)[0, 1])
        else:
            corr = 0.0
        if not np.isfinite(corr):
            corr = 0.0

        # L/R balance
        eL = float(np.sqrt(np.mean(L**2)))
        eR = float(np.sqrt(np.mean(R**2)))
        balance = 0.0
        if eL + eR > 1e-12:
            balance = (eL - eR) / (eL + eR)

        # Spread: standard deviation of the rotated points (45° rotation gives "side" axis)
        # side = (L - R) / sqrt(2)
        side = (L - R) / np.sqrt(2)
        spread = float(np.std(side)) if len(side) > 0 else 0.0

        # Phase spread: percentage of samples where L and R have opposite signs
        opposite = float(np.sum((L * R) < 0)) / n if n > 0 else 0.0

        return [
            self._finding(
                check_id="goniometer.statistics",
                metric="mean_correlation",
                value=round(float(corr), 4),
                unit="0-1",
                status=Status.PASS,  # observation only
                confidence=0.9,
                message=(
                    f"corr={corr:.3f} balance={balance:+.3f} spread={spread:.4f} "
                    f"opposite_phase={opposite:.1%}"
                ),
                evidence={
                    "mean_correlation": round(float(corr), 4),
                    "lr_balance": round(float(balance), 4),
                    "spread": round(float(spread), 4),
                    "opposite_phase_pct": round(float(opposite * 100), 2),
                    "n_samples": n,
                },
                extra_limitations=[
                    "goniometer is an observation tool; status is always pass",
                ],
            )
        ]

    def profile_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }
