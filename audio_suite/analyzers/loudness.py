"""Loudness analyzer — ITU-R BS.1770-4 integrated loudness in LUFS.

This is a measurement analyzer: it returns the value as `observation`-style
findings. Profile thresholds decide whether to escalate to warning/fail.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..models import PCM, Profile, Status
from . import register
from .base import AudioAnalyzer

# ITU-R BS.1770-4 filter coefficients
# Stage 1: high-shelf for head acoustics
# Stage 2: high-pass for RLB
_PRE_FILTER_BA = (
    np.array([1.53512485958697, -2.69169618940638, 1.19839281085285]),
    np.array([1.0, -1.69065929318241, 0.73248077421585]),
)
_RLB_FILTER_BA = (
    np.array([1.0, -2.0, 1.0]),
    np.array([1.0, -1.99004745483398, 0.99007225036621]),
)


# Channel weights (L, R, C, LFE, Ls, Rs, ...)
# Per BS.1770: L=R=C=1.0, LFE=0.0, Ls=Rs=1.41 (when 5.1)
def _channel_weight(idx: int, n_ch: int, layout: str) -> float:
    if n_ch == 1:
        return 1.0
    if n_ch == 2:
        return 1.0  # stereo L/R both weight 1.0
    if n_ch == 6 and layout == "5.1":
        weights = [1.0, 1.0, 1.0, 0.0, 1.41, 1.41]
        return weights[idx] if idx < len(weights) else 1.0
    return 1.0


def _apply_filter(x: np.ndarray, b: np.ndarray, a: np.ndarray) -> np.ndarray:
    from scipy.signal import lfilter

    return lfilter(b, a, x)


def compute_loudness_lufs(audio: PCM) -> float:
    """Compute integrated loudness in LUFS per ITU-R BS.1770-4.

    Returns -inf for digital silence (which we clamp to -70 LUFS in callers).
    """
    if audio.n_frames == 0:
        return -70.0

    # 400 ms block, 75% overlap (100 ms hop) per the gating spec
    block_ms = 400
    hop_ms = 100
    block_samples = int(audio.sample_rate * block_ms / 1000)
    hop_samples = int(audio.sample_rate * hop_ms / 1000)

    if block_samples <= 0 or audio.n_frames < block_samples:
        # Too short for proper gating — compute raw mean loudness
        return _mean_loudness(audio, 0, audio.n_frames)

    blocks: list[float] = []
    for start in range(0, audio.n_frames - block_samples + 1, hop_samples):
        lu = _mean_loudness(audio, start, start + block_samples)
        blocks.append(lu)

    if not blocks:
        return -70.0

    # Absolute gate: -70 LUFS
    gated = [b for b in blocks if b >= -70.0]
    if not gated:
        return -70.0

    # Relative gate: -10 dB below mean of gated
    mean_gated = 10 * np.log10(np.mean([10 ** (b / 10) for b in gated]))
    rel_gate = mean_gated - 10.0
    rel_gated = [b for b in gated if b >= rel_gate]
    if not rel_gated:
        rel_gated = gated
    return 10 * np.log10(np.mean([10 ** (b / 10) for b in rel_gated]))


def _mean_loudness(audio: PCM, start: int, end: int) -> float:
    """Mean loudness over a block (LUFS)."""
    z = 0.0
    for c in range(audio.channels):
        w = _channel_weight(c, audio.channels, audio.channel_layout)
        if w == 0.0:
            continue
        x = audio.samples[c, start:end]
        # Pre-filter then RLB
        y = _apply_filter(_apply_filter(x, *_PRE_FILTER_BA), *_RLB_FILTER_BA)
        z += w * np.mean(y.astype(np.float64) ** 2)
    if z <= 0:
        return -70.0
    return -0.691 + 10 * np.log10(z)


@register
class LoudnessAnalyzer(AudioAnalyzer):
    ID = "loudness"
    NAME = "Integrated Loudness (ITU-R BS.1770-4)"
    VERSION = "1.0.0"
    METHOD = "BS.1770-4 K-weighted gating, 400ms/100ms hop"
    DEFAULT_LIMITATIONS = [
        "BS.1770 is a measurement, not a perceptual model",
        "Short signals (<400ms) use ungated mean",
        "Does not detect true-peak; use true_peak analyzer",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        return audio.n_frames > 0

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        lufs = compute_loudness_lufs(audio)
        # Clamp for JSON safety (CT-10)
        if not np.isfinite(lufs):
            lufs = -70.0

        min_lufs = params.get("min_lufs", -24.0)
        max_lufs = params.get("max_lufs", -16.0)

        if lufs < min_lufs or lufs > max_lufs:
            status = Status.WARNING
            msg = f"loudness {lufs:.1f} LUFS outside [{min_lufs}, {max_lufs}]"
        else:
            status = Status.PASS
            msg = f"loudness {lufs:.1f} LUFS within target"

        return [
            self._finding(
                check_id="loudness.integrated",
                metric="integrated_loudness",
                value=round(lufs, 2),
                unit="LUFS",
                status=status,
                confidence=0.95,
                message=msg,
                evidence={
                    "block_ms": 400,
                    "hop_ms": 100,
                    "min_lufs": min_lufs,
                    "max_lufs": max_lufs,
                },
            )
        ]

    def profile_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "min_lufs": {"type": "number", "default": -24.0},
                "max_lufs": {"type": "number", "default": -16.0},
            },
            "additionalProperties": False,
        }
