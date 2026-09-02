"""Gera e salva o bundle de evidência."""
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, List

def build_bundle(
    input_audio: Path,
    policy: Dict[str, Any],
    findings: List[Dict],
    provenance: Dict[str, Any],
    pcm_canonical_sha256: str,
    decoder_info: Dict[str, Any],
    decision: str,
    dry_run: bool = False
) -> Dict[str, Any]:
    """Constrói o evidence bundle JSON."""
    from datetime import datetime

    # Subject hash
    file_sha256 = hashlib.sha256(open(input_audio, "rb").read()).hexdigest()

    bundle = {
        "schema": "audio-evidence-bundle/1.0",
        "subject": {
            "path": str(input_audio),
            "file_sha256": file_sha256,
            "pcm_canonical_sha256": pcm_canonical_sha256
        },
        "execution": {
            "suite_version": "audio-suite/0.1.0-alpha",
            "profile": policy.get("name"),
            "profile_sha256": policy.get("_profile_sha256"),
            "decoder": decoder_info.get("decoder"),
            "ffmpeg_version": decoder_info.get("ffmpeg_version"),
            "sample_rate_hz": 48000,
            "status": "completed",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        },
        "findings": findings,
        "provenance": provenance,
        "decision": decision,
        "signature": {
            "status": "unsigned",
            "reason": "Alpha não gera assinatura; use modo CI com chave secreta em v1.0"
        }
    }
    return bundle

def save_bundle(bundle: Dict[str, Any], output_path: Path):
    """Salva bundle JSON com pretty-print."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, indent=2)
