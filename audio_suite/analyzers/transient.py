"""Transient analyzer — smearing, pre-echo, punch loss.

Per Fase 2 TRANSIENT. Heuristic based on attack-time measurement on the
strongest onsets.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from ..models import PCM, Profile, Status
from . import register
from .base import AudioAnalyzer


def _envelope(x: np.ndarray, win: int = 64) -> np.ndarray:
    """Simple abs-mean envelope."""
    if len(x) == 0:
        return x
    kernel = np.ones(win) / win
    return np.convolve(np.abs(x), kernel, mode="same")


def _detect_onsets(env: np.ndarray, sr: int, min_separation_ms: float = 200.0) -> list[int]:
    if len(env) < 2:
        return []
    diff = np.diff(env)
    threshold = float(np.percentile(diff, 99.0))
    candidates = np.where(diff > threshold)[0]
    min_sep = int(sr * min_separation_ms / 1000.0)
    onsets: list[int] = []
    last = -min_sep * 2
    for c in candidates:
        if c - last >= min_sep:
            onsets.append(int(c))
            last = c
    return onsets


def _attack_time_ms(env: np.ndarray, onset: int, sr: int, lookback_ms: float = 5.0) -> float:
    """Time from 10% to 90% of peak around onset (in ms)."""
    lookback = int(sr * lookback_ms / 1000.0)
    s = max(0, onset - lookback)
    e = min(len(env), onset + lookback * 4)
    seg = env[s:e]
    if seg.size < 4:
        return 0.0
    peak = float(seg.max())
    if peak <= 0:
        return 0.0
    above_10 = np.where(seg > 0.1 * peak)[0]
    above_90 = np.where(seg > 0.9 * peak)[0]
    if len(above_10) == 0 or len(above_90) == 0:
        return 0.0
    t10 = above_10[0]
    t90 = above_90[0]
    if t90 <= t10:
        return 0.0
    return 1000.0 * (t90 - t10) / sr


@register
class TransientAnalyzer(AudioAnalyzer):
    ID = "transient"
    NAME = "Transient Smearing Detector"
    VERSION = "1.0.0"
    METHOD = "onset detection + 10-90% attack time"
    DEFAULT_LIMITATIONS = [
        "Heuristic; calibrated against synthetic transients",
        "Pre-echo detection requires codec-aware corpus (A2)",
        "Percussive content only; sustained tones report no onsets",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        return audio.n_frames >= 1024

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        max_attack_ms = float(params.get("max_attack_ms", 5.0))

        x = audio.mono_mix().astype(np.float64)
        env = _envelope(x)
        onsets = _detect_onsets(env, audio.sample_rate)
        if not onsets:
            return [self._finding(
                check_id="transient.smearing",
                metric="attack_time_ms",
                value=None,
                unit="ms",
                status=Status.NOT_APPLICABLE,
                message="no onsets detected; transient analysis not applicable",
                evidence={"onsets_detected": 0},
            )]

        attacks = [_attack_time_ms(env, o, audio.sample_rate) for o in onsets[:20]]
        attacks = [a for a in attacks if a > 0]
        if not attacks:
            return [self._finding(
                check_id="transient.smearing",
                metric="attack_time_ms",
                value=None,
                unit="ms",
                status=Status.NOT_APPLICABLE,
                message="onsets found but attack time undetermined",
                evidence={"onsets_detected": len(onsets)},
            )]

        worst = max(attacks)
        mean = float(np.mean(attacks))
        if worst > max_attack_ms:
            status = Status.WARNING
            msg = f"transient smeared: worst attack {worst:.2f}ms > {max_attack_ms}ms"
        else:
            status = Status.PASS
            msg = f"transient attack ok: worst {worst:.2f}ms"

        return [self._finding(
            check_id="transient.smearing",
            metric="attack_time_ms",
            value=round(float(worst), 3),
            unit="ms",
            status=status,
            confidence=0.75,
            message=msg,
            evidence={
                "worst_attack_ms": round(float(worst), 3),
                "mean_attack_ms": round(mean, 3),
                "onsets_detected": len(onsets),
                "max_attack_ms": max_attack_ms,
            },
        )]

    def profile_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "max_attack_ms": {"type": "number", "minimum": 0.1, "default": 5.0},
            },
            "additionalProperties": False,
        }
