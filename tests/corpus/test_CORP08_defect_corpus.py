"""CORP-08 — corpus de defeito injetado com ground truth.

Garantias:
  - ≥ 6 tipos de defeito com ground truth (DoD)
  - expected_findings são rule_ids registrados (CONTR-02)
  - corpus 100% determinístico (mesma seed → mesmos bytes)
  - todo caso com detector registrado é detectado (recall 1.0 no corpus) —
    regressão em detector quebra este teste
  - gaps de cobertura documentados (ex.: dc_offset) ficam visíveis
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.corpus.defects import CORPUS_CASES, DefectCase, render_case_wav  # noqa: E402


def test_corpus_has_at_least_six_defect_types():
    types = {c.defect_type for c in CORPUS_CASES}
    assert len(types) >= 6, f"corpus precisa de ≥6 tipos de defeito, tem {len(types)}: {types}"


def test_ground_truth_uses_registered_rule_ids():
    from audio_suite.rule_ids import RULE_IDS

    valid = set(RULE_IDS.values())
    for case in CORPUS_CASES:
        for rid in case.expected_findings:
            assert rid in valid, f"{case.name}: {rid} não é rule_id registrado (CONTR-02)"


def test_corpus_is_deterministic():
    for case in CORPUS_CASES:
        a = render_case_wav(case)
        b = render_case_wav(case)
        assert a == b, f"caso {case.name} não é determinístico"


def test_coverage_gaps_are_explicit():
    """Casos sem detector ficam com expected_findings=[] e coverage_gap=True."""
    for case in CORPUS_CASES:
        if case.coverage_gap:
            assert case.expected_findings == [], f"{case.name}: coverage_gap exige expected_findings vazio"
            assert case.notes, f"{case.name}: coverage_gap exige nota explicativa"
    # o gap de dc_offset precisa estar documentado (não silencioso)
    assert any(c.defect_type == "dc_offset" and c.coverage_gap for c in CORPUS_CASES), (
        "gap de DC offset deve permanecer explícito até existir detector"
    )


def test_detectors_catch_every_non_gap_case():
    """DoD CORP-08: recall 1.0 do corpus — detector que regridi quebra aqui."""
    from scripts.detector_score import compute_scores  # type: ignore[import-not-found]

    score = compute_scores()
    misses = [c for c in score["cases"] if not c["coverage_gap"] and not c["hit"]]
    assert not misses, "detectores falharam em casos com ground truth: " + ", ".join(
        f"{m['case']} esperado={m['expected']} apontado={m['flagged']}" for m in misses
    )
    assert score["corpus_size"] >= 6


def test_score_script_reports_coverage_gaps():
    from scripts.detector_score import compute_scores  # type: ignore[import-not-found]

    score = compute_scores()
    assert "dc_offset" in score["coverage_gaps"]
