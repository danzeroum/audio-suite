"""Acoustic context analyzer — scene changes, RT60, noise floor (Fase 3).

Detects:
  - Scene change: abrupt spectral profile shift (e.g., room change, mic swap)
  - RT60 estimation: reverberation time via Schroeder integration
  - Noise floor: background noise level between signal segments

Per the roadmap (Fase 3 ACOUSTIC_C): "Mudanças de sala, RT60, ruído entre trechos."
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..models import PCM, Profile, Status
from . import register
from .base import AudioAnalyzer


def _spectrogram_db(
    x: np.ndarray, sr: int, n_fft: int = 2048, hop: int = 512
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    from scipy.signal import get_window

    if len(x) < n_fft:
        x = np.pad(x, (0, n_fft - len(x)))
    win = get_window("hann", n_fft)
    frames = []
    for i in range(0, len(x) - n_fft + 1, hop):
        frames.append(x[i : i + n_fft] * win)
    if not frames:
        return np.array([]), np.array([]), np.array([])
    S = np.abs(np.fft.rfft(np.stack(frames), axis=1))
    S_db = 20 * np.log10(S + 1e-12)
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
    times = np.arange(len(frames)) * hop / sr
    return S_db, freqs, times


def _detect_scene_changes(
    S_db: np.ndarray, times: np.ndarray, threshold_db: float = 12.0
) -> list[dict[str, Any]]:
    """Detect abrupt spectral profile changes via cosine distance between frames."""
    if S_db.size == 0 or S_db.shape[0] < 2:
        return []
    events = []
    # Normalize each frame
    norms = np.linalg.norm(S_db, axis=1, keepdims=True) + 1e-12
    normalized = S_db / norms
    # Cosine similarity between consecutive frames
    sim = np.sum(normalized[1:] * normalized[:-1], axis=1)
    # Convert to angle (distance)
    dist = np.arccos(np.clip(sim, -1.0, 1.0))
    # Find large jumps
    above = dist > np.deg2rad(threshold_db)  # threshold as degrees of spectral angle
    for i in np.where(above)[0]:
        events.append(
            {
                "time_ms": round(float(times[i + 1] * 1000), 2),
                "spectral_angle_deg": round(float(np.degrees(dist[i])), 2),
            }
        )
    return events


def _estimate_rt60(x: np.ndarray, sr: int) -> float:
    """Estimate RT60 via Schroeder backward integration on the energy envelope.

    Returns RT60 in seconds, or 0.0 if estimation fails.
    """
    if len(x) < sr:
        return 0.0
    # Energy envelope
    env = x**2
    # Schroeder: cumulative sum from the end, backwards
    schroeder = np.cumsum(env[::-1])[::-1]
    if schroeder[0] <= 0:
        return 0.0
    schroeder_db = 10 * np.log10(schroeder / schroeder[0] + 1e-12)
    # Fit a line to the decay portion (from 0 to -30 dB)
    try:
        decay_mask = schroeder_db >= -30.0
        if np.sum(decay_mask) < 4:
            return 0.0
        t = np.arange(len(schroeder)) / sr
        coeffs = np.polyfit(t[decay_mask], schroeder_db[decay_mask], 1)
        slope = coeffs[0]  # dB/s
        if slope >= -1.0:
            return 0.0
        rt60 = -60.0 / slope
        return float(np.clip(rt60, 0.0, 10.0))
    except Exception:
        return 0.0


def _noise_floor_db(x: np.ndarray, sr: int) -> float:
    """Estimate noise floor as the 10th percentile of short-term RMS."""
    if len(x) < 256:
        return -120.0
    frame = int(sr * 0.05)  # 50 ms
    n_frames = len(x) // frame
    if n_frames < 2:
        return -120.0
    rms = np.array([np.sqrt(np.mean(x[i * frame : (i + 1) * frame] ** 2)) for i in range(n_frames)])
    rms = rms[rms > 1e-12]
    if len(rms) == 0:
        return -120.0
    p10 = float(np.percentile(rms, 10))
    return 20 * np.log10(p10 + 1e-12)


@register
class AcousticContextAnalyzer(AudioAnalyzer):
    ID = "acoustic_context"
    NAME = "Acoustic Context (scene change, RT60, noise floor)"
    VERSION = "1.0.0"
    METHOD = "spectral cosine distance + Schroeder RT60 + RMS percentile"
    DEFAULT_LIMITATIONS = [
        "Scene change detection is heuristic; corpus needed (A2)",
        "RT60 estimation assumes a decay segment exists; may fail on continuous speech",
        "Noise floor is the 10th percentile; not a true statistical minimum",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        return audio.n_frames >= 4096

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        scene_threshold_deg = float(params.get("scene_change_threshold_deg", 30.0))
        max_rt60_s = float(params.get("max_rt60_s", 2.0))

        x = audio.mono_mix().astype(np.float64)
        S_db, freqs, times = _spectrogram_db(x, audio.sample_rate)
        scenes = _detect_scene_changes(S_db, times, scene_threshold_deg)
        rt60 = _estimate_rt60(x, audio.sample_rate)
        noise_floor = _noise_floor_db(x, audio.sample_rate)

        findings: list = []

        if scenes:
            findings.append(
                self._finding(
                    check_id="acoustic_context.scene_changes",
                    metric="scene_change_count",
                    value=float(len(scenes)),
                    unit="events",
                    status=Status.WARNING,
                    confidence=0.7,
                    message=f"{len(scenes)} scene changes detected",
                    evidence={"events": scenes[:20]},
                )
            )
        else:
            findings.append(
                self._finding(
                    check_id="acoustic_context.scene_changes",
                    metric="scene_change_count",
                    value=0.0,
                    unit="events",
                    status=Status.PASS,
                    confidence=0.7,
                    message="no scene changes detected",
                    evidence={"threshold_deg": scene_threshold_deg},
                )
            )

        if rt60 > max_rt60_s:
            rt60_status = Status.WARNING
            rt60_msg = f"RT60 {rt60:.2f}s exceeds {max_rt60_s}s"
        else:
            rt60_status = Status.PASS
            rt60_msg = f"RT60 {rt60:.2f}s within {max_rt60_s}s"

        findings.append(
            self._finding(
                check_id="acoustic_context.rt60",
                metric="reverberation_time",
                value=round(float(rt60), 3),
                unit="s",
                status=rt60_status,
                confidence=0.6,
                message=rt60_msg,
                evidence={
                    "method": "schroeder_backward_integration",
                    "max_rt60_s": max_rt60_s,
                },
            )
        )

        findings.append(
            self._finding(
                check_id="acoustic_context.noise_floor",
                metric="noise_floor_db",
                value=round(float(noise_floor), 2),
                unit="dBFS",
                status=Status.PASS,  # observation only
                confidence=0.75,
                message=f"noise floor estimated at {noise_floor:.1f} dBFS",
                evidence={
                    "method": "rms_10th_percentile",
                    "frame_ms": 50,
                },
                extra_limitations=["noise floor is an observation, not a pass/fail metric"],
            )
        )

        return findings

    def profile_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "scene_change_threshold_deg": {"type": "number", "minimum": 0.0, "default": 30.0},
                "max_rt60_s": {"type": "number", "minimum": 0.0, "default": 2.0},
            },
            "additionalProperties": False,
        }
