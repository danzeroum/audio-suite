"""Spectral health analyzer — centroid, flatness, rolloff.

Per Fase 2 (SPECTRAL_H): these are DESCRIPTORS, not defects.
The analyzer ALWAYS returns status=observation (PASS by default; the profile
may escalate via overlay if needed, but per the principle of guidance,
"nunca falhe um build porque o centroid está 'alto demais'").
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..models import PCM, Profile, Status
from . import register
from .base import AudioAnalyzer


def _stft(x: np.ndarray, sr: int, n_fft: int = 2048, hop: int = 512) -> tuple[np.ndarray, np.ndarray]:
    from scipy.signal import get_window

    if len(x) < n_fft:
        x = np.pad(x, (0, n_fft - len(x)))
    win = get_window("hann", n_fft)
    frames = []
    for i in range(0, len(x) - n_fft + 1, hop):
        frames.append(x[i : i + n_fft] * win)
    if not frames:
        return np.array([]), np.array([])
    S = np.abs(np.fft.rfft(np.stack(frames), axis=1))
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
    return S, freqs


def _spectral_centroid(S: np.ndarray, freqs: np.ndarray) -> float:
    if S.size == 0:
        return 0.0
    mag = S.mean(axis=0)
    total = mag.sum()
    if total <= 0:
        return 0.0
    return float(np.sum(freqs * mag) / total)


def _spectral_flatness(S: np.ndarray) -> float:
    if S.size == 0:
        return 0.0
    mag = S.mean(axis=0) + 1e-12
    geo = np.exp(np.mean(np.log(mag)))
    arith = float(np.mean(mag))
    if arith <= 0:
        return 0.0
    return float(geo / arith)


def _spectral_rolloff(S: np.ndarray, freqs: np.ndarray, pct: float = 0.85) -> float:
    if S.size == 0:
        return 0.0
    mag = S.mean(axis=0)
    total = mag.sum()
    if total <= 0:
        return 0.0
    cum = np.cumsum(mag) / total
    idx = int(np.searchsorted(cum, pct))
    return float(freqs[min(idx, len(freqs) - 1)])


@register
class SpectralAnalyzer(AudioAnalyzer):
    ID = "spectral_health"
    NAME = "Spectral Descriptors (Centroid/Flatness/Rolloff)"
    VERSION = "1.0.0"
    METHOD = "STFT 2048/512 + Hann window, mean across frames"
    DEFAULT_LIMITATIONS = [
        "Descriptors are observations, not quality judgments",
        "Per-frame variation not captured (mean only)",
        "Window parameters fixed; user override is Fase 5",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        return audio.n_frames >= 256

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        n_fft = int(params.get("n_fft", 2048))
        hop = int(params.get("hop", 512))

        x = audio.mono_mix().astype(np.float64)
        S, freqs = _stft(x, audio.sample_rate, n_fft, hop)

        centroid = _spectral_centroid(S, freqs)
        flatness = _spectral_flatness(S)
        rolloff = _spectral_rolloff(S, freqs, 0.85)

        return [
            self._finding(
                check_id="spectral_health.descriptors",
                metric="spectral_centroid",
                value=round(float(centroid), 2),
                unit="Hz",
                status=Status.PASS,  # descriptor — never fail
                confidence=0.9,
                message=(f"centroid={centroid:.0f}Hz flatness={flatness:.3f} rolloff={rolloff:.0f}Hz"),
                evidence={
                    "centroid_hz": round(float(centroid), 2),
                    "flatness": round(float(flatness), 4),
                    "rolloff_85_hz": round(float(rolloff), 2),
                    "n_fft": n_fft,
                    "hop": hop,
                    "window": "hann",
                },
                extra_limitations=[
                    "status=pass by design; descriptors do not fail builds",
                ],
            )
        ]

    def profile_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "n_fft": {"type": "integer", "minimum": 64, "default": 2048},
                "hop": {"type": "integer", "minimum": 16, "default": 512},
            },
            "additionalProperties": False,
        }
