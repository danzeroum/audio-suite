"""T-91 to T-110: Integration, Security & Governance end-to-end.

These tests tie everything together: full pipeline runs, signed bundles,
tamper detection, SARIF validity, profile governance, and CI smoke tests.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from audio_suite.cli import main as cli_main
from audio_suite.models import ExitCode
from audio_suite.policy import load_profile, validate_profile

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "fixtures" / "generated"
PYTHON = sys.executable


def run_cli(*args: str) -> tuple[int, str, str]:
    import io
    from contextlib import redirect_stderr, redirect_stdout

    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = cli_main(list(args))
        except SystemExit as e:
            code = int(e.code) if e.code is not None else 0
    return code, out.getvalue(), err.getvalue()


# T-91: CI smoke test — `audio-suite --version` works
def test_T91_ci_version_smoke():
    result = subprocess.run(
        [PYTHON, "-m", "audio_suite", "--version"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 0
    assert "audio-suite" in result.stdout


# T-92: CI smoke test — `audio-suite inspect` works
def test_T92_ci_inspect_smoke():
    result = subprocess.run(
        [PYTHON, "-m", "audio_suite", "inspect", str(FIX / "sine_1k_mono.wav")],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["sample_rate_hz"] == 44100


# T-93: CI smoke test — full analyze on clean signal
def test_T93_ci_analyze_clean_smoke():
    result = subprocess.run(
        [PYTHON, "-m", "audio_suite", "analyze", str(FIX / "sine_1k_mono.wav")],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["aggregate_status"] in ("pass", "warning")


# T-94: CI smoke test — full analyze on clipped signal (exit 1)
def test_T94_ci_analyze_clipped_smoke():
    result = subprocess.run(
        [PYTHON, "-m", "audio_suite", "analyze", str(FIX / "clipped.wav")],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["aggregate_status"] == "fail"


# T-95: SARIF importable into GitHub (validates against schema structure)
def test_T95_sarif_github_compatible():
    code, out, _ = run_cli("analyze", str(FIX / "clipped.wav"), "--format", "sarif")
    sarif = json.loads(out)
    # Required fields for GitHub code scanning
    assert sarif["version"] == "2.1.0"
    run = sarif["runs"][0]
    assert "tool" in run
    assert "results" in run
    for r in run["results"]:
        assert "ruleId" in r
        assert "level" in r
        assert "message" in r
        assert "locations" in r


# T-96: Ed25519 sign + verify roundtrip
def test_T96_sign_verify_roundtrip(tmp_path):
    from audio_suite.security.signing import generate_keypair, sign_payload, verify_payload

    priv, pub = generate_keypair(tmp_path)
    payload = {"tool": "audio-suite", "findings": [{"a": 1}]}
    sig = sign_payload(payload, key_path=str(priv))
    assert verify_payload(payload, sig) is True


# T-97: Tamper detection on signed bundle
def test_T97_bundle_tamper_detection(tmp_path):
    from audio_suite.security.signing import generate_keypair, sign_payload, verify_payload

    priv, pub = generate_keypair(tmp_path)
    payload = {"a": 1, "b": 2}
    sig = sign_payload(payload, key_path=str(priv))
    # Tamper
    tampered = {"a": 1, "b": 3}
    assert verify_payload(tampered, sig) is False


# T-98: Profile governance — data_classification enforced
def test_T98_data_classification_validated():
    with pytest.raises(Exception, match="data_classification"):
        validate_profile(
            {
                "name": "t",
                "version": "1",
                "analyzers": {},
                "data_classification": "top-secret",  # invalid
            }
        )


# T-99: Profile governance — retention_policy is a mapping
def test_T99_retention_policy_validated():
    with pytest.raises(Exception, match="retention_policy"):
        validate_profile(
            {
                "name": "t",
                "version": "1",
                "analyzers": {},
                "retention_policy": "should-be-dict",
            }
        )


# T-100: Default profile loads successfully
def test_T100_default_profile_loads():
    prof = load_profile(ROOT / "audio_suite" / "default_profile.yaml")
    assert prof.name == "default"
    assert "loudness" in prof.analyzers
    assert "clipping" in prof.analyzers


# T-101: Strict profile loads successfully
def test_T101_strict_profile_loads():
    prof = load_profile(ROOT / "profiles" / "strict.yaml", strict=True)
    assert prof.is_strict() is True
    assert prof.data_classification == "confidential"


# T-102: PII redaction applied to bundle
def test_T102_pii_redaction_in_bundle():
    from audio_suite.security.pii import redact_pii

    fake_bundle = {
        "subject": {"source_path": "/home/john/audio/secret.wav"},
        "findings": [{"email": "user@foo.com"}],
    }
    red = redact_pii(fake_bundle)
    assert "[REDACTED:userpath]" in red["subject"]["source_path"]
    assert red["findings"][0]["email"] == "[REDACTED:email]"


# T-103: Manifest of fixtures is consistent
def test_T103_fixture_manifest_consistent():
    manifest = json.loads((FIX / "manifest.json").read_text())
    for name, meta in manifest.items():
        path = FIX / name
        if path.exists() and path.stat().st_size > 0:
            # Verify sha256 matches
            from audio_suite.decode import sha256_of_file

            actual = sha256_of_file(path)
            assert actual == meta["sha256"], f"sha mismatch for {name}"


# T-104: Analyzer contract — every analyzer has schema, applicable, analyze
def test_T104_analyzer_contract_complete():
    from audio_suite.analyzers import all_analyzers

    for aid, a in all_analyzers().items():
        assert callable(a.applicable)
        assert callable(a.analyze)
        assert isinstance(a.profile_schema(), dict)


# T-105: Exit codes are correct per spec (0, 1, 2, 3, 64)
def test_T105_exit_codes():
    assert ExitCode.OK == 0
    assert ExitCode.FINDING == 1
    assert ExitCode.INVALID_PROFILE == 2
    assert ExitCode.INVALID_INPUT == 3
    assert ExitCode.USAGE == 64


# T-106: Usage error exits 64
def test_T106_usage_error():
    code, _, _ = run_cli()  # no args
    assert code == ExitCode.USAGE


# T-107: Invalid input exits 3
def test_T107_invalid_input():
    code, _, _ = run_cli("inspect", "/nonexistent.wav")
    assert code == ExitCode.INVALID_INPUT


# T-108: Invalid profile exits 2
def test_T108_invalid_profile(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: t\nversion: '1'\nanalyzers:\n  nope: {}\n")
    code, _, _ = run_cli("validate", str(bad))
    assert code == ExitCode.INVALID_PROFILE


# T-109: Full signed bundle pipeline end-to-end
def test_T109_full_signed_pipeline(tmp_path):
    from audio_suite.security.signing import generate_keypair, verify_payload

    priv, pub = generate_keypair(tmp_path)
    out_path = tmp_path / "signed.json"
    code, _, _ = run_cli(
        "analyze",
        str(FIX / "sine_1k_mono.wav"),
        "--sign",
        "--signing-key",
        str(priv),
        "--output",
        str(out_path),
    )
    assert code == ExitCode.OK
    data = json.loads(out_path.read_text())
    assert data["signature"]["signed"] is True
    # Verify
    signed_payload = {
        "tool": data["tool"],
        "subject": data["subject"],
        "profile": data["profile"],
        "findings": data["findings"],
        "aggregate_status": data["aggregate_status"],
        "measurement_fingerprint": data["measurement_fingerprint"],
    }
    assert verify_payload(signed_payload, data["signature"]) is True


# T-110: Aggregate status precedence is enforced end-to-end
def test_T110_aggregate_precedence_e2e():
    """A clipped signal (FAIL) must produce aggregate=FAIL even if other
    analyzers return PASS."""
    code, out, _ = run_cli("analyze", str(FIX / "clipped.wav"))
    assert code == ExitCode.FINDING
    data = json.loads(out)
    assert data["aggregate_status"] == "fail"
    # Verify at least one finding is FAIL and the aggregate reflects it
    statuses = [f["status"] for f in data["findings"]]
    assert "fail" in statuses
    assert data["aggregate_status"] == "fail"
