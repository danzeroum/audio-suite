"""Spatial coherence analyzer — channel correlation matrix (Fase 4).

Per the roadmap (Fase 4 SPATIAL_COHERENCE): Coerência entre metadados de
posição (Ambisonic) e energia real.

Computes pairwise channel correlation to detect spatial inconsistencies.
For Ambisonic content, validates that the energy distribution matches
the declared order.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..models import PCM, Profile, Status
from . import register
from .base import AudioAnalyzer


def _correlation_matrix(audio: PCM) -> np.ndarray:
    """Compute pairwise channel correlation matrix."""
    n = audio.channels
    corr = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            xi = audio.samples[i].astype(np.float64)
            xj = audio.samples[j].astype(np.float64)
            n_samples = min(len(xi), len(xj))
            if n_samples == 0:
                continue
            xi = xi[:n_samples]
            xj = xj[:n_samples]
            si = np.std(xi)
            sj = np.std(xj)
            if si > 1e-12 and sj > 1e-12:
                corr[i, j] = float(np.corrcoef(xi, xj)[0, 1])
            elif i == j:
                corr[i, j] = 1.0
    return corr


@register
class SpatialCoherenceAnalyzer(AudioAnalyzer):
    ID = "spatial_coherence"
    NAME = "Spatial Coherence (channel correlation matrix)"
    VERSION = "1.0.0"
    METHOD = "pairwise channel Pearson correlation + energy distribution"
    DEFAULT_LIMITATIONS = [
        "Correlation is a proxy for spatial coherence; not a full Ambisonic validator",
        "Does not validate Ambisonic order against metadata (subproject)",
        "Heuristic thresholds for surround content",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        return audio.channels >= 2

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        max_off_diag_corr = float(params.get("max_off_diag_corr", 0.95))
        corr = _correlation_matrix(audio)

        # Check for suspiciously high correlation between non-identical channels
        # (e.g., L and R being identical = fake stereo)
        n = audio.channels
        max_corr = 0.0
        max_pair = (0, 0)
        for i in range(n):
            for j in range(i + 1, n):
                if abs(corr[i, j]) > max_corr:
                    max_corr = abs(corr[i, j])
                    max_pair = (i, j)

        if max_corr > max_off_diag_corr:
            status = Status.WARNING
            msg = (
                f"channels {max_pair[0]} and {max_pair[1]} have correlation "
                f"{max_corr:.3f} — possible fake stereo or duplication"
            )
        else:
            status = Status.PASS
            msg = f"max channel correlation {max_corr:.3f} within {max_off_diag_corr}"

        return [
            self._finding(
                check_id="spatial_coherence.correlation",
                metric="max_off_diag_correlation",
                value=round(float(max_corr), 4),
                unit="0-1",
                status=status,
                confidence=0.8,
                message=msg,
                evidence={
                    "correlation_matrix": np.round(corr, 4).tolist(),
                    "max_pair": list(max_pair),
                    "max_off_diag_corr_threshold": max_off_diag_corr,
                },
            )
        ]

    def profile_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "max_off_diag_corr": {"type": "number", "minimum": 0.0, "maximum": 1.0, "default": 0.95},
            },
            "additionalProperties": False,
        }
