"""Canonical seed-based fixture generators (CORP-01.r).

This module is the PRIMARY source of every test fixture in audio-suite.

Invariants:
  - Every stochastic generator receives an explicit integer ``seed`` and uses
    ``numpy.random.Generator`` (PCG64) created via :func:`make_rng`.
  - Global RNG state (``np.random.seed`` / ``random.*``) is NEVER used.
  - The same seed on the same numpy version must produce byte-identical WAV
    bytes on any machine (verified by tests/unit/test_CORP01_generators.py).

Manifest schema (tests/fixtures/generated/manifest.json), one entry per file:

    {
      "<name>": {
        "sha256": "...",                # SHA-256 of the file bytes
        "purpose": "...",               # human description
        "subtype": "PCM_16",            # libsndfile subtype ("" for raw)
        "sample_rate": 44100,           # 0 for raw/non-audio
        "channels": 1,                  # 0 for raw/non-audio
        "seed": 42,                     # int | null (null = deterministic formula)
        "generator": "gen_sine",        # canonical generator name
        "expected_findings": ["AS-PEAK-002"]   # OPTIONAL (list[rule_id])
      }
    }
"""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

SR = 44100
DURATION_S = 3.0
N = int(SR * DURATION_S)


def make_rng(seed: int) -> np.random.Generator:
    """Create an explicit, locally-scoped ``numpy.random.Generator`` (PCG64).

    This is the ONLY sanctioned way for fixture generators to obtain
    randomness. Global state (``np.random.seed``/``np.random.*`` legacy API or
    the stdlib ``random`` module) is forbidden by CORP-01.r.
    """
    return np.random.Generator(np.random.PCG64(seed))


# ---------------------------------------------------------------------------
# Base signal generators (deterministic formulas or seed-based noise)
# ---------------------------------------------------------------------------
def gen_sine(
    freq_hz: float = 1000.0, sr: int = SR, dur_s: float = DURATION_S, amp: float = 0.5, channels: int = 1
) -> np.ndarray:
    t = np.arange(int(sr * dur_s)) / sr
    x = amp * np.sin(2 * np.pi * freq_hz * t).astype(np.float32)
    if channels == 2:
        x = np.stack([x, x])
    return x


def gen_silence(sr: int = SR, dur_s: float = DURATION_S, channels: int = 1) -> np.ndarray:
    n = int(sr * dur_s)
    x = np.zeros(n, dtype=np.float32)
    if channels == 2:
        x = np.stack([x, x])
    return x


def gen_white_noise(
    sr: int = SR, dur_s: float = DURATION_S, amp: float = 0.3, channels: int = 1, seed: int = 42
) -> np.ndarray:
    rng = make_rng(seed)
    x = (amp * rng.standard_normal(int(sr * dur_s))).astype(np.float32)
    if channels == 2:
        x = np.stack([x, x])
    return x


def gen_pink_noise(
    sr: int = SR, dur_s: float = DURATION_S, amp: float = 0.3, channels: int = 1, seed: int = 7
) -> np.ndarray:
    rng = make_rng(seed)
    n = int(sr * dur_s)
    rows = 8
    base = rng.standard_normal((rows, n))
    out = np.zeros(n)
    for k in range(rows):
        step = 1 << k
        idx = np.arange(0, n, step)
        out += np.repeat(base[k, : len(idx)], step)[:n]
    out = out / np.max(np.abs(out)) * amp
    x = out.astype(np.float32)
    if channels == 2:
        x = np.stack([x, x])
    return x


def gen_clipped(sr: int = SR, dur_s: float = DURATION_S, amp: float = 1.5, channels: int = 1) -> np.ndarray:
    x = gen_sine(440, sr, dur_s, amp=amp, channels=1)
    x = np.clip(x, -1.0, 1.0)
    if channels == 2:
        x = np.stack([x, x])
    return x


def gen_click(
    sr: int = SR, dur_s: float = DURATION_S, amp: float = 0.9, click_pos_ms: int = 500, channels: int = 1
) -> np.ndarray:
    x = gen_sine(440, sr, dur_s, amp=0.3, channels=1)
    pos = int(sr * click_pos_ms / 1000)
    if 0 <= pos < len(x):
        x[pos] = amp
    if channels == 2:
        x = np.stack([x, x])
    return x


def gen_dropout(
    sr: int = SR, dur_s: float = DURATION_S, dropout_ms: int = 50, start_ms: int = 800, channels: int = 1
) -> np.ndarray:
    x = gen_sine(440, sr, dur_s, amp=0.3, channels=1)
    s = int(sr * start_ms / 1000)
    e = s + int(sr * dropout_ms / 1000)
    x[s:e] = 0.0
    if channels == 2:
        x = np.stack([x, x])
    return x


def gen_phase_inverted_stereo(sr: int = SR, dur_s: float = DURATION_S) -> np.ndarray:
    x = gen_sine(440, sr, dur_s, amp=0.3, channels=1)
    return np.stack([x, -x])


def gen_louder_left(sr: int = SR, dur_s: float = DURATION_S) -> np.ndarray:
    L = gen_sine(440, sr, dur_s, amp=0.5, channels=1)
    R = gen_sine(440, sr, dur_s, amp=0.1, channels=1)
    return np.stack([L, R])


def gen_loop_clean(sr: int = SR, dur_s: float = 1.0, freq: float = 220.0) -> np.ndarray:
    n = int(sr * dur_s)
    period_samples = int(sr / freq)
    n = (n // period_samples) * period_samples
    t = np.arange(n) / sr
    return (0.3 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def gen_loop_discontinuous(sr: int = SR, dur_s: float = 1.0, freq: float = 220.0) -> np.ndarray:
    x = gen_loop_clean(sr, dur_s, freq)
    half = len(x) // 2
    x[half:] += 0.3
    return x.astype(np.float32)


def gen_aliasing(sr: int = SR, dur_s: float = DURATION_S) -> np.ndarray:
    t = np.arange(int(sr * dur_s)) / sr
    x = 0.3 * np.sin(2 * np.pi * 7000 * t) + 0.2 * np.sin(2 * np.pi * 19000 * t)
    return x.astype(np.float32)


def gen_high_bandwidth(sr: int = 96000, dur_s: float = DURATION_S) -> np.ndarray:
    t = np.arange(int(sr * dur_s)) / sr
    x = 0.3 * np.sin(2 * np.pi * 40000 * t) + 0.3 * np.sin(2 * np.pi * 1000 * t)
    return x.astype(np.float32)


def gen_speech_like(sr: int = SR, dur_s: float = DURATION_S, seed: int = 99) -> np.ndarray:
    """Modulated noise resembling voiced speech (numpy-only)."""
    rng = make_rng(seed)
    t = np.arange(int(sr * dur_s)) / sr
    f0 = 150
    pulse = np.sign(np.sin(2 * np.pi * f0 * t))
    pulse = np.maximum(pulse, 0)
    kernel = np.ones(11) / 11
    pulse = np.convolve(pulse, kernel, mode="same").astype(np.float32)
    noise = rng.standard_normal(len(t)).astype(np.float32) * 0.1
    x = 0.3 * pulse * (1 + noise)
    sib = rng.standard_normal(len(t)).astype(np.float32) * 0.5
    S = np.fft.rfft(sib)
    freqs = np.fft.rfftfreq(len(sib), 1.0 / sr)
    band = (freqs >= 5000) & (freqs <= 10000)
    S[~band] = 0
    sib_filtered = np.fft.irfft(S, n=len(sib)).astype(np.float32)
    mask = np.zeros(len(t), dtype=np.float32)
    s = int(sr * 1.0)
    e = int(sr * 1.2)
    mask[s:e] = 1.0
    x = x + 0.4 * sib_filtered * mask
    return x.astype(np.float32)


def gen_truncated_wav_bytes(valid_bytes: int) -> bytes:
    """WAV bytes of sine_1k truncated to ``valid_bytes``."""
    x = gen_sine(440)
    full = wav_bytes(x)
    return full[:valid_bytes]


# === Extended generators (CORP-03) ===
def gen_dc_offset(sr=SR, dur_s=DURATION_S, offset=0.1):
    t = np.arange(int(sr * dur_s)) / sr
    x = 0.3 * np.sin(2 * np.pi * 440 * t) + offset
    return x.astype(np.float32)


def gen_stereo_wide(sr=SR, dur_s=DURATION_S):
    t = np.arange(int(sr * dur_s)) / sr
    L = 0.3 * np.sin(2 * np.pi * 440 * t)
    R = 0.3 * np.sin(2 * np.pi * 554 * t)
    return np.stack([L.astype(np.float32), R.astype(np.float32)])


def gen_dual_mono(sr=SR, dur_s=DURATION_S):
    t = np.arange(int(sr * dur_s)) / sr
    x = 0.3 * np.sin(2 * np.pi * 440 * t).astype(np.float32)
    return np.stack([x, x])


def gen_sine_amped(sr=SR, dur_s=DURATION_S, freq=440, amp=0.8):
    return gen_sine(freq, sr, dur_s, amp=amp, channels=1)


def gen_low_snr(sr=SR, dur_s=DURATION_S, seed: int = 123):
    rng = make_rng(seed)
    t = np.arange(int(sr * dur_s)) / sr
    signal = 0.05 * np.sin(2 * np.pi * 1000 * t)
    noise = 0.3 * rng.standard_normal(len(t))
    return (signal + noise).astype(np.float32)


def gen_freq_sweep(sr=SR, dur_s=DURATION_S, f0=100, f1=8000):
    t = np.arange(int(sr * dur_s)) / sr
    freq = f0 * (f1 / f0) ** (t / dur_s)
    phase = 2 * np.pi * np.cumsum(freq) / sr
    return (0.3 * np.sin(phase)).astype(np.float32)


def gen_interleaved_noise(sr=SR, dur_s=DURATION_S, seed: int = 0):
    """Periodic noise bursts. Each burst derives from an explicit child seed."""
    t = np.arange(int(sr * dur_s)) / sr
    x = 0.3 * np.sin(2 * np.pi * 440 * t)
    for i in range(0, int(dur_s * 2)):
        start = int(i * sr * 0.5)
        end = start + int(sr * 0.01)
        if end < len(x):
            # CORP-01.r: explicit per-burst seed (base + burst index), no global RNG
            burst_rng = make_rng(seed + i)
            x[start:end] += 0.5 * burst_rng.standard_normal(end - start)
    return x.astype(np.float32)


def gen_polarity_inverted(sr=SR, dur_s=DURATION_S):
    t = np.arange(int(sr * dur_s)) / sr
    x = 0.3 * np.sin(2 * np.pi * 440 * t)
    mid = len(x) // 2
    x[mid:] = -x[mid:]
    return x.astype(np.float32)


def gen_short_1s(sr=SR):
    return gen_sine(440, sr, 1.0, channels=1)


def gen_very_long_30s(sr=SR):
    return gen_sine(440, sr, 30.0, channels=1)


def gen_two_tone(sr=SR, dur_s=DURATION_S):
    t = np.arange(int(sr * dur_s)) / sr
    x = 0.2 * np.sin(2 * np.pi * 440 * t) + 0.2 * np.sin(2 * np.pi * 880 * t)
    return x.astype(np.float32)


def gen_modulated_am(sr=SR, dur_s=DURATION_S):
    t = np.arange(int(sr * dur_s)) / sr
    carrier = 0.3 * np.sin(2 * np.pi * 1000 * t)
    am = 0.5 * (1 + np.sin(2 * np.pi * 5 * t))
    return (carrier * am).astype(np.float32)


def gen_violin_like(sr=SR, dur_s=DURATION_S):
    t = np.arange(int(sr * dur_s)) / sr
    f = 440
    x = (
        0.3 * np.sin(2 * np.pi * f * t)
        + 0.15 * np.sin(2 * np.pi * 2 * f * t)
        + 0.1 * np.sin(2 * np.pi * 3 * f * t)
        + 0.05 * np.sin(2 * np.pi * 4 * f * t)
    )
    vibrato = 0.02 * np.sin(2 * np.pi * 5 * t)
    return (x * (1 + vibrato)).astype(np.float32)


# ---------------------------------------------------------------------------
# WAV serialization helpers (byte-deterministic)
# ---------------------------------------------------------------------------
def _float32_wav_bytes(samples: np.ndarray, sr: int) -> bytes:
    """Deterministic IEEE-float WAV writer (numpy-only).

    libsndfile embeds a wall-clock timestamp in the PEAK chunk of float WAV
    files, which makes their bytes non-reproducible across runs/machines.
    We therefore serialize float fixtures with an explicit, timestamp-free
    RIFF writer (format tag 3, fact + data chunks).
    """
    import struct

    data = samples.T if samples.ndim == 2 else samples.reshape(-1, 1)
    data = np.ascontiguousarray(data, dtype="<f4")
    n_frames, n_ch = data.shape
    payload = data.tobytes()
    fmt = struct.pack(
        "<4sIHHIIHH",
        b"fmt ",
        16,
        3,
        n_ch,
        sr,
        sr * n_ch * 4,
        n_ch * 4,
        32,
    )
    fact = struct.pack("<4sII", b"fact", 4, n_frames)
    datah = struct.pack("<4sI", b"data", len(payload))
    riff_size = 4 + len(fmt) + len(fact) + len(datah) + len(payload)  # WAVE + chunks
    return b"RIFF" + struct.pack("<I", riff_size) + b"WAVE" + fmt + fact + datah + payload


def wav_bytes(samples: np.ndarray, sr: int = SR, subtype: str = "PCM_16") -> bytes:
    """Serialize samples to WAV bytes (deterministic for same input).

    PCM subtypes go through libsndfile (byte-stable, no PEAK chunk).
    Float subtypes go through the explicit deterministic writer above.
    """
    if subtype.upper() in ("FLOAT", "DOUBLE", "FLOAT_32", "FLOAT_64"):
        return _float32_wav_bytes(samples, sr)
    buf = io.BytesIO()
    data = samples.T if samples.ndim == 2 else samples.reshape(-1, 1)
    sf.write(buf, data, sr, subtype=subtype, format="WAV")
    return buf.getvalue()


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Fixture registry — single source of truth for every fixture
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FixtureSpec:
    """Declarative specification of one generated fixture.

    Either ``signal`` (callable returning float32 samples) or ``raw_bytes``
    (callable returning raw file content) must be set — never both.
    """

    name: str
    purpose: str
    subtype: str = "PCM_16"
    sample_rate: int = SR
    channels: int = 1
    seed: int | None = None
    generator: str = ""
    signal: Callable[[], np.ndarray] | None = None
    raw_bytes: Callable[[], bytes] | None = None
    expected_findings: list[str] | None = None
    tags: list[str] = field(default_factory=list)

    def render_bytes(self) -> bytes:
        if self.raw_bytes is not None:
            return self.raw_bytes()
        if self.signal is None:
            raise ValueError(f"fixture {self.name!r} has neither signal nor raw_bytes")
        return wav_bytes(self.signal(), self.sample_rate, self.subtype)


def _s(name: str, purpose: str, gen_name: str, fn: Callable, **kw: Any) -> FixtureSpec:
    kw.setdefault("channels", 2 if (getattr(fn, "__annotations__", {}).get("_stereo")) else 1)
    return FixtureSpec(name=name, purpose=purpose, generator=gen_name, signal=fn, **kw)


#: The canonical fixture set (38 fixtures, byte-compatible with v0.1.0 corpus).
FIXTURE_SPECS: list[FixtureSpec] = [
    # --- core references ---
    FixtureSpec(
        "sine_1k_mono.wav",
        "clean 1 kHz reference",
        generator="gen_sine",
        signal=lambda: gen_sine(1000, channels=1),
    ),
    FixtureSpec(
        "sine_1k_stereo.wav",
        "clean stereo reference",
        channels=2,
        generator="gen_sine",
        signal=lambda: gen_sine(1000, channels=2),
    ),
    FixtureSpec(
        "sine_440.wav", "440 Hz tone", generator="gen_sine", signal=lambda: gen_sine(440, channels=1)
    ),
    FixtureSpec(
        "silence.wav", "digital silence", generator="gen_silence", signal=lambda: gen_silence(channels=1)
    ),
    FixtureSpec(
        "silence_stereo.wav",
        "stereo silence",
        channels=2,
        generator="gen_silence",
        signal=lambda: gen_silence(channels=2),
    ),
    FixtureSpec(
        "white_noise.wav",
        "white noise",
        seed=42,
        generator="gen_white_noise",
        signal=lambda: gen_white_noise(),
    ),
    FixtureSpec(
        "pink_noise.wav", "pink noise", seed=7, generator="gen_pink_noise", signal=lambda: gen_pink_noise()
    ),
    FixtureSpec("clipped.wav", "hard-clipped sine", generator="gen_clipped", signal=lambda: gen_clipped()),
    FixtureSpec(
        "click_500ms.wav", "click at 500ms", generator="gen_click", signal=lambda: gen_click(click_pos_ms=500)
    ),
    FixtureSpec(
        "dropout_50ms.wav",
        "50ms dropout",
        generator="gen_dropout",
        signal=lambda: gen_dropout(dropout_ms=50, start_ms=800),
    ),
    FixtureSpec(
        "dropout_100ms.wav",
        "100ms dropout",
        generator="gen_dropout",
        signal=lambda: gen_dropout(dropout_ms=100, start_ms=800),
    ),
    FixtureSpec(
        "phase_inverted.wav",
        "L=-R phase inverted",
        channels=2,
        generator="gen_phase_inverted_stereo",
        signal=lambda: gen_phase_inverted_stereo(),
    ),
    FixtureSpec(
        "louder_left.wav",
        "L louder than R",
        channels=2,
        generator="gen_louder_left",
        signal=lambda: gen_louder_left(),
    ),
    FixtureSpec(
        "loop_clean.wav", "loop wraps cleanly", generator="gen_loop_clean", signal=lambda: gen_loop_clean()
    ),
    FixtureSpec(
        "loop_discontinuous.wav",
        "loop discontinuous",
        generator="gen_loop_discontinuous",
        signal=lambda: gen_loop_discontinuous(),
    ),
    FixtureSpec("aliasing.wav", "aliasing test", generator="gen_aliasing", signal=lambda: gen_aliasing()),
    FixtureSpec(
        "high_bw_96k.wav",
        "96 kHz high bandwidth",
        sample_rate=96000,
        generator="gen_high_bandwidth",
        signal=lambda: gen_high_bandwidth(sr=96000),
    ),
    FixtureSpec(
        "speech_like.wav",
        "synthetic speech",
        seed=99,
        generator="gen_speech_like",
        signal=lambda: gen_speech_like(),
    ),
    FixtureSpec(
        "sine_1k_24bit.wav",
        "24-bit reference",
        subtype="PCM_24",
        generator="gen_sine",
        signal=lambda: gen_sine(1000, channels=1),
    ),
    FixtureSpec(
        "sine_1k_float32.wav",
        "32-bit float",
        subtype="FLOAT",
        generator="gen_sine",
        signal=lambda: gen_sine(1000, channels=1, amp=0.5),
    ),
    # --- extended (CORP-03) ---
    FixtureSpec(
        "dc_offset.wav", "signal with DC offset", generator="gen_dc_offset", signal=lambda: gen_dc_offset()
    ),
    FixtureSpec(
        "stereo_wide.wav",
        "wide stereo",
        channels=2,
        generator="gen_stereo_wide",
        signal=lambda: gen_stereo_wide(),
    ),
    FixtureSpec(
        "dual_mono.wav",
        "dual mono (L==R)",
        channels=2,
        generator="gen_dual_mono",
        signal=lambda: gen_dual_mono(),
    ),
    FixtureSpec(
        "sine_amped.wav", "high-amplitude sine", generator="gen_sine_amped", signal=lambda: gen_sine_amped()
    ),
    FixtureSpec(
        "low_snr.wav", "low SNR signal", seed=123, generator="gen_low_snr", signal=lambda: gen_low_snr()
    ),
    FixtureSpec(
        "freq_sweep.wav", "log frequency sweep", generator="gen_freq_sweep", signal=lambda: gen_freq_sweep()
    ),
    FixtureSpec(
        "interleaved_noise.wav",
        "periodic noise bursts",
        seed=0,
        generator="gen_interleaved_noise",
        signal=lambda: gen_interleaved_noise(),
    ),
    FixtureSpec(
        "polarity_inverted.wav",
        "polarity flip",
        generator="gen_polarity_inverted",
        signal=lambda: gen_polarity_inverted(),
    ),
    FixtureSpec("short_1s.wav", "1-second signal", generator="gen_short_1s", signal=lambda: gen_short_1s()),
    FixtureSpec(
        "long_30s.wav", "30-second signal", generator="gen_very_long_30s", signal=lambda: gen_very_long_30s()
    ),
    FixtureSpec(
        "two_tone.wav", "440+880 Hz two-tone", generator="gen_two_tone", signal=lambda: gen_two_tone()
    ),
    FixtureSpec(
        "am_modulated.wav", "AM-modulated", generator="gen_modulated_am", signal=lambda: gen_modulated_am()
    ),
    FixtureSpec(
        "violin_like.wav",
        "harmonic violin-like",
        generator="gen_violin_like",
        signal=lambda: gen_violin_like(),
    ),
    FixtureSpec("sine_220.wav", "220 Hz tone", generator="gen_sine", signal=lambda: gen_sine(220)),
    FixtureSpec("sine_8k.wav", "8 kHz tone", generator="gen_sine", signal=lambda: gen_sine(8000)),
    # --- malformed / negative-path ---
    FixtureSpec(
        "truncated.wav",
        "truncated WAV",
        generator="gen_truncated_wav_bytes",
        raw_bytes=lambda: gen_truncated_wav_bytes(20),
    ),
    FixtureSpec(
        "empty.wav",
        "empty file",
        subtype="",
        sample_rate=0,
        channels=0,
        generator="empty_file",
        raw_bytes=lambda: b"",
    ),
    FixtureSpec(
        "audio.txt",
        "non-audio",
        subtype="",
        sample_rate=0,
        channels=0,
        generator="non_audio",
        raw_bytes=lambda: b"not audio",
    ),
]

FIXTURE_SPECS_BY_NAME: dict[str, FixtureSpec] = {s.name: s for s in FIXTURE_SPECS}


def build_manifest() -> dict[str, dict[str, Any]]:
    """Render every fixture and return the manifest dict (in-memory)."""
    manifest: dict[str, dict[str, Any]] = {}
    for spec in FIXTURE_SPECS:
        data = spec.render_bytes()
        entry: dict[str, Any] = {
            "sha256": sha256_of(data),
            "purpose": spec.purpose,
            "subtype": spec.subtype,
            "sample_rate": spec.sample_rate,
            "channels": spec.channels,
            "seed": spec.seed,
            "generator": spec.generator,
        }
        if spec.expected_findings:
            entry["expected_findings"] = list(spec.expected_findings)
        manifest[spec.name] = entry
    return manifest


def write_fixtures(target_dir: Path) -> Path:
    """Write all fixture files + manifest to ``target_dir`` (deterministic)."""
    target_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest()
    for spec in FIXTURE_SPECS:
        (target_dir / spec.name).write_bytes(spec.render_bytes())
    manifest_path = target_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest_path
