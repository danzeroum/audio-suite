"""CORP-04 Golden Master — suite de regressão de processo.

DoD: um off-by-one em qualquer analyzer-core é rejeitado com diff legível;
suíte completa roda em < 90 s. Diffs são publicados como artifacts
(gm-diff.json + gm-diff.html) em AUDIO_SUITE_GM_DIFF_DIR (default:
test-results/gm-diff/).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from audio_suite.golden import (
    DEFAULT_EXPECTED_DIR,
    DEFAULT_MANIFEST,
    GM_ANALYZER_IDS,
    load_golden_manifest,
    verify_golden,
)

ROOT = Path(__file__).resolve().parents[2]


def _diff_dir() -> Path:
    env = os.environ.get("AUDIO_SUITE_GM_DIFF_DIR")
    return Path(env) if env else ROOT / "test-results" / "gm-diff"


def test_golden_master_integrity():
    """Golden Master: métricas dos analyzers-core dentro das tolerâncias ±2σ.

    Em violação, escreve gm-diff.json + gm-diff.html legíveis e falha com
    um resumo acionável (o diff completo está nos artifacts).
    """
    t0 = time.time()
    violations, summary = verify_golden(
        manifest_path=DEFAULT_MANIFEST,
        expected_dir=DEFAULT_EXPECTED_DIR,
        diff_dir=None,  # artifacts escritos abaixo, uma única vez
    )
    elapsed = time.time() - t0

    if violations:
        json_path, html_path = _write_artifacts(violations, summary)
        head = "\n".join(
            f"  {v.fixture:24s} {v.analyzer:24s} {v.kind:16s} {v.detail}" for v in violations[:12]
        )
        more = f"\n  … +{len(violations) - 12} violações (ver artifact)" if len(violations) > 12 else ""
        pytest.fail(
            "Golden Master violado (CORP-04).\n"
            f"Diff legível: {html_path}\nDiff machine-readable: {json_path}\n"
            f"Primeiras violações:\n{head}{more}\n"
            "Se a mudança é intencional: rode `audio-suite golden freeze`, "
            "adicione label `golden-regen` e justifique no CHANGELOG."
        )

    # Guarda de budget (CORP-04.r): suíte GM < 90 s
    assert elapsed < 90.0, f"GM suite excedeu 90 s ({elapsed:.1f}s) — TEST-05 investigar"


def _write_artifacts(violations, summary):
    d = _diff_dir()
    d.mkdir(parents=True, exist_ok=True)
    from audio_suite.golden import write_diff_artifacts

    json_path, html_path = write_diff_artifacts(d, violations, summary)
    return json_path, html_path


# ---------------------------------------------------------------------------
# Meta-testes: sanidade do próprio Golden Master
# ---------------------------------------------------------------------------
def test_golden_expected_files_exist_for_all_analyzers():
    for aid in GM_ANALYZER_IDS:
        p = DEFAULT_EXPECTED_DIR / f"{aid}.json"
        assert p.exists(), f"golden file ausente: {p} — rode 'audio-suite golden freeze'"
        payload = json.loads(p.read_text())
        assert payload["analyzer"] == aid


def test_golden_manifest_fixtures_match_expected():
    manifest = load_golden_manifest(DEFAULT_MANIFEST)
    for aid in GM_ANALYZER_IDS:
        payload = json.loads((DEFAULT_EXPECTED_DIR / f"{aid}.json").read_text())
        for fixture in manifest["fixtures"]:
            assert fixture in payload["fixtures"], (
                f"{aid}.json não cobre a fixture {fixture} — regenere com golden freeze"
            )


def test_golden_tolerances_are_empirical_not_hardcoded():
    """Toda métrica float dos expected files precisa de tolerância declarada.

    Impede o anti-pattern de hard-code 0,05: tolerâncias vêm da calibração
    (±2σ) registrada em manifest.yaml/calibration.json.
    """
    import math

    manifest = load_golden_manifest(DEFAULT_MANIFEST)
    tolerances = manifest.get("tolerances", {})
    missing = []
    for aid in GM_ANALYZER_IDS:
        payload = json.loads((DEFAULT_EXPECTED_DIR / f"{aid}.json").read_text())
        metric_tol = tolerances.get(aid, {})
        for fixture, findings in payload["fixtures"].items():
            for f in findings:
                if f["value"] is not None and f["metric"] not in metric_tol and "*" not in metric_tol:
                    missing.append(f"{aid}/{f['metric']} ({fixture})")
    assert not missing, (
        f"métricas sem tolerância empírica declarada: {sorted(set(missing))} — "
        "rode scripts/golden_calibrate.py"
    )
    # Tolerâncias devem ser decimais plausíveis (derivadas), não "0.05" mágico.
    for aid, metrics in tolerances.items():
        for metric, tol in metrics.items():
            assert isinstance(tol, (int, float)) and tol >= 0.0
            assert not (math.isclose(tol, 0.05) and metric == "*"), (
                "tolerância mágica 0.05 proibida (CORP-04.r)"
            )


def test_golden_calibration_provenance_present():
    calib = ROOT / "tests" / "golden" / "calibration.json"
    assert calib.exists(), "calibration.json ausente — rode scripts/golden_calibrate.py"
    data = json.loads(calib.read_text())
    for key in ("method", "sigma", "tolerances", "seed", "trials"):
        assert key in data, f"calibration.json sem campo de proveniência: {key}"
