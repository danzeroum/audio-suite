"""Execution: orquestra validação com TOCTOU (O1) + timeout por analyzer (O2)."""
from __future__ import annotations

import concurrent.futures
import importlib
import time
import traceback
from pathlib import Path
from typing import Any

from .discovery import detect_pii_in_tags, probe_media, probe_media_fallback, redact_pii_in_findings
from .normalization import (
    DegenerateInputError,
    compute_file_hash,
    compute_pcm_hash,
    decode_pcm_canonical,
)

ANALYZER_PATHS: dict[str, str] = {
    "loudness": "analyzers.loudness",
    "signal": "analyzers.signal",
    "metadata": "analyzers.metadata",
    "phase": "analyzers.phase",
    "provenance": "analyzers.provenance",
    "rights_manifest": "analyzers.rights_manifest",
    "regression": "analyzers.regression",
    "similarity": "analyzers.similarity",
    "speech": "analyzers.speech",
}

DEFAULT_ANALYZER_TIMEOUT_S = 60.0


class ExecutionResult:
    """Resultado da execução do pipeline."""

    def __init__(self) -> None:
        self.findings: list[dict[str, Any]] = []
        self.provenance: dict[str, Any] = {"events": []}
        self.pcm_hash: str = ""
        self.decoder_info: dict[str, Any] = {}
        self.decoder_used: str = "ffmpeg"
        self.has_nan_sanitized: bool = False
        self.is_empty: bool = False
        self.toctou_detected: bool = False
        self.had_timeout: list[str] = []
        self.truncated_analyzers: list[str] = []
        self.phase_skipped_mono: bool = False
        self.rights_manifest_missing: bool = False
        self.provenance_partial: bool = False
        self.media_info: dict[str, Any] = {}
        self.pcm: Any = None
        self.sample_rate: int = 48000
        self.channels: int = 0


def run_validation(
    input_audio: Path,
    policy: dict[str, Any],
    dry_run: bool = False,
    verbose: bool = False,
    analyzer_timeout_s: float = DEFAULT_ANALYZER_TIMEOUT_S,
    rights_manifest_path: Path | None = None,
    provenance_events_path: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], str, dict[str, Any], ExecutionResult]:
    """Executa o pipeline completo.

    Returns
    -------
    (findings, provenance, pcm_hash, decoder_info, exec_result)
        exec_result contém metadados extras para o bundle.
    """
    result = ExecutionResult()
    start_time = time.time()

    # ----- O1: TOCTOU — hash antes da análise -----
    file_hash_before = compute_file_hash(input_audio)

    # ----- 1. Discovery -----
    try:
        media_info = probe_media(input_audio)
    except Exception as exc:
        if verbose:
            print(f"probe ffmpeg falhou ({exc}); tentando fallback")
        try:
            media_info = probe_media_fallback(input_audio)
            result.decoder_used = "fallback"
        except Exception as exc2:
            raise RuntimeError(f"Discovery falhou: {exc2}") from exc2
    result.media_info = media_info

    result.decoder_info = {
        "decoder": result.decoder_used,
        "ffmpeg_version": "unknown",
        "decode_timestamp": int(start_time),
    }

    # ----- 2. Normalização PCM -----
    try:
        pcm, actual_sr, ch, norm_meta = decode_pcm_canonical(
            input_audio, sample_rate=48000
        )
    except DegenerateInputError as exc:
        result.findings.append({
            "id": "NORM-DEGENERATE",
            "name": "Input degenerado",
            "value": str(exc),
            "status": "indeterminate",
            "severity": "error",
            "description": "Entrada degenerada impossibilita análise acústica.",
        })
        result.pcm_hash = ""
        return result.findings, result.provenance, result.pcm_hash, result.decoder_info, result

    result.pcm = pcm
    result.sample_rate = actual_sr
    result.channels = ch
    result.has_nan_sanitized = norm_meta.get("nan_sanitized", False)
    result.is_empty = norm_meta.get("empty", False)
    if norm_meta.get("decoder_used") == "fallback":
        result.decoder_used = "fallback"
        result.decoder_info["decoder"] = "fallback"

    result.pcm_hash = compute_pcm_hash(pcm) if pcm.size > 0 else ""

    # ----- O1: TOCTOU — hash depois da análise -----
    try:
        file_hash_after = compute_file_hash(input_audio)
        if file_hash_before != file_hash_after:
            result.toctou_detected = True
            result.findings.append({
                "id": "TOCTOU-01",
                "name": "Arquivo modificado durante análise",
                "value": f"hash_antes={file_hash_before[:12]}... hash_depois={file_hash_after[:12]}...",
                "unit": None,
                "threshold": "hashes devem ser idênticos",
                "status": "indeterminate",
                "severity": "error",
                "description": (
                    "O arquivo foi modificado entre o início e o fim da análise. "
                    "O bundle pode não corresponder ao conteúdo atual."
                ),
            })
    except Exception:
        pass  # arquivo pode ter sido removido

    # ----- 3. Metadados / PII -----
    tag_pii_findings = detect_pii_in_tags(media_info.get("tags", {}))
    result.findings.extend(tag_pii_findings)

    # ----- 4. Analyzers (com timeout — O2) -----
    for check in policy.get("checks", []):
        analyzer_id = check.get("analyzer")
        if not analyzer_id or analyzer_id not in ANALYZER_PATHS:
            continue

        check_timeout = float(check.get("timeout_s", analyzer_timeout_s))
        try:
            analyzer_findings = _run_analyzer_with_timeout(
                analyzer_id=analyzer_id,
                check=check,
                pcm=pcm,
                media_info=media_info,
                input_audio=input_audio,
                rights_manifest_path=rights_manifest_path,
                provenance_events_path=provenance_events_path,
                timeout_s=check_timeout,
                verbose=verbose,
            )
            # Marca IDs e severidade
            for f in analyzer_findings:
                if "id" not in f:
                    f["id"] = f"{analyzer_id.upper()}-{check.get('id', '00')}"
                if "name" not in f:
                    f["name"] = f"{analyzer_id} ({check.get('id', '')})"
                if "severity" not in f:
                    f["severity"] = check.get("severity", "info")
                if "analyzer" not in f:
                    f["analyzer"] = analyzer_id
            result.findings.extend(analyzer_findings)

            # Phase-specific: se skip por mono, marca limitation
            if analyzer_id == "phase":
                if any(f.get("status") == "not_applicable" and "mono" in f.get("description", "").lower() for f in analyzer_findings):
                    result.phase_skipped_mono = True

        except concurrent.futures.TimeoutError:
            result.had_timeout.append(analyzer_id)
            result.findings.append({
                "id": f"{analyzer_id.upper()}-TIMEOUT",
                "name": f"{analyzer_id} — timeout",
                "value": f"{check_timeout}s",
                "unit": "s",
                "status": "indeterminate",
                "severity": "error",
                "description": f"Analyzer excedeu timeout de {check_timeout}s.",
                "analyzer": analyzer_id,
            })
        except Exception as exc:
            if verbose:
                print(f"Analyzer {analyzer_id} falhou: {exc}")
                traceback.print_exc()
            result.findings.append({
                "id": f"{analyzer_id.upper()}-ERR",
                "name": f"{analyzer_id} — erro de execução",
                "value": str(exc),
                "status": "indeterminate",
                "severity": "error",
                "description": "Analyzer falhou durante execução.",
                "analyzer": analyzer_id,
            })

    # ----- 5. Redação de PII (O9) -----
    result.findings = redact_pii_in_findings(result.findings)

    # ----- 6. Provenance -----
    result.provenance = {
        "events": [{
            "event_type": "decode_canonical",
            "input_sha256": file_hash_before,
            "output_pcm_sha256": result.pcm_hash,
            "decoder": result.decoder_used,
            "timestamp": int(time.time()),
        }]
    }

    return result.findings, result.provenance, result.pcm_hash, result.decoder_info, result


def _run_analyzer_with_timeout(
    analyzer_id: str,
    check: dict[str, Any],
    pcm: Any,
    media_info: dict[str, Any],
    input_audio: Path,
    rights_manifest_path: Path | None,
    provenance_events_path: Path | None,
    timeout_s: float,
    verbose: bool,
) -> list[dict[str, Any]]:
    """Executa um analyzer com timeout (O2)."""
    module_path = ANALYZER_PATHS[analyzer_id]
    module = importlib.import_module(module_path)
    if not hasattr(module, "run_analyzer"):
        return [{
            "id": f"{analyzer_id.upper()}-STUB",
            "name": f"{analyzer_id} (stub)",
            "value": "Not implemented",
            "status": "indeterminate",
            "severity": "info",
            "description": "Analyzer não implementado.",
        }]

    kwargs: dict[str, Any] = {
        "pcm": pcm,
        "media_info": media_info,
        "params": check.get("params", {}),
        "verbose": verbose,
    }
    # Analyzers extras com hooks especiais
    if analyzer_id == "rights_manifest":
        kwargs["manifest_path"] = rights_manifest_path
    if analyzer_id == "provenance":
        kwargs["events_path"] = provenance_events_path
        kwargs["input_audio"] = input_audio

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(module.run_analyzer, **kwargs)
        return future.result(timeout=timeout_s)
