#!/usr/bin/env python3
"""CORP-08 — precisão/recall por detector sobre o corpus de defeito injetado.

Para cada analyzer (detector), agrega sobre todos os casos do corpus:
  - TP: caso com o rule_id do detector esperado E o detector apontou
  - FP: detector apontou num caso sem o rule_id dele no ground truth
  - FN: caso com o rule_id esperado mas o detector não apontou
  - N/A: cobertura (casos com coverage_gap não têm detector — reportados à parte)

"Apontar" = finding com status flag (warning/fail/needs_review).

Saídas:
  - tabela Markdown (stdout) — publicada no README e no relatório de release
  - JSON machine-readable (--json PATH) — artifact de CI

Uso:
    python scripts/detector_score.py [--json detector-score.json] [--md detector-score.md]
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from audio_suite.analyzers import all_analyzers  # noqa: E402
from audio_suite.decode import decode  # noqa: E402
from audio_suite.models import Profile, Status  # noqa: E402
from audio_suite.rule_ids import get_rule_id  # noqa: E402
from tests.corpus.defects import CORPUS_CASES, render_case_wav  # noqa: E402

#: Detectores (analyzers objetivos) sob avaliação no corpus
DETECTOR_IDS = [
    "glitch",
    "clipping",
    "true_peak",
    "loop",
    "channel_balance",
    "mono_compat",
]

FLAG_STATUSES = {Status.WARNING.value, Status.FAIL.value, Status.NEEDS_REVIEW.value}


def compute_scores() -> dict:
    from audio_suite.rule_ids import RULE_IDS

    profile_stub = Profile(name="score", version="0", analyzers={})
    registry = all_analyzers()

    # detector → conjunto de rule_ids que ele emite (CONTR-02)
    rules_by_detector: dict[str, set[str]] = {aid: set() for aid in DETECTOR_IDS}
    for (aid, _metric), rid in RULE_IDS.items():
        if aid in rules_by_detector:
            rules_by_detector[aid].add(rid)

    per_detector: dict[str, dict[str, int]] = {}
    per_rule: dict[str, dict[str, int]] = {}
    cases_report: list[dict] = []

    for case in CORPUS_CASES:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(render_case_wav(case))
            tmp_path = tmp.name
        audio = decode(tmp_path)
        expected = set(case.expected_findings)

        flagged: set[str] = set()
        det_rules: dict[str, set[str]] = {aid: set() for aid in DETECTOR_IDS}
        for aid in DETECTOR_IDS:
            analyzer = registry[aid]
            if not analyzer.applicable(audio, profile_stub):
                continue
            for f in analyzer.analyze(audio, {}):
                if f.status.value in FLAG_STATUSES:
                    rid = get_rule_id(aid, f.metric)
                    if rid:
                        det_rules[aid].add(rid)
                        flagged.add(rid)

        for aid in DETECTOR_IDS:
            d = per_detector.setdefault(aid, {"tp": 0, "fp": 0, "fn": 0, "cases": 0, "flagged": 0})
            d["cases"] += 1
            mine = det_rules[aid]
            det_expected = expected & rules_by_detector[aid]
            if mine:
                d["flagged"] += 1
            if mine & expected:
                d["tp"] += 1
            elif mine:
                d["fp"] += 1
            if det_expected and not (mine & expected):
                d["fn"] += 1

        for rid in expected:
            r = per_rule.setdefault(rid, {"tp": 0, "fp": 0, "fn": 0})
            r["tp" if rid in flagged else "fn"] += 1
        for rid in flagged - expected:
            r = per_rule.setdefault(rid, {"tp": 0, "fp": 0, "fn": 0})
            r["fp"] += 1

        cases_report.append(
            {
                "case": case.name,
                "defect_type": case.defect_type,
                "expected": sorted(expected),
                "flagged": sorted(flagged),
                "coverage_gap": case.coverage_gap,
                "hit": bool(expected) and expected.issubset(flagged),
            }
        )

    def _pr(tp: int, fp: int, fn: int) -> tuple[str, str]:
        precision = tp / (tp + fp) if (tp + fp) else None
        recall = tp / (tp + fn) if (tp + fn) else None
        return (
            f"{precision:.2f}" if precision is not None else "—",
            f"{recall:.2f}" if recall is not None else "—",
        )

    rule_rows = []
    for rid, c in sorted(per_rule.items()):
        p, r = _pr(c["tp"], c["fp"], c["fn"])
        rule_rows.append(
            {"rule_id": rid, "tp": c["tp"], "fp": c["fp"], "fn": c["fn"], "precision": p, "recall": r}
        )

    detector_rows = []
    for aid, c in sorted(per_detector.items()):
        p, r = _pr(c["tp"], c["fp"], c["fn"])
        detector_rows.append(
            {
                "detector": aid,
                "tp": c["tp"],
                "fp": c["fp"],
                "fn": c["fn"],
                "precision": p,
                "recall": r,
                "flag_rate": f"{c['flagged']}/{c['cases']}",
            }
        )

    gaps = [c["defect_type"] for c in cases_report if c["coverage_gap"]]
    return {
        "schema": "audio-suite/detector-score@1",
        "corpus_size": len(CORPUS_CASES),
        "coverage_gaps": gaps,
        "by_rule": rule_rows,
        "by_detector": detector_rows,
        "cases": cases_report,
    }


def to_markdown(score: dict) -> str:
    lines = [
        "### Precisão/Recall por detector (CORP-08)",
        "",
        f"Corpus: {score['corpus_size']} casos de defeito injetado com ground truth.",
        "",
        "| detector | TP | FP | FN | precisão | recall |",
        "|---|---|---|---|---|---|",
    ]
    for r in score["by_detector"]:
        lines.append(
            f"| {r['detector']} | {r['tp']} | {r['fp']} | {r['fn']} | {r['precision']} | {r['recall']} |"
        )
    lines += ["", "| rule_id | TP | FP | FN | precisão | recall |", "|---|---|---|---|---|---|"]
    for r in score["by_rule"]:
        lines.append(
            f"| {r['rule_id']} | {r['tp']} | {r['fp']} | {r['fn']} | {r['precision']} | {r['recall']} |"
        )
    if score["coverage_gaps"]:
        lines += [
            "",
            "**Gaps de cobertura** (defeitos sem detector registrado, recall N/A): "
            + ", ".join(f"`{g}`" for g in score["coverage_gaps"]),
        ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", dest="json_path", default=None)
    parser.add_argument("--md", dest="md_path", default=None)
    args = parser.parse_args()

    score = compute_scores()
    md = to_markdown(score)
    print(md)
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(score, indent=2, ensure_ascii=False))
    if args.md_path:
        Path(args.md_path).write_text(md, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
