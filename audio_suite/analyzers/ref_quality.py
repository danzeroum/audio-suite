"""Reference quality analyzer — full-reference and no-reference modes.

Per Fase 2 REF_QUALITY and rule 2 (Sem referência = sem métrica full-reference):

Modes:
  - speech-full-ref: STOI-like measurement (simplified)
  - audio-full-ref: ViSQOL-like measurement (simplified)
  - source-sep-ref: SI-SDR
  - no-reference: returns indeterminate (NEVER claims to be a ViSQOL/SI-SDR)

The simplified implementations here are NOT the reference algorithms — they
are deterministic proxies suitable for CI gating. Production deployments
should swap in the official Visqol/SI-SDR packages and bump the version.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from ..models import PCM, Profile, Status
from . import register
from .base import AudioAnalyzer


def _align(ref: np.ndarray, deg: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
    """Cross-correlation alignment (sample-level)."""
    n = min(len(ref), len(deg))
    ref = ref[:n]
    deg = deg[:n]
    if n == 0:
        return ref, deg
    corr = np.correlate(ref, deg, mode="full")
    lag = int(np.argmax(np.abs(corr)) - (len(deg) - 1))
    if lag > 0:
        ref = ref[lag:]
        deg = deg[:len(ref)]
    elif lag < 0:
        deg = deg[-lag:]
        ref = ref[:len(deg)]
    return ref, deg


def _stoi_like(ref: np.ndarray, deg: np.ndarray, sr: int) -> float:
    """Simplified STOI proxy: normalized correlation of short-term envelopes."""
    ref, deg = _align(ref, deg, sr)
    n = min(len(ref), len(deg))
    if n < 256:
        return 0.0
    ref = ref[:n]
    deg = deg[:n]
    # Normalize
    ref = ref / (np.linalg.norm(ref) + 1e-12)
    deg = deg / (np.linalg.norm(deg) + 1e-12)
    # Short-term correlation
    win = 256
    scores = []
    for i in range(0, n - win, win // 2):
        a = ref[i:i + win]
        b = deg[i:i + win]
        denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-12
        scores.append(float(np.dot(a, b) / denom))
    if not scores:
        return 0.0
    return float(np.clip(np.mean(scores), -1.0, 1.0))


def _visqol_like(ref: np.ndarray, deg: np.ndarray, sr: int) -> float:
    """Simplified ViSQOL proxy: spectral similarity mapped to 1-5 MOS scale."""
    ref, deg = _align(ref, deg, sr)
    n = min(len(ref), len(deg))
    if n < 1024:
        return 1.0
    n_fft = 1024
    win = np.hanning(n_fft)
    R = np.abs(np.fft.rfft(ref[:n_fft] * win)) + 1e-12
    D = np.abs(np.fft.rfft(deg[:n_fft] * win)) + 1e-12
    # NSIM (per-band similarity)
    nsim = np.mean(2 * R * D / (R ** 2 + D ** 2))
    # Map [0, 1] to [1, 5]
    return float(1.0 + 4.0 * np.clip(nsim, 0.0, 1.0))


def _si_sdr(ref: np.ndarray, deg: np.ndarray) -> float:
    """SI-SDR in dB (Le Roux et al.)."""
    ref, deg = _align(ref, deg, 0)
    n = min(len(ref), len(deg))
    if n == 0:
        return -100.0
    ref = ref[:n]
    deg = deg[:n]
    # Optimal scaling
    alpha = float(np.dot(ref, deg) / (np.dot(ref, ref) + 1e-12))
    target = alpha * ref
    noise = deg - target
    s_target = float(np.sum(target ** 2)) + 1e-12
    s_noise = float(np.sum(noise ** 2)) + 1e-12
    return 10 * np.log10(s_target / s_noise)


@register
class RefQualityAnalyzer(AudioAnalyzer):
    ID = "ref_quality"
    NAME = "Reference Quality (full-ref + no-ref fallback)"
    VERSION = "1.0.0"
    METHOD = "mode-dependent: STOI/ViSQOL/SI-SDR proxies OR indeterminate"
    DEFAULT_LIMITATIONS = [
        "STOI/ViSQOL implementations are simplified proxies, not the reference algorithms",
        "No-reference mode returns indeterminate (rule 2)",
        "Reference must be provided via profile.params.reference_path with declared hash",
        "Alignment is sample-level; sub-sample drift not corrected",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        # Applicable in all cases — no-reference mode returns indeterminate.
        return True

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        from ..decode import decode, sha256_of_file

        mode = params.get("mode", "no-reference")
        ref_path = params.get("reference_path")
        ref_sha = params.get("reference_sha256")

        if mode == "no-reference" or not ref_path:
            return [self._finding(
                check_id="ref_quality.indeterminate",
                metric="quality_score",
                value=None,
                unit="score",
                status=Status.INDETERMINATE,
                message=(
                    "no-reference mode: cannot compute full-reference metric "
                    "(rule 2: sem referência = sem métrica full-reference)"
                ),
                evidence={"mode": mode},
                extra_limitations=[
                    "do not interpret indeterminate as pass or fail",
                ],
            )]

        # Verify reference hash if declared
        if ref_sha:
            actual_sha = sha256_of_file(ref_path)
            if actual_sha != ref_sha:
                return [self._finding(
                    check_id="ref_quality.hash_mismatch",
                    metric="quality_score",
                    value=None,
                    unit="score",
                    status=Status.ERROR,
                    message=f"reference hash mismatch: declared {ref_sha[:12]}.. vs actual {actual_sha[:12]}..",
                    evidence={"declared_sha256": ref_sha, "actual_sha256": actual_sha},
                )]

        try:
            ref_audio = decode(ref_path)
        except Exception as exc:
            return [self._finding(
                check_id="ref_quality.decode_error",
                metric="quality_score",
                value=None,
                unit="score",
                status=Status.ERROR,
                message=f"could not decode reference: {exc}",
                evidence={"reference_path": ref_path},
            )]

        ref = ref_audio.mono_mix().astype(np.float64)
        deg = audio.mono_mix().astype(np.float64)

        # Resample reference to match if needed (explicit, declared in evidence)
        resampled = False
        if ref_audio.sample_rate != audio.sample_rate:
            from ..decode import _resample
            ref = _resample(ref.reshape(1, -1), ref_audio.sample_rate, audio.sample_rate)[0]
            resampled = True

        if mode == "speech-full-ref":
            score = _stoi_like(ref, deg, audio.sample_rate)
            metric = "stoi_proxy"
            unit = "0-1"
            min_score = float(params.get("min_score", 0.6))
            status = Status.PASS if score >= min_score else Status.WARNING
            msg = f"STOI proxy {score:.3f} (min {min_score})"
        elif mode == "audio-full-ref":
            score = _visqol_like(ref, deg, audio.sample_rate)
            metric = "visqol_proxy"
            unit = "MOS"
            min_score = float(params.get("min_score", 3.5))
            status = Status.PASS if score >= min_score else Status.WARNING
            msg = f"ViSQOL proxy {score:.2f} MOS (min {min_score})"
        elif mode == "source-sep-ref":
            score = _si_sdr(ref, deg)
            metric = "si_sdr_db"
            unit = "dB"
            min_score = float(params.get("min_score", 5.0))
            status = Status.PASS if score >= min_score else Status.WARNING
            msg = f"SI-SDR {score:.2f} dB (min {min_score})"
        else:
            return [self._finding(
                check_id="ref_quality.unknown_mode",
                metric="quality_score",
                value=None,
                unit="score",
                status=Status.NOT_APPLICABLE,
                message=f"unknown mode: {mode}",
                evidence={"mode": mode},
            )]

        if not np.isfinite(score):
            score = 0.0
            status = Status.INDETERMINATE
            msg = "score was non-finite"

        return [self._finding(
            check_id=f"ref_quality.{mode}",
            metric=metric,
            value=round(float(score), 4),
            unit=unit,
            status=status,
            confidence=0.8,
            message=msg,
            evidence={
                "mode": mode,
                "reference_sha256": ref_sha or ref_audio.file_sha256,
                "reference_sample_rate_hz": ref_audio.sample_rate,
                "resampled": resampled,
                "min_score": min_score,
            },
        )]

    def profile_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["no-reference", "speech-full-ref", "audio-full-ref", "source-sep-ref"],
                    "default": "no-reference",
                },
                "reference_path": {"type": "string"},
                "reference_sha256": {"type": "string"},
                "min_score": {"type": "number"},
            },
            "additionalProperties": False,
        }
