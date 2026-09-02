"""CLI formats: SARIF 2.1.0 output — F2.1 + A9.

Aviso (A9): SARIF não cria comentários automaticamente no GitHub.
Requer upload via `github/codeql-action/upload-sarif` e permissões adequadas.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Mapeia severidade interna → SARIF level
SEVERITY_TO_LEVEL = {
    "error": "error",
    "warning": "warning",
    "info": "note",
}

# Mapeia status interno → SARIF level (fallback)
STATUS_TO_LEVEL = {
    "fail": "error",
    "warning": "warning",
    "pass": "none",
    "indeterminate": "warning",
    "not_applicable": "none",
    "needs_review": "warning",
}


def bundle_to_sarif(bundle: dict[str, Any]) -> dict[str, Any]:
    """Converte evidence bundle em SARIF 2.1.0."""
    findings: list[dict[str, Any]] = bundle.get("findings", [])
    subject_path = bundle.get("subject", {}).get("path", "")

    rules: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    rule_index_map: dict[str, int] = {}

    for f in findings:
        rule_id = f.get("id", "UNKNOWN")
        if rule_id not in rule_index_map:
            rule = {
                "id": rule_id,
                "name": (f.get("name", rule_id) or rule_id)[:200],
                "shortDescription": {
                    "text": (f.get("name", rule_id) or rule_id)[:200]
                },
                "fullDescription": {
                    "text": (f.get("description", "") or "")[:1000]
                },
            }
            rules.append(rule)
            rule_index_map[rule_id] = len(rules) - 1

        severity = f.get("severity", "info")
        status = f.get("status", "info")
        level = SEVERITY_TO_LEVEL.get(severity) or STATUS_TO_LEVEL.get(status, "note")

        result: dict[str, Any] = {
            "ruleId": rule_id,
            "ruleIndex": rule_index_map[rule_id],
            "level": level,
            "message": {
                "text": _format_finding_message(f),
            },
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {
                            "uri": subject_path,
                        }
                    }
                }
            ],
            "properties": {
                "analyzer": f.get("analyzer"),
                "value": f.get("value"),
                "unit": f.get("unit"),
                "threshold": f.get("threshold"),
                "status": status,
                "severity": severity,
                "reliability": f.get("reliability"),
            },
        }
        results.append(result)

    sarif = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "audio-suite",
                        "version": "0.2.0-beta",
                        "informationUri": "https://github.com/danzeroum/audio-suite",
                        "rules": rules,
                    }
                },
                "results": results,
                "invocations": [
                    {
                        "executionSuccessful": bundle.get("execution", {}).get("status") == "completed",
                        "endTimeUtc": bundle.get("execution", {}).get("timestamp"),
                    }
                ],
            }
        ],
    }
    return sarif


def _format_finding_message(f: dict[str, Any]) -> str:
    name = f.get("name", "Finding")
    value = f.get("value", "")
    unit = f.get("unit") or ""
    threshold = f.get("threshold") or ""
    status = f.get("status", "")

    parts = [f"{name}: {status.upper()}"]
    if value != "":
        parts.append(f"value={value} {unit}".strip())
    if threshold:
        parts.append(f"threshold={threshold}")
    return " | ".join(parts)


def save_sarif(sarif: dict[str, Any], output_path: Path) -> None:
    """Salva SARIF JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(sarif, f, ensure_ascii=False, indent=2)
