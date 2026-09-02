"""T-71 to T-80: Phase 4 multichannel + spatial analyzers.

Tests for:
  - MULTICHANNEL_LAYOUT (5.1/7.1 validation)
  - BINAURAL_COMPATIBILITY (lateral lows, phase)
  - SPATIAL_COHERENCE (channel correlation matrix)
  - GONIOMETER (Lissajous statistics)
"""

from __future__ import annotations

import numpy as np
import pytest

from audio_suite.analyzers import all_analyzers
from audio_suite.models import PCM, Profile, Status

SR = 44100


def profile_with(**analyzers) -> Profile:
    return Profile(name="t", version="1", analyzers=analyzers)


def make_51_pcm(n_seconds: float = 1.0, sr: int = SR) -> PCM:
    """Build a 5.1 multichannel PCM with LFE below 120 Hz."""
    n = int(sr * n_seconds)
    t = np.arange(n) / sr
    # L, R, C, LFE, Ls, Rs
    L = 0.3 * np.sin(2 * np.pi * 440 * t)
    R = 0.3 * np.sin(2 * np.pi * 440 * t)
    C = 0.3 * np.sin(2 * np.pi * 1000 * t)
    LFE = 0.5 * np.sin(2 * np.pi * 50 * t)  # 50 Hz — valid LFE content
    Ls = 0.2 * np.sin(2 * np.pi * 200 * t)
    Rs = 0.2 * np.sin(2 * np.pi * 200 * t)
    samples = np.stack([L, R, C, LFE, Ls, Rs]).astype(np.float32)
    return PCM(samples=samples, sample_rate=sr, channel_layout="5.1")


def make_51_no_lfe_pcm(n_seconds: float = 1.0, sr: int = SR) -> PCM:
    """5.1 where LFE channel has high-frequency content (anomaly)."""
    n = int(sr * n_seconds)
    t = np.arange(n) / sr
    L = 0.3 * np.sin(2 * np.pi * 440 * t)
    R = 0.3 * np.sin(2 * np.pi * 440 * t)
    C = 0.3 * np.sin(2 * np.pi * 1000 * t)
    LFE = 0.5 * np.sin(2 * np.pi * 5000 * t)  # 5 kHz in LFE — wrong
    Ls = 0.2 * np.sin(2 * np.pi * 200 * t)
    Rs = 0.2 * np.sin(2 * np.pi * 200 * t)
    samples = np.stack([L, R, C, LFE, Ls, Rs]).astype(np.float32)
    return PCM(samples=samples, sample_rate=sr, channel_layout="5.1")


# === MULTICHANNEL_LAYOUT ===


def test_multichannel_layout_51_valid():
    """A properly constructed 5.1 signal should pass."""
    a = all_analyzers()["multichannel_layout"]
    pcm = make_51_pcm()
    profile = profile_with()
    assert a.applicable(pcm, profile) is True
    findings = a.analyze(pcm, {})
    # Should have LFE, stereo compat, and center findings
    lfe_f = [f for f in findings if f.check_id == "multichannel_layout.lfe"][0]
    assert lfe_f.status == Status.PASS
    assert lfe_f.value > 80.0  # >80% energy below 120 Hz


def test_multichannel_layout_lfe_anomaly():
    """LFE with high-frequency content should warn."""
    a = all_analyzers()["multichannel_layout"]
    pcm = make_51_no_lfe_pcm()
    findings = a.analyze(pcm, {})
    lfe_f = [f for f in findings if f.check_id == "multichannel_layout.lfe"][0]
    assert lfe_f.status == Status.WARNING
    assert lfe_f.value < 80.0


def test_multichannel_layout_applicability_stereo(sine_1k_stereo):
    """Stereo (2ch) is NOT applicable to multichannel_layout."""
    a = all_analyzers()["multichannel_layout"]
    profile = profile_with()
    assert a.applicable(sine_1k_stereo, profile) is False


def test_multichannel_layout_applicability_mono(sine_1k):
    a = all_analyzers()["multichannel_layout"]
    assert a.applicable(sine_1k, profile_with()) is False


def test_multichannel_layout_stereo_compat():
    """L+R downmix should have energy."""
    a = all_analyzers()["multichannel_layout"]
    pcm = make_51_pcm()
    findings = a.analyze(pcm, {})
    compat_f = [f for f in findings if f.check_id == "multichannel_layout.stereo_compat"][0]
    assert compat_f.status == Status.PASS


# === BINAURAL_COMPAT ===


def test_binaural_compat_clean_stereo(sine_1k_stereo):
    """Clean stereo (L=R) should have low lateral content."""
    a = all_analyzers()["binaural_compat"]
    findings = a.analyze(sine_1k_stereo, {"max_lateral_low_db": -20.0})
    f = findings[0]
    # L=R means side=0, so lateral_low_db should be very low
    assert f.status == Status.PASS


def test_binaural_compat_lateral_lows():
    """Stereo with strong low-frequency difference should warn."""
    a = all_analyzers()["binaural_compat"]
    sr = SR
    t = np.arange(sr * 2) / sr
    # L = 50 Hz tone, R = different phase -> side channel has 50 Hz content
    L = 0.3 * np.sin(2 * np.pi * 50 * t)
    R = 0.3 * np.sin(2 * np.pi * 50 * t + np.pi / 2)  # 90° phase
    samples = np.stack([L, R]).astype(np.float32)
    pcm = PCM(samples=samples, sample_rate=sr, channel_layout="stereo")
    findings = a.analyze(pcm, {"max_lateral_low_db": -20.0, "lateral_low_cutoff_hz": 200.0})
    f = findings[0]
    assert f.status == Status.WARNING


def test_binaural_compat_applicability_mono(sine_1k):
    a = all_analyzers()["binaural_compat"]
    assert a.applicable(sine_1k, profile_with()) is False


# === SPATIAL_COHERENCE ===


def test_spatial_coherence_identical_channels():
    """Identical L/R (fake stereo) should be detected."""
    a = all_analyzers()["spatial_coherence"]
    sr = SR
    t = np.arange(sr * 2) / sr
    x = 0.3 * np.sin(2 * np.pi * 440 * t).astype(np.float32)
    samples = np.stack([x, x])  # identical
    pcm = PCM(samples=samples, sample_rate=sr, channel_layout="stereo")
    findings = a.analyze(pcm, {"max_off_diag_corr": 0.95})
    f = findings[0]
    assert f.value > 0.95
    assert f.status == Status.WARNING


def test_spatial_coherence_independent_channels():
    """Independent L/R should have low correlation."""
    a = all_analyzers()["spatial_coherence"]
    sr = SR
    rng = np.random.default_rng(42)
    L = rng.standard_normal(sr * 2).astype(np.float32) * 0.3
    R = rng.standard_normal(sr * 2).astype(np.float32) * 0.3
    samples = np.stack([L, R])
    pcm = PCM(samples=samples, sample_rate=sr, channel_layout="stereo")
    findings = a.analyze(pcm, {"max_off_diag_corr": 0.95})
    f = findings[0]
    assert f.value < 0.5
    assert f.status == Status.PASS


def test_spatial_coherence_applicability_mono(sine_1k):
    a = all_analyzers()["spatial_coherence"]
    assert a.applicable(sine_1k, profile_with()) is False


# === GONIOMETER ===


def test_goniometer_returns_statistics(sine_1k_stereo):
    """Goniometer should return Lissajous statistics."""
    a = all_analyzers()["goniometer"]
    findings = a.analyze(sine_1k_stereo, {})
    f = findings[0]
    assert f.status == Status.PASS  # observation only
    assert "mean_correlation" in f.evidence
    assert "lr_balance" in f.evidence
    assert "spread" in f.evidence


def test_goniometer_clean_stereo_correlation(sine_1k_stereo):
    """L=R stereo should have correlation ~1.0."""
    a = all_analyzers()["goniometer"]
    findings = a.analyze(sine_1k_stereo, {})
    f = findings[0]
    assert f.value > 0.95  # high correlation


def test_goniometer_applicability_mono(sine_1k):
    a = all_analyzers()["goniometer"]
    assert a.applicable(sine_1k, profile_with()) is False


def test_goniometer_never_fails():
    """Goniometer is an observation tool — status always PASS."""
    a = all_analyzers()["goniometer"]
    sr = SR
    rng = np.random.default_rng(0)
    L = rng.standard_normal(sr).astype(np.float32)
    R = rng.standard_normal(sr).astype(np.float32)
    samples = np.stack([L, R])
    pcm = PCM(samples=samples, sample_rate=sr, channel_layout="stereo")
    findings = a.analyze(pcm, {})
    assert findings[0].status == Status.PASS


# === Phase 3.5: Audit log + self-check ===


def test_audit_log_append_and_verify(tmp_path):
    """Audit log should chain entries and verify integrity."""
    from audio_suite.audit import AuditLog

    log_path = tmp_path / "audit.log"
    log = AuditLog(log_path, actor="tester")
    e1 = log.append("analyze", "file1.wav", {"result": "pass"})
    e2 = log.append("sign", "file1.wav", {"key": "test"})
    assert e1.entry_hash != ""
    assert e2.prev_hash == e1.entry_hash
    # Verify chain
    valid, errors = log.verify_chain()
    assert valid, f"chain broken: {errors}"


def test_audit_log_tamper_detection(tmp_path):
    """Modifying an entry should break the chain."""
    from audio_suite.audit import AuditLog

    log_path = tmp_path / "audit.log"
    log = AuditLog(log_path, actor="tester")
    log.append("analyze", "file1.wav")
    log.append("sign", "file1.wav")
    # Tamper: modify the first line
    lines = log_path.read_text().strip().split("\n")
    import json

    entry = json.loads(lines[0])
    entry["action"] = "TAMPERED"
    lines[0] = json.dumps(entry, sort_keys=True)
    log_path.write_text("\n".join(lines) + "\n")
    # Verify should fail
    log2 = AuditLog(log_path, actor="tester")
    valid, errors = log2.verify_chain()
    assert not valid
    assert len(errors) > 0


def test_self_check_passes():
    """Self-check should pass on a valid installation."""
    from audio_suite.audit import self_check

    results = self_check()
    assert results["overall"] is True
    assert results["failed"] == 0
    assert results["passed"] > 0


def test_self_check_cli():
    """The `audio-suite self-check` CLI command should work."""
    import io
    from contextlib import redirect_stdout

    from audio_suite.cli import main

    out = io.StringIO()
    with redirect_stdout(out):
        try:
            main(["self-check"])
        except SystemExit:
            pass
    import json

    data = json.loads(out.getvalue())
    assert data["overall"] is True
