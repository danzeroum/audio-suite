"""Deterministic fixture generator for audio-suite tests.

Every fixture is reproducible: same seed -> same bytes -> same sha256.
Fixtures are written under tests/fixtures/generated/ with a manifest
recording their expected sha256 and intended test purpose.

Run:
    python scripts/gen_fixtures.py
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import soundfile as sf


SR = 44100
DURATION_S = 3.0
N = int(SR * DURATION_S)
FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "generated"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"


def _save(path: Path, samples: np.ndarray, sr: int = SR, subtype: str = "PCM_16") -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    # soundfile expects (frames, channels)
    data = samples.T if samples.ndim == 2 else samples.reshape(-1, 1)
    sf.write(str(path), data, sr, subtype=subtype)
    with open(path, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    return sha


def gen_sine(freq_hz: float = 1000.0, sr: int = SR, dur_s: float = DURATION_S,
             amp: float = 0.5, channels: int = 1) -> np.ndarray:
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


def gen_white_noise(sr: int = SR, dur_s: float = DURATION_S, amp: float = 0.3,
                    channels: int = 1, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    x = (amp * rng.standard_normal(int(sr * dur_s))).astype(np.float32)
    if channels == 2:
        x = np.stack([x, x])
    return x


def gen_pink_noise(sr: int = SR, dur_s: float = DURATION_S, amp: float = 0.3,
                   channels: int = 1, seed: int = 7) -> np.ndarray:
    """Voss-McCartney pink noise approximation."""
    rng = np.random.default_rng(seed)
    n = int(sr * dur_s)
    # 8 octaves
    rows = 8
    base = rng.standard_normal((rows, n))
    # Each row updates every 2^k samples
    out = np.zeros(n)
    for k in range(rows):
        step = 1 << k
        idx = np.arange(0, n, step)
        out += np.repeat(base[k, :len(idx)], step)[:n]
    out = out / np.max(np.abs(out)) * amp
    x = out.astype(np.float32)
    if channels == 2:
        x = np.stack([x, x])
    return x


def gen_clipped(sr: int = SR, dur_s: float = DURATION_S, amp: float = 1.5,
                channels: int = 1) -> np.ndarray:
    """Hard-clipped sine."""
    x = gen_sine(440, sr, dur_s, amp=amp, channels=1)
    x = np.clip(x, -1.0, 1.0)
    if channels == 2:
        x = np.stack([x, x])
    return x


def gen_click(sr: int = SR, dur_s: float = DURATION_S, amp: float = 0.9,
              click_pos_ms: int = 500, channels: int = 1) -> np.ndarray:
    """Sine with a single-sample click inserted."""
    x = gen_sine(440, sr, dur_s, amp=0.3, channels=1)
    pos = int(sr * click_pos_ms / 1000)
    if 0 <= pos < len(x):
        x[pos] = amp
    if channels == 2:
        x = np.stack([x, x])
    return x


def gen_dropout(sr: int = SR, dur_s: float = DURATION_S, dropout_ms: int = 50,
                start_ms: int = 800, channels: int = 1) -> np.ndarray:
    """Sine with a zeroed-out region."""
    x = gen_sine(440, sr, dur_s, amp=0.3, channels=1)
    s = int(sr * start_ms / 1000)
    e = s + int(sr * dropout_ms / 1000)
    x[s:e] = 0.0
    if channels == 2:
        x = np.stack([x, x])
    return x


def gen_phase_inverted_stereo(sr: int = SR, dur_s: float = DURATION_S) -> np.ndarray:
    """L = sine, R = -L (will cancel in mono)."""
    x = gen_sine(440, sr, dur_s, amp=0.3, channels=1)
    return np.stack([x, -x])


def gen_louder_left(sr: int = SR, dur_s: float = DURATION_S) -> np.ndarray:
    """Stereo with L louder than R."""
    L = gen_sine(440, sr, dur_s, amp=0.5, channels=1)
    R = gen_sine(440, sr, dur_s, amp=0.1, channels=1)
    return np.stack([L, R])


def gen_loop_clean(sr: int = SR, dur_s: float = 1.0, freq: float = 220.0) -> np.ndarray:
    """A sine whose period evenly divides the block, so loop wraps cleanly."""
    n = int(sr * dur_s)
    # Make N a multiple of the period so wrap is smooth
    period_samples = int(sr / freq)
    n = (n // period_samples) * period_samples
    t = np.arange(n) / sr
    return (0.3 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def gen_loop_discontinuous(sr: int = SR, dur_s: float = 1.0, freq: float = 220.0) -> np.ndarray:
    """A sine with a deliberate discontinuity at the wrap."""
    x = gen_loop_clean(sr, dur_s, freq)
    # Insert DC offset on second half to break wrap continuity
    half = len(x) // 2
    x[half:] += 0.3
    return x.astype(np.float32)


def gen_aliasing(sr: int = SR, dur_s: float = DURATION_S) -> np.ndarray:
    """Signal that triggers aliasing when downsampled naively."""
    t = np.arange(int(sr * dur_s)) / sr
    # 7 kHz + 19 kHz mix; if downsampled to 22050 without filtering,
    # the 19 kHz component aliases back into audible range.
    x = 0.3 * np.sin(2 * np.pi * 7000 * t) + 0.2 * np.sin(2 * np.pi * 19000 * t)
    return x.astype(np.float32)


def gen_high_bandwidth(sr: int = 96000, dur_s: float = DURATION_S) -> np.ndarray:
    """Signal with content up to 40 kHz (for 96 kHz fixtures)."""
    t = np.arange(int(sr * dur_s)) / sr
    x = 0.3 * np.sin(2 * np.pi * 40000 * t) + 0.3 * np.sin(2 * np.pi * 1000 * t)
    return x.astype(np.float32)


def gen_speech_like(sr: int = SR, dur_s: float = DURATION_S, seed: int = 99) -> np.ndarray:
    """Modulated noise that vaguely resembles voiced speech."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(sr * dur_s)) / sr
    # Pulse train at 150 Hz (F0)
    f0 = 150
    pulse = np.sign(np.sin(2 * np.pi * f0 * t))
    pulse = np.maximum(pulse, 0)
    # Smooth pulse
    from scipy.signal import medfilt
    pulse = medfilt(pulse, kernel_size=11).astype(np.float32)
    # Modulated noise
    noise = rng.standard_normal(len(t)).astype(np.float32) * 0.1
    x = 0.3 * pulse * (1 + noise)
    # Add a sibilant burst (5-10 kHz emphasis)
    sib = rng.standard_normal(len(t)).astype(np.float32) * 0.5
    from scipy.signal import butter, sosfilt
    sos = butter(4, [5000 / (sr / 2), 10000 / (sr / 2)], btype="bandpass", output="sos")
    sib_filtered = sosfilt(sos, sib).astype(np.float32)
    # Sibilant only in [1.0s, 1.2s]
    mask = np.zeros(len(t), dtype=np.float32)
    s = int(sr * 1.0)
    e = int(sr * 1.2)
    mask[s:e] = 1.0
    x = x + 0.4 * sib_filtered * mask
    return x.astype(np.float32)


def gen_truncated_wav(path: Path, valid_bytes: int) -> str:
    """Write a valid WAV then truncate to `valid_bytes`."""
    x = gen_sine(440)
    full = path.parent / (path.stem + "_full.wav")
    _save(full, x)
    with open(full, "rb") as f:
        data = f.read()
    truncated = data[:valid_bytes]
    path.write_bytes(truncated)
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict] = {}

    fixtures = [
        ("sine_1k_mono.wav", gen_sine(1000, channels=1), "PCM_16", "clean 1 kHz reference"),
        ("sine_1k_stereo.wav", gen_sine(1000, channels=2), "PCM_16", "clean stereo reference"),
        ("sine_440.wav", gen_sine(440, channels=1), "PCM_16", "440 Hz tone"),
        ("silence.wav", gen_silence(channels=1), "PCM_16", "digital silence"),
        ("silence_stereo.wav", gen_silence(channels=2), "PCM_16", "stereo silence"),
        ("white_noise.wav", gen_white_noise(), "PCM_16", "white noise"),
        ("pink_noise.wav", gen_pink_noise(), "PCM_16", "pink noise"),
        ("clipped.wav", gen_clipped(), "PCM_16", "hard-clipped sine"),
        ("click_500ms.wav", gen_click(click_pos_ms=500), "PCM_16", "single-sample click at 500ms"),
        ("dropout_50ms.wav", gen_dropout(dropout_ms=50, start_ms=800), "PCM_16", "50ms dropout at 800ms"),
        ("dropout_100ms.wav", gen_dropout(dropout_ms=100, start_ms=800), "PCM_16", "100ms dropout at 800ms"),
        ("phase_inverted.wav", gen_phase_inverted_stereo(), "PCM_16", "L=-R will cancel in mono"),
        ("louder_left.wav", gen_louder_left(), "PCM_16", "L louder than R by ~14 dB"),
        ("loop_clean.wav", gen_loop_clean(), "PCM_16", "loop wraps cleanly"),
        ("loop_discontinuous.wav", gen_loop_discontinuous(), "PCM_16", "loop has DC jump"),
        ("aliasing.wav", gen_aliasing(), "PCM_16", "19 kHz content may alias on bad resampling"),
        ("high_bw_96k.wav", gen_high_bandwidth(sr=96000), "PCM_16", "96 kHz with 40 kHz content"),
        ("speech_like.wav", gen_speech_like(), "PCM_16", "synthetic voice with sibilant burst"),
        ("sine_1k_24bit.wav", gen_sine(1000, channels=1), "PCM_24", "24-bit reference"),
        ("sine_1k_float32.wav", gen_sine(1000, channels=1, amp=0.5), "FLOAT", "32-bit float reference"),
    ]

    for name, samples, subtype, purpose in fixtures:
        path = FIXTURE_DIR / name
        sha = _save(path, samples, subtype=subtype)
        manifest[name] = {
            "sha256": sha,
            "purpose": purpose,
            "subtype": subtype,
            "sample_rate": SR if "96k" not in name else 96000,
            "channels": 2 if samples.ndim == 2 else 1,
        }

    # Truncated fixture (corrupt WAV — truncated below header size)
    trunc_path = FIXTURE_DIR / "truncated.wav"
    trunc_sha = gen_truncated_wav(trunc_path, valid_bytes=20)
    manifest["truncated.wav"] = {
        "sha256": trunc_sha,
        "purpose": "corrupt WAV (truncated below header, <44 bytes)",
        "subtype": "PCM_16",
        "sample_rate": SR,
        "channels": 1,
    }

    # Empty file
    empty_path = FIXTURE_DIR / "empty.wav"
    empty_path.write_bytes(b"")
    manifest["empty.wav"] = {
        "sha256": hashlib.sha256(b"").hexdigest(),
        "purpose": "empty file (should fail decode)",
        "subtype": "",
        "sample_rate": 0,
        "channels": 0,
    }

    # Wrong extension
    bad_ext = FIXTURE_DIR / "audio.txt"
    bad_ext.write_bytes(b"not audio")
    manifest["audio.txt"] = {
        "sha256": hashlib.sha256(b"not audio").hexdigest(),
        "purpose": "non-audio extension (should fail decode)",
        "subtype": "",
        "sample_rate": 0,
        "channels": 0,
    }

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"Generated {len(manifest)} fixtures in {FIXTURE_DIR}")
    print(f"Manifest: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
