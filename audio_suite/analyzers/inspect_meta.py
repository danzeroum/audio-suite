"""Inspect analyzer — extracts technical metadata from the audio file.

This is the analyzer backing the `audio-suite inspect` CLI command.
Output is informational; status is always PASS unless the file is unreadable
(in which case the decoder raises before this analyzer runs).
"""
from __future__ import annotations

from typing import Any

from ..models import PCM, Profile, Status
from . import register
from .base import AudioAnalyzer


@register
class InspectAnalyzer(AudioAnalyzer):
    ID = "inspect"
    NAME = "Technical Metadata Inspector"
    VERSION = "1.0.0"
    METHOD = "container + acoustic property extraction"
    DEFAULT_LIMITATIONS = [
        "Metadata is best-effort from libsndfile/ffmpeg",
        "Some formats do not expose all fields (e.g. encoder delay for WAV)",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        return True

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        info = {
            "file_sha256": audio.file_sha256,
            "source_path": audio.source_path,
            "sample_rate_hz": audio.sample_rate,
            "channels": audio.channels,
            "channel_layout": audio.channel_layout,
            "frames": audio.n_frames,
            "duration_s": round(audio.duration_s, 4),
            "provenance": audio.provenance,
        }
        return [self._finding(
            check_id="inspect.metadata",
            metric="metadata",
            value=None,
            unit="json",
            status=Status.PASS,
            confidence=1.0,
            message="metadata extracted",
            evidence=info,
        )]

    def profile_schema(self) -> dict[str, Any]:
        return {"type": "object", "additionalProperties": False}
