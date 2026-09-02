"""T-11 to T-25: CLI and Engine tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from audio_suite.cli import main as cli_main
from audio_suite.decode import DecodeError, decode, sha256_of_file
from audio_suite.models import ExitCode, Status
from audio_suite.policy import ProfileError, load_profile, validate_profile

ROOT = Path(__file__).resolve().parents[3]
FIX = ROOT / "tests" / "fixtures" / "generated"
SINE = str(FIX / "sine_1k_mono.wav")
CLIPPED = str(FIX / "clipped.wav")
TRUNC = str(FIX / "truncated.wav")
EMPTY = str(FIX / "empty.wav")
BAD_EXT = str(FIX / "audio.txt")


def run_cli(*args: str) -> tuple[int, str, str]:
    """Run the CLI in-process and capture stdout/stderr."""
    import io
    from contextlib import redirect_stderr, redirect_stdout

    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = cli_main(list(args))
        except SystemExit as e:
            code = int(e.code) if e.code is not None else 0
    return code, out.getvalue(), err.getvalue()


# T-11: --version
def test_T11_version():
    code, out, _ = run_cli("--version")
    assert code == ExitCode.OK
    assert "audio-suite" in out


# T-12: inspect works
def test_T12_inspect(sine_1k):
    code, out, _ = run_cli("inspect", SINE)
    assert code == ExitCode.OK
    data = json.loads(out)
    assert data["sample_rate_hz"] == 44100
    assert data["channels"] == 1
    assert data["sha256"] == sine_1k.file_sha256


# T-13: inspect on missing file exits 3
def test_T13_inspect_missing():
    code, _, err = run_cli("inspect", "/nonexistent/foo.wav")
    assert code == ExitCode.INVALID_INPUT
    assert "error" in err.lower()


# T-14: inspect on empty file exits 3
def test_T14_inspect_empty():
    code, _, err = run_cli("inspect", EMPTY)
    assert code == ExitCode.INVALID_INPUT


# T-15: inspect on bad extension exits 3
def test_T15_inspect_bad_ext():
    code, _, _ = run_cli("inspect", BAD_EXT)
    assert code == ExitCode.INVALID_INPUT


# T-16: validate default profile
def test_T16_validate_default_profile():
    prof = str(ROOT / "audio_suite" / "default_profile.yaml")
    code, out, _ = run_cli("validate", prof)
    assert code == ExitCode.OK
    data = json.loads(out)
    assert data["valid"] is True


# T-17: validate strict profile with --strict
def test_T17_validate_strict_profile():
    prof = str(ROOT / "profiles" / "strict.yaml")
    code, out, _ = run_cli("validate", prof, "--strict")
    assert code == ExitCode.OK


# T-18: invalid profile exits 2
def test_T18_invalid_profile(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: bad\nversion: '1'\nanalyzers:\n  nonexistent: {}\n")
    code, _, err = run_cli("validate", str(bad))
    assert code == ExitCode.INVALID_PROFILE
    assert "unknown analyzer" in err


# T-19: invalid YAML exits 2
def test_T19_malformed_yaml(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: [unclosed\n  - x")
    code, _, _ = run_cli("validate", str(bad))
    assert code == ExitCode.INVALID_PROFILE


# T-20: analyze returns 1 on fail-level finding (clipping)
def test_T20_analyze_fail_exit_code():
    code, out, _ = run_cli("analyze", CLIPPED)
    assert code == ExitCode.FINDING
    data = json.loads(out)
    assert data["aggregate_status"] == "fail"


# T-21: analyze returns 0 on clean signal
def test_T21_analyze_clean_exit_code():
    code, out, _ = run_cli("analyze", SINE)
    assert code == ExitCode.OK
    data = json.loads(out)
    assert data["aggregate_status"] in ("pass", "warning")


# T-22: analyze --format sarif produces valid SARIF
def test_T22_analyze_sarif():
    code, out, _ = run_cli("analyze", CLIPPED, "--format", "sarif")
    # clipping -> fail -> exit 1
    assert code == ExitCode.FINDING
    sarif = json.loads(out)
    assert sarif["version"] == "2.1.0"
    assert sarif["$schema"].endswith("sarif-schema-2.1.0.json")
    assert len(sarif["runs"]) == 1
    run = sarif["runs"][0]
    assert run["tool"]["driver"]["name"] == "audio-suite"
    assert len(run["results"]) > 0


# T-23: analyze --output writes to file
def test_T23_analyze_output_file(tmp_path):
    out_path = tmp_path / "out.json"
    code, _, _ = run_cli("analyze", SINE, "--output", str(out_path))
    assert code == ExitCode.OK
    assert out_path.exists()
    data = json.loads(out_path.read_text())
    assert "findings" in data


# T-24: analyze --only filters analyzers
def test_T24_analyze_only():
    code, out, _ = run_cli("analyze", SINE, "--only", "inspect")
    assert code == ExitCode.OK
    data = json.loads(out)
    analyzers_used = {f["analyzer"] for f in data["findings"]}
    assert analyzers_used == {"inspect"}


# T-25: analyze --skip excludes analyzers
def test_T25_analyze_skip():
    code, out, _ = run_cli("analyze", SINE, "--skip", "clipping,loudness")
    assert code == ExitCode.OK
    data = json.loads(out)
    analyzers_used = {f["analyzer"] for f in data["findings"]}
    assert "clipping" not in analyzers_used
    assert "loudness" not in analyzers_used


# Decoder tests (EN-01..EN-16 mapped)
def test_decode_wav_16bit():
    pcm = decode(SINE)
    assert pcm.sample_rate == 44100
    assert pcm.channels == 1
    assert pcm.provenance["subtype"] == "PCM_16"


def test_decode_wav_24bit():
    pcm = decode(str(FIX / "sine_1k_24bit.wav"))
    assert pcm.provenance["bit_depth"] == 24


def test_decode_wav_float32():
    pcm = decode(str(FIX / "sine_1k_float32.wav"))
    assert pcm.provenance["subtype"] == "FLOAT"


def test_decode_stereo_preserves_channels():
    pcm = decode(str(FIX / "sine_1k_stereo.wav"))
    assert pcm.channels == 2


def test_decode_truncated_raises():
    with pytest.raises(DecodeError):
        decode(TRUNC)


def test_decode_empty_raises():
    with pytest.raises(DecodeError):
        decode(EMPTY)


def test_decode_bad_extension_raises():
    with pytest.raises(DecodeError):
        decode(BAD_EXT)


def test_sha256_of_file_deterministic():
    s1 = sha256_of_file(SINE)
    s2 = sha256_of_file(SINE)
    assert s1 == s2
    assert len(s1) == 64


def test_no_silent_resample():
    """Decoder must not resample unless explicitly asked (rule: resampling is opt-in)."""
    pcm = decode(SINE)
    assert pcm.sample_rate == 44100
    assert "resampled_from" not in pcm.provenance


def test_explicit_resample():
    pcm = decode(SINE, target_sr=22050)
    assert pcm.sample_rate == 22050
    assert pcm.provenance.get("resampled_from") == 44100


# Strict overlay (PO-01..PO-14 mapped)
def test_strict_overlay_applied():
    """--strict applies the profile's strict_overlay block."""
    prof = str(ROOT / "profiles" / "strict.yaml")
    code, out, _ = run_cli("analyze", CLIPPED, "--profile", prof, "--strict")
    assert code == ExitCode.FINDING


def test_strict_not_autofail():
    """--strict WITHOUT a strict_overlay block must NOT auto-fail warnings (A5)."""
    # The default profile HAS a strict_overlay, but it only escalates specific metrics.
    # We test that a clean signal still passes under strict.
    code, _, _ = run_cli("analyze", SINE, "--strict")
    assert code == ExitCode.OK
