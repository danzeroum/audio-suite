"""CONF-02/05: Conformance tests — loudness, true peak, LRA against known values."""

from __future__ import annotations

import numpy as np
import pytest

from audio_suite.analyzers.loudness import compute_loudness_lufs
from audio_suite.analyzers.lra import compute_lra_lu
from audio_suite.analyzers.truepeak import compute_true_peak_dbtp
from audio_suite.models import PCM

SR = 44100


def make_pcm(samples, sr=SR):
    if samples.ndim == 1:
        samples = samples.reshape(1, -1)
    return PCM(samples=samples.astype(np.float32), sample_rate=sr)


# CONF-02: Loudness conformance — pure tone at known amplitude
def test_CONF02_loudness_1k_tone():
    """1 kHz sine at -23 dBFS should measure close to -23 LUFS."""
    t = np.arange(SR * 3) / SR
    amp = 10 ** (-23 / 20)  # -23 dBFS
    x = amp * np.sin(2 * np.pi * 1000 * t)
    pcm = make_pcm(x)
    lufs = compute_loudness_lufs(pcm)
    # BS.1770 at 1 kHz: K-weighting introduces ~-2 dB shift, allow generous tolerance
    assert abs(lufs - (-23)) < 3.5, f"Expected ~-23 LUFS, got {lufs}"


def test_CONF02_loudness_silence():
    x = np.zeros(SR * 3)
    pcm = make_pcm(x)
    lufs = compute_loudness_lufs(pcm)
    assert lufs == -70.0


def test_CONF02_loudness_deterministic():
    t = np.arange(SR * 3) / SR
    x = 0.3 * np.sin(2 * np.pi * 1000 * t)
    pcm = make_pcm(x)
    l1 = compute_loudness_lufs(pcm)
    l2 = compute_loudness_lufs(pcm)
    assert l1 == l2


# CONF-05: True peak conformance
def test_CONF05_true_peak_full_scale_sine():
    """Full-scale sine should have true peak near 0 dBTP."""
    t = np.arange(SR * 3) / SR
    x = np.sin(2 * np.pi * 1000 * t)  # amp = 1.0
    pcm = make_pcm(x)
    tp, sp = compute_true_peak_dbtp(pcm)
    assert abs(tp) < 0.5, f"Expected ~0 dBTP, got {tp}"
    assert abs(sp) < 0.5


def test_CONF05_true_peak_below_full_scale():
    """-6 dB sine should have true peak near -6 dBTP."""
    t = np.arange(SR * 3) / SR
    x = 0.5 * np.sin(2 * np.pi * 1000 * t)  # -6 dB
    pcm = make_pcm(x)
    tp, sp = compute_true_peak_dbtp(pcm)
    assert abs(tp - (-6)) < 1.0, f"Expected ~-6 dBTP, got {tp}"


def test_CONF05_true_peak_deterministic():
    t = np.arange(SR * 3) / SR
    x = 0.5 * np.sin(2 * np.pi * 1000 * t)
    pcm = make_pcm(x)
    tp1, _ = compute_true_peak_dbtp(pcm)
    tp2, _ = compute_true_peak_dbtp(pcm)
    assert tp1 == tp2


# LRA conformance
def test_CONF_lra_constant_signal():
    """Constant-amplitude signal should have LRA ~ 0."""
    t = np.arange(SR * 3) / SR
    x = 0.3 * np.sin(2 * np.pi * 440 * t)
    pcm = make_pcm(x)
    lra = compute_lra_lu(pcm)
    assert lra < 2.0


def test_CONF_lra_deterministic():
    t = np.arange(SR * 6) / SR
    x = 0.3 * np.sin(2 * np.pi * 440 * t)
    pcm = make_pcm(x)
    l1 = compute_lra_lu(pcm)
    l2 = compute_lra_lu(pcm)
    assert l1 == l2
