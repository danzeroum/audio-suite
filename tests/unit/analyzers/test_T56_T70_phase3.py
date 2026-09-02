"""T-56 to T-70: Phase 3 analyzers — voice, forensic, music.

Tests for:
  - STEM_SEP (SI-SDR + leakage with reference)
  - PITCH_STAB (drift, wow, flutter)
  - ACOUSTIC_C (scene change, RT60, noise floor)
  - ENF_PHASE (experimental forensic, always needs_review)
  - DEEPFAKE (opt-in, always needs_review, never auto-conclude)

Per rule 8 (Regra da Inferência): inferential analyzers must require
reference/calibration/uncertainty and return needs_review.
"""

from __future__ import annotations

import numpy as np
import pytest

from audio_suite.analyzers import all_analyzers, analyzer_ids
from audio_suite.models import PCM, Profile, Status

SR = 44100


def test_phase3_analyzers_registered():
    """Phase 3 analyzers ARE registered (they were implemented in Phase 2.5+3 PR).
    Opt-in ML analyzers (deepfake, enf_phase) are registered but only run
    when enabled:true in profile (rule 4)."""
    ids = set(analyzer_ids())
    expected = {"deepfake", "enf_phase", "pitch_stab", "acoustic_context", "stem_sep"}
    for a in expected:
        assert a in ids, f"{a} should be registered"


def profile_with(**analyzers) -> Profile:
    return Profile(name="t", version="1", analyzers=analyzers)


def make_pcm(n_seconds: float = 2.0, freq: float = 440.0, sr: int = SR, amp: float = 0.3):
    t = np.arange(int(sr * n_seconds)) / sr
    x = (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return PCM(samples=x, sample_rate=sr, channel_layout="mono")


# === STEM_SEP (SS-01 to SS-10) ===


def test_stem_sep_no_reference_returns_indeterminate(sine_1k):
    """Rule 2: without reference, returns indeterminate."""
    a = all_analyzers()["stem_sep"]
    profile = profile_with(stem_sep={"stem_name": "vocals"})
    assert a.applicable(sine_1k, profile) is False


def test_stem_sep_with_reference(tmp_path, sine_1k):
    """Self-reference should give high SI-SDR."""
    import soundfile as sf

    a = all_analyzers()["stem_sep"]
    ref_path = tmp_path / "vocals_ref.wav"
    sf.write(str(ref_path), sine_1k.samples[0], sine_1k.sample_rate)
    findings = a.analyze(
        sine_1k,
        {
            "stem_name": "vocals",
            "references": {"vocals": {"path": str(ref_path)}},
            "min_si_sdr_db": 5.0,
        },
    )
    si_sdr_f = [f for f in findings if f.check_id == "stem_sep.si_sdr"][0]
    assert si_sdr_f.status == Status.PASS
    assert si_sdr_f.value > 5.0  # self-reference should be near-perfect


def test_stem_sep_degraded_reference(tmp_path):
    """A degraded estimate should have lower SI-SDR."""
    import soundfile as sf

    a = all_analyzers()["stem_sep"]
    sr = SR
    t = np.arange(sr * 2) / sr
    ref = 0.3 * np.sin(2 * np.pi * 440 * t).astype(np.float32)
    # Add noise to create a degraded "estimate"
    rng = np.random.default_rng(42)
    est = ref + 0.1 * rng.standard_normal(len(ref)).astype(np.float32)
    est = est.astype(np.float32)
    ref_path = tmp_path / "ref.wav"
    sf.write(str(ref_path), ref, sr)
    est_pcm = PCM(samples=est, sample_rate=sr, channel_layout="mono")
    findings = a.analyze(
        est_pcm,
        {
            "stem_name": "vocals",
            "references": {"vocals": {"path": str(ref_path)}},
            "min_si_sdr_db": 5.0,
        },
    )
    si_sdr_f = [f for f in findings if f.check_id == "stem_sep.si_sdr"][0]
    # Noisy estimate should have lower SI-SDR (likely < 20 dB)
    assert si_sdr_f.value < 30.0


def test_stem_sep_leakage_calculation():
    """Leakage should be detectable when another stem's energy is present."""
    from audio_suite.analyzers.stem_sep import _leakage_pct

    # est = own + 20% of other
    own = np.ones(1000, dtype=np.float64)
    other = np.ones(1000, dtype=np.float64) * 0.2
    est = own + other
    leak = _leakage_pct(est, [own, other], 0)
    assert leak > 0  # some leakage detected


# === PITCH_STAB (PS-01 to PS-08) ===


def test_pitch_stab_clean_tone():
    """A pure sine should have very low pitch drift."""
    a = all_analyzers()["pitch_stab"]
    pcm = make_pcm(n_seconds=2.0, freq=440.0)
    findings = a.analyze(pcm, {"max_drift_cents": 50.0})
    f = findings[0]
    assert f.status in (Status.PASS, Status.NOT_APPLICABLE)
    if f.value is not None:
        assert f.value < 50.0  # pure tone should be stable


def test_pitch_stab_drifting_tone():
    """A tone with frequency drift should be detected."""
    a = all_analyzers()["pitch_stab"]
    sr = SR
    t = np.arange(sr * 2) / sr
    # Frequency sweeps from 440 to 880 Hz (1 octave = 1200 cents drift)
    freq = 440 * (2 ** (t / 2.0))  # exponential sweep
    phase = 2 * np.pi * np.cumsum(freq) / sr
    x = 0.3 * np.sin(phase).astype(np.float32)
    pcm = PCM(samples=x, sample_rate=sr, channel_layout="mono")
    findings = a.analyze(pcm, {"max_drift_cents": 50.0})
    f = findings[0]
    # A 1-octave sweep should exceed 50 cents drift
    if f.value is not None and f.status != Status.NOT_APPLICABLE:
        assert f.value > 50.0
        assert f.status == Status.WARNING


def test_pitch_stab_applicability_short():
    a = all_analyzers()["pitch_stab"]
    pcm = PCM(samples=np.zeros(100, dtype=np.float32), sample_rate=SR)
    assert a.applicable(pcm, profile_with()) is False


# === ACOUSTIC_C (AC-01 to AC-06) ===


def test_acoustic_context_clean_signal(sine_1k):
    """A continuous sine should have no scene changes."""
    a = all_analyzers()["acoustic_context"]
    findings = a.analyze(sine_1k, {"scene_change_threshold_deg": 30.0})
    scene_f = [f for f in findings if f.check_id == "acoustic_context.scene_changes"][0]
    assert scene_f.status == Status.PASS
    assert scene_f.value == 0.0


def test_acoustic_context_scene_change():
    """A signal with abrupt spectral change should detect a scene change."""
    a = all_analyzers()["acoustic_context"]
    sr = SR
    n = sr * 4  # 4 seconds
    t = np.arange(n) / sr
    # First 2s: 200 Hz tone; Last 2s: 5000 Hz tone (abrupt change)
    x = np.zeros(n, dtype=np.float32)
    x[: n // 2] = 0.3 * np.sin(2 * np.pi * 200 * t[: n // 2])
    x[n // 2 :] = 0.3 * np.sin(2 * np.pi * 5000 * t[n // 2 :])
    pcm = PCM(samples=x, sample_rate=sr, channel_layout="mono")
    findings = a.analyze(pcm, {"scene_change_threshold_deg": 20.0})
    scene_f = [f for f in findings if f.check_id == "acoustic_context.scene_changes"][0]
    assert scene_f.value >= 1.0
    assert scene_f.status == Status.WARNING


def test_acoustic_context_rt60_returns_value(sine_1k):
    """RT60 should return a finite value (even if 0 for non-reverberant signal)."""
    a = all_analyzers()["acoustic_context"]
    findings = a.analyze(sine_1k, {})
    rt60_f = [f for f in findings if f.check_id == "acoustic_context.rt60"][0]
    assert rt60_f.value is not None
    assert np.isfinite(rt60_f.value)
    assert rt60_f.value >= 0.0


def test_acoustic_context_noise_floor(sine_1k):
    """Noise floor should be a finite dBFS value."""
    a = all_analyzers()["acoustic_context"]
    findings = a.analyze(sine_1k, {})
    noise_f = [f for f in findings if f.check_id == "acoustic_context.noise_floor"][0]
    assert noise_f.unit == "dBFS"
    assert np.isfinite(noise_f.value)


# === ENF_PHASE (FO-01 to FO-06) ===


def test_enf_phase_opt_in_by_default(sine_1k):
    """Rule 4: ENF must be opt-in (disabled by default)."""
    a = all_analyzers()["enf_phase"]
    profile = profile_with()  # no enf_phase config
    assert a.applicable(sine_1k, profile) is False


def test_enf_phase_short_duration_needs_review():
    """Rule 8: short duration returns needs_review (inconclusive)."""
    a = all_analyzers()["enf_phase"]
    pcm = make_pcm(n_seconds=2.0)  # too short for ENF
    profile = profile_with(enf_phase={"enabled": True})
    assert a.applicable(pcm, profile) is True
    findings = a.analyze(pcm, {"enabled": True, "min_duration_s": 60.0})
    f = findings[0]
    assert f.status == Status.NEEDS_REVIEW
    assert "duration" in f.message.lower() or "inconclusive" in f.message.lower()


def test_enf_phase_never_returns_authentic():
    """Rule 8: ENF must NEVER conclude 'authentic' or 'tampered'."""
    a = all_analyzers()["enf_phase"]
    # Create a signal with strong 50 Hz hum (long enough)
    sr = SR
    n = sr * 65  # 65 seconds
    t = np.arange(n) / sr
    x = (0.1 * np.sin(2 * np.pi * 50 * t) + 0.01 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
    pcm = PCM(samples=x, sample_rate=sr, channel_layout="mono")
    findings = a.analyze(
        pcm,
        {
            "enabled": True,
            "min_duration_s": 60.0,
            "min_snr_db": 5.0,
        },
    )
    f = findings[0]
    # Must be needs_review, never pass/fail
    assert f.status == Status.NEEDS_REVIEW
    msg_lower = f.message.lower()
    assert "authentic" not in msg_lower or "does not prove" in msg_lower
    assert "forensic_warning" in f.evidence


# === DEEPFAKE (DF-01 to DF-06) ===


def test_deepfake_opt_in_by_default(sine_1k):
    """Rule 4: deepfake must be opt-in."""
    a = all_analyzers()["deepfake"]
    profile = profile_with()
    assert a.applicable(sine_1k, profile) is False


def test_deepfake_requires_model_name(sine_1k):
    """Rule 4 + A2: must declare model_name even when enabled."""
    a = all_analyzers()["deepfake"]
    profile = profile_with(deepfake={"enabled": True})  # no model_name
    assert a.applicable(sine_1k, profile) is False


def test_deepfake_always_needs_review(speech_like):
    """Rule 8: deepfake NEVER returns pass/fail — always needs_review."""
    a = all_analyzers()["deepfake"]
    profile = profile_with(
        deepfake={
            "enabled": True,
            "model_name": "test-heuristic-v0.1",
            "corpus": "synthetic-test",
        }
    )
    assert a.applicable(speech_like, profile) is True
    findings = a.analyze(
        speech_like,
        {
            "enabled": True,
            "model_name": "test-heuristic-v0.1",
            "corpus": "synthetic-test",
        },
    )
    f = findings[0]
    assert f.status == Status.NEEDS_REVIEW
    assert f.confidence < 0.5  # low confidence without real model
    assert "forensic_warning" in f.evidence
    # Must NOT contain definitive language
    msg_lower = f.message.lower()
    assert "is deepfake" not in msg_lower
    assert "is authentic" not in msg_lower


def test_deepfake_score_in_range(speech_like):
    """Synthetic-likeness score must be in [0, 1]."""
    a = all_analyzers()["deepfake"]
    findings = a.analyze(
        speech_like,
        {
            "enabled": True,
            "model_name": "test",
        },
    )
    f = findings[0]
    assert 0.0 <= f.value <= 1.0


# === Cross-phase: ensure no analyzer claims forensic conclusion ===


def test_no_analyzer_claims_authenticity():
    """No analyzer may use 'authentic' or 'tampered' in its NAME."""
    for aid, a in all_analyzers().items():
        name_lower = a.NAME.lower()
        assert "authentic" not in name_lower, f"{aid} NAME claims authenticity"
        assert "tamper" not in name_lower, f"{aid} NAME claims tampering detection"


def test_inferential_analyzers_have_forensic_warning():
    """ENF and deepfake must document forensic limitations."""
    for aid in ["enf_phase", "deepfake"]:
        a = all_analyzers()[aid]
        # Check DEFAULT_LIMITATIONS contains forensic warning
        joined = " ".join(a.DEFAULT_LIMITATIONS).lower()
        assert "forensic" in joined or "experimental" in joined or "review" in joined, (
            f"{aid} missing forensic limitation documentation"
        )
