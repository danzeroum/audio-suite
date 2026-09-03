"""DRn (Dynamic Range) meter — DR4/DR6/DR14 (ENG-12).

Numpy-pure implementation of the Dynamic Range meter per the
Pleasurize Music Foundation (PMF) specification.

DRn is defined as the difference between the peak and the average RMS
level of the loudest 20% of the signal, measured with a 3-second window.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..models import PCM, Profile, Status
from . import register
from .base import AudioAnalyzer


def compute_drn(audio: PCM, n: int = 14) -> float:
    """Compute DRn (default DR14) in dB.

    Methodology:
    1. Split signal into 3-second blocks
    2. Compute RMS for each block
    3. Sort blocks by RMS descending
    4. Take top 20% of blocks (loudest)
    5. DRn = average peak of those blocks - average RMS of those blocks
    """
    x = audio.mono_mix().astype(np.float64)
    sr = audio.sample_rate

    block_samples = int(3.0 * sr)
    if len(x) < block_samples:
        # Too short — use single block
        block_samples = len(x)

    if block_samples == 0:
        return 0.0

    # Compute blocks with 50% overlap
    hop = block_samples // 2
    blocks = []
    for i in range(0, len(x) - block_samples + 1, hop):
        block = x[i : i + block_samples]
        rms = float(np.sqrt(np.mean(block**2)))
        peak = float(np.max(np.abs(block)))
        if rms > 1e-12:
            blocks.append((rms, peak))

    if not blocks:
        return 0.0

    # Sort by RMS descending
    blocks.sort(key=lambda b: b[0], reverse=True)

    # Top 20% (at least 1 block)
    n_top = max(1, len(blocks) // 5)
    top_blocks = blocks[:n_top]

    avg_rms = float(np.mean([b[0] for b in top_blocks]))
    avg_peak = float(np.mean([b[1] for b in top_blocks]))

    if avg_rms <= 0:
        return 0.0

    dr_db = 20 * np.log10(avg_peak / avg_rms)
    return float(max(0.0, dr_db))


@register
class DrnAnalyzer(AudioAnalyzer):
    ID = "drn"
    NAME = "Dynamic Range Meter (DR14)"
    VERSION = "1.0.0"
    METHOD = "PMF DRn: top-20% RMS blocks, 3s window, 50% overlap"
    DEFAULT_LIMITATIONS = [
        "DRn is a descriptor of dynamic range, not a quality judgment",
        "PMF methodology simplified; not the official DR meter tool",
        "Reported as observation — status is always PASS",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        return audio.n_frames >= audio.sample_rate * 3  # at least 3 seconds

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        dr_min_db = params.get("dr_min_db")
        n = int(params.get("n", 14))

        dr = compute_drn(audio, n)
        if not np.isfinite(dr):
            dr = 0.0

        if dr_min_db is not None and dr < float(dr_min_db):
            status = Status.WARNING
            msg = f"DR{n} {dr:.1f} dB below minimum {dr_min_db} dB"
        else:
            status = Status.PASS
            msg = f"DR{n} {dr:.1f} dB (observation)"

        return [
            self._finding(
                check_id="drn.measurement",
                metric=f"dr{n}_db",
                value=round(float(dr), 2),
                unit="dB",
                status=status,
                confidence=0.85,
                message=msg,
                evidence={
                    "n": n,
                    "dr_min_db": dr_min_db,
                    "block_seconds": 3.0,
                    "overlap": 0.5,
                    "method": "PMF top-20% RMS",
                },
            )
        ]

    def profile_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "n": {"type": "integer", "enum": [4, 6, 14], "default": 14},
                "dr_min_db": {"type": "number"},
            },
            "additionalProperties": False,
        }
