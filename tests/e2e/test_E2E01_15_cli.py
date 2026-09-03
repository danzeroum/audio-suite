"""TEST-02: End-to-end tests — CLI, bundle, Docker, Action."""

from __future__ import annotations

import json
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

import pytest

from audio_suite.cli import main as cli_main
from audio_suite.models import ExitCode

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "fixtures" / "generated"
PYTHON = sys.executable


def run_cli(*args):
    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = cli_main(list(args))
        except SystemExit as e:
            code = int(e.code) if e.code else 0
    return code, out.getvalue(), err.getvalue()


# E2E-01: Full CLI pipeline — clean signal → exit 0
def test_E2E01_clean_signal_exit_0():
    code, out, _ = run_cli("analyze", str(FIX / "sine_1k_mono.wav"))
    assert code == ExitCode.OK
    data = json.loads(out)
    assert data["aggregate_status"] in ("pass", "warning")


# E2E-02: Full CLI pipeline — clipped signal → exit 1
def test_E2E02_clipped_signal_exit_1():
    code, out, _ = run_cli("analyze", str(FIX / "clipped.wav"))
    assert code == ExitCode.FINDING
    data = json.loads(out)
    assert data["aggregate_status"] == "fail"


# E2E-03: SARIF output is valid
def test_E2E03_sarif_output():
    code, out, _ = run_cli("analyze", str(FIX / "sine_1k_mono.wav"), "--format", "sarif")
    assert code == ExitCode.OK
    sarif = json.loads(out)
    assert sarif["version"] == "2.1.0"


# E2E-04: HTML output
def test_E2E04_html_output(tmp_path):
    out_path = tmp_path / "report.html"
    code, _, _ = run_cli(
        "analyze", str(FIX / "sine_1k_mono.wav"), "--format", "html", "--output", str(out_path)
    )
    assert code == ExitCode.OK
    assert "<!DOCTYPE html>" in out_path.read_text()


# E2E-05: CSV output
def test_E2E05_csv_output():
    code, out, _ = run_cli("analyze", str(FIX / "sine_1k_mono.wav"), "--format", "csv")
    assert code == ExitCode.OK
    assert "analyzer" in out


# E2E-06: Signed bundle → verify
def test_E2E06_signed_bundle(tmp_path):
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
    payload = {
        "tool": data["tool"],
        "subject": data["subject"],
        "profile": data["profile"],
        "findings": data["findings"],
        "aggregate_status": data["aggregate_status"],
        "measurement_fingerprint": data["measurement_fingerprint"],
    }
    assert verify_payload(payload, data["signature"]) is True


# E2E-07: Profile validation → exit 2 on invalid
def test_E2E07_invalid_profile(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: bad\nversion: '1'\nanalyzers:\n  nope: {}\n")
    code, _, _ = run_cli("validate", str(bad))
    assert code == ExitCode.INVALID_PROFILE


# E2E-08: Missing file → exit 3
def test_E2E08_missing_file():
    code, _, _ = run_cli("inspect", "/nonexistent.wav")
    assert code == ExitCode.INVALID_INPUT


# E2E-09: Subprocess works
def test_E2E09_subprocess():
    result = subprocess.run(
        [PYTHON, "-m", "audio_suite", "--version"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 0
    assert "audio-suite" in result.stdout


# E2E-10: --only filter works
def test_E2E10_only_filter():
    code, out, _ = run_cli("analyze", str(FIX / "sine_1k_mono.wav"), "--only", "inspect")
    assert code == ExitCode.OK
    data = json.loads(out)
    analyzers = {f["analyzer"] for f in data["findings"]}
    assert analyzers == {"inspect"}


# E2E-11: --skip filter works
def test_E2E11_skip_filter():
    code, out, _ = run_cli("analyze", str(FIX / "sine_1k_mono.wav"), "--skip", "clipping,loudness,glitch")
    assert code == ExitCode.OK
    data = json.loads(out)
    analyzers = {f["analyzer"] for f in data["findings"]}
    assert "clipping" not in analyzers


# E2E-12: Strict mode doesn't auto-fail clean signal
def test_E2E12_strict_clean():
    code, _, _ = run_cli("analyze", str(FIX / "sine_1k_mono.wav"), "--strict")
    assert code == ExitCode.OK


# E2E-13: Self-check command
def test_E2E13_self_check():
    code, out, _ = run_cli("self-check")
    assert code == ExitCode.OK
    data = json.loads(out)
    assert data["overall"] is True


# E2E-14: Audit log append + verify
def test_E2E14_audit(tmp_path):
    log_path = tmp_path / "audit.log"
    code, out, _ = run_cli("audit", "--log", str(log_path), "--action", "test", "--subject", "file.wav")
    assert code == ExitCode.OK
    # Verify chain
    code2, out2, _ = run_cli("audit", "--log", str(log_path), "--action", "v", "--subject", "v", "--verify")
    assert code2 == ExitCode.OK
    data = json.loads(out2)
    assert data["valid"] is True


# E2E-15: Custom profile works
def test_E2E15_custom_profile():
    prof = str(ROOT / "profiles" / "podcast.yaml")
    code, out, _ = run_cli("analyze", str(FIX / "sine_1k_mono.wav"), "--profile", prof)
    assert code == ExitCode.OK
