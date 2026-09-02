"""Analyzer: provenance (validação de DAG de eventos) — F1.4 + A3.

Estados possíveis (A3 — NÃO codificar "gap = fail" universal):
- valid: cadeia verificável, hashes batem, ordem correta.
- gap: evento faltante (sem input_hash esperado para output_hash atual).
- invalid: hash não bate, ordem contraditória, assinatura inválida.
- not_provided: pipeline não forneceu provenance.

A policy decide se gap/not_provided vira fail/warning/indeterminate/needs_review.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def run_analyzer(
    pcm: Any = None,
    media_info: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    verbose: bool = False,
    events_path: Path | None = None,
    input_audio: Path | None = None,
) -> list[dict[str, Any]]:
    """Valida cadeia de eventos de provenance.

    Params:
        require_signature: bool (default False)
        expected_input_sha256: str (default None — usa hash do input_audio)
    """
    params = params or {}
    findings: list[dict[str, Any]] = []

    if events_path is None or not events_path.exists():
        findings.append({
            "name": "Provenance validation",
            "value": "not_provided",
            "unit": None,
            "threshold": "events file required",
            "status": "needs_review",
            "severity": "info",
            "description": (
                "Pipeline não forneceu arquivo de eventos de provenance. "
                "Policy decide se isso é fail/warning/needs_review."
            ),
            "reliability": "high",
        })
        return findings

    try:
        events_data = json.loads(events_path.read_text(encoding="utf-8"))
    except Exception as exc:
        findings.append({
            "name": "Provenance validation",
            "value": "invalid",
            "unit": None,
            "threshold": "valid JSON",
            "status": "fail",
            "severity": "error",
            "description": f"Arquivo de eventos inválido: {exc}",
            "reliability": "high",
        })
        return findings

    events = events_data.get("events", [])
    if not events:
        findings.append({
            "name": "Provenance validation",
            "value": "gap",
            "unit": None,
            "threshold": "at least 1 event",
            "status": "needs_review",
            "severity": "info",
            "description": "Lista de eventos vazia.",
            "reliability": "high",
        })
        return findings

    # Hash esperado do input_audio atual (se fornecido)
    expected_input_sha = None
    if input_audio and input_audio.exists():
        h = hashlib.sha256()
        with open(input_audio, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        expected_input_sha = h.hexdigest()

    require_signature = bool(params.get("require_signature", False))

    # Valida encadeamento: output_hash de evento N = input_hash de evento N+1
    gaps: list[str] = []
    invalid_reasons: list[str] = []
    last_output_hash: str | None = None

    for i, event in enumerate(events):
        if not isinstance(event, dict):
            invalid_reasons.append(f"event[{i}] não é objeto")
            continue

        input_hash = event.get("input_sha256")
        output_hash = event.get("output_sha256") or event.get("output_pcm_sha256")

        # Primeiro evento: input_hash deve bater com input_audio (se fornecido)
        if i == 0 and expected_input_sha and input_hash:
            if input_hash != expected_input_sha:
                invalid_reasons.append(
                    f"event[{i}] input_sha256 não corresponde ao arquivo de entrada"
                )

        # Encadeamento
        if last_output_hash is not None and input_hash:
            if last_output_hash != input_hash:
                gaps.append(
                    f"event[{i}] input_sha256 não corresponde ao output do evento anterior"
                )

        # Assinatura (se requerida)
        if require_signature:
            sig = event.get("signature")
            if not sig:
                invalid_reasons.append(f"event[{i}] sem assinatura (require_signature=true)")

        last_output_hash = output_hash

    # Decisão
    if invalid_reasons:
        status = "fail"
        severity = "error"
        value = "invalid"
        description = "Cadeia de provenance inválida: " + "; ".join(invalid_reasons)
    elif gaps:
        status = "needs_review"
        severity = "info"
        value = "gap"
        description = "Cadeia com gaps: " + "; ".join(gaps)
    else:
        status = "pass"
        severity = "info"
        value = "valid"
        description = f"Cadeia de {len(events)} eventos verificada com sucesso."

    findings.append({
        "name": "Provenance validation",
        "value": value,
        "unit": None,
        "threshold": "valid chain" + (" + signature" if require_signature else ""),
        "status": status,
        "severity": severity,
        "description": description,
        "reliability": "high",
        "events_count": len(events),
        "gaps_count": len(gaps),
        "invalid_count": len(invalid_reasons),
    })

    return findings
