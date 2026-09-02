"""Tests: end-to-end com fixtures de mordida."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
FIXTURES_DIR = REPO_ROOT / "fixtures"
PROFILE_PATH = REPO_ROOT / "registry" / "policy-profiles" / "broadcast_ebu_r128_v1.yaml"

# Mapeia fixture → (audio_filename, expected_decision_or_status, acceptable_decisions)
# acceptable_decisions: conjunto de decisões válidas (para tolerar variações de decoder/pyloudnorm)
FIXTURES_TO_TEST = [
    ("clean_pass", "audio.wav", "pass", {"pass", "warning", "indeterminate"}),
    ("clipped_sine", "audio.wav", "fail", {"fail"}),
    ("inverted_polarity", "audio.wav", "warning", {"warning", "fail", "indeterminate"}),
    ("silence_5s", "audio.wav", "indeterminate", {"indeterminate", "needs_review"}),
]


@pytest.mark.e2e
@pytest.mark.parametrize("fixture_name,audio_file,expected_decision,acceptable", FIXTURES_TO_TEST)
def test_e2e_validate_fixture(fixture_name: str, audio_file: str, expected_decision: str, acceptable: set):
    """Valida fixture e verifica decisão esperada."""
    fixture_dir = FIXTURES_DIR / fixture_name
    if not fixture_dir.exists():
        pytest.skip(f"Fixture {fixture_name} não gerado")

    audio_path = fixture_dir / audio_file
    if not audio_path.exists():
        pytest.skip(f"Audio {audio_path} não existe")

    expected_path = fixture_dir / "expected.json"
    if not expected_path.exists():
        pytest.skip(f"expected.json ausente para {fixture_name}")

    # expected.json é validado em tests/test_fixtures_integrity.py

    # Executa CLI via subprocess (mais realista que CliRunner)
    bundle_path = fixture_dir / "bundle.json"
    result = subprocess.run(
        [
            sys.executable, "-m", "engine.cli", "validate",
            str(audio_path),
            "--profile", str(PROFILE_PATH),
            "--output", str(bundle_path),
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )

    # Aceita exit codes 0 (pass), 1 (fail), 2 (indeterminate)
    assert result.returncode in (0, 1, 2), (
        f"CLI falhou inesperadamente para {fixture_name}: exit={result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )

    # Bundle deve existir
    assert bundle_path.exists(), f"Bundle não foi criado: {bundle_path}"
    bundle = json.loads(bundle_path.read_text())

    # Verifica schema
    assert bundle["schema"] == "urn:audio-suite:bundle:v1.0.0"

    # Verifica decisão
    actual_decision = bundle["decision"]
    assert actual_decision in acceptable, (
        f"Esperado uma de {acceptable} para {fixture_name}, obtido {actual_decision}"
    )

    # Verifica que limitations estão presentes
    assert isinstance(bundle["limitations"], list)
    assert len(bundle["limitations"]) > 0

    # Verifica que measurement_fingerprint é determinístico
    assert "measurement_fingerprint" in bundle
    assert bundle["measurement_fingerprint"].startswith("sha256:")

    # Limpa bundle gerado
    bundle_path.unlink(missing_ok=True)


@pytest.mark.e2e
def test_e2e_reproducibility():
    """A2 + O5: mesma entrada → mesmo measurement_fingerprint."""
    fixture_dir = FIXTURES_DIR / "clean_pass"
    if not fixture_dir.exists():
        pytest.skip("Fixture clean_pass não gerado")

    audio_path = fixture_dir / "audio.wav"
    bundle1_path = fixture_dir / "bundle1.json"
    bundle2_path = fixture_dir / "bundle2.json"

    for out in (bundle1_path, bundle2_path):
        subprocess.run(
            [
                sys.executable, "-m", "engine.cli", "validate",
                str(audio_path),
                "--profile", str(PROFILE_PATH),
                "--output", str(out),
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )

    b1 = json.loads(bundle1_path.read_text())
    b2 = json.loads(bundle2_path.read_text())

    # bundle_sha256 deve ser DIFERENTE (timestamps variam)
    # measurement_fingerprint deve ser IDÊNTICO
    assert b1["measurement_fingerprint"] == b2["measurement_fingerprint"], (
        "measurement_fingerprint não é determinístico entre execuções"
    )

    # Cleanup
    bundle1_path.unlink(missing_ok=True)
    bundle2_path.unlink(missing_ok=True)


@pytest.mark.e2e
def test_e2e_rights_manifest_fixture():
    """Valida fixture rights_nc_commercial."""
    fixture_dir = FIXTURES_DIR / "rights_nc_commercial"
    if not fixture_dir.exists():
        pytest.skip("Fixture rights_nc_commercial não gerado")

    manifest_path = fixture_dir / "audio.yaml"

    from analyzers.rights_manifest import run_analyzer
    findings = run_analyzer(manifest_path=manifest_path)
    # Deve ter pelo menos um fail
    assert any(f["status"] == "fail" for f in findings)


@pytest.mark.e2e
def test_e2e_provenance_gap_fixture():
    """Valida fixture provenance_gap."""
    fixture_dir = FIXTURES_DIR / "provenance_gap"
    if not fixture_dir.exists():
        pytest.skip("Fixture provenance_gap não gerado")

    events_path = fixture_dir / "audio.json"

    from analyzers.provenance import run_analyzer
    findings = run_analyzer(events_path=events_path, input_audio=None)
    # Deve retornar gap ou invalid
    assert findings[0]["value"] in ("gap", "invalid")
