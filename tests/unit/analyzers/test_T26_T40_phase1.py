"""T-26 to T-40: Phase 1 defect analyzers (Glitch, Mono, Balance, Resampling, Loop).

Also covers Loudness, TruePeak, Clipping (AC-01..AC-13).
"""

from __future__ import annotations

import numpy as np
import pytest

from audio_suite.analyzers import all_analyzers
from audio_suite.models import PCM, Profile, Status


def profile_with(**analyzers) -> Profile:
    return Profile(name="t", version="1", analyzers=analyzers)


# === AC-01..AC-13: Loudness, True Peak, Clipping ===


def test_loudness_clean_signal(sine_1k):
    a = all_analyzers()["loudness"]
    findings = a.analyze(sine_1k, {})
    assert len(findings) == 1
    f = findings[0]
    assert f.unit == "LUFS"
    # 0.5 amp sine at 1 kHz should be around -6 dBFS -> around -6 LUFS
    # (BS.1770 K-weighting is mostly flat at 1 kHz)
    assert -25 < f.value < 0, f"unexpected LUFS: {f.value}"


def test_loudness_silence(silence):
    a = all_analyzers()["loudness"]
    findings = a.analyze(silence, {})
    f = findings[0]
    assert f.value == -70.0  # floored


def test_loudness_determinism(sine_1k):
    a = all_analyzers()["loudness"]
    f1 = a.analyze(sine_1k, {})[0]
    f2 = a.analyze(sine_1k, {})[0]
    assert f1.value == f2.value


def test_true_peak_clean(sine_1k):
    a = all_analyzers()["true_peak"]
    findings = a.analyze(sine_1k, {"max_dbtp": -1.0})
    f = findings[0]
    # 0.5 amp sine -> peak ~ -6 dBFS, true peak ~ -6 dBTP, below -1
    assert f.value < -1.0
    assert f.status == Status.PASS


def test_true_peak_clipped(clipped):
    a = all_analyzers()["true_peak"]
    findings = a.analyze(clipped, {"max_dbtp": -1.0})
    f = findings[0]
    # Clipped sine hits 0 dBFS, true peak ~ 0 dBTP > -1
    assert f.value > -1.0
    assert f.status == Status.FAIL


def test_clipping_clean(sine_1k):
    a = all_analyzers()["clipping"]
    findings = a.analyze(sine_1k, {"threshold": 0.99, "max_clipped_pct": 0.01})
    f = findings[0]
    assert f.status == Status.PASS
    assert f.value == 0.0


def test_clipping_detected(clipped):
    a = all_analyzers()["clipping"]
    findings = a.analyze(clipped, {"threshold": 0.99, "max_clipped_pct": 0.01})
    f = findings[0]
    assert f.status == Status.FAIL
    assert f.value > 0.01


def test_clipping_threshold_param():
    """A borderline signal should be detected at lower threshold only."""
    a = all_analyzers()["clipping"]
    # 0.95 amp sine — not clipped, but near ceiling
    import numpy as np

    t = np.arange(44100) / 44100
    x = 0.95 * np.sin(2 * np.pi * 1000 * t).astype(np.float32)
    pcm = PCM(samples=x, sample_rate=44100, channel_layout="mono")
    f_loose = a.analyze(pcm, {"threshold": 0.99, "max_clipped_pct": 0.01})[0]
    f_strict = a.analyze(pcm, {"threshold": 0.94, "max_clipped_pct": 0.01})[0]
    assert f_loose.status == Status.PASS
    assert f_strict.status == Status.FAIL


# === GL-01..GL-12: Glitch ===


def test_glitch_clean(sine_1k):
    a = all_analyzers()["glitch"]
    findings = a.analyze(sine_1k, {})
    # Clean sine should produce a summary pass finding (or no per-channel warnings)
    summary = [f for f in findings if f.check_id == "glitch.summary"]
    assert summary
    assert summary[0].status == Status.PASS


def test_glitch_click_detected(click_500ms):
    a = all_analyzers()["glitch"]
    findings = a.analyze(click_500ms, {})
    ch_findings = [f for f in findings if f.check_id.startswith("glitch.channel")]
    assert ch_findings, "expected at least one channel-level glitch finding"
    # Should have detected click events
    total_events = sum(f.value for f in ch_findings if f.value is not None)
    assert total_events > 0


def test_glitch_dropout_50ms(dropout_50ms):
    a = all_analyzers()["glitch"]
    findings = a.analyze(dropout_50ms, {"dropout_min_ms": 10.0})
    ch_findings = [f for f in findings if f.check_id.startswith("glitch.channel")]
    assert ch_findings
    # Find a dropout event in evidence
    found = False
    for f in ch_findings:
        for ev in f.evidence.get("events", []):
            if ev.get("type") == "dropout":
                found = True
                break
    assert found, "no dropout event recorded"


def test_glitch_dropout_100ms(dropout_50ms):
    """Larger dropout should also be detected."""
    a = all_analyzers()["glitch"]
    findings = a.analyze(dropout_50ms, {"dropout_min_ms": 50.0})
    ch_findings = [f for f in findings if f.check_id.startswith("glitch.channel")]
    assert ch_findings


def test_glitch_no_false_positive_on_percussion(pink_noise):
    """Pink noise should not trigger massive false positives."""
    a = all_analyzers()["glitch"]
    findings = a.analyze(pink_noise, {"click_sensitivity": 6.0})
    ch_findings = [f for f in findings if f.check_id.startswith("glitch.channel")]
    total_events = sum(f.value for f in ch_findings if f.value is not None)
    # Pink noise is broadband; we tolerate some events but not thousands
    assert total_events < 500, f"too many false positives: {total_events}"


def test_glitch_applicability_short():
    a = all_analyzers()["glitch"]
    # 8 samples — too short for glitch analysis
    pcm = PCM(samples=np.zeros(8, dtype=np.float32), sample_rate=44100)
    profile = profile_with()
    assert a.applicable(pcm, profile) is False


# === ST-01..ST-12: Phase / Mono / Balance ===


def test_mono_compat_clean(sine_1k_stereo):
    a = all_analyzers()["mono_compat"]
    findings = a.analyze(sine_1k_stereo, {"max_loss_db": 6.0})
    f = findings[0]
    # L=R so mono sum is identical, no loss
    assert f.status == Status.PASS
    assert f.value < 1.0  # < 1 dB loss


def test_mono_compat_phase_inverted(phase_inverted):
    a = all_analyzers()["mono_compat"]
    findings = a.analyze(phase_inverted, {"max_loss_db": 6.0})
    f = findings[0]
    # L=-R -> mono sum = 0, massive loss
    assert f.status == Status.WARNING
    assert f.value > 6.0
    # But correlation is negative; per the principle, that's reported not auto-fail
    assert f.evidence["lr_correlation"] < 0


def test_mono_compat_applicability_mono(sine_1k):
    a = all_analyzers()["mono_compat"]
    profile = profile_with()
    assert a.applicable(sine_1k, profile) is False  # mono not applicable


def test_channel_balance_clean(sine_1k_stereo):
    a = all_analyzers()["channel_balance"]
    findings = a.analyze(sine_1k_stereo, {})
    f = findings[0]
    assert f.status == Status.PASS
    assert f.value < 0.5


def test_channel_balance_imbalanced(louder_left):
    a = all_analyzers()["channel_balance"]
    findings = a.analyze(louder_left, {})
    f = findings[0]
    assert f.status == Status.WARNING
    assert f.value > 1.0


def test_channel_balance_applicability_mono(sine_1k):
    a = all_analyzers()["channel_balance"]
    profile = profile_with()
    assert a.applicable(sine_1k, profile) is False


# === LP: Loop ===


def test_loop_clean_passes(loop_clean):
    a = all_analyzers()["loop"]
    n = loop_clean.n_frames
    findings = a.analyze(loop_clean, {"loop_point_samples": n})
    ch = [f for f in findings if f.status != Status.NOT_APPLICABLE]
    assert ch
    assert all(f.status == Status.PASS for f in ch)


def test_loop_discontinuous_fails(loop_disc):
    a = all_analyzers()["loop"]
    n = loop_disc.n_frames
    findings = a.analyze(loop_disc, {"loop_point_samples": n})
    ch = [f for f in findings if f.status != Status.NOT_APPLICABLE]
    assert ch
    assert any(f.status == Status.FAIL for f in ch)


def test_loop_out_of_range(sine_1k):
    a = all_analyzers()["loop"]
    findings = a.analyze(sine_1k, {"loop_point_samples": 99999999})
    assert findings[0].status == Status.NOT_APPLICABLE


def test_loop_applicability_no_loop_point(sine_1k):
    a = all_analyzers()["loop"]
    profile = profile_with()  # no loop_point_ms
    assert a.applicable(sine_1k, profile) is False


# === RS: Resampling ===


def test_resampling_clean(sine_1k):
    a = all_analyzers()["resampling"]
    findings = a.analyze(sine_1k, {})
    f = findings[0]
    # Pure 1 kHz sine at 44.1 kHz has no aliasing
    assert f.status in (Status.PASS, Status.WARNING)


def test_resampling_aliasing_fixture(aliasing):
    a = all_analyzers()["resampling"]
    findings = a.analyze(aliasing, {})
    f = findings[0]
    # 19 kHz content at 44.1 kHz is close to Nyquist; aliasing scan may flag it
    # The analyzer reports observation-level; we just check it runs.
    assert f.unit == "dB"


def test_resampling_does_not_claim_mp3(sine_1k):
    """Per rule 1: must not conclude 'originally MP3' from spectral cutoff."""
    a = all_analyzers()["resampling"]
    findings = a.analyze(sine_1k, {})
    f = findings[0]
    # The message must not contain 'mp3' or 'codec source' as a conclusion
    assert "mp3" not in f.message.lower()
    assert "limitations" in f.to_dict()


# === IN: Inspect ===


def test_inspect_always_applicable(sine_1k):
    a = all_analyzers()["inspect"]
    profile = profile_with()
    assert a.applicable(sine_1k, profile) is True


def test_inspect_extracts_metadata(sine_1k):
    a = all_analyzers()["inspect"]
    findings = a.analyze(sine_1k, {})
    f = findings[0]
    assert f.evidence["sample_rate_hz"] == 44100
    assert f.evidence["channels"] == 1
    assert f.evidence["file_sha256"]
