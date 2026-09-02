"""Normalization: decode PCM canônico + fallback + proteções degeneradas (O8).

Decodifica qualquer formato suportado pelo ffmpeg para PCM float32 @ 48kHz,
com canais preservados. Em ambientes sem ffmpeg, cai para fallback
(soundfile/wave) e declara essa condição via `decoder_used`.

Trata entradas degeneradas (O8):
- 0 amostras → retorna array vazio + flag
- NaN/Inf → sanitizado para 0.0 + flag
- sample_rate inválido → erro explícito
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np


class DegenerateInputError(RuntimeError):
    """Levantada quando o input é degenerado a ponto de invalidar a análise."""


def decode_pcm_canonical(
    filepath: Path,
    sample_rate: int = 48000,
    channels: int | None = None,
) -> tuple[np.ndarray, int, int, dict[str, Any]]:
    """Decodifica para PCM float32 @ sample_rate.

    Returns
    -------
    (pcm, sample_rate_out, channels_out, meta)
        meta contém: decoder_used ("ffmpeg" | "fallback"),
        fallback_reason (str | None), nan_sanitized (bool), empty (bool).
    """
    if sample_rate <= 0:
        raise DegenerateInputError(f"sample_rate inválido: {sample_rate}")

    last_error: Exception | None = None
    try:
        pcm, sr_out, ch_out = _decode_with_ffmpeg(filepath, sample_rate, channels)
        meta: dict[str, Any] = {
            "decoder_used": "ffmpeg",
            "fallback_reason": None,
        }
        return _sanitize(pcm, sr_out, ch_out, meta)
    except Exception as exc:
        last_error = exc

    # Fallback (S3) — sem garantia de hash idêntico ao ffmpeg
    try:
        pcm, sr_out, ch_out = _decode_with_fallback(filepath, sample_rate, channels)
        meta = {
            "decoder_used": "fallback",
            "fallback_reason": f"ffmpeg indisponível ou falhou: {last_error}",
        }
        return _sanitize(pcm, sr_out, ch_out, meta)
    except Exception as exc:
        raise RuntimeError(
            f"Falha na normalização PCM (ffmpeg e fallback): {exc}"
        ) from exc


def _decode_with_ffmpeg(
    filepath: Path,
    sample_rate: int,
    channels: int | None,
) -> tuple[np.ndarray, int, int]:
    import ffmpeg

    args = (
        ffmpeg.input(str(filepath))
        .output("pipe:", format="f32le", acodec="pcm_f32le", ar=sample_rate)
        .compile()
    )
    process = ffmpeg.run_async(
        args, pipe_stdout=True, pipe_stderr=True, overwrite_output=True
    )
    stdout, stderr = process.communicate()
    if process.returncode != 0:
        raise RuntimeError(f"ffmpeg falhou: {stderr.decode(errors='replace')}")

    probe = ffmpeg.probe(str(filepath))
    audio_streams = [s for s in probe["streams"] if s["codec_type"] == "audio"]
    if not audio_streams:
        raise ValueError("Nenhum stream de áudio no arquivo")
    stream = audio_streams[0]
    ch_out = int(stream.get("channels", 2) or 2)
    sr_out = sample_rate  # forçamos o resample

    if not stdout:
        return np.zeros((0, ch_out), dtype=np.float32), sr_out, ch_out

    bytes_per_sample = 4
    frame_size = ch_out * bytes_per_sample
    if len(stdout) % frame_size != 0:
        excess = len(stdout) % frame_size
        stdout = stdout[:-excess] if excess else stdout

    frames = len(stdout) // frame_size
    pcm = np.frombuffer(stdout, dtype=np.float32).reshape((frames, ch_out))

    if channels is not None and channels != ch_out:
        if channels == 1 and ch_out > 1:
            pcm = np.mean(pcm, axis=1, keepdims=True)
        elif channels > ch_out:
            new_pcm = np.zeros((frames, channels), dtype=np.float32)
            new_pcm[:, 0] = pcm[:, 0] if ch_out > 0 else 0
            pcm = new_pcm

    return pcm, sr_out, channels or ch_out


def _decode_with_fallback(
    filepath: Path,
    sample_rate: int,
    channels: int | None,
) -> tuple[np.ndarray, int, int]:
    """Fallback: lê via soundfile ou wave stdlib + resample ingênuo."""
    try:
        import soundfile as sf
        data, sr_in = sf.read(str(filepath), dtype="float32", always_2d=True)
        ch_in = data.shape[1] if data.ndim == 2 else 1
    except ImportError:
        data, sr_in, ch_in = _read_wav_stdlib(filepath)

    if data.size == 0:
        return np.zeros((0, ch_in), dtype=np.float32), sample_rate, ch_in

    # resample linear simples (não é tão bom quanto ffmpeg, mas funciona)
    if sr_in != sample_rate:
        ratio = sample_rate / sr_in
        new_len = max(1, int(len(data) * ratio))
        indices = np.linspace(0, len(data) - 1, new_len)
        if data.ndim == 2:
            data = np.stack([
                np.interp(indices, np.arange(len(data)), data[:, c])
                for c in range(data.shape[1])
            ], axis=1).astype(np.float32)
        else:
            data = np.interp(indices, np.arange(len(data)), data).astype(np.float32)

    if data.ndim == 1:
        data = data.reshape(-1, 1)

    if channels is not None and channels != data.shape[1]:
        if channels == 1 and data.shape[1] > 1:
            data = np.mean(data, axis=1, keepdims=True)

    return data.astype(np.float32), sample_rate, data.shape[1]


def _read_wav_stdlib(filepath: Path) -> tuple[np.ndarray, int, int]:
    import wave
    with wave.open(str(filepath), "rb") as wf:
        n = wf.getnframes()
        ch = wf.getnchannels()
        sw = wf.getsampwidth()
        sr = wf.getframerate()
        raw = wf.readframes(n)

    if sw == 1:
        a = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        a = (a - 128.0) / 128.0
    elif sw == 2:
        a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sw == 4:
        a = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise DegenerateInputError(f"sample width não suportado: {sw}")

    if ch > 1:
        a = a.reshape(-1, ch)
    else:
        a = a.reshape(-1, 1)
    return a, sr, ch


def _sanitize(
    pcm: np.ndarray,
    sr_out: int,
    ch_out: int,
    meta: dict[str, Any],
) -> tuple[np.ndarray, int, int, dict[str, Any]]:
    """Sanitiza NaN/Inf e marca entradas degeneradas (O8)."""
    if pcm.size == 0:
        meta["empty"] = True
        meta["nan_sanitized"] = False
        return pcm, sr_out, ch_out, meta

    has_nan = bool(np.any(np.isnan(pcm)))
    has_inf = bool(np.any(np.isinf(pcm)))
    if has_nan or has_inf:
        pcm = np.nan_to_num(pcm, nan=0.0, posinf=0.0, neginf=0.0)
        meta["nan_sanitized"] = True
    else:
        meta["nan_sanitized"] = False

    meta["empty"] = False
    return pcm, sr_out, ch_out, meta


def compute_pcm_hash(pcm: np.ndarray) -> str:
    """SHA-256 do buffer PCM (determinístico)."""
    if pcm.dtype != np.float32:
        pcm = pcm.astype(np.float32)
    return hashlib.sha256(pcm.tobytes()).hexdigest()


def compute_file_hash(filepath: Path, algorithm: str = "sha256") -> str:
    """Hash de arquivo streaming (para TOCTOU)."""
    h = hashlib.new(algorithm)
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
