"""SARIF 2.1.0 output for GitHub code scanning integration.

Spec: https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..models import Bundle, Status


def status_to_sarif_level(status: Status) -> str:
    return {
        Status.PASS: "none",
        Status.WARNING: "warning",
        Status.FAIL: "error",
        Status.NOT_APPLICABLE: "none",
        Status.INDETERMINATE: "none",
        Status.NEEDS_REVIEW: "note",
        Status.ERROR: "error",
    }.get(status, "none")


def bundle_to_sarif(bundle: Bundle, *, output_path: str | Path | None = None) -> dict[str, Any]:
    """Convert a bundle to a SARIF 2.1.0 report dict."""
    # Accept both Bundle dataclass and dict for flexibility
    if hasattr(bundle, "to_dict"):
        b = bundle.to_dict()
    else:
        b = bundle
    rules: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    seen_rules: set[str] = set()

    for f in b["findings"]:
        rule_id = f"{f['analyzer']}/{f['check_id']}"
        if rule_id not in seen_rules:
            rules.append(
                {
                    "id": rule_id,
                    "name": f["check_id"],
                    "shortDescription": {"text": f.get("message", "")[:200]},
                    "fullDescription": {"text": " ".join(f.get("limitations", [])) or f.get("method", "")},
                    "helpUri": "https://github.com/audio-suite/audio-suite",
                    "properties": {
                        "analyzer": f["analyzer"],
                        "method": f.get("method", ""),
                    },
                }
            )
            seen_rules.add(rule_id)

        status = Status(f["status"])
        location = {
            "physicalLocation": {
                "artifactLocation": {
                    "uri": b["subject"].get("source_path", "") or "in-memory",
                },
            }
        }
        if f.get("time_range_ms"):
            location["physicalLocation"]["region"] = {
                "startLine": 1,
                "startColumn": 1,
                "properties": {
                    "time_range_ms": f["time_range_ms"],
                },
            }

        results.append(
            {
                "ruleId": rule_id,
                "level": status_to_sarif_level(status),
                "message": {"text": f.get("message", "")},
                "locations": [location],
                "properties": {
                    "metric": f.get("metric"),
                    "value": f.get("value"),
                    "unit": f.get("unit"),
                    "confidence": f.get("confidence"),
                    "limitations": f.get("limitations", []),
                },
                "partialFingerprints": {
                    "metric/v1": f"{f.get('analyzer')}:{f.get('check_id')}:{f.get('value')}",
                },
            }
        )

    sarif = {
        "$schema": "https://docs.oasis-open.org/sarif/sarif/v2.1.0/cs01/schemas/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": b["tool"]["name"],
                        "version": b["tool"]["version"],
                        "informationUri": "https://github.com/audio-suite/audio-suite",
                        "rules": rules,
                    }
                },
                "results": results,
                "properties": {
                    # EVID-02.r+ / EVID-07: ambiente e reprodução no SARIF
                    "environment_hash": (b.get("environment") or {}).get("environment_hash"),
                    "dsp_backend": (b.get("environment") or {}).get("dsp_backend"),
                    "reproduction_command": b.get("reproduction_command"),
                },
                "invocations": [
                    {
                        "executionSuccessful": True,
                        "toolExecutionNotifications": [],
                    }
                ],
            }
        ],
    }

    if output_path is not None:
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(sarif, indent=2), encoding="utf-8")

    return sarif
