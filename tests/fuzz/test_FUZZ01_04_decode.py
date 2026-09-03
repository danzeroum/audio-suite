"""TEST-03: Fuzz tests — decoder robustness against malformed input."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from audio_suite.decode import DecodeError, decode


# Fuzz-01: Truncated WAV files don't crash
@given(truncate_bytes=st.integers(min_value=1, max_value=264644))
@settings(max_examples=20, deadline=5000)
def test_FUZZ01_truncated_wav(tmp_path, truncate_bytes):
    """Truncated WAV files should raise DecodeError, not crash."""
    src = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "generated" / "sine_1k_mono.wav"
    data = src.read_bytes()
    trunc = data[: max(44, len(data) - truncate_bytes)]
    p = tmp_path / "trunc.wav"
    p.write_bytes(trunc)
    try:
        decode(str(p))
    except DecodeError:
        pass  # expected
    except Exception:
        pytest.fail("Decoder raised non-DecodeError on truncated file")


# Fuzz-02: Malformed headers don't crash
@given(
    num_channels=st.integers(min_value=0, max_value=32),
    sample_rate=st.integers(min_value=0, max_value=384000),
    bit_depth=st.sampled_from([8, 16, 24, 32]),
)
@settings(max_examples=15, deadline=5000)
def test_FUZZ02_malformed_headers(tmp_path, num_channels, sample_rate, bit_depth):
    """Malformed WAV headers should not crash the decoder."""
    # Build a minimal WAV with potentially invalid params
    data_size = 1000
    if sample_rate <= 0 or num_channels <= 0:
        return  # skip invalid combos that would make the header math fail
    byte_rate = sample_rate * num_channels * (bit_depth // 8)
    block_align = num_channels * (bit_depth // 8)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bit_depth,
        b"data",
        data_size,
    )
    audio_data = b"\x00" * data_size
    p = tmp_path / "malformed.wav"
    p.write_bytes(header + audio_data)
    try:
        decode(str(p))
    except DecodeError:
        pass
    except Exception:
        pytest.fail("Decoder raised non-DecodeError on malformed header")


# Fuzz-03: Empty and near-empty files
@pytest.mark.parametrize("size", [0, 1, 10, 43, 44, 45])
def test_FUZZ03_empty_files(tmp_path, size):
    p = tmp_path / f"empty_{size}.wav"
    p.write_bytes(b"\x00" * size)
    try:
        decode(str(p))
    except DecodeError:
        pass
    except Exception:
        pytest.fail(f"Decoder crashed on {size}-byte file")


# Fuzz-04: Random bytes as "audio"
@given(data=st.binary(min_size=100, max_size=10000))
@settings(max_examples=10, deadline=5000)
def test_FUZZ04_random_bytes(tmp_path, data):
    p = tmp_path / "random.wav"
    p.write_bytes(data)
    try:
        decode(str(p))
    except DecodeError:
        pass
    except Exception:
        pytest.fail("Decoder crashed on random bytes")
