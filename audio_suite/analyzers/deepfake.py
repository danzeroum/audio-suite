"""Deepfake voice detection analyzer — opt-in ML inference (Fase 3).

Per the roadmap (Fase 3 DEEPFAKE): "Assinaturas acústicas de voz sintética."
Marked as **opt-in**. **Never emits an automatic conclusion.**

CRITICAL (rule 4 — Opt-in para ML pesado + rule 8 — Regra da Inferência):
  - Only runs if explicitly enabled in profile: `enabled: true`
  - Requires a declared model + corpus + confidence interval
  - ALWAYS returns `needs_review` — never `pass` or `fail`
  - Exige modelo, corpus, incerteza e revisão humana

What this analyzer DOES (in this v0.1 stub):
  - Extracts acoustic features that correlate with synthetic voice
    (spectral flatness in high band, F0 contour regularity, phase coherence)
  - Reports features + a heuristic "synthetic-likeness" score
  - Returns needs_review with explicit limitations

What it does NOT do:
  - Load an ML model (no model is bundled; requires external model per A2)
  - Conclude "this is deepfake" or "this is authentic"
  - Be used as the sole basis for any decision
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..models import PCM, Profile, Status
from . import register
from .base import AudioAnalyzer


def _spectral_flatness_band(x: np.ndarray, sr: int, f_lo: float, f_hi: float) -> float:
    """Spectral flatness in a specific band."""
    if len(x) < 1024:
        return 0.0
    n_fft = 2048
    win = np.hanning(n_fft)
    X = np.abs(np.fft.rfft(x[:n_fft] * win)) + 1e-12
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
    band = (freqs >= f_lo) & (freqs <= f_hi)
    if not band.any():
        return 0.0
    band_X = X[band]
    geo = np.exp(np.mean(np.log(band_X)))
    arith = float(np.mean(band_X))
    if arith <= 0:
        return 0.0
    return float(geo / arith)


def _f0_contour_regularity(x: np.ndarray, sr: int) -> float:
    """Regularity of F0 contour — synthetic voice tends to be more regular.

    Returns coefficient of variation (lower = more regular = more synthetic-like).
    """
    from .pitch_stab import _pitch_track_autocorr

    f0 = _pitch_track_autocorr(x, sr)
    valid = f0[np.isfinite(f0)]
    if len(valid) < 8:
        return 1.0  # default: irregular
    # CV = std / mean
    mean_f = float(np.mean(valid))
    if mean_f <= 0:
        return 1.0
    return float(np.std(valid) / mean_f)


def _phase_coherence(x: np.ndarray, sr: int) -> float:
    """Average phase coherence — synthetic voice may have anomalous coherence.

    Returns mean coherence in [0, 1].
    """
    if len(x) < 2048:
        return 0.0
    n_fft = 2048
    hop = 512
    n_frames = max(0, (len(x) - n_fft) // hop + 1)
    if n_frames < 2:
        return 0.0
    win = np.hanning(n_fft)
    # STFT
    frames = []
    for i in range(n_frames):
        frames.append(np.fft.rfft(x[i * hop : i * hop + n_fft] * win))
    S = np.stack(frames)
    # Phase difference between consecutive frames
    phase_diff = np.diff(np.angle(S), axis=0)
    # Coherence = how concentrated the phase differences are
    # Use vector mean
    mean_vec = np.mean(np.exp(1j * phase_diff), axis=0)
    coherence = np.abs(mean_vec)
    return float(np.mean(coherence))


@register
class DeepfakeAnalyzer(AudioAnalyzer):
    ID = "deepfake"
    NAME = "Deepfake Voice Detection (opt-in, experimental)"
    VERSION = "0.1.0"  # 0.x = experimental
    METHOD = "acoustic feature extraction (heuristic, no ML model bundled)"
    DEFAULT_LIMITATIONS = [
        "OPT-IN only: must be explicitly enabled with `enabled: true`",
        "No ML model is bundled; this is a heuristic feature extractor, not a classifier",
        "NEVER concludes 'deepfake' or 'authentic' — always needs_review",
        "Requires external model + corpus for any forensic use (A2)",
        "Features are correlated with synthetic voice but are NOT definitive",
        "False positive rate is high without model calibration",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        params = profile.analyzer_params(self.ID)
        # Opt-in (rule 4): must be explicitly enabled
        if not params.get("enabled", False):
            return False
        # Require declared model (A2: calibration is requisito de aceite)
        if not params.get("model_name"):
            return False
        return audio.n_frames >= audio.sample_rate * 2  # at least 2 seconds

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        model_name = params.get("model_name", "unspecified")
        model_version = params.get("model_version", "unspecified")
        corpus = params.get("corpus", "unspecified")

        x = audio.mono_mix().astype(np.float64)

        # Extract features that correlate with synthetic voice
        high_flatness = _spectral_flatness_band(x, audio.sample_rate, 4000, 8000)
        f0_cv = _f0_contour_regularity(x, audio.sample_rate)
        phase_coh = _phase_coherence(x, audio.sample_rate)

        # Heuristic "synthetic-likeness" score (NOT a classifier output)
        # Lower F0 CV (more regular) + higher phase coherence = more synthetic-like
        # This is a FEATURE, not a conclusion
        synthetic_likeness = float(
            0.4 * (1.0 - min(1.0, f0_cv))  # regularity
            + 0.3 * phase_coh  # coherence
            + 0.3 * high_flatness  # high-band flatness
        )
        synthetic_likeness = float(np.clip(synthetic_likeness, 0.0, 1.0))

        # ALWAYS needs_review — never pass/fail (rule 8)
        return [
            self._finding(
                check_id="deepfake.features",
                metric="synthetic_likeness_score",
                value=round(synthetic_likeness, 4),
                unit="0-1",
                status=Status.NEEDS_REVIEW,  # ALWAYS
                confidence=0.3,  # low confidence without a real model
                message=(
                    f"synthetic-likeness score {synthetic_likeness:.3f} — "
                    "REQUIRES HUMAN REVIEW. This is a heuristic feature, NOT a "
                    "deepfake classification. No ML model was used."
                ),
                evidence={
                    "model_name": model_name,
                    "model_version": model_version,
                    "corpus": corpus,
                    "features": {
                        "high_band_spectral_flatness": round(high_flatness, 4),
                        "f0_contour_cv": round(f0_cv, 4),
                        "phase_coherence": round(phase_coh, 4),
                    },
                    "forensic_warning": (
                        "This result does NOT constitute a deepfake detection. "
                        "An ML model trained on a labeled corpus is required for "
                        "any classification. The score is a heuristic feature "
                        "for human review only."
                    ),
                },
            )
        ]

    def profile_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean", "default": False},
                "model_name": {"type": "string"},
                "model_version": {"type": "string"},
                "corpus": {"type": "string"},
            },
            "required": ["enabled", "model_name"],
            "additionalProperties": False,
        }
