"""Discovery: probe de mídia + detecção de PII + redação.

Módulos:
- probe_media: coleta metadados via ffmpeg (fallback audioread/soundfile).
- detect_pii_in_tags: regex para email/telefone em tags.
- redact_pii_in_findings: substitui PII por placeholder antes de persistir
  no bundle (O9).
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Probe de mídia
# ---------------------------------------------------------------------------

def probe_media(filepath: Path) -> dict[str, Any]:
    """Retorna metadados do arquivo via ffmpeg probe.

    Em ambientes sem ffmpeg, callers devem capturar RuntimeError e tratar.
    """
    try:
        import ffmpeg
    except ImportError as exc:
        raise RuntimeError("ffmpeg-python não disponível") from exc

    try:
        probe = ffmpeg.probe(str(filepath))
    except Exception as exc:
        raise RuntimeError(f"Falha no probe ffmpeg: {exc}") from exc

    audio_streams = [s for s in probe.get("streams", []) if s.get("codec_type") == "audio"]
    if not audio_streams:
        raise ValueError("Nenhum stream de áudio encontrado")

    stream = audio_streams[0]
    tags = stream.get("tags", {})
    fmt = probe.get("format", {})

    return {
        "format": fmt.get("format_name"),
        "duration_s": float(fmt.get("duration", "0") or "0"),
        "size_bytes": int(fmt.get("size", "0") or "0"),
        "bit_rate_bps": int(fmt.get("bit_rate", "0") or "0"),
        "audio_codec": stream.get("codec_name"),
        "sample_rate_hz": int(stream.get("sample_rate", "0") or "0"),
        "channels": int(stream.get("channels", "0") or "0"),
        "channel_layout": stream.get("channel_layout"),
        "bits_per_sample": int(stream.get("bits_per_sample", "0") or "0"),
        "tags": tags,
    }


def probe_media_fallback(filepath: Path) -> dict[str, Any]:
    """Fallback quando ffmpeg não está disponível (S3).

    Usa soundfile (se instalado) ou wave (stdlib). Sem hash PCM canônico
    equivalente ao ffmpeg; declara `decoder: fallback` no bundle.
    """
    try:
        import soundfile as sf
        info = sf.info(str(filepath))
        return {
            "format": info.format,
            "duration_s": info.duration,
            "size_bytes": filepath.stat().st_size,
            "bit_rate_bps": 0,
            "audio_codec": info.subtype,
            "sample_rate_hz": info.samplerate,
            "channels": info.channels,
            "channel_layout": "mono" if info.channels == 1 else "stereo",
            "bits_per_sample": 0,
            "tags": {},
        }
    except ImportError:
        pass

    # último recurso: wave stdlib (WAV apenas)
    import wave
    try:
        with wave.open(str(filepath), "rb") as wf:
            return {
                "format": "wav",
                "duration_s": wf.getnframes() / float(wf.getframerate() or 1),
                "size_bytes": filepath.stat().st_size,
                "bit_rate_bps": 0,
                "audio_codec": f"pcm_s{wf.getsampwidth()*8}le",
                "sample_rate_hz": wf.getframerate(),
                "channels": wf.getnchannels(),
                "channel_layout": "mono" if wf.getnchannels() == 1 else "stereo",
                "bits_per_sample": wf.getsampwidth() * 8,
                "tags": {},
            }
    except Exception as exc:
        raise RuntimeError(f"Falha no probe fallback: {exc}") from exc


# ---------------------------------------------------------------------------
# Detecção de PII
# ---------------------------------------------------------------------------

PII_PATTERNS: dict[str, str] = {
    "email": r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    # Phone: +55 11 98765-4321, (11) 98765-4321, 11987654321, etc.
    "phone": r"(?:\+?55\s?)?\(?\d{2}\)?\s?9?\d{4}\-?\d{4}",
    "cpf": r"\b\d{3}\.?\d{3}\.?\d{3}\-?\d{2}\b",
}


def detect_pii_in_tags(tags: dict[str, Any]) -> list[dict[str, Any]]:
    """Busca PII em tags de metadados. Retorna findings (sem redação aqui).

    A redação é aplicada posteriormente por `redact_pii_in_findings` antes
    de persistir o bundle (O9).
    """
    findings: list[dict[str, Any]] = []
    for tag_name, tag_value in tags.items():
        text = str(tag_value)
        for pii_type, pattern in PII_PATTERNS.items():
            if re.search(pattern, text, re.IGNORECASE):
                findings.append({
                    "id": f"MD-PII-{pii_type.upper()}-{str(tag_name).upper()[:32]}",
                    "name": f"PII detectado em tag '{tag_name}'",
                    "value": text,  # será redigido depois
                    "unit": None,
                    "threshold": f"pattern:{pii_type}",
                    "status": "fail",
                    "severity": "error",
                    "description": (
                        f"Tag '{tag_name}' contém possível {pii_type} pessoal. "
                        "O valor original será redigido no bundle."
                    ),
                    "pii_type": pii_type,
                })
    return findings


# ---------------------------------------------------------------------------
# Redação de PII (O9)
# ---------------------------------------------------------------------------

def _redact_value(text: str, pii_type: str) -> str:
    if pii_type == "email":
        return re.sub(
            PII_PATTERNS["email"],
            "***@***.**",
            text,
            flags=re.IGNORECASE,
        )
    if pii_type == "phone":
        return re.sub(
            PII_PATTERNS["phone"],
            "+** ** ****-****",
            text,
        )
    if pii_type == "cpf":
        return re.sub(
            PII_PATTERNS["cpf"],
            "***.***.***-**",
            text,
        )
    return text


def redact_pii_in_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Substitui valores de PII por placeholder em todos os findings.

    Preserva o hash do valor original (SHA-256, truncado) para correlação
    forense sem expor o dado.
    """
    redacted: list[dict[str, Any]] = []
    for f in findings:
        new_f = dict(f)
        pii_type = f.get("pii_type")
        if pii_type and isinstance(f.get("value"), str):
            original = f["value"]
            # hash curto para correlação
            digest = hashlib.sha256(original.encode("utf-8")).hexdigest()[:12]
            new_f["value"] = _redact_value(original, pii_type)
            new_f["pii_value_sha256_short"] = digest
            new_f["pii_redacted"] = True
        redacted.append(new_f)
    return redacted
