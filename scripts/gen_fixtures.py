"""Deterministic fixture generator for audio-suite tests."""
from __future__ import annotations

import hashlib
import io
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
    data = samples.T if samples.ndim == 2 else samples.reshape(-1, 1)
    sf.write(str(path), data, sr, subtype=subtype)
    with open(str(path), "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    return sha


def _save_wav_bytes(samples: np.ndarray, sr: int = SR, subtype: str = "PCM_16") -> bytes:
    """Write WAV to bytes buffer (avoids filesystem issues on CI)."""
    buf = io.BytesIO()
    data = samples.T if samples.ndim == 2 else samples.reshape(-1, 1)
    sf.write(buf, data, sr, subtype=subtype, format="WAV")
    return buf.getvalue()


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
    rng = np.random.default_rng(seed)
    n = int(sr * dur_s)
    rows = 8
    base = rng.standard_normal((rows, n))
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
    x = gen_sine(440, sr, dur_s, amp=amp, channels=1)
    x = np.clip(x, -1.0, 1.0)
    if channels == 2:
        x = np.stack([x, x])
    return x


def gen_click(sr: int = SR, dur_s: float = DURATION_S, amp: float = 0.9,
              click_pos_ms: int = 500, channels: int = 1) -> np.ndarray:
    x = gen_sine(440, sr, dur_s, amp=0.3, channels=1)
    pos = int(sr * click_pos_ms / 1000)
    if 0 <= pos < len(x):
        x[pos] = amp
    if channels == 2:
        x = np.stack([x, x])
    return x


def gen_dropout(sr: int = SR, dur_s: float = DURATION_S, dropout_ms: int = 50,
                start_ms: int = 800, channels: int = 1) -> np.ndarray:
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
    rng = np.random.default_rng(seed)
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


def gen_truncated_wav(path: Path, valid_bytes: int) -> str:
    """Write WAV bytes then truncate. Uses BytesIO to avoid filesystem issues."""
    x = gen_sine(440)
    full_data = _save_wav_bytes(x)
    truncated = full_data[:valid_bytes]
    path.write_bytes(truncated)
    with open(str(path), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


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

def gen_low_snr(sr=SR, dur_s=DURATION_S):
    rng = np.random.default_rng(123)
    t = np.arange(int(sr * dur_s)) / sr
    signal = 0.05 * np.sin(2 * np.pi * 1000 * t)
    noise = 0.3 * rng.standard_normal(len(t))
    return (signal + noise).astype(np.float32)

def gen_freq_sweep(sr=SR, dur_s=DURATION_S, f0=100, f1=8000):
    t = np.arange(int(sr * dur_s)) / sr
    freq = f0 * (f1 / f0) ** (t / dur_s)
    phase = 2 * np.pi * np.cumsum(freq) / sr
    return (0.3 * np.sin(phase)).astype(np.float32)

def gen_interleaved_noise(sr=SR, dur_s=DURATION_S):
    t = np.arange(int(sr * dur_s)) / sr
    x = 0.3 * np.sin(2 * np.pi * 440 * t)
    for i in range(0, int(dur_s * 2)):
        start = int(i * sr * 0.5)
        end = start + int(sr * 0.01)
        if end < len(x):
            x[start:end] += 0.5 * np.random.default_rng(i).standard_normal(end - start)
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
    x = (0.3 * np.sin(2*np.pi*f*t) + 0.15*np.sin(2*np.pi*2*f*t) +
         0.1*np.sin(2*np.pi*3*f*t) + 0.05*np.sin(2*np.pi*4*f*t))
    vibrato = 0.02 * np.sin(2 * np.pi * 5 * t)
    return (x * (1 + vibrato)).astype(np.float32)


def get_extended_fixtures():
    return [
        ("dc_offset.wav", gen_dc_offset(), "PCM_16", "signal with DC offset"),
        ("stereo_wide.wav", gen_stereo_wide(), "PCM_16", "wide stereo"),
        ("dual_mono.wav", gen_dual_mono(), "PCM_16", "dual mono (L==R)"),
        ("sine_amped.wav", gen_sine_amped(), "PCM_16", "high-amplitude sine"),
        ("low_snr.wav", gen_low_snr(), "PCM_16", "low SNR signal"),
        ("freq_sweep.wav", gen_freq_sweep(), "PCM_16", "log frequency sweep"),
        ("interleaved_noise.wav", gen_interleaved_noise(), "PCM_16", "periodic noise bursts"),
        ("polarity_inverted.wav", gen_polarity_inverted(), "PCM_16", "polarity flip"),
        ("short_1s.wav", gen_short_1s(), "PCM_16", "1-second signal"),
        ("long_30s.wav", gen_very_long_30s(), "PCM_16", "30-second signal"),
        ("two_tone.wav", gen_two_tone(), "PCM_16", "440+880 Hz two-tone"),
        ("am_modulated.wav", gen_modulated_am(), "PCM_16", "AM-modulated"),
        ("violin_like.wav", gen_violin_like(), "PCM_16", "harmonic violin-like"),
        ("sine_220.wav", gen_sine(220), "PCM_16", "220 Hz tone"),
        ("sine_8k.wav", gen_sine(8000), "PCM_16", "8 kHz tone"),
    ]


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
        ("click_500ms.wav", gen_click(click_pos_ms=500), "PCM_16", "click at 500ms"),
        ("dropout_50ms.wav", gen_dropout(dropout_ms=50, start_ms=800), "PCM_16", "50ms dropout"),
        ("dropout_100ms.wav", gen_dropout(dropout_ms=100, start_ms=800), "PCM_16", "100ms dropout"),
        ("phase_inverted.wav", gen_phase_inverted_stereo(), "PCM_16", "L=-R phase inverted"),
        ("louder_left.wav", gen_louder_left(), "PCM_16", "L louder than R"),
        ("loop_clean.wav", gen_loop_clean(), "PCM_16", "loop wraps cleanly"),
        ("loop_discontinuous.wav", gen_loop_discontinuous(), "PCM_16", "loop discontinuous"),
        ("aliasing.wav", gen_aliasing(), "PCM_16", "aliasing test"),
        ("high_bw_96k.wav", gen_high_bandwidth(sr=96000), "PCM_16", "96 kHz high bandwidth"),
        ("speech_like.wav", gen_speech_like(), "PCM_16", "synthetic speech"),
        ("sine_1k_24bit.wav", gen_sine(1000, channels=1), "PCM_24", "24-bit reference"),
        ("sine_1k_float32.wav", gen_sine(1000, channels=1, amp=0.5), "FLOAT", "32-bit float"),
    ]

    for name, samples, subtype, purpose in fixtures:
        path = FIXTURE_DIR / name
        sha = _save(path, samples, subtype=subtype)
        manifest[name] = {
            "sha256": sha, "purpose": purpose, "subtype": subtype,
            "sample_rate": SR if "96k" not in name else 96000,
            "channels": 2 if samples.ndim == 2 else 1,
        }

    # Truncated
    trunc_path = FIXTURE_DIR / "truncated.wav"
    trunc_sha = gen_truncated_wav(trunc_path, valid_bytes=20)
    manifest["truncated.wav"] = {"sha256": trunc_sha, "purpose": "truncated WAV", "subtype": "PCM_16", "sample_rate": SR, "channels": 1}

    # Empty
    empty_path = FIXTURE_DIR / "empty.wav"
    empty_path.write_bytes(b"")
    manifest["empty.wav"] = {"sha256": hashlib.sha256(b"").hexdigest(), "purpose": "empty file", "subtype": "", "sample_rate": 0, "channels": 0}

    # Bad extension
    bad_ext = FIXTURE_DIR / "audio.txt"
    bad_ext.write_bytes(b"not audio")
    manifest["audio.txt"] = {"sha256": hashlib.sha256(b"not audio").hexdigest(), "purpose": "non-audio", "subtype": "", "sample_rate": 0, "channels": 0}

    # Extended
    for name, samples, subtype, purpose in get_extended_fixtures():
        path = FIXTURE_DIR / name
        sha = _save(path, samples, subtype=subtype)
        manifest[name] = {"sha256": sha, "purpose": purpose, "subtype": subtype, "sample_rate": SR, "channels": 2 if samples.ndim == 2 else 1}

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"Generated {len(manifest)} fixtures in {FIXTURE_DIR}")
    print(f"Manifest: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
