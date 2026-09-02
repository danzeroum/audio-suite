"""ENG-12: DRn meter tests + PROF-07: compliance command tests."""

from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO

import numpy as np
import pytest

from audio_suite.analyzers.drn import DrnAnalyzer, compute_drn
from audio_suite.models import PCM, Status

SR = 44100


def make_pcm(n_seconds=5.0, sr=SR, amp=0.3):
    t = np.arange(int(sr * n_seconds)) / sr
    x = (amp * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    return PCM(samples=x.reshape(1, -1), sample_rate=sr)


# DRn tests
def test_drn_constant_signal_low():
    """Constant-amplitude signal should have low DRn."""
    pcm = make_pcm(5.0, amp=0.3)
    dr = compute_drn(pcm)
    # Pure sine has DR ~3 dB (peak/RMS = 1.414 → 3 dB)
    assert 0 < dr < 10, f"Expected low DR for sine, got {dr}"


def test_drn_dynamic_signal_higher():
    """Signal with wide dynamics should have higher DRn."""
    sr = SR
    n = sr * 10
    t = np.arange(n) / sr
    # First 5s quiet, last 5s loud
    x = np.zeros(n, dtype=np.float64)
    x[: n // 2] = 0.01 * np.sin(2 * np.pi * 440 * t[: n // 2])
    x[n // 2 :] = 0.9 * np.sin(2 * np.pi * 440 * t[n // 2 :])
    pcm = PCM(samples=x.reshape(1, -1).astype(np.float32), sample_rate=sr)
    dr = compute_drn(pcm)
    # Dynamic signal should have higher DR than constant
    constant_dr = compute_drn(make_pcm(5.0, amp=0.3))
    assert dr > constant_dr, f"Dynamic DR {dr} should > constant DR {constant_dr}"


def test_drn_applicability_short():
    a = DrnAnalyzer()
    from audio_suite.models import Profile

    profile = Profile(name="t", version="1", analyzers={})
    pcm = make_pcm(1.0)  # too short
    assert a.applicable(pcm, profile) is False


def test_drn_returns_pass():
    """DRn is a descriptor — status always PASS unless min set."""
    a = DrnAnalyzer()
    pcm = make_pcm(5.0)
    findings = a.analyze(pcm, {})
    f = findings[0]
    assert f.status == Status.PASS
    assert f.unit == "dB"


def test_drn_min_threshold_warning():
    """If dr_min_db is set and DR below it, should warn."""
    a = DrnAnalyzer()
    pcm = make_pcm(5.0, amp=0.3)
    findings = a.analyze(pcm, {"dr_min_db": 20.0})
    f = findings[0]
    assert f.status == Status.WARNING


def test_drn_deterministic():
    pcm = make_pcm(5.0)
    dr1 = compute_drn(pcm)
    dr2 = compute_drn(pcm)
    assert dr1 == dr2


# Compliance command tests
def test_compliance_ebu():
    from audio_suite.cli import main

    out = StringIO()
    with redirect_stdout(out):
        try:
            main(["compliance", "tests/fixtures/generated/sine_1k_mono.wav", "--target", "ebu"])
        except SystemExit:
            pass
    data = json.loads(out.getvalue())
    assert data["target"] == "ebu"
    assert data["spec_name"] == "EBU R128"
    assert "compliance" in data
    assert "delta" in data


def test_compliance_spotify():
    from audio_suite.cli import main

    out = StringIO()
    with redirect_stdout(out):
        try:
            main(["compliance", "tests/fixtures/generated/sine_1k_mono.wav", "--target", "spotify"])
        except SystemExit:
            pass
    data = json.loads(out.getvalue())
    assert data["target"] == "spotify"
    assert data["requirements"]["lufs_target"] == -14.0


def test_compliance_all_targets():
    from audio_suite.cli import main

    for target in ["ebu", "spotify", "podcast", "atsc", "cine"]:
        out = StringIO()
        with redirect_stdout(out):
            try:
                main(["compliance", "tests/fixtures/generated/sine_1k_mono.wav", "--target", target])
            except SystemExit:
                pass
        data = json.loads(out.getvalue())
        assert data["target"] == target
        assert "compliance" in data
