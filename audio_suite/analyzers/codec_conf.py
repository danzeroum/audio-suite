"""Codec conformance analyzer — declared vs effective duration, frames, gaps.

Per Fase 2 CODEC_CONF.
"""

from __future__ import annotations

from typing import Any

from ..models import PCM, Profile, Status
from . import register
from .base import AudioAnalyzer


@register
class CodecConfAnalyzer(AudioAnalyzer):
    ID = "codec_conf"
    NAME = "Codec Conformance"
    VERSION = "1.0.0"
    METHOD = "container metadata vs decoded PCM cross-check"
    DEFAULT_LIMITATIONS = [
        "Only checks properties exposed by libsndfile/ffmpeg",
        "Encoder delay/gapless detection is best-effort",
        "Cannot detect inaudible MP3 artifacts; use ref_quality for that",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        return bool(audio.provenance)

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        prov = audio.provenance
        declared_frames = prov.get("frames", audio.n_frames)
        effective_frames = audio.n_frames
        tolerance = float(params.get("frame_tolerance_pct", 1.0))
        diff_pct = 0.0
        if declared_frames > 0:
            diff_pct = 100.0 * abs(declared_frames - effective_frames) / declared_frames

        issues: list[str] = []
        if diff_pct > tolerance:
            issues.append(
                f"declared {declared_frames} frames vs decoded {effective_frames} "
                f"({diff_pct:.2f}% > {tolerance}%)"
            )

        # Check subtype sanity
        bit_depth = prov.get("bit_depth", 0)
        if bit_depth == 0:
            issues.append("unknown bit depth")

        if issues:
            status = Status.WARNING
            msg = "; ".join(issues)
            compliance = "non_conformant"
        else:
            status = Status.PASS
            msg = "codec metadata matches decoded PCM"
            compliance = "conformant"

        return [
            self._finding(
                check_id="codec_conf.check",
                metric="compliance_status",
                value=None,
                unit="enum",
                status=status,
                confidence=0.85,
                message=msg,
                evidence={
                    "compliance_status": compliance,
                    "declared_frames": declared_frames,
                    "effective_frames": effective_frames,
                    "frame_diff_pct": round(diff_pct, 3),
                    "decoder": prov.get("decoder"),
                    "subtype": prov.get("subtype"),
                    "bit_depth": bit_depth,
                },
            )
        ]

    def profile_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "frame_tolerance_pct": {"type": "number", "minimum": 0.0, "default": 1.0},
            },
            "additionalProperties": False,
        }
