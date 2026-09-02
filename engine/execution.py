"""Orquestrador de validação."""
import importlib
import sys
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Tuple

from .discovery import probe_media, detect_pii_in_tags
from .normalization import decode_pcm_canonical, compute_pcm_hash
from .policy import apply_policy

def run_validation(
    input_audio: Path,
    policy: Dict[str, Any],
    dry_run: bool = False,
    verbose: bool = False
) -> Tuple[List[Dict], Dict, str, Dict]:
    """
    Executa o pipeline completo de validação.
    Retorna: (findings, provenance, pcm_hash, decoder_info)
    """
    import time

    start_time = time.time()

    # 1. Discovery
    media_info = probe_media(input_audio)
    decoder_info = {
        "decoder": "ffmpeg",
        "ffmpeg_version": "git-2024-07-01",  # Fixar para determinismo
        "decode_timestamp": int(start_time)
    }

    # 2. Normalização PCM
    pcm, actual_sr, ch = decode_pcm_canonical(input_audio, sample_rate=48000)
    pcm_hash = compute_pcm_hash(pcm)

    # 3. Executa analyzers declarados no profile
    findings = []

    # Metadados primeiro (PII em tags)
    tag_pii_findings = detect_pii_in_tags(media_info.get("tags", {}))
    findings.extend(tag_pii_findings)

    # Analyzers
    analyzer_paths = {
        "loudness": "analyzers.loudness",
        "signal": "analyzers.signal",
        "metadata": "analyzers.metadata",
        "regression": "analyzers.regression",
        "similarity": "analyzers.similarity",
        "speech": "analyzers.speech"
    }

    # Carrega analyzers do sys.path (repo raiz)
    for check in policy.get("checks", []):
        analyzer_id = check.get("analyzer")
        if not analyzer_id or analyzer_id not in analyzer_paths:
            continue

        try:
            module_path = analyzer_paths[analyzer_id]
            module = importlib.import_module(module_path)
            if hasattr(module, "run_analyzer"):
                # Passa PCM, params do profile, media_info
                analyzer_findings = module.run_analyzer(
                    pcm=pcm,
                    media_info=media_info,
                    params=check.get("params", {}),
                    verbose=verbose
                )
                # Adiciona ID e nome do check aos findings
                for f in analyzer_findings:
                    if "id" not in f:
                        f["id"] = f"{analyzer_id.upper()}-{check.get('id', '00')}"
                    if "name" not in f:
                        f["name"] = f"{analyzer_id} ({check.get('id', '')})"
                    if "severity" not in f:
                        f["severity"] = check.get("severity", "info")
                findings.extend(analyzer_findings)
            else:
                if verbose:
                    print(f"Analyzer {analyzer_id} não tem run_analyzer()")
        except Exception as e:
            if verbose:
                print(f"❌ Analyzer {analyzer_id} falhou: {e}")
            findings.append({
                "id": f"{analyzer_id.upper()}-ERR",
                "name": f"{analyzer_id} — erro de execução",
                "value": str(e),
                "status": "indeterminate",
                "severity": "error",
                "description": "Analyzer falhou durante execução"
            })

    # 4. Provenance (declaração mínima)
    provenance = {
        "events": [{
            "event_type": "decode_canonical",
            "input_sha256": hashlib.sha256(open(input_audio, "rb").read()).hexdigest(),
            "output_pcm_sha256": pcm_hash,
            "decoder": decoder_info["decoder"],
            "timestamp": int(time.time())
        }]
    }

    # 5. Decisão
    # (feita no CLI após receber findings)

    return findings, provenance, pcm_hash, decoder_info
