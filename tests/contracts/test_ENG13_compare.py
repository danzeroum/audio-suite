"""ENG-13 — testes do `audio-suite compare A.wav B.wav`.

DoD:
  - dois WAVs que diferem só em centroide/BPM → regression_detected: false
  - um WAV com clipping novo → true com o rule_id do clipping no diff
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from audio_suite.compare import compare_files  # noqa: E402
from audio_suite.policy import load_profile  # noqa: E402
from tests.fixtures.generators import wav_bytes  # noqa: E402

SR = 44100


def _write_wav(tmp_path: Path, name: str, samples: np.ndarray) -> str:
    p = tmp_path / name
    p.write_bytes(wav_bytes(samples.astype(np.float32), SR, "PCM_16"))
    return str(p)


def _sine(freq: float, amp: float = 0.3, dur_s: float = 2.0) -> np.ndarray:
    t = np.arange(int(SR * dur_s)) / SR
    return amp * np.sin(2 * np.pi * freq * t)


@pytest.fixture(scope="module")
def gm_profile():
    return load_profile(ROOT / "tests" / "golden" / "gm_profile.yaml")


def test_descriptive_only_difference_is_not_regression(tmp_path, gm_profile):
    """Senoide 1 kHz vs 2 kHz mesmo nível: muda centroide, não é regressão."""
    a = _write_wav(tmp_path, "a_1k.wav", _sine(1000))
    b = _write_wav(tmp_path, "b_2k.wav", _sine(2000))
    diff = compare_files(a, b, profile=gm_profile)
    assert diff["regression_detected"] is False
    assert diff["findings"]["only_in_b"] == []
    # descritores (spectral centroid) aparecem como observation, nunca regressão
    obs_metrics = {o["metric"] for o in diff["observations"]}
    assert "spectral_centroid" in obs_metrics
    # Δ de métricas objetivas presente
    assert "delta_integrated_loudness" in diff["deltas"]
    # JSON valida contra o schema CONTR-01 (compare_files já valida; revalida explícito)
    import jsonschema

    schema = json.loads((ROOT / "schemas" / "compare-v1.json").read_text())
    jsonschema.validate(diff, schema)


def test_new_clipping_is_regression_with_rule_id(tmp_path, gm_profile):
    """B com clipping novo → regression_detected true + AS-PEAK-002 no diff."""
    a = _write_wav(tmp_path, "clean.wav", _sine(440))
    t = np.arange(int(SR * 2)) / SR
    clipped = np.clip(1.6 * np.sin(2 * np.pi * 440 * t), -1.0, 1.0)
    b = _write_wav(tmp_path, "clipped.wav", clipped)
    diff = compare_files(a, b, profile=gm_profile)
    assert diff["regression_detected"] is True
    assert "AS-PEAK-002" in diff["findings"]["only_in_b"]
    assert "AS-PEAK-001" in diff["findings"]["only_in_b"]  # true peak também cruza
    assert diff["regression_reasons"]


def test_identical_files_no_regression(tmp_path, gm_profile):
    x = _sine(440)
    a = _write_wav(tmp_path, "same_a.wav", x)
    b = _write_wav(tmp_path, "same_b.wav", x)
    diff = compare_files(a, b, profile=gm_profile)
    assert diff["regression_detected"] is False
    assert diff["findings"]["only_in_b"] == []
    assert diff["findings"]["only_in_a"] == []
    for v in diff["deltas"].values():
        assert abs(v) < 1e-6


def test_resolved_defect_is_not_regression(tmp_path, gm_profile):
    """Regressão é só em B: defeito que existe em A e some em B não é regressão."""
    t = np.arange(int(SR * 2)) / SR
    clipped = np.clip(1.6 * np.sin(2 * np.pi * 440 * t), -1.0, 1.0)
    a = _write_wav(tmp_path, "was_clipped.wav", clipped)
    b = _write_wav(tmp_path, "now_clean.wav", _sine(440))
    diff = compare_files(a, b, profile=gm_profile)
    assert diff["regression_detected"] is False
    assert diff["findings"]["only_in_a"]  # defeito resolvido aparece em only_in_a


def test_cli_compare_end_to_end(tmp_path, gm_profile):
    from audio_suite.cli import main as cli_main

    a = _write_wav(tmp_path, "cli_a.wav", _sine(440))
    b = _write_wav(tmp_path, "cli_b.wav", _sine(2000))
    out = tmp_path / "diff.json"
    rc = cli_main(
        ["compare", a, b, "--profile", str(ROOT / "tests" / "golden" / "gm_profile.yaml"), "-o", str(out)]
    )
    assert rc == 0
    payload = json.loads(out.read_text())
    assert payload["schema"] == "audio-suite/compare@1"

    # com clipping novo + --fail-on-regression → exit 1
    t = np.arange(int(SR * 2)) / SR
    clipped = _write_wav(tmp_path, "cli_clipped.wav", np.clip(1.6 * np.sin(2 * np.pi * 440 * t), -1, 1))
    rc2 = cli_main(
        [
            "compare",
            a,
            clipped,
            "--profile",
            str(ROOT / "tests" / "golden" / "gm_profile.yaml"),
            "--fail-on-regression",
        ]
    )
    assert rc2 == 1
