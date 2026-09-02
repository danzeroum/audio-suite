"""LRA (Loudness Range) analyzer — EBU R128 LU range.

Per Fase 2: observation by default. The profile may declare explicit
min/max bounds to escalate to warning/fail.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from ..models import PCM, Profile, Status
from . import register
from .base import AudioAnalyzer
from .loudness import _mean_loudness


def compute_lra_lu(audio: PCM) -> float:
    """Compute Loudness Range in LU per EBU R128.

    Short-term (3s) blocks with 66% overlap; 10th and 95th percentiles of
    the gated distribution; LRA = P95 - P10.
    """
    if audio.n_frames < int(audio.sample_rate * 3):
        # Too short for short-term blocks; fall back to a single block
        return 0.0

    block_ms = 3000
    hop_ms = 1000
    block_samples = int(audio.sample_rate * block_ms / 1000)
    hop_samples = int(audio.sample_rate * hop_ms / 1000)

    blocks: list[float] = []
    for start in range(0, audio.n_frames - block_samples + 1, hop_samples):
        lu = _mean_loudness(audio, start, start + block_samples)
        if lu > -70.0:
            blocks.append(lu)

    if len(blocks) < 4:
        return 0.0

    # Relative gate at -10 LU below mean
    mean_abs = 10 * np.log10(np.mean([10 ** (b / 10) for b in blocks]))
    rel_gate = mean_abs - 10.0
    gated = [b for b in blocks if b >= rel_gate]
    if len(gated) < 4:
        gated = blocks

    p10 = float(np.percentile(gated, 10))
    p95 = float(np.percentile(gated, 95))
    return max(0.0, p95 - p10)


@register
class LraAnalyzer(AudioAnalyzer):
    ID = "lra"
    NAME = "Loudness Range (EBU R128)"
    VERSION = "1.0.0"
    METHOD = "3s/1s short-term blocks, P95-P10 of gated distribution"
    DEFAULT_LIMITATIONS = [
        "LRA is a descriptor; observation by default",
        "Signals <3s return LRA=0",
        "Gating threshold -70 LUFS absolute, -10 LU relative",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        return audio.n_frames > 0

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        lra = compute_lra_lu(audio)
        if not np.isfinite(lra):
            lra = 0.0

        min_lu = params.get("min_lu")
        max_lu = params.get("max_lu")

        if min_lu is not None and lra < float(min_lu):
            status = Status.WARNING
            msg = f"LRA {lra:.1f} LU below min {min_lu}"
        elif max_lu is not None and lra > float(max_lu):
            status = Status.WARNING
            msg = f"LRA {lra:.1f} LU above max {max_lu}"
        else:
            status = Status.PASS
            msg = f"LRA {lra:.1f} LU (observation)"

        return [self._finding(
            check_id="lra.range",
            metric="loudness_range",
            value=round(float(lra), 2),
            unit="LU",
            status=status,
            confidence=0.9,
            message=msg,
            evidence={
                "min_lu": min_lu,
                "max_lu": max_lu,
                "block_ms": 3000,
                "hop_ms": 1000,
            },
        )]

    def profile_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "min_lu": {"type": "number"},
                "max_lu": {"type": "number"},
            },
            "additionalProperties": False,
        }
