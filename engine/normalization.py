"""Decode PCM canônico determinístico."""
import ffmpeg
import numpy as np
from pathlib import Path
from typing import Tuple, Dict, Any
import hashlib

def decode_pcm_canonical(
    filepath: Path,
    sample_rate: int = 48000,
    channels: int = None  # None = preservar
) -> Tuple[np.ndarray, int, int]:
    """
    Decodifica o áudio para PCM float32 @ sample_rate com canais preservados.
    Retorna (pcm_interleaved, sample_rate, channels_out).
    """
    try:
        # Usar ffmpeg-python para construir o pipeline
        args = (
            ffmpeg
            .input(str(filepath))
            .output('pipe:', format='f32le', acodec='pcm_f32le')
            .compile()
        )
        # Adiciona resample se necessário
        if sample_rate != 48000:
            args = (
                ffmpeg
                .input(str(filepath))
                .filter('aformat', sample_rates=str(sample_rate))
                .output('pipe:', format='f32le', acodec='pcm_f32le')
                .compile()
            )

        # Executa ffmpeg
        process = ffmpeg.run_async(
            args,
            pipe_stdout=True,
            pipe_stderr=True,
            overwrite_output=True
        )
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            raise RuntimeError(f"ffmpeg falhou:\n{stderr.decode()}")

        # Determina número de canais original
        probe = ffmpeg.probe(str(filepath))
        audio_streams = [s for s in probe["streams"] if s["codec_type"] == "audio"]
        if not audio_streams:
            raise ValueError("Nenhum stream de áudio no arquivo")
        stream = audio_streams[0]
        ch_out = int(stream.get("channels", 2))
        sr_out = int(stream.get("sample_rate", sample_rate))

        # Lê PCM do stdout
        if not stdout:
            raise ValueError("Nenhum dado PCM retornado pelo ffmpeg")

        # Calcula frames
        bytes_per_sample = 4  # float32
        frame_size = ch_out * bytes_per_sample
        if len(stdout) % frame_size != 0:
            # Trunca para múltiplo
            excess = len(stdout) % frame_size
            stdout = stdout[:-excess] if excess else stdout

        frames = len(stdout) // frame_size
        pcm = np.frombuffer(stdout, dtype=np.float32).reshape((frames, ch_out))

        # Se o usuário pediu canais específicos → downmix/upmix
        if channels is not None and channels != ch_out:
            if channels == 1 and ch_out > 1:
                # Downmix para mono
                pcm = np.mean(pcm, axis=1, keepdims=True)
            elif channels > ch_out:
                # Upmix: repete canal esquerdo
                new_pcm = np.zeros((frames, channels), dtype=np.float32)
                new_pcm[:, 0] = pcm[:, 0] if ch_out > 0 else 0
                pcm = new_pcm

        return pcm, sr_out, channels or ch_out

    except Exception as e:
        raise RuntimeError(f"Falha na normalização PCM: {e}")

def compute_pcm_hash(pcm: np.ndarray) -> str:
    """SHA-256 do buffer PCM (determinístico)."""
    # Garante little-endian, sem metadados
    if pcm.dtype != np.float32:
        pcm = pcm.astype(np.float32)
    return hashlib.sha256(pcm.tobytes()).hexdigest()
