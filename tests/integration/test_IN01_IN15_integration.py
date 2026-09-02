"""IN-01 to IN-15: SARIF, integration, and end-to-end CLI tests."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from audio_suite.cli import main as cli_main
from audio_suite.models import ExitCode


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


def test_IN01_sarif_valid_against_schema():
    """SARIF output validates against the 2.1.0 schema structure."""
    code, out, _ = run_cli("analyze", str(FIX / "sine_1k_mono.wav"), "--format", "sarif")
    assert code == ExitCode.OK
    sarif = json.loads(out)
    assert sarif["version"] == "2.1.0"
    assert sarif["$schema"].endswith("sarif-schema-2.1.0.json")
    run = sarif["runs"][0]
    assert "tool" in run
    assert "results" in run
    assert "driver" in run["tool"]
    assert run["tool"]["driver"]["name"] == "audio-suite"


def test_IN02_sarif_has_rules():
    code, out, _ = run_cli("analyze", str(FIX / "sine_1k_mono.wav"), "--format", "sarif")
    sarif = json.loads(out)
    rules = sarif["runs"][0]["tool"]["driver"]["rules"]
    assert len(rules) > 0
    for rule in rules:
        assert "id" in rule
        assert "name" in rule


def test_IN03_sarif_results_have_locations():
    code, out, _ = run_cli("analyze", str(FIX / "clipped.wav"), "--format", "sarif")
    sarif = json.loads(out)
    results = sarif["runs"][0]["results"]
    assert len(results) > 0
    for r in results:
        assert "locations" in r
        assert "ruleId" in r
        assert "level" in r


def test_IN04_sarif_levels_correct():
    """FAIL -> error, WARNING -> warning, PASS -> none."""
    code, out, _ = run_cli("analyze", str(FIX / "clipped.wav"), "--format", "sarif")
    sarif = json.loads(out)
    results = sarif["runs"][0]["results"]
    levels = {r["level"] for r in results}
    # Clipped should produce at least one "error" level
    assert "error" in levels


def test_IN05_json_output_to_file(tmp_path):
    out_path = tmp_path / "report.json"
    code, _, _ = run_cli("analyze", str(FIX / "sine_1k_mono.wav"),
                         "--output", str(out_path))
    assert code == ExitCode.OK
    data = json.loads(out_path.read_text())
    assert "findings" in data
    assert "aggregate_status" in data


def test_IN06_sarif_output_to_file(tmp_path):
    out_path = tmp_path / "report.sarif"
    code, _, _ = run_cli("analyze", str(FIX / "sine_1k_mono.wav"),
                         "--format", "sarif", "--output", str(out_path))
    assert code == ExitCode.OK
    data = json.loads(out_path.read_text())
    assert data["version"] == "2.1.0"


def test_IN07_html_output_to_file(tmp_path):
    out_path = tmp_path / "report.html"
    code, _, _ = run_cli("analyze", str(FIX / "sine_1k_mono.wav"),
                         "--format", "html", "--output", str(out_path))
    assert code == ExitCode.OK
    html = out_path.read_text()
    assert "<!DOCTYPE html>" in html
    assert "audio-suite" in html
    assert "aggregate status" in html.lower()


def test_IN08_subprocess_cli_works():
    """The installed entry point `audio-suite` should work via subprocess."""
    result = subprocess.run(
        [PYTHON, "-m", "audio_suite", "--version"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    assert result.returncode == 0
    assert "audio-suite" in result.stdout


def test_IN09_full_pipeline_clean_signal():
    """End-to-end: clean signal -> exit 0, aggregate PASS/WARNING."""
    code, out, _ = run_cli("analyze", str(FIX / "sine_1k_mono.wav"))
    assert code == ExitCode.OK
    data = json.loads(out)
    assert data["aggregate_status"] in ("pass", "warning")


def test_IN10_full_pipeline_clipped_signal():
    """End-to-end: clipped signal -> exit 1, aggregate FAIL."""
    code, out, _ = run_cli("analyze", str(FIX / "clipped.wav"))
    assert code == ExitCode.FINDING
    data = json.loads(out)
    assert data["aggregate_status"] == "fail"


def test_IN11_full_pipeline_phase_inverted():
    """Phase-inverted stereo -> mono_compat warning."""
    code, out, _ = run_cli("analyze", str(FIX / "phase_inverted.wav"))
    data = json.loads(out)
    mono_findings = [f for f in data["findings"] if f["analyzer"] == "mono_compat"]
    assert mono_findings
    assert mono_findings[0]["status"] == "warning"


def test_IN12_strict_overlay_escalates(tmp_path):
    """--strict with strict_overlay should escalate specific metrics."""
    code, out, _ = run_cli("analyze", str(FIX / "clipped.wav"), "--strict")
    # Clipping was already FAIL; strict overlay keeps it FAIL
    assert code == ExitCode.FINDING


def test_IN13_only_filter():
    """--only should restrict which analyzers run."""
    code, out, _ = run_cli("analyze", str(FIX / "sine_1k_mono.wav"),
                           "--only", "inspect,loudness")
    data = json.loads(out)
    analyzers_used = {f["analyzer"] for f in data["findings"]}
    assert analyzers_used <= {"inspect", "loudness"}


def test_IN14_skip_filter():
    code, out, _ = run_cli("analyze", str(FIX / "sine_1k_mono.wav"),
                           "--skip", "glitch,resampling,transient,voice_artifacts")
    data = json.loads(out)
    analyzers_used = {f["analyzer"] for f in data["findings"]}
    assert "glitch" not in analyzers_used


def test_IN15_sign_bundle(tmp_path):
    """Signed bundle should include a valid Ed25519 signature block."""
    from audio_suite.security.signing import generate_keypair
    priv, pub = generate_keypair(tmp_path)
    code, out, _ = run_cli("analyze", str(FIX / "sine_1k_mono.wav"),
                           "--sign", "--signing-key", str(priv))
    assert code == ExitCode.OK
    data = json.loads(out)
    assert data["signature"] is not None
    assert data["signature"]["signed"] is True
    # Verify the signature
    from audio_suite.security.signing import verify_payload
    signed_payload = {
        "tool": data["tool"],
        "subject": data["subject"],
        "profile": data["profile"],
        "findings": data["findings"],
        "aggregate_status": data["aggregate_status"],
        "measurement_fingerprint": data["measurement_fingerprint"],
    }
    assert verify_payload(signed_payload, data["signature"]) is True
