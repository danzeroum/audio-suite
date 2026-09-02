"""Identifica metadados de mídia a partir do arquivo."""
import ffmpeg
import hashlib
from pathlib import Path
from typing import Dict, Any

def probe_media(filepath: Path) -> Dict[str, Any]:
    """Retorna metadados do arquivo via ffmpeg probe."""
    try:
        probe = ffmpeg.probe(str(filepath))
        audio_streams = [
            s for s in probe.get("streams", []) if s.get("codec_type") == "audio"
        ]
        if not audio_streams:
            raise ValueError("Nenhum stream de áudio encontrado")

        stream = audio_streams[0]
        tags = stream.get("tags", {})

        return {
            "format": probe.get("format", {}).get("format_name"),
            "duration_s": float(probe.get("format", {}).get("duration", "0")),
            "size_bytes": int(probe.get("format", {}).get("size", "0")),
            "bit_rate_bps": int(probe.get("format", {}).get("bit_rate", "0")),
            "audio_codec": stream.get("codec_name"),
            "sample_rate_hz": int(stream.get("sample_rate", "0")),
            "channels": int(stream.get("channels", "0")),
            "channel_layout": stream.get("channel_layout"),
            "tags": tags
        }
    except Exception as e:
        raise RuntimeError(f"Falha no probe ffmpeg: {e}")

def detect_pii_in_tags(tags: Dict[str, str]) -> Dict[str, Any]:
    """Busca PII em tags de metadados. Retorna findings."""
    import re
    findings = []
    pii_patterns = {
        "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "phone": r"(?:\+?55)?[ -]?[1-9][0-9][ -]?(?:[0-9]{4}-?[0-9]{4}|[0-9]{8,9})"
    }

    for tag_name, tag_value in tags.items():
        for pii_type, pattern in pii_patterns.items():
            if re.search(pattern, str(tag_value), re.IGNORECASE):
                findings.append({
                    "id": f"MD-{pii_type.upper()}-{tag_name.upper()}",
                    "name": f"PII detectado em tag '{tag_name}'",
                    "value": tag_value,
                    "unit": None,
                    "threshold": f"Pattern {pii_type}",
                    "status": "fail",
                    "severity": "error",
                    "description": f"Valor da tag '{tag_name}' contém possível {pii_type} pessoal."
                })
    return findings
