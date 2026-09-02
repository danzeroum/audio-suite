"""Tests shared utilities — fixtures de áudio sintético."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def tmp_wav_factory(tmp_path: Path):
    """Factory para criar WAVs sintéticos em tmp_path."""

    def _make(name: str, pcm: np.ndarray, sr: int = 48000) -> Path:
        path = tmp_path / name
        if pcm.dtype != np.float32:
            pcm = pcm.astype(np.float32)
        pcm = np.clip(pcm, -1.0, 1.0)
        pcm_i16 = (pcm * 32767).astype(np.int16)
        if pcm_i16.ndim == 1:
            pcm_i16 = pcm_i16.reshape(-1, 1)
        import scipy.io.wavfile as wavfile
        wavfile.write(str(path), sr, pcm_i16)
        return path

    return _make


@pytest.fixture
def clean_stereo_pcm():
    """3s de senoide estéreo limpa em ~-20 dBFS."""
    sr = 48000
    t = np.linspace(0, 3.0, int(3.0 * sr), endpoint=False)
    left = 0.1 * np.sin(2 * np.pi * 440 * t)
    right = 0.1 * np.sin(2 * np.pi * 440 * t + np.pi / 6)
    return np.stack([left, right], axis=1).astype(np.float32), sr


@pytest.fixture
def clipped_pcm():
    """Senoide saturada (clipping)."""
    sr = 48000
    t = np.linspace(0, 1.0, sr, endpoint=False)
    left = 1.5 * np.sin(2 * np.pi * 440 * t)
    right = 1.5 * np.sin(2 * np.pi * 440 * t + np.pi / 4)
    pcm = np.stack([left, right], axis=1).astype(np.float32)
    return np.clip(pcm, -1.0, 1.0), sr


@pytest.fixture
def inverted_polarity_pcm():
    """Estéreo com canal direito invertido."""
    sr = 48000
    t = np.linspace(0, 3.0, int(3.0 * sr), endpoint=False)
    left = 0.2 * np.sin(2 * np.pi * 440 * t)
    right = -left
    return np.stack([left, right], axis=1).astype(np.float32), sr


@pytest.fixture
def mono_pcm():
    """Mono."""
    sr = 48000
    t = np.linspace(0, 1.0, sr, endpoint=False)
    sig = 0.1 * np.sin(2 * np.pi * 440 * t)
    return sig.reshape(-1, 1).astype(np.float32), sr


@pytest.fixture
def silence_pcm():
    """5s de silêncio."""
    sr = 48000
    return np.zeros((int(5.0 * sr), 2), dtype=np.float32), sr


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
