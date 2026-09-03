"""PROF-06.r — sub-variantes de music-master (streaming/shortform/club).

Herança `extends:` validada: filho herda analyzers/overlays do pai e sobrescreve
apenas o que declara. Descritores permanecem observation (R1 — o linter
PROF-08.r bloqueia qualquer overlay sobre métrica DESC).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from audio_suite.policy import load_profile  # noqa: E402

VARIANTS = {
    "streaming": {"min_lufs": -15.0, "max_lufs": -13.0, "max_dbtp": -1.0},
    "shortform": {"min_lufs": -13.0, "max_lufs": -9.0, "max_dbtp": -1.0},
    "club": {"min_lufs": -14.0, "max_lufs": -11.0, "max_dbtp": -2.0},
}


@pytest.mark.parametrize("variant", list(VARIANTS))
def test_variant_inherits_from_music_master(variant):
    p = load_profile(ROOT / "profiles" / "music-master" / f"{variant}.yaml")
    assert p.name == f"music-master/{variant}"
    # herdado do pai: analyzers que o filho não sobrescreve
    expected_analyzers = {
        "inspect",
        "loudness",
        "true_peak",
        "clipping",
        "glitch",
        "mono_compat",
        "channel_balance",
        "spectral_health",
        "lra",
        "codec_conf",
        "resampling",
        "transient",
        "ref_quality",
    }
    assert set(p.analyzers) == expected_analyzers
    # herdado: strict_overlay do pai (defeitos objetivos → error), ativo com --strict
    p_strict = load_profile(
        ROOT / "profiles" / "music-master" / f"{variant}.yaml", strict=True
    )
    assert p_strict.strict_overlay.get("clipping", {}).get("clipped_sample_pct") == "fail"
    assert p_strict.strict_overlay.get("true_peak", {}).get("true_peak") == "fail"
    assert p_strict.strict_overlay.get("glitch", {}).get("glitch_event_count") == "fail"
    # R1: NENHUM overlay sobre métrica descritiva (AS-DESC-*)
    from audio_suite.rule_ids import RULE_IDS, rule_id_class

    for aid, metrics in p_strict.strict_overlay.items():
        for metric, status in metrics.items():
            rid = RULE_IDS.get((aid, metric))
            if rid:
                assert rule_id_class(rid) == "objective", f"{aid}/{metric} não pode ser overlay"


@pytest.mark.parametrize("variant,expected", list(VARIANTS.items()))
def test_variant_thresholds(variant, expected):
    """Os limiares declarados no prompt/PR vencem sobre o pai."""
    p = load_profile(ROOT / "profiles" / "music-master" / f"{variant}.yaml")
    loud = p.analyzer_params("loudness")
    tp = p.analyzer_params("true_peak")
    assert loud["min_lufs"] == expected["min_lufs"]
    assert loud["max_lufs"] == expected["max_lufs"]
    assert tp["max_dbtp"] == expected["max_dbtp"]


def test_load_profile_by_name():
    """Resolução por nome (profiles/<nome>.yaml) — PROF-06.r conveniência."""
    p = load_profile("music-master")
    assert p.name == "music-master"
    assert p.analyzer_params("loudness")["min_lufs"] == -16.0


def test_inheritance_chain_and_unknown_parent():
    """extends em cadeia funciona; pai inexistente falha com erro claro."""
    import yaml

    from audio_suite.policy import ProfileError, _resolve_inheritance

    tmp = ROOT / "test-results" / "prof06r-tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    grandparent = tmp / "gp.yaml"
    grandparent.write_text(
        yaml.safe_dump({"name": "gp", "version": "1", "analyzers": {"loudness": {"min_lufs": -20.0}}})
    )
    parent = tmp / "p.yaml"
    parent.write_text(
        yaml.safe_dump({"extends": "gp", "name": "p", "analyzers": {"loudness": {"max_lufs": -10.0}}})
    )
    child = tmp / "c.yaml"
    child.write_text(yaml.safe_dump({"extends": "p", "name": "c"}))
    merged = _resolve_inheritance(yaml.safe_load(child.read_text()), child)
    assert merged["analyzers"]["loudness"] == {"min_lufs": -20.0, "max_lufs": -10.0}

    orphan = tmp / "orphan.yaml"
    orphan.write_text(yaml.safe_dump({"extends": "nao-existe", "name": "x"}))
    with pytest.raises(ProfileError, match="não encontrado"):
        _resolve_inheritance(yaml.safe_load(orphan.read_text()), orphan)


def test_music_master_profiles_pass_r1_linter():
    """O linter PROF-08.r valida os novos perfis (descritivo nunca fail)."""
    import subprocess

    res = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "lint_rule_registry.py")],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stderr
