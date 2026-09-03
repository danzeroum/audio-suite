"""ENG-13 — `audio-suite compare A.wav B.wav`: diff acústico objetivo.

Compara dois arquivos e produz `diff.json` com:
  - ΔLUFS, ΔdBTP, ΔLRA (e Δ de mono_compat quando ambos estéreo)
  - novos achados: rule_ids (CONTR-02) que aparecem flagados em B e não em A
  - observações: descritores (classe descritiva) entram SEMPRE como
    observation — R1: descritivo jamais gera regressão
  - `regression_detected: bool` — true SOMENTE se:
      (a) defeito objetivo novo (rule_id flagado em B e não em A), ou
      (b) limiar de plataforma violado em B que A respeitava.
    Ambos derivam dos findings objetivos (status warning/fail).

Mesma disciplina de contrato do bundle (CONTR-01): a saída é validada contra
`schemas/compare-v1.json` antes de ser emitida.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import __version__
from .decode import decode
from .models import Profile, Status
from .policy import load_profile
from .rule_ids import get_rule_id

#: Analyzers objetivos (podem flagar defeito — entram no critério de regressão)
OBJECTIVE_ANALYZERS = [
    "loudness",
    "true_peak",
    "clipping",
    "glitch",
    "loop",
    "mono_compat",
    "channel_balance",
]

#: Descritores/observação (R1 — nunca geram regressão)
DESCRIPTOR_ANALYZERS = [
    "spectral_health",
    "lra",  # medida também entra em deltas, mas status de LRA é observação
    "timbre_distance",
    "harmonic_tension",
    "spectral_irregularity",
    "inharmonicity",
    "fatigue_index",
    "rhythmic_grid_alignment",
    "melodic_contour",
]

COMPARE_ANALYZERS = OBJECTIVE_ANALYZERS + DESCRIPTOR_ANALYZERS

FLAG_STATUSES = {Status.WARNING, Status.FAIL, Status.NEEDS_REVIEW}


@dataclass(frozen=True)
class SideResult:
    """Medidas coletadas de um lado da comparação."""

    file: str
    sha256: str
    metrics: dict[str, float] = field(default_factory=dict)  # metric → valor
    flagged_rule_ids: set[str] = field(default_factory=set)
    observations: list[dict[str, Any]] = field(default_factory=list)


def _analyze_side(path: str, profile: Profile) -> SideResult:
    from .analyzers import all_analyzers

    audio = decode(path)
    registry = all_analyzers()
    metrics: dict[str, float] = {}
    flagged: set[str] = set()
    observations: list[dict[str, Any]] = []

    for aid in COMPARE_ANALYZERS:
        analyzer = registry.get(aid)
        if analyzer is None or not analyzer.applicable(audio, profile):
            continue
        for f in analyzer.analyze(audio, profile.analyzer_params(aid)):
            rid = get_rule_id(aid, f.metric)
            if f.value is not None and aid != "inspect":
                metrics[f"{aid}.{f.metric}"] = float(f.value)
            if aid in OBJECTIVE_ANALYZERS:
                if f.status in FLAG_STATUSES and rid:
                    flagged.add(rid)
            else:
                # classe descritiva: TODO finding entra como observation (R1) —
                # nunca gera regression, mesmo quando flag (needs_review)
                observations.append(
                    {
                        "rule_id": rid,
                        "analyzer": aid,
                        "metric": f.metric,
                        "value": round(float(f.value), 6) if f.value is not None else None,
                        "status": f.status.value,
                        "note": "classe descritiva — nunca gera regressão (R1)",
                    }
                )
    return SideResult(
        file=str(path),
        sha256=audio.file_sha256,
        metrics=metrics,
        flagged_rule_ids=flagged,
        observations=observations,
    )


_DELTA_KEYS = ("loudness.integrated_loudness", "true_peak.true_peak", "lra.loudness_range")


def compare_files(a_path: str, b_path: str, profile: Profile | None = None) -> dict[str, Any]:
    """Compara A e B e devolve o diff como dict (validável por schema)."""
    profile = profile or load_profile(str(Path(__file__).parent / "default_profile.yaml"))
    a = _analyze_side(a_path, profile)
    b = _analyze_side(b_path, profile)

    deltas: dict[str, float] = {}
    for key in _DELTA_KEYS:
        if key in a.metrics and key in b.metrics:
            deltas[f"delta_{key.split('.')[-1]}"] = round(b.metrics[key] - a.metrics[key], 6)
    mb_a = a.metrics.get("mono_compat.max_band_loss")
    mb_b = b.metrics.get("mono_compat.max_band_loss")
    if mb_a is not None and mb_b is not None:
        deltas["delta_max_band_loss"] = round(mb_b - mb_a, 6)

    new_objective = sorted(b.flagged_rule_ids - a.flagged_rule_ids)
    resolved = sorted(a.flagged_rule_ids - b.flagged_rule_ids)
    unchanged = sorted(a.flagged_rule_ids & b.flagged_rule_ids)

    regression_reasons: list[str] = []
    if new_objective:
        regression_reasons.append("novo defeito objetivo em B: " + ", ".join(new_objective))

    result: dict[str, Any] = {
        "schema": "audio-suite/compare@1",
        "tool": {"name": "audio-suite", "version": __version__},
        "a": {"file": a.file, "sha256": a.sha256, "flagged_rule_ids": sorted(a.flagged_rule_ids)},
        "b": {"file": b.file, "sha256": b.sha256, "flagged_rule_ids": sorted(b.flagged_rule_ids)},
        "deltas": deltas,
        "findings": {
            "only_in_a": resolved,
            "only_in_b": new_objective,
            "unchanged": unchanged,
        },
        "observations": sorted(b.observations, key=lambda o: (o["rule_id"], o["metric"])),
        "regression_detected": bool(new_objective),
        "regression_reasons": regression_reasons,
        "note": (
            "regression_detected reflete apenas defeitos objetivos (R1: descritores "
            "são observação); IDs estáveis por CONTR-02; schema CONTR-01"
        ),
    }
    _validate_schema(result)
    return result


def _validate_schema(payload: dict[str, Any]) -> None:
    schema_path = Path(__file__).resolve().parent.parent / "schemas" / "compare-v1.json"
    if not schema_path.exists():
        return  # schema é defesa em profundidade, não dependência de runtime
    import jsonschema

    with open(schema_path) as f:
        schema = json.load(f)
    jsonschema.validate(instance=payload, schema=schema)
