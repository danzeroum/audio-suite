"""Loop point analyzer — detects discontinuities at declared loop points.

Per Fase 1: opt-in. The audio must declare loop points (via profile params
or embedded metadata). The analyzer checks amplitude and first-derivative
continuity at the loop boundary.

A loop is "clean" if both:
  - |x[N-1] - x[0]| < amplitude_threshold   (no DC jump)
  - |x'[N-1] - x'[0]| < derivative_threshold (no click from slope mismatch)
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..models import PCM, Profile, Status
from . import register
from .base import AudioAnalyzer


@register
class LoopAnalyzer(AudioAnalyzer):
    ID = "loop"
    NAME = "Loop Point Continuity"
    VERSION = "1.0.0"
    METHOD = "amplitude + first-derivative discontinuity at declared loop boundary"
    DEFAULT_LIMITATIONS = [
        "Opt-in: requires loop points declared in profile or metadata",
        "Only checks the wraparound point (last -> first); interior loops need separate calls",
        "Does not assess musical quality of the loop",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        params = profile.analyzer_params(self.ID)
        return "loop_point_ms" in params or "loop_point_samples" in params

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        amp_thr = float(params.get("amplitude_threshold", 0.05))
        deriv_thr = float(params.get("derivative_threshold", 0.1))

        if "loop_point_samples" in params:
            loop_n = int(params["loop_point_samples"])
        else:
            loop_ms = float(params["loop_point_ms"])
            loop_n = int(audio.sample_rate * loop_ms / 1000.0)

        if loop_n <= 1 or loop_n > audio.n_frames:
            return [
                self._finding(
                    check_id="loop.point",
                    metric="loop_status",
                    value=None,
                    unit="pass/fail",
                    status=Status.NOT_APPLICABLE,
                    message=f"loop point {loop_n} out of range (1..{audio.n_frames})",
                    evidence={"loop_point_samples": loop_n},
                )
            ]

        results: list = []
        for c in range(audio.channels):
            x = audio.samples[c].astype(np.float64)
            # Wrap: last sample of loop vs first sample of loop
            last = x[loop_n - 1]
            first = x[0]
            amp_jump = abs(last - first)
            # Derivatives
            d_last = last - x[loop_n - 2] if loop_n >= 2 else 0.0
            d_first = x[1] - first if loop_n >= 2 else 0.0
            deriv_jump = abs(d_last - d_first)

            if amp_jump > amp_thr or deriv_jump > deriv_thr:
                status = Status.FAIL
                msg = f"loop boundary discontinuity on ch{c}: amp={amp_jump:.4f} deriv={deriv_jump:.4f}"
            else:
                status = Status.PASS
                msg = f"loop boundary clean on ch{c}"

            results.append(
                self._finding(
                    check_id=f"loop.channel_{c}",
                    metric="loop_amplitude_jump",
                    value=round(float(amp_jump), 5),
                    unit="amplitude",
                    status=status,
                    confidence=0.95,
                    message=msg,
                    time_range_ms=(
                        round(1000.0 * (loop_n - 1) / audio.sample_rate, 3),
                        round(1000.0 * loop_n / audio.sample_rate, 3),
                    ),
                    evidence={
                        "loop_point_samples": loop_n,
                        "amplitude_jump": round(float(amp_jump), 5),
                        "derivative_jump": round(float(deriv_jump), 5),
                        "thresholds": {"amp": amp_thr, "deriv": deriv_thr},
                    },
                )
            )

        return results

    def profile_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "loop_point_ms": {"type": "number", "minimum": 0},
                "loop_point_samples": {"type": "integer", "minimum": 1},
                "amplitude_threshold": {"type": "number", "minimum": 0.0, "default": 0.05},
                "derivative_threshold": {"type": "number", "minimum": 0.0, "default": 0.1},
            },
            # anyOf allows empty config (analyzer returns NOT_APPLICABLE)
            # OR a config with one of the loop point declarations.
            "additionalProperties": False,
        }
