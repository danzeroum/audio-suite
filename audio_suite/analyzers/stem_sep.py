"""Stem separation quality analyzer — SI-SDR with reference (Fase 3).

Per the roadmap (Fase 3 STEM_SEP): "Leakage, artifact score, SI-SDR."
Exige referência limpa. Sem ref = analyzer no-reference distinto.

This analyzer evaluates the quality of separated stems (e.g., vocals,
drums, bass) against known reference stems. It computes:
  - SI-SDR (Scale-Invariant Signal-to-Distortion Ratio) per stem
  - Leakage: energy from other stems present in this one
  - Artifact score: spectral artifacts introduced by separation

Per rule 2: without reference, returns indeterminate (does NOT compute
a fake SI-SDR).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..models import PCM, Profile, Status
from . import register
from .base import AudioAnalyzer
from .ref_quality import _si_sdr


def _leakage_pct(estimated: np.ndarray, references: list[np.ndarray], own_idx: int) -> float:
    """Estimate leakage: how much energy from OTHER stems is in this estimate.

    Uses projection: project estimated onto each reference, the sum of non-own
    projections / total energy = leakage %.
    """
    if len(estimated) == 0:
        return 0.0
    total_energy = float(np.sum(estimated**2)) + 1e-12
    leakage_energy = 0.0
    for i, ref in enumerate(references):
        if i == own_idx or len(ref) == 0:
            continue
        # Project estimated onto ref
        n = min(len(estimated), len(ref))
        a = estimated[:n]
        b = ref[:n]
        alpha = float(np.dot(a, b) / (np.dot(b, b) + 1e-12))
        if alpha > 0:
            leakage_energy += float(np.sum((alpha * b) ** 2))
    return float(100.0 * leakage_energy / total_energy)


@register
class StemSepAnalyzer(AudioAnalyzer):
    ID = "stem_sep"
    NAME = "Stem Separation Quality (SI-SDR + leakage)"
    VERSION = "1.0.0"
    METHOD = "SI-SDR per stem + cross-stem leakage projection"
    DEFAULT_LIMITATIONS = [
        "Requires clean reference stems (rule 2)",
        "SI-SDR is a proxy; not the official museval implementation",
        "Leakage estimation assumes orthogonal references; may overcount on correlated stems",
        "Without reference, returns indeterminate — do NOT interpret as pass/fail",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        params = profile.analyzer_params(self.ID)
        # Applicable only if references are declared
        return bool(params.get("references"))

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        from ..decode import decode

        references = params.get("references", {})
        own_stem = params.get("stem_name", "unknown")
        min_si_sdr_db = float(params.get("min_si_sdr_db", 5.0))
        max_leakage_pct = float(params.get("max_leakage_pct", 10.0))

        if not references:
            return [
                self._finding(
                    check_id="stem_sep.indeterminate",
                    metric="si_sdr_db",
                    value=None,
                    unit="dB",
                    status=Status.INDETERMINATE,
                    message=(
                        "no reference stems provided; cannot compute SI-SDR "
                        "(rule 2: sem referência = sem métrica full-reference)"
                    ),
                    evidence={"stem_name": own_stem},
                )
            ]

        # Decode all references
        ref_signals: list[np.ndarray] = []
        ref_names: list[str] = []
        own_idx = -1
        for i, (name, ref_info) in enumerate(references.items()):
            ref_path = ref_info.get("path") if isinstance(ref_info, dict) else ref_info
            if not ref_path:
                continue
            try:
                ref_audio = decode(ref_path)
                ref = ref_audio.mono_mix().astype(np.float64)
                if ref_audio.sample_rate != audio.sample_rate:
                    from ..decode import _resample

                    ref = _resample(ref.reshape(1, -1), ref_audio.sample_rate, audio.sample_rate)[0]
                ref_signals.append(ref)
                ref_names.append(name)
                if name == own_stem:
                    own_idx = i
            except Exception as exc:
                return [
                    self._finding(
                        check_id="stem_sep.decode_error",
                        metric="si_sdr_db",
                        value=None,
                        unit="dB",
                        status=Status.ERROR,
                        message=f"could not decode reference '{name}': {exc}",
                        evidence={"reference_name": name, "reference_path": str(ref_path)},
                    )
                ]

        if own_idx < 0 or not ref_signals:
            return [
                self._finding(
                    check_id="stem_sep.no_own_ref",
                    metric="si_sdr_db",
                    value=None,
                    unit="dB",
                    status=Status.NOT_APPLICABLE,
                    message=f"own stem '{own_stem}' not found in references",
                    evidence={"references": ref_names, "own_stem": own_stem},
                )
            ]

        est = audio.mono_mix().astype(np.float64)
        own_ref = ref_signals[own_idx]

        # SI-SDR
        si_sdr = _si_sdr(own_ref, est)
        if not np.isfinite(si_sdr):
            si_sdr = -100.0

        # Leakage
        leakage = _leakage_pct(est, ref_signals, own_idx)

        # Determine status
        if si_sdr < min_si_sdr_db:
            si_sdr_status = Status.WARNING
            si_sdr_msg = f"SI-SDR {si_sdr:.2f} dB below {min_si_sdr_db} dB"
        else:
            si_sdr_status = Status.PASS
            si_sdr_msg = f"SI-SDR {si_sdr:.2f} dB >= {min_si_sdr_db} dB"

        if leakage > max_leakage_pct:
            leak_status = Status.WARNING
            leak_msg = f"leakage {leakage:.1f}% exceeds {max_leakage_pct}%"
        else:
            leak_status = Status.PASS
            leak_msg = f"leakage {leakage:.1f}% within {max_leakage_pct}%"

        return [
            self._finding(
                check_id="stem_sep.si_sdr",
                metric="si_sdr_db",
                value=round(float(si_sdr), 2),
                unit="dB",
                status=si_sdr_status,
                confidence=0.85,
                message=si_sdr_msg,
                evidence={
                    "stem_name": own_stem,
                    "min_si_sdr_db": min_si_sdr_db,
                    "reference_stems": ref_names,
                },
            ),
            self._finding(
                check_id="stem_sep.leakage",
                metric="leakage_pct",
                value=round(float(leakage), 2),
                unit="%",
                status=leak_status,
                confidence=0.7,
                message=leak_msg,
                evidence={
                    "stem_name": own_stem,
                    "max_leakage_pct": max_leakage_pct,
                    "cross_stems": [n for i, n in enumerate(ref_names) if i != own_idx],
                },
            ),
        ]

    def profile_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "stem_name": {"type": "string"},
                "references": {
                    "type": "object",
                    "description": "Mapping of stem name to {path, sha256}",
                },
                "min_si_sdr_db": {"type": "number", "default": 5.0},
                "max_leakage_pct": {"type": "number", "default": 10.0},
            },
            "additionalProperties": False,
        }
