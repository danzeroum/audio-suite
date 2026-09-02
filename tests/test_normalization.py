"""Tests: normalization (decode + hash + sanitize + fallback + degenerate)."""
from __future__ import annotations

import numpy as np
import pytest

from engine.normalization import (
    DegenerateInputError,
    compute_file_hash,
    compute_pcm_hash,
    decode_pcm_canonical,
)


class TestDecodePCMRCanonical:
    def test_decode_stereo_wav(self, tmp_wav_factory, clean_stereo_pcm):
        pcm, sr = clean_stereo_pcm
        path = tmp_wav_factory("test.wav", pcm, sr)
        decoded, dec_sr, dec_ch, meta = decode_pcm_canonical(path)
        assert dec_sr == 48000
        assert dec_ch == 2
        assert decoded.dtype == np.float32
        assert meta["decoder_used"] in ("ffmpeg", "fallback")

    def test_decode_mono_wav(self, tmp_wav_factory, mono_pcm):
        pcm, sr = mono_pcm
        path = tmp_wav_factory("mono.wav", pcm, sr)
        decoded, _dec_sr, dec_ch, _meta = decode_pcm_canonical(path)
        assert dec_ch == 1
        assert decoded.shape[1] == 1

    def test_invalid_sample_rate_raises(self, tmp_path):
        path = tmp_path / "dummy.wav"
        path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")
        with pytest.raises(DegenerateInputError):
            decode_pcm_canonical(path, sample_rate=-1)

    def test_nonexistent_file_raises(self, tmp_path):
        path = tmp_path / "nonexistent.wav"
        with pytest.raises((RuntimeError, FileNotFoundError)):
            decode_pcm_canonical(path)


class TestSanitizeDegenerate:
    def test_nan_sanitized(self):
        """Testa sanitização de NaN/Inf diretamente (sem passar por WAV)."""
        from engine.normalization import _sanitize

        pcm = np.zeros((100, 2), dtype=np.float32)
        pcm[10, 0] = np.nan
        pcm[20, 1] = np.inf
        meta = {"decoder_used": "ffmpeg", "fallback_reason": None}
        sanitized, _, _, meta_out = _sanitize(pcm, 48000, 2, meta)
        assert meta_out["nan_sanitized"] is True
        assert not np.any(np.isnan(sanitized))
        assert not np.any(np.isinf(sanitized))

    def test_no_nan_no_sanitization(self):
        from engine.normalization import _sanitize

        pcm = np.zeros((100, 2), dtype=np.float32)
        meta = {"decoder_used": "ffmpeg", "fallback_reason": None}
        _, _, _, meta_out = _sanitize(pcm, 48000, 2, meta)
        assert meta_out["nan_sanitized"] is False


class TestComputeHashes:
    def test_pcm_hash_deterministic(self, clean_stereo_pcm):
        pcm, _ = clean_stereo_pcm
        h1 = compute_pcm_hash(pcm)
        h2 = compute_pcm_hash(pcm)
        assert h1 == h2
        assert len(h1) == 64

    def test_file_hash_deterministic(self, tmp_path):
        path = tmp_path / "test.txt"
        path.write_bytes(b"hello world")
        h1 = compute_file_hash(path)
        h2 = compute_file_hash(path)
        assert h1 == h2
        assert len(h1) == 64

    def test_file_hash_changes_with_content(self, tmp_path):
        p1 = tmp_path / "a.txt"
        p2 = tmp_path / "b.txt"
        p1.write_bytes(b"content A")
        p2.write_bytes(b"content B")
        assert compute_file_hash(p1) != compute_file_hash(p2)
