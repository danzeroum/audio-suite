"""CORP-05: Metamorphic tests — relations between transformations."""

from __future__ import annotations

import numpy as np
import pytest

from audio_suite.analyzers.clipping import ClippingAnalyzer
from audio_suite.analyzers.loudness import compute_loudness_lufs
from audio_suite.analyzers.truepeak import compute_true_peak_dbtp
from audio_suite.models import PCM, Profile

SR = 44100


def make_pcm(x, sr=SR):
    if x.ndim == 1:
        x = x.reshape(1, -1)
    return PCM(samples=x.astype(np.float32), sample_rate=sr)


# MET-01: Channel swap preserves loudness
def test_MET01_channel_swap_preserves_loudness():
    t = np.arange(SR * 3) / SR
    L = 0.3 * np.sin(2 * np.pi * 440 * t)
    R = 0.3 * np.sin(2 * np.pi * 554 * t)
    stereo = np.stack([L, R])
    swapped = np.stack([R, L])
    l1 = compute_loudness_lufs(make_pcm(stereo))
    l2 = compute_loudness_lufs(make_pcm(swapped))
    assert abs(l1 - l2) < 0.1


# MET-02: -6 dB gain reduces level by ~6 dB
def test_MET02_gain_6db():
    t = np.arange(SR * 3) / SR
    x = 0.5 * np.sin(2 * np.pi * 1000 * t)
    x_quiet = x * 0.5  # -6 dB
    l1 = compute_loudness_lufs(make_pcm(x))
    l2 = compute_loudness_lufs(make_pcm(x_quiet))
    diff = l1 - l2
    assert 5.0 < diff < 7.0, f"Expected ~6 dB diff, got {diff}"


# MET-03: Dual mono → mono mix preserves loudness
def test_MET03_dual_mono_to_mono():
    t = np.arange(SR * 3) / SR
    x = 0.3 * np.sin(2 * np.pi * 440 * t)
    stereo = np.stack([x, x])
    l_stereo = compute_loudness_lufs(make_pcm(stereo))
    l_mono = compute_loudness_lufs(make_pcm(x))
    # BS.1770 weights L and R at 1.0 each, so stereo dual-mono should be +3 LU
    diff = l_stereo - l_mono
    assert 2.0 < diff < 4.0, f"Expected ~3 LU diff, got {diff}"


# MET-04: Time duplication preserves stationary metrics
def test_MET04_time_duplication():
    t = np.arange(SR) / SR
    x = 0.3 * np.sin(2 * np.pi * 440 * t)
    x_doubled = np.tile(x, 2)
    l1 = compute_loudness_lufs(make_pcm(x))
    l2 = compute_loudness_lufs(make_pcm(x_doubled))
    assert abs(l1 - l2) < 0.5


# MET-05: Silence padding doesn't change active segment metrics
def test_MET05_silence_padding():
    t = np.arange(SR * 3) / SR
    x = 0.3 * np.sin(2 * np.pi * 440 * t)
    padded = np.concatenate([np.zeros(SR), x, np.zeros(SR)])
    l1 = compute_loudness_lufs(make_pcm(x))
    l2 = compute_loudness_lufs(make_pcm(padded))
    # Gating should exclude the silence
    assert abs(l1 - l2) < 1.0


# MET-06: True peak is monotonically related to amplitude
def test_MET06_true_peak_monotonic():
    t = np.arange(SR * 3) / SR
    results = []
    for amp in [0.1, 0.3, 0.5, 0.7, 0.9]:
        x = amp * np.sin(2 * np.pi * 1000 * t)
        tp, _ = compute_true_peak_dbtp(make_pcm(x))
        results.append(tp)
    # Should be monotonically increasing
    for i in range(len(results) - 1):
        assert results[i] < results[i + 1], f"Not monotonic: {results}"


# MET-07: Clipping count scales with amplitude
def test_MET07_clipping_scales():
    a = ClippingAnalyzer()
    t = np.arange(SR) / SR
    counts = []
    for amp in [0.5, 0.9, 1.0, 1.2, 1.5]:
        x = amp * np.sin(2 * np.pi * 440 * t)
        pcm = make_pcm(x)
        f = a.analyze(pcm, {"threshold": 0.99, "max_clipped_pct": 100})
        counts.append(f[0].evidence.get("total_clipped_samples", 0))
    # Higher amplitude = more clipping (for amp > 1)
    assert counts[3] > counts[0]  # 1.2 amp clips more than 0.5
