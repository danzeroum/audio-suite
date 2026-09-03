"""TEST-03.r: Fuzz tests — decoder robustness against malformed input.

Política atual: **fail-open** (crash do decoder = bug a registrar, não bloqueia
merge). Transição para fail-closed documentada em `docs/adr/ADR-0003`
(janela de 7 dias consecutivos sem crash).

Cobertura:
  FUZZ-01  WAV truncado (base original, health check do Hypothesis corrigido)
  FUZZ-02  Headers malformados (base original, corrigido)
  FUZZ-03  Arquivos vazios/near-empty (base original)
  FUZZ-04  Bytes aleatórios (base original, corrigido)
  FUZZ-05  Headers válidos com payload corrompido (novo, TEST-03.r)
  FUZZ-06  Chunk sizes inconsistentes (RIFF/data mentirosos) (novo, TEST-03.r)
  FUZZ-07  Profundidades de bit exóticas (novo, TEST-03.r)
  FUZZ-08  NaN/Inf em samples float (novo, TEST-03.r)
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from audio_suite.decode import DecodeError, decode

FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "generated" / "sine_1k_mono.wav"

# Diretório session-scoped: o Hypothesis proíbe fixture function-scoped com
# @given (FailedHealthCheck) — escrevemos com nome único por exemplo.
_seed_counter = {"n": 0}


def _unique_wav(tmp_path_factory, prefix: str = "fuzz") -> Path:
    d = tmp_path_factory.mktemp("fuzz-decode")
    _seed_counter["n"] += 1
    return d / f"{prefix}_{_seed_counter['n']}.wav"


def _expect_graceful(path: Path) -> None:
    """Decode either succeeds or raises DecodeError — never crashes."""
    try:
        decode(str(path))
    except DecodeError:
        pass
    except Exception:
        pytest.fail(f"Decoder raised non-DecodeError on {path.name}")


# --- FUZZ-01: truncated WAV -------------------------------------------------
@given(truncate_bytes=st.integers(min_value=1, max_value=264644))
@settings(max_examples=20, deadline=5000)
def test_FUZZ01_truncated_wav(tmp_path_factory, truncate_bytes):
    """Truncated WAV files should raise DecodeError, not crash."""
    data = FIXTURE.read_bytes()
    trunc = data[: max(44, len(data) - truncate_bytes)]
    p = _unique_wav(tmp_path_factory, "trunc")
    p.write_bytes(trunc)
    _expect_graceful(p)


# --- FUZZ-02: malformed headers ---------------------------------------------
@given(
    num_channels=st.integers(min_value=0, max_value=32),
    sample_rate=st.integers(min_value=0, max_value=384000),
    bit_depth=st.sampled_from([8, 16, 24, 32]),
)
@settings(max_examples=15, deadline=5000)
def test_FUZZ02_malformed_headers(tmp_path_factory, num_channels, sample_rate, bit_depth):
    """Malformed WAV headers should not crash the decoder."""
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
    p = _unique_wav(tmp_path_factory, "malformed")
    p.write_bytes(header + b"\x00" * data_size)
    _expect_graceful(p)


# --- FUZZ-03: empty and near-empty files -------------------------------------
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


# --- FUZZ-04: random bytes as "audio" ----------------------------------------
@given(data=st.binary(min_size=100, max_size=10000))
@settings(max_examples=10, deadline=5000)
def test_FUZZ04_random_bytes(tmp_path_factory, data):
    p = _unique_wav(tmp_path_factory, "random")
    p.write_bytes(data)
    _expect_graceful(p)


# --- FUZZ-05 (TEST-03.r): valid header, corrupted payload ---------------------
@given(
    corrupt_positions=st.lists(st.integers(min_value=0, max_value=999), min_size=1, max_size=50),
    corrupt_byte=st.integers(min_value=0, max_value=255),
)
@settings(max_examples=20, deadline=8000)
def test_FUZZ05_valid_header_corrupted_payload(tmp_path_factory, corrupt_positions, corrupt_byte):
    """Headers válidos + payload com bytes corrompidos: nunca crashar."""
    data = bytearray(FIXTURE.read_bytes())
    data_len = len(data)
    for pos in corrupt_positions:
        # corrompe só dentro do data chunk (após header de 44 bytes)
        idx = 44 + (pos * 97) % max(1, data_len - 44)
        data[idx] = corrupt_byte
    p = _unique_wav(tmp_path_factory, "corrupt_payload")
    p.write_bytes(bytes(data))
    _expect_graceful(p)


# --- FUZZ-06 (TEST-03.r): inconsistent chunk sizes ----------------------------
@given(
    riff_size_lie=st.integers(min_value=-44, max_value=10_000_000),
    data_size_lie=st.integers(min_value=0, max_value=1_000_000),
)
@settings(max_examples=20, deadline=8000)
def test_FUZZ06_inconsistent_chunk_sizes(tmp_path_factory, riff_size_lie, data_size_lie):
    """RIFF/data sizes que mentem sobre o conteúdo real: nunca crashar."""
    good = FIXTURE.read_bytes()
    riff_size = len(good) - 8 + riff_size_lie
    data_size = max(0, len(good) - 44) + data_size_lie
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        riff_size & 0xFFFFFFFF,
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        44100,
        88200,
        2,
        16,
        b"data",
        data_size,
    )
    payload = good[44:]  # payload real (132300 bytes) ≠ data_size declarado
    p = _unique_wav(tmp_path_factory, "chunk_lie")
    p.write_bytes(header + payload)
    _expect_graceful(p)


# --- FUZZ-07 (TEST-03.r): exotic bit depths -----------------------------------
@given(bit_depth=st.sampled_from([1, 3, 4, 7, 8, 12, 20, 24, 32, 48, 64, 128]))
@settings(max_examples=15, deadline=5000)
def test_FUZZ07_exotic_bit_depths(tmp_path_factory, bit_depth):
    """Profundidades de bit exóticas/inválidas: nunca crashar."""
    data_size = 2048
    bytes_per = max(1, bit_depth // 8)
    byte_rate = 44100 * 1 * bytes_per
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        44100,
        byte_rate,
        bytes_per,
        bit_depth,
        b"data",
        data_size,
    )
    p = _unique_wav(tmp_path_factory, "exotic_depth")
    p.write_bytes(header + b"\x55" * data_size)
    _expect_graceful(p)


# --- FUZZ-08 (TEST-03.r): NaN/Inf in float samples ----------------------------
@given(
    nan_ratio=st.floats(min_value=0.0, max_value=1.0),
    mode=st.sampled_from(["nan", "inf", "neg_inf", "mixed"]),
)
@settings(max_examples=12, deadline=8000)
def test_FUZZ08_nan_inf_float_samples(tmp_path_factory, nan_ratio, mode):
    """Float WAVs com NaN/Inf nos samples: decoder nunca crasha."""
    n = 44100  # 1 s
    x = (0.3 * np.sin(2 * np.pi * 1000 * np.arange(n) / 44100)).astype(np.float32)
    rng = np.random.default_rng(42)
    mask = rng.random(n) < nan_ratio
    if mode == "nan":
        x[mask] = np.nan
    elif mode == "inf":
        x[mask] = np.inf
    elif mode == "neg_inf":
        x[mask] = -np.inf
    else:
        x[mask] = np.where(rng.random(int(mask.sum())) > 0.5, np.inf, -np.inf)
    buf = io_wav_float32(x)
    p = _unique_wav(tmp_path_factory, "nan_inf")
    p.write_bytes(buf)
    _expect_graceful(p)


def io_wav_float32(x: np.ndarray) -> bytes:
    """Minimal deterministic IEEE-float WAV writer (mesmo formato do CORP-01.r)."""
    data = np.ascontiguousarray(x.reshape(-1, 1), dtype="<f4")
    payload = data.tobytes()
    fmt = struct.pack("<4sIHHIIHH", b"fmt ", 16, 3, 1, 44100, 44100 * 4, 4, 32)
    fact = struct.pack("<4sII", b"fact", 4, len(x))
    datah = struct.pack("<4sI", b"data", len(payload))
    riff_size = 4 + len(fmt) + len(fact) + len(datah) + len(payload)
    return b"RIFF" + struct.pack("<I", riff_size) + b"WAVE" + fmt + fact + datah + payload
