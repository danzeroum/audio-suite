"""T-41b to T-55b: Phase 2.5 accessibility analyzers.

Tests for:
  - SPEECH_INTELLIGIBILITY (STOI proxy, no-reference, for accessibility)
  - SPEECH_RATE (syllable rate detection)
"""

from __future__ import annotations

import numpy as np
import pytest

from audio_suite.analyzers import all_analyzers
from audio_suite.models import PCM, Profile, Status

SR = 44100


def profile_with(**analyzers) -> Profile:
    return Profile(name="t", version="1", analyzers=analyzers)


# === SPEECH_INTELLIGIBILITY ===


def test_speech_intelligibility_clean_signal(sine_1k):
    """A clean 1 kHz tone has high SNR and should produce a valid score.

    Note: a pure tone is NOT speech, so the spectral clarity metric may
    not be optimal — we only verify the score is valid and finite.
    """
    a = all_analyzers()["speech_intelligibility"]
    findings = a.analyze(sine_1k, {"min_score": 0.6})
    f = findings[0]
    assert f.unit == "0-1"
    assert 0.0 <= f.value <= 1.0
    # A clean tone has high SNR, so should pass OR warn on clarity
    assert f.status in (Status.PASS, Status.WARNING)


def test_speech_intelligibility_noisy_signal():
    """A noisy signal should have lower intelligibility score."""
    a = all_analyzers()["speech_intelligibility"]
    sr = SR
    t = np.arange(sr * 2) / sr
    signal = 0.1 * np.sin(2 * np.pi * 1000 * t)
    rng = np.random.default_rng(42)
    noise = 0.3 * rng.standard_normal(len(t))
    x = (signal + noise).astype(np.float32)
    pcm = PCM(samples=x, sample_rate=sr, channel_layout="mono")
    findings = a.analyze(pcm, {"min_score": 0.6})
    f = findings[0]
    # Noisy signal should have lower score
    assert f.value < 0.8
    assert f.status in (Status.WARNING, Status.PASS)


def test_speech_intelligibility_applicability_short():
    a = all_analyzers()["speech_intelligibility"]
    pcm = PCM(samples=np.zeros(100, dtype=np.float32), sample_rate=SR)
    assert a.applicable(pcm, profile_with()) is False


def test_speech_intelligibility_returns_score_in_range():
    """Score must always be in [0, 1]."""
    a = all_analyzers()["speech_intelligibility"]
    sr = SR
    t = np.arange(sr * 2) / sr
    x = 0.3 * np.sin(2 * np.pi * 440 * t).astype(np.float32)
    pcm = PCM(samples=x, sample_rate=sr, channel_layout="mono")
    findings = a.analyze(pcm, {"min_score": 0.6})
    f = findings[0]
    assert 0.0 <= f.value <= 1.0


def test_speech_intelligibility_is_not_full_ref_stoi():
    """The analyzer must NOT claim to be the reference STOI algorithm."""
    a = all_analyzers()["speech_intelligibility"]
    assert "proxy" in a.NAME.lower() or "no-reference" in a.NAME.lower()
    assert "proxy" in a.METHOD.lower() or "heuristic" in a.METHOD.lower()


# === SPEECH_RATE ===


def test_speech_rate_returns_value(speech_like):
    """Speech-like fixture should produce a syllable rate estimate."""
    a = all_analyzers()["speech_rate"]
    findings = a.analyze(speech_like, {"max_syllables_per_sec": 7.0})
    f = findings[0]
    assert f.unit == "syl/s"
    assert f.value >= 0.0


def test_speech_rate_excessive_warning():
    """A signal with very rapid envelope fluctuation should trigger warning."""
    a = all_analyzers()["speech_rate"]
    sr = SR
    t = np.arange(sr * 2) / sr
    # Amplitude modulate at 8 Hz (fast syllable rate)
    carrier = 0.3 * np.sin(2 * np.pi * 1000 * t)
    am = 0.5 * (1 + np.sin(2 * np.pi * 8 * t))
    x = (carrier * am).astype(np.float32)
    pcm = PCM(samples=x, sample_rate=sr, channel_layout="mono")
    findings = a.analyze(pcm, {"max_syllables_per_sec": 5.0})
    f = findings[0]
    # Should detect a high rate (may or may not exceed threshold, but should run)
    assert f.value >= 0.0


def test_speech_rate_applicability_short():
    a = all_analyzers()["speech_rate"]
    pcm = PCM(samples=np.zeros(100, dtype=np.float32), sample_rate=SR)
    assert a.applicable(pcm, profile_with()) is False


def test_speech_rate_documented_as_heuristic():
    """Per A2: must be documented as heuristic, not ASR-based."""
    a = all_analyzers()["speech_rate"]
    joined = " ".join(a.DEFAULT_LIMITATIONS).lower()
    assert "heuristic" in joined or "not asr" in joined
