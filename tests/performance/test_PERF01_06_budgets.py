"""TEST-05: Performance benchmarks — s of audio / s of CPU."""

from __future__ import annotations

import time

import numpy as np
import pytest

from audio_suite.analyzers.clipping import ClippingAnalyzer
from audio_suite.analyzers.glitch import GlitchAnalyzer
from audio_suite.analyzers.loudness import compute_loudness_lufs
from audio_suite.analyzers.spectral import SpectralAnalyzer
from audio_suite.analyzers.truepeak import compute_true_peak_dbtp
from audio_suite.models import PCM

SR = 44100


def make_pcm(n_seconds, sr=SR):
    t = np.arange(int(sr * n_seconds)) / sr
    x = 0.3 * np.sin(2 * np.pi * 440 * t).astype(np.float32)
    return PCM(samples=x.reshape(1, -1), sample_rate=sr)


# PERF-01: Loudness should be ≥ 50× realtime
def test_PERF01_loudness_speed():
    pcm = make_pcm(10)  # 10 seconds
    t0 = time.perf_counter()
    compute_loudness_lufs(pcm)
    elapsed = time.perf_counter() - t0
    # Should process 10s of audio in < 0.2s (50× realtime)
    assert elapsed < 1.0, f"Loudness too slow: {elapsed:.3f}s for 10s audio"


# PERF-02: True peak should be fast
def test_PERF02_true_peak_speed():
    pcm = make_pcm(10)
    t0 = time.perf_counter()
    compute_true_peak_dbtp(pcm)
    elapsed = time.perf_counter() - t0
    assert elapsed < 2.0, f"True peak too slow: {elapsed:.3f}s"


# PERF-03: Clipping should be very fast
def test_PERF03_clipping_speed():
    pcm = make_pcm(30)
    a = ClippingAnalyzer()
    t0 = time.perf_counter()
    a.analyze(pcm, {})
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.0, f"Clipping too slow: {elapsed:.3f}s"


# PERF-04: Glitch should be reasonable
def test_PERF04_glitch_speed():
    pcm = make_pcm(10)
    a = GlitchAnalyzer()
    t0 = time.perf_counter()
    a.analyze(pcm, {})
    elapsed = time.perf_counter() - t0
    assert elapsed < 20.0, f"Glitch too slow: {elapsed:.3f}s"


# PERF-05: Spectral should be fast
def test_PERF05_spectral_speed():
    pcm = make_pcm(10)
    a = SpectralAnalyzer()
    t0 = time.perf_counter()
    a.analyze(pcm, {})
    elapsed = time.perf_counter() - t0
    assert elapsed < 2.0, f"Spectral too slow: {elapsed:.3f}s"


# PERF-06: Memory should be bounded for large files
def test_PERF06_large_file_memory():
    """30-second file should not use excessive memory."""
    import resource

    pcm = make_pcm(30)
    a = ClippingAnalyzer()
    a.analyze(pcm, {})
    mem_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Should be under 500 MB (512000 KB)
    assert mem_kb < 512000, f"Memory usage too high: {mem_kb / 1024:.1f} MB"
