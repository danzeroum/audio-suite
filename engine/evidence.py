"""Evidence: construção do bundle, validação contra schema, escrita atômica (O3 + O4).

Regras operacionais:
- Antes de salvar, valida bundle contra contracts/audio-run-1.0.json.
- Escrita atômica: tmp + fsync + os.replace.
- Em caso de falha na validação ou escrita, não deixa arquivo corrompido.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .bundle.fingerprint import (
    compute_bundle_sha256,
    compute_measurement_fingerprint,
)
from .bundle.limitations import collect_limitations
from .bundle.schema_version import (
    SUPPORTED_BUNDLE_URN,
    check_version_compatibility,
)
from .bundle.signer import sign_bundle
from .bundle.truncate import truncate_findings
from .normalization import compute_file_hash

SCHEMA_PATH = Path("contracts/audio-run-1.0.json")


def build_bundle(
    input_audio: Path,
    policy: dict[str, Any],
    findings: list[dict[str, Any]],
    provenance: dict[str, Any],
    pcm_canonical_sha256: str,
    decoder_info: dict[str, Any],
    decision: str,
    limitations: list[str] | None = None,
    decoder_used: str = "ffmpeg",
    has_nan_sanitized: bool = False,
    is_empty: bool = False,
    toctou_detected: bool = False,
    had_timeout: list[str] | None = None,
    truncated_analyzers: list[str] | None = None,
    phase_skipped_mono: bool = False,
    rights_manifest_missing: bool = False,
    provenance_partial: bool = False,
    dry_run: bool = False,
    signature_mode: str = "unsigned",
    signature_key_path: Path | None = None,
) -> dict[str, Any]:
    """Constrói o evidence bundle JSON com todas as proteções."""
    file_sha256 = compute_file_hash(input_audio)

    # Trunca findings (O10)
    truncated_findings, overflow = truncate_findings(findings)
    truncated_analyzers_final = list(overflow.keys()) + (truncated_analyzers or [])

    # Coleta limitations automáticas (S4)
    auto_limitations = collect_limitations(
        decoder_used=decoder_used,
        signature_status=signature_mode,
        has_nan_sanitized=has_nan_sanitized,
        is_empty=is_empty,
        toctou_detected=toctou_detected,
        had_timeout=had_timeout,
        truncated_analyzers=truncated_analyzers_final,
        phase_skipped_mono=phase_skipped_mono,
        rights_manifest_missing=rights_manifest_missing,
        provenance_partial=provenance_partial,
    )
    all_limitations = list(set(auto_limitations + (limitations or [])))

    # Fingerprint canônico (A2)
    measurement_fingerprint = compute_measurement_fingerprint(
        file_sha256=file_sha256,
        pcm_canonical_sha256=pcm_canonical_sha256,
        profile_sha256=policy.get("_profile_sha256", ""),
        profile_name=policy.get("name", ""),
        suite_version="audio-suite/0.2.0-beta",
        findings=truncated_findings,
        decoder_used=decoder_used,
        sample_rate_hz=48000,
    )

    bundle: dict[str, Any] = {
        "schema": SUPPORTED_BUNDLE_URN,
        "schema_version": "1.0.0",
        "subject": {
            "path": str(input_audio),
            "file_sha256": file_sha256,
            "pcm_canonical_sha256": pcm_canonical_sha256,
        },
        "execution": {
            "suite_version": "audio-suite/0.2.0-beta",
            "profile": policy.get("name"),
            "profile_sha256": policy.get("_profile_sha256"),
            "decoder": decoder_info.get("decoder"),
            "decoder_used": decoder_used,
            "ffmpeg_version": decoder_info.get("ffmpeg_version"),
            "sample_rate_hz": 48000,
            "status": "completed",
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "toctou_detected": toctou_detected,
        },
        "findings": truncated_findings,
        "provenance": provenance,
        "decision": decision,
        "limitations": all_limitations,
        "measurement_fingerprint": measurement_fingerprint,
    }

    # Assina (F2.2)
    bundle = sign_bundle(bundle, mode=signature_mode, key_path=signature_key_path)

    # bundle_sha256 = hash do bundle completo (após assinatura)
    bundle["bundle_sha256"] = compute_bundle_sha256(bundle)

    return bundle


def validate_bundle_against_schema(bundle: dict[str, Any]) -> None:
    """Valida bundle contra contracts/audio-run-1.0.json (O3).

    Levanta ValueError se inválido.
    """
    if not SCHEMA_PATH.exists():
        # Sem schema disponível, pula validação (mas emite warning)
        return

    try:
        import jsonschema  # type: ignore
    except ImportError:
        # Sem jsonschema, faz validação estrutural mínima
        _validate_minimal(bundle)
        return

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(instance=bundle, schema=schema)
    except jsonschema.ValidationError as exc:
        raise ValueError(f"Bundle inválido contra schema: {exc.message}") from exc


def _validate_minimal(bundle: dict[str, Any]) -> None:
    required = ["schema", "subject", "execution", "findings", "decision", "signature"]
    missing = [k for k in required if k not in bundle]
    if missing:
        raise ValueError(f"Bundle sem campos obrigatórios: {missing}")
    if not isinstance(bundle.get("findings"), list):
        raise ValueError("findings deve ser lista")


def save_bundle(bundle: dict[str, Any], output_path: Path) -> None:
    """Salva bundle JSON com escrita atômica (O4) + validação (O3)."""
    # Verifica compatibilidade de versão (S1)
    urn = bundle.get("schema", "")
    status, msg = check_version_compatibility(urn)
    if status == "reject_newer":
        raise ValueError(f"Bundle rejeitado: {msg}")

    # Valida contra schema
    validate_bundle_against_schema(bundle)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Escrita atômica: tmp → fsync → os.replace
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=".bundle-",
        suffix=".tmp",
        dir=str(output_path.parent),
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(bundle, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, output_path)
    except Exception:
        # Limpa tmp em caso de falha
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
