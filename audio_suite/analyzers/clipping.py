"""Clipping analyzer — detects hard digital clipping.

Clipping is an OBJECTIVE defect (per the principle: "Defeito objetivo → fail").
We detect:
  - sample-level clipping (|x| >= threshold, default 0.99 of full scale)
  - sustained clipping (multiple consecutive clipped samples = more severe)
  - intersample-revealing clusters (samples near ceiling that, when oversampled,
    exceed 0 dBFS — delegated to true_peak analyzer but mentioned here)
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..models import PCM, Profile, Status
from . import register
from .base import AudioAnalyzer


@register
class ClippingAnalyzer(AudioAnalyzer):
    ID = "clipping"
    NAME = "Digital Clipping Detector"
    VERSION = "1.0.0"
    METHOD = "amplitude threshold + consecutive-run analysis"
    DEFAULT_LIMITATIONS = [
        "Detects hard clipping only; soft saturation is not flagged",
        "Threshold of 0.99 may miss subtle limiter abuse",
        "Cannot distinguish intentional clipping (e.g. guitar distortion) from accidental",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        return audio.n_frames > 0

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        threshold = float(params.get("threshold", 0.99))
        min_run = int(params.get("min_run_samples", 3))
        max_acceptable_pct = float(params.get("max_clipped_pct", 0.01))

        all_clipped_mask = np.zeros(audio.n_frames, dtype=bool)
        per_channel: list[dict[str, Any]] = []
        for c in range(audio.channels):
            x = audio.samples[c]
            clipped = np.abs(x) >= threshold
            all_clipped_mask |= clipped
            n_clipped = int(np.sum(clipped))
            pct = 100.0 * n_clipped / audio.n_frames if audio.n_frames else 0.0
            # Detect runs
            runs = self._runs(clipped, min_run)
            per_channel.append(
                {
                    "channel": c,
                    "clipped_samples": n_clipped,
                    "clipped_pct": round(pct, 4),
                    "sustained_runs": len(runs),
                    "longest_run_samples": max((r[1] - r[0] for r in runs), default=0),
                }
            )

        total_clipped = int(np.sum(all_clipped_mask))
        total_pct = 100.0 * total_clipped / audio.n_frames if audio.n_frames else 0.0

        if total_pct > max_acceptable_pct:
            status = Status.FAIL
            msg = f"{total_pct:.3f}% samples clipped (max {max_acceptable_pct}%)"
        elif total_clipped > 0:
            status = Status.WARNING
            msg = f"{total_clipped} clipped samples detected ({total_pct:.4f}%)"
        else:
            status = Status.PASS
            msg = "no clipping detected"

        return [
            self._finding(
                check_id="clipping.samples",
                metric="clipped_sample_pct",
                value=round(total_pct, 4),
                unit="%",
                status=status,
                confidence=0.99,
                message=msg,
                evidence={
                    "threshold": threshold,
                    "min_run_samples": min_run,
                    "max_clipped_pct": max_acceptable_pct,
                    "total_clipped_samples": total_clipped,
                    "per_channel": per_channel,
                },
            )
        ]

    def profile_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "threshold": {"type": "number", "minimum": 0.0, "maximum": 1.0, "default": 0.99},
                "min_run_samples": {"type": "integer", "minimum": 1, "default": 3},
                "max_clipped_pct": {"type": "number", "minimum": 0.0, "default": 0.01},
            },
            "additionalProperties": False,
        }

    @staticmethod
    def _runs(mask: np.ndarray, min_run: int) -> list[tuple[int, int]]:
        """Return list of (start, end) ranges where mask is True for >= min_run."""
        if not mask.any():
            return []
        # Find transitions
        diff = np.diff(mask.astype(np.int8), prepend=0, append=0)
        starts = np.where(diff == 1)[0]
        ends = np.where(diff == -1)[0]
        return [(int(s), int(e)) for s, e in zip(starts, ends) if e - s >= min_run]
