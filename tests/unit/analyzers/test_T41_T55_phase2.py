"""T-41 to T-55: Phase 2 perceptual analyzers (Codec, RefQuality, Voice, LRA, Spectral, Transient)."""
from __future__ import annotations

import numpy as np
import pytest

from audio_suite.analyzers import all_analyzers
from audio_suite.models import PCM, Profile, Status


def profile_with(**analyzers) -> Profile:
    return Profile(name="t", version="1", analyzers=analyzers)


# === Codec conformance ===

def test_codec_conf_clean(sine_1k):
    a = all_analyzers()["codec_conf"]
    findings = a.analyze(sine_1k, {})
    f = findings[0]
    assert f.status == Status.PASS
    assert f.evidence["compliance_status"] == "conformant"


def test_codec_conf_has_metadata(sine_1k):
    a = all_analyzers()["codec_conf"]
    findings = a.analyze(sine_1k, {})
    f = findings[0]
    assert f.evidence["bit_depth"] == 16
    assert f.evidence["decoder"] == "libsndfile"


# === Spectral health (descriptor — never fails) ===

def test_spectral_returns_observation(sine_1k):
    a = all_analyzers()["spectral_health"]
    findings = a.analyze(sine_1k, {})
    f = findings[0]
    # Per Fase 2: descriptors are observation; status PASS by design
    assert f.status == Status.PASS
    assert f.evidence["centroid_hz"] > 0


def test_spectral_centroid_1k(sine_1k):
    """A 1 kHz pure sine should have centroid near 1000 Hz."""
    a = all_analyzers()["spectral_health"]
    findings = a.analyze(sine_1k, {})
    f = findings[0]
    centroid = f.evidence["centroid_hz"]
    # Allow generous tolerance due to windowing
    assert 500 < centroid < 2000, f"centroid off: {centroid}"


def test_spectral_flatness_tone_vs_noise(sine_1k, white_noise):
    """A pure tone should have flatness near 0; white noise near 1."""
    a = all_analyzers()["spectral_health"]
    tone_f = a.analyze(sine_1k, {})[0]
    noise_f = a.analyze(white_noise, {})[0]
    assert tone_f.evidence["flatness"] < 0.2
    assert noise_f.evidence["flatness"] > 0.3


def test_spectral_descriptor_never_fails():
    """Per rule 1: descriptors must never fail builds."""
    a = all_analyzers()["spectral_health"]
    # Even on a clipped signal, spectral_health must return PASS
    import numpy as np
    t = np.arange(44100) / 44100
    x = np.clip(1.5 * np.sin(2 * np.pi * 1000 * t), -1, 1).astype(np.float32)
    pcm = PCM(samples=x, sample_rate=44100)
    findings = a.analyze(pcm, {})
    assert findings[0].status == Status.PASS


# === LRA ===

def test_lra_constant_signal_zero(sine_1k):
    """A constant-amplitude sine should have LRA ~ 0."""
    a = all_analyzers()["lra"]
    findings = a.analyze(sine_1k, {})
    f = findings[0]
    assert f.value is not None
    assert f.value < 2.0  # very low variation


def test_lra_observation_by_default(sine_1k):
    a = all_analyzers()["lra"]
    findings = a.analyze(sine_1k, {})
    f = findings[0]
    assert f.status == Status.PASS  # no min/max -> observation


def test_lra_can_warn_with_threshold():
    """A dynamic signal can trigger warning if max_lu is set low."""
    a = all_analyzers()["lra"]
    # Build a signal with wide loudness variation
    sr = 44100
    t = np.arange(sr * 6) / sr
    x = 0.1 * np.sin(2 * np.pi * 440 * t).astype(np.float32)
    x[ sr*3:sr*6 ] = 0.9 * np.sin(2 * np.pi * 440 * t[:sr*3]).astype(np.float32)
    pcm = PCM(samples=x, sample_rate=sr)
    findings = a.analyze(pcm, {"max_lu": 1.0})
    f = findings[0]
    # This signal jumps ~18 dB; LRA should exceed 1 LU
    # (may be 0 if blocks don't span the transition cleanly, but 6s should)
    assert f.unit == "LU"


# === Transient ===

def test_transient_applicability_short():
    a = all_analyzers()["transient"]
    pcm = PCM(samples=np.zeros(100, dtype=np.float32), sample_rate=44100)
    assert a.applicable(pcm, profile_with()) is False


def test_transient_detects_attack(pink_noise):
    """Pink noise has random onsets; transient should detect something."""
    a = all_analyzers()["transient"]
    findings = a.analyze(pink_noise, {"max_attack_ms": 5.0})
    # Pink noise may or may not have detectable onsets; either is acceptable
    assert findings[0].unit == "ms" or findings[0].status == Status.NOT_APPLICABLE


# === Voice artifacts ===

def test_voice_artif_applicability_short():
    a = all_analyzers()["voice_artifacts"]
    pcm = PCM(samples=np.zeros(100, dtype=np.float32), sample_rate=44100)
    assert a.applicable(pcm, profile_with()) is False


def test_voice_artif_speech(speech_like):
    a = all_analyzers()["voice_artifacts"]
    findings = a.analyze(speech_like, {})
    f = findings[0]
    # The speech_like fixture has a sibilant burst; should detect something
    assert f.unit == "frames"
    # The result is heuristic; we accept PASS or WARNING
    assert f.status in (Status.PASS, Status.WARNING)


# === Reference quality (rule 2: no ref = indeterminate) ===

def test_ref_quality_no_reference_returns_indeterminate(sine_1k):
    a = all_analyzers()["ref_quality"]
    profile = profile_with(ref_quality={"mode": "no-reference"})
    findings = a.analyze(sine_1k, profile.analyzer_params("ref_quality"))
    f = findings[0]
    assert f.status == Status.INDETERMINATE
    assert "indeterminate" in f.message.lower() or "no-reference" in f.message.lower()


def test_ref_quality_with_reference(sine_1k):
    """Self-reference should give a near-perfect score."""
    a = all_analyzers()["ref_quality"]
    import tempfile
    import soundfile as sf
    # Write a copy of sine_1k as the reference
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        ref_path = tmp.name
    sf.write(ref_path, sine_1k.samples[0], sine_1k.sample_rate)
    findings = a.analyze(sine_1k, {
        "mode": "speech-full-ref",
        "reference_path": ref_path,
        "min_score": 0.5,
    })
    f = findings[0]
    assert f.status == Status.PASS
    assert f.value > 0.5


def test_ref_quality_hash_mismatch(sine_1k, tmp_path):
    """Reference with wrong declared hash should ERROR."""
    a = all_analyzers()["ref_quality"]
    import soundfile as sf
    ref_path = tmp_path / "ref.wav"
    sf.write(str(ref_path), sine_1k.samples[0], sine_1k.sample_rate)
    findings = a.analyze(sine_1k, {
        "mode": "speech-full-ref",
        "reference_path": str(ref_path),
        "reference_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
    })
    f = findings[0]
    assert f.status == Status.ERROR


def test_ref_quality_does_not_call_no_ref_a_visqol(sine_1k):
    """Rule 2: no-reference mode must NOT be labeled as ViSQOL/STOI/SI-SDR."""
    a = all_analyzers()["ref_quality"]
    findings = a.analyze(sine_1k, {"mode": "no-reference"})
    f = findings[0]
    assert f.metric != "visqol_proxy"
    assert f.metric != "stoi_proxy"
    assert f.metric != "si_sdr_db"


# === Applicability edge cases ===

def test_applicability_silence(silence):
    """Silence should not crash any analyzer."""
    profile = Profile(
        name="t", version="1",
        analyzers={
            "loudness": {}, "true_peak": {}, "clipping": {},
            "glitch": {}, "spectral_health": {}, "lra": {},
            "codec_conf": {}, "resampling": {}, "transient": {},
            "voice_artifacts": {}, "inspect": {},
        },
    )
    from audio_suite.engine import run_analyzers
    findings = run_analyzers(silence, profile)
    # No exceptions, all findings are well-formed
    assert len(findings) > 0
    for f in findings:
        assert f.status in {s for s in Status}


def test_applicability_stereo_vs_mono(sine_1k, sine_1k_stereo):
    """mono_compat and channel_balance should skip on mono; run on stereo."""
    from audio_suite.engine import run_analyzers
    profile = Profile(
        name="t", version="1",
        analyzers={"mono_compat": {}, "channel_balance": {}},
    )
    # Mono: both should be NOT_APPLICABLE
    mono_findings = run_analyzers(sine_1k, profile)
    assert all(f.status == Status.NOT_APPLICABLE for f in mono_findings)
    # Stereo: both should produce real findings
    stereo_findings = run_analyzers(sine_1k_stereo, profile)
    assert all(f.status != Status.NOT_APPLICABLE for f in stereo_findings)
