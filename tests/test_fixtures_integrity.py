"""Tests: fixtures integrity (S2)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def test_fixtures_dir_exists():
    assert FIXTURES_DIR.exists()


def test_index_json_exists():
    assert (FIXTURES_DIR / "index.json").exists()


def test_expected_fixtures_present():
    """Verifica que todos os 10 fixtures esperados estão presentes."""
    index = json.loads((FIXTURES_DIR / "index.json").read_text())
    expected = {
        "clean_pass", "clipped_sine", "true_peak_over", "lufs_too_hot",
        "inverted_polarity", "mono_when_stereo_req", "metadata_with_email",
        "silence_5s", "rights_nc_commercial", "provenance_gap",
    }
    actual = set(index.get("fixtures", []))
    missing = expected - actual
    assert not missing, f"Fixtures faltando: {missing}"


@pytest.mark.parametrize("fixture_name", [
    "clean_pass", "clipped_sine", "true_peak_over", "lufs_too_hot",
    "inverted_polarity", "mono_when_stereo_req", "metadata_with_email",
    "silence_5s", "rights_nc_commercial", "provenance_gap",
])
def test_fixture_has_expected_json(fixture_name):
    """Cada fixture deve ter expected.json com hash do arquivo."""
    fixture_dir = FIXTURES_DIR / fixture_name
    if not fixture_dir.exists():
        pytest.skip(f"Fixture {fixture_name} não gerado (rode scripts/generate_fixtures.py)")
    expected_path = fixture_dir / "expected.json"
    assert expected_path.exists(), f"expected.json ausente em {fixture_dir}"
    expected = json.loads(expected_path.read_text())
    assert "fixture_sha256" in expected
    assert "expected_decision" in expected


@pytest.mark.parametrize("fixture_name", [
    "clean_pass", "clipped_sine", "true_peak_over", "lufs_too_hot",
    "inverted_polarity", "mono_when_stereo_req", "metadata_with_email",
    "silence_5s",
])
def test_audio_fixture_has_wav(fixture_name):
    fixture_dir = FIXTURES_DIR / fixture_name
    if not fixture_dir.exists():
        pytest.skip(f"Fixture {fixture_name} não gerado")
    wav = fixture_dir / "audio.wav"
    assert wav.exists(), f"audio.wav ausente em {fixture_dir}"


@pytest.mark.parametrize("fixture_name", [
    "clean_pass", "clipped_sine", "true_peak_over", "lufs_too_hot",
    "inverted_polarity", "mono_when_stereo_req", "metadata_with_email",
    "silence_5s",
])
def test_fixture_hash_matches_expected(fixture_name):
    """S2: hash do arquivo deve corresponder ao hash declarado."""
    import hashlib
    fixture_dir = FIXTURES_DIR / fixture_name
    if not fixture_dir.exists():
        pytest.skip(f"Fixture {fixture_name} não gerado")
    wav = fixture_dir / "audio.wav"
    expected = json.loads((fixture_dir / "expected.json").read_text())
    h = hashlib.sha256()
    with open(wav, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    assert h.hexdigest() == expected["fixture_sha256"], (
        f"Hash do arquivo {wav} não corresponde ao declarado em expected.json. "
        "Fixture foi corrompido ou regravado sem atualizar o expected."
    )


def test_fixtures_synthetic_license():
    """S2: todos os fixtures são sintéticos (sem áudio de terceiros)."""
    index = json.loads((FIXTURES_DIR / "index.json").read_text())
    assert "synthetic" in index.get("license", "").lower()
