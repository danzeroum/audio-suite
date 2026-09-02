"""Audio container decoding into canonical PCM.

Supports WAV (PCM 16/24/32-bit, float32), FLAC, and MP3 via soundfile/libsndfile.
For formats libsndfile cannot handle, falls back to ffmpeg subprocess.

Decoding is deterministic: the same file always produces the same float32 PCM
and the same file_sha256. No hidden resampling — if the source is 44100 Hz,
we keep 44100 Hz (CT: resampling must be explicit).
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from .models import PCM

SUPPORTED_EXTENSIONS = {".wav", ".flac", ".mp3", ".ogg", ".aiff", ".aif"}


class DecodeError(Exception):
    """Raised when an audio file cannot be decoded."""


def sha256_of_file(path: str | os.PathLike) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def detect_format(path: str | os.PathLike) -> str:
    ext = Path(path).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise DecodeError(f"unsupported extension: {ext}")
    return ext.lstrip(".")


def _layout_from_channels(n: int) -> str:
    return {1: "mono", 2: "stereo", 6: "5.1", 8: "7.1"}.get(n, f"custom-{n}ch")


def decode(path: str | os.PathLike, *, target_sr: int | None = None) -> PCM:
    """Decode an audio file into canonical PCM.

    Args:
        path: filesystem path to the audio file.
        target_sr: if set, explicit resample target. If None, keep source sr
                   (resampling must be opt-in — never silent).

    Returns:
        PCM dataclass with float32 samples in [-1, 1).

    Raises:
        DecodeError: if the file is missing, empty, truncated or unparseable.
    """
    p = Path(path)
    if not p.exists():
        raise DecodeError(f"file does not exist: {path}")
    if p.stat().st_size == 0:
        raise DecodeError(f"file is empty: {path}")

    file_sha = sha256_of_file(p)
    fmt = detect_format(p)

    # Try libsndfile first (WAV/FLAC/OGG/AIFF). Falls back to ffmpeg for MP3
    # if libsndfile can't read it.
    samples: np.ndarray | None = None
    sr: int = 0
    subtype: str = ""
    provenance: dict[str, Any] = {}

    try:
        info = sf.info(str(p))
        # Read full file
        data, sr = sf.read(str(p), always_2d=True, dtype="float32")
        samples = data.T  # shape (channels, frames)
        subtype = info.subtype
        provenance = {
            "container": info.format,
            "subtype": info.subtype,
            "bit_depth": _bit_depth_from_subtype(info.subtype),
            "decoder": "libsndfile",
            "frames": info.frames,
            "channels": info.channels,
        }
    except Exception as exc:
        if fmt == "mp3":
            # Fallback: ffmpeg -> wav -> libsndfile
            samples, sr, subtype, provenance = _decode_via_ffmpeg(p)
        else:
            raise DecodeError(f"libsndfile failed on {path}: {exc}") from exc

    if samples is None or sr == 0:
        raise DecodeError(f"decoding produced no samples: {path}")

    # Explicit resampling (opt-in only)
    if target_sr is not None and target_sr != sr:
        samples = _resample(samples, sr, target_sr)
        provenance["resampled_from"] = sr
        provenance["resampled_to"] = target_sr
        sr = target_sr

    layout = _layout_from_channels(samples.shape[0])
    provenance["format"] = fmt

    return PCM(
        samples=samples,
        sample_rate=int(sr),
        channel_layout=layout,
        file_sha256=file_sha,
        source_path=str(p),
        provenance=provenance,
    )


def _decode_via_ffmpeg(p: Path) -> tuple[np.ndarray, int, str, dict[str, Any]]:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_wav = Path(tmp.name)
    try:
        # Decode to 32-bit float WAV
        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(p),
            "-acodec",
            "pcm_f32le",
            "-f",
            "wav",
            str(tmp_wav),
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        if result.returncode != 0:
            raise DecodeError(f"ffmpeg failed: {result.stderr.decode('utf-8', 'replace')}")
        data, sr = sf.read(str(tmp_wav), always_2d=True, dtype="float32")
        samples = data.T
        info = sf.info(str(tmp_wav))
        prov = {
            "container": info.format,
            "subtype": info.subtype,
            "bit_depth": 32,
            "decoder": "ffmpeg+libsndfile",
            "frames": info.frames,
            "channels": info.channels,
        }
        return samples, sr, info.subtype, prov
    finally:
        try:
            tmp_wav.unlink()
        except OSError:
            pass


def _bit_depth_from_subtype(subtype: str) -> int:
    s = subtype.lower()
    if "float" in s:
        return 32
    if "double" in s:
        return 64
    if "24" in s:
        return 24
    if "16" in s:
        return 16
    if "32" in s:
        return 32
    if "u8" in s or "8" in s:
        return 8
    return 0


def _resample(samples: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    """Polyphase resampling (scipy.signal.resample_poly).

    Deterministic and phase-linear. Used only when explicitly requested.
    """
    from math import gcd

    from scipy.signal import resample_poly

    g = gcd(int(sr_from), int(sr_to))
    up = int(sr_to) // g
    down = int(sr_from) // g
    out = np.stack([resample_poly(samples[c], up, down) for c in range(samples.shape[0])])
    return out.astype(np.float32, copy=False)
