#!/usr/bin/env python3
"""PROF-08.r — linter do registry de rule_ids: descritivo NUNCA falha (R1).

A R1 deixa de ser promessa e vira teste executável. Três camadas:

  1. PERFIS SHIPPED: nenhum strict_overlay em default_profile.yaml,
     profiles/*.yaml ou tests/golden/gm_profile.yaml pode mapear métrica da
     classe descritiva (AS-DESC-*) ou forense (AS-FORE-*) para fail.
  2. PROBE DINÂMICO: todos os analyzers registrados rodam sobre sinais
     sintéticos canônicos (sine mono/stereo, ruído, clipped) — nenhum finding
     com rule_id descritivo/forense pode terminar em fail/error.
  3. SCAN ESTÁTICO: módulos de analyzers cuja família de rule_ids é 100%
     descritiva/forense (ex.: descriptors.py) não podem conter os literais
     Status.FAIL/Status.ERROR — um commit que os introduza é rejeitado.

Uso:
    python scripts/lint_rule_registry.py            # exit 0 = OK, 1 = violação

CI: job `rule-registry-lint` + hook `.githooks/pre-commit`.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import yaml  # noqa: E402

from audio_suite.analyzers import all_analyzers  # noqa: E402
from audio_suite.models import PCM, Profile, Status  # noqa: E402
from audio_suite.rule_ids import RULE_IDS  # noqa: E402


def rule_class(rule_id: str) -> str:
    """Classe de um rule_id pelo prefixo (CONTR-02)."""
    if rule_id.startswith("AS-DESC-"):
        return "descriptive"
    if rule_id.startswith("AS-FORE-"):
        return "forensic"
    return "objective"


#: Classes que NÃO podem terminar em fail/error (R1 + R8)
NEVER_FAIL_CLASSES = {"descriptive", "forensic"}

NEVER_FAIL_STATUSES = {Status.FAIL, Status.ERROR}

PROFILE_PATHS = [
    ROOT / "audio_suite" / "default_profile.yaml",
    ROOT / "tests" / "golden" / "gm_profile.yaml",
    *(ROOT / "profiles").glob("*.yaml"),
    *(ROOT / "profiles" / "music-master").glob("*.yaml"),
]


# ---------------------------------------------------------------------------
# 1. Perfis shipped
# ---------------------------------------------------------------------------
def lint_profiles() -> list[str]:
    violations: list[str] = []
    for path in PROFILE_PATHS:
        if not path.exists():
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        overlay = raw.get("strict_overlay") or {}
        if not isinstance(overlay, dict):
            continue
        for aid, metrics in overlay.items():
            if not isinstance(metrics, dict):
                continue
            for metric, new_status in metrics.items():
                rid = RULE_IDS.get((aid, metric))
                if rid is None:
                    continue  # regra não registrada: contratado em outro lugar
                if rule_class(rid) in NEVER_FAIL_CLASSES and str(new_status) in ("fail", "error"):
                    violations.append(
                        f"{path.relative_to(ROOT)}: strict_overlay[{aid}][{metric}] → "
                        f"{new_status} viola R1 ({rid} é classe {rule_class(rid)})"
                    )
    return violations


# ---------------------------------------------------------------------------
# 2. Probe dinâmico
# ---------------------------------------------------------------------------
def _probe_signals() -> list[tuple[str, PCM]]:
    sr = 44100
    n = sr * 2
    t = np.arange(n) / sr
    mono = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    noise = (0.2 * np.random.Generator(np.random.PCG64(11)).standard_normal(n)).astype(np.float32)
    clipped = np.clip(1.5 * np.sin(2 * np.pi * 440 * t), -1, 1).astype(np.float32)
    stereo = np.stack([(0.3 * np.sin(2 * np.pi * 440 * t)), (0.3 * np.sin(2 * np.pi * 554 * t))]).astype(
        np.float32
    )
    return [
        ("mono_sine", PCM(samples=mono, sample_rate=sr)),
        ("noise", PCM(samples=noise, sample_rate=sr)),
        ("clipped", PCM(samples=clipped, sample_rate=sr)),
        ("stereo", PCM(samples=stereo, sample_rate=sr)),
        ("silence", PCM(samples=np.zeros(n, dtype=np.float32), sample_rate=sr)),
    ]


def lint_dynamic() -> list[str]:
    violations: list[str] = []
    registry = all_analyzers()
    stub = Profile(name="lint", version="0", analyzers={})
    for signal_name, audio in _probe_signals():
        for aid, analyzer in sorted(registry.items()):
            try:
                if not analyzer.applicable(audio, stub):
                    continue
                findings = analyzer.analyze(audio, {})
            except Exception as exc:  # noqa: BLE001
                violations.append(
                    f"probe {signal_name}/{aid}: analyzer lançou exceção: {type(exc).__name__}: {exc}"
                )
                continue
            for f in findings:
                rid = RULE_IDS.get((aid, f.metric))
                if rid and rule_class(rid) in NEVER_FAIL_CLASSES and f.status in NEVER_FAIL_STATUSES:
                    violations.append(
                        f"probe {signal_name}/{aid}: finding {rid} ({f.metric}) "
                        f"terminou em {f.status.value} — viola R1/R8"
                    )
    return violations


# ---------------------------------------------------------------------------
# 3. Scan estático
# ---------------------------------------------------------------------------
def _module_of_analyzer(aid: str) -> str:
    registry = all_analyzers()
    analyzer = registry.get(aid)
    if analyzer is None:
        return ""
    return analyzer.__class__.__module__.split(".")[-1]


def lint_static() -> list[str]:
    violations: list[str] = []
    # famílias de rule_id por módulo
    module_classes: dict[str, set[str]] = {}
    for (aid, _metric), rid in RULE_IDS.items():
        mod = _module_of_analyzer(aid)
        if mod:
            module_classes.setdefault(mod, set()).add(rule_class(rid))

    analyzers_dir = ROOT / "audio_suite" / "analyzers"
    for py in sorted(analyzers_dir.glob("*.py")):
        if py.stem in ("__init__", "base"):
            continue
        classes = module_classes.get(py.stem)
        # módulo com QUALQUER regra never-fail (descritiva/forense) entra no
        # escopo do scan — ex.: descriptors.py (7× AS-DESC + spectral_irregularity)
        # e lra.py (AS-DESC-007)
        if not classes or not (classes & NEVER_FAIL_CLASSES):
            continue
        source = py.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if (
                isinstance(node, ast.Attribute)
                and node.attr in ("FAIL", "ERROR")
                and isinstance(node.value, ast.Name)
                and node.value.id == "Status"
            ):
                line = getattr(node, "lineno", "?")
                violations.append(
                    f"{py.relative_to(ROOT)}:{line}: módulo com regras never-fail "
                    f"contém Status.{node.attr} — descritivo/forense não pode falhar (R1/R8)"
                )
    return violations


def main() -> int:
    violations = lint_profiles() + lint_dynamic() + lint_static()
    if violations:
        sys.stderr.write(f"PROF-08.r: {len(violations)} violação(ões) de R1/R8:\n")
        for v in violations:
            sys.stderr.write(f"  - {v}\n")
        return 1
    print(
        "PROF-08.r OK: perfis shipped limpos; probe dinâmico sem descritivo/forense "
        "em fail; módulos 100% descritivos sem Status.FAIL/ERROR."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
