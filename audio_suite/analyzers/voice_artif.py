"""Voice artifact analyzer — objective artifacts only (Fase 2).

Per roadmap: plosives, sibilance, mouth clicks, abrupt gain changes.
Roboticidade / emotion are deferred to needs_review (Fase 3, ML-based).
"""
from __future__ import annotations

from typing import Any

import numpy as np

from ..models import PCM, Profile, Status
from . import register
from .base import AudioAnalyzer


def _stft(x: np.ndarray, sr: int, n_fft: int = 1024, hop: int = 256) -> np.ndarray:
    from scipy.signal import get_window
    if len(x) < n_fft:
        x = np.pad(x, (0, n_fft - len(x)))
    win = get_window("hann", n_fft)
    frames = []
    for i in range(0, len(x) - n_fft + 1, hop):
        frames.append(x[i:i + n_fft] * win)
    if not frames:
        return np.zeros((1, n_fft // 2 + 1))
    return np.abs(np.fft.rfft(np.stack(frames), axis=1))


@register
class VoiceArtifAnalyzer(AudioAnalyzer):
    ID = "voice_artifacts"
    NAME = "Voice Artifact Detector (Objective)"
    VERSION = "1.0.0"
    METHOD = "spectral burst detection in plosive/sibilant bands"
    DEFAULT_LIMITATIONS = [
        "Objective artifacts only; emotion/roboticity deferred to Fase 3",
        "Language-agnostic; no ASR-based features",
        "Calibrated against synthetic voice; corpus needed (A2)",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        return audio.n_frames >= 2048

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        sib_thr = float(params.get("sibilance_threshold_db", 6.0))
        plosive_thr = float(params.get("plosive_threshold_db", 10.0))

        x = audio.mono_mix().astype(np.float64)
        S = _stft(x, audio.sample_rate)
        freqs = np.fft.rfftfreq(1024, 1.0 / audio.sample_rate)

        # Sibilance band: 5-10 kHz
        sib_mask = (freqs >= 5000) & (freqs <= 10000)
        # Plosive band: 80-300 Hz with sudden energy burst
        plos_mask = (freqs >= 80) & (freqs <= 300)

        sib_energy = S[:, sib_mask].mean(axis=1) if sib_mask.any() else np.zeros(S.shape[0])
        plos_energy = S[:, plos_mask].mean(axis=1) if plos_mask.any() else np.zeros(S.shape[0])
        total_energy = S.mean(axis=1) + 1e-12

        sib_db = 10 * np.log10((sib_energy + 1e-12) / total_energy)
        plos_db = 10 * np.log10((plos_energy + 1e-12) / total_energy)

        sib_events = int(np.sum(sib_db > sib_thr))
        plos_events = int(np.sum(plos_db > plosive_thr))

        total_events = sib_events + plos_events
        if total_events == 0:
            status = Status.PASS
            msg = "no voice artifacts detected"
        else:
            status = Status.WARNING
            msg = f"{total_events} voice artifact frames (sib={sib_events}, plos={plos_events})"

        return [self._finding(
            check_id="voice_artifacts.objective",
            metric="artifact_frame_count",
            value=float(total_events),
            unit="frames",
            status=status,
            confidence=0.65,
            message=msg,
            evidence={
                "sibilance_events": sib_events,
                "plosive_events": plos_events,
                "sibilance_threshold_db": sib_thr,
                "plosive_threshold_db": plosive_thr,
                "n_frames_analyzed": int(S.shape[0]),
            },
        )]

    def profile_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "sibilance_threshold_db": {"type": "number", "default": 6.0},
                "plosive_threshold_db": {"type": "number", "default": 10.0},
            },
            "additionalProperties": False,
        }
