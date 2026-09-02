"""Analyzer: rights_manifest (validação de licenças vs. propósito) — F1.5.

Valida registry/license-declarations/rights-manifest.yaml:
- commercial_use_allowed=false em projeto commercial_campaign → fail
- attribution_required=true sem attribution_text → fail
- license unknown → needs_review
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

KNOWN_LICENSES = {
    "CC0", "CC-BY-4.0", "CC-BY-3.0", "CC-BY-SA-4.0", "CC-BY-SA-3.0",
    "CC-BY-NC-4.0", "CC-BY-NC-SA-4.0", "CC-BY-NC-ND-4.0",
    "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause",
    "CC-PDDC", "PDM",
}

NC_LICENSE_PREFIXES = ("CC-BY-NC",)


def run_analyzer(
    pcm: Any = None,
    media_info: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    verbose: bool = False,
    manifest_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Valida rights manifest contra propósito do projeto."""
    params = params or {}
    findings: list[dict[str, Any]] = []

    if manifest_path is None:
        # Se caller não passou path, retorna not_provided
        findings.append({
            "name": "Rights manifest",
            "value": "not_provided",
            "unit": None,
            "threshold": "manifest file required",
            "status": "needs_review",
            "severity": "info",
            "description": (
                "Rights manifest não fornecido. "
                "Policy decide se isso bloqueia."
            ),
            "reliability": "high",
        })
        return findings

    if not manifest_path.exists():
        findings.append({
            "name": "Rights manifest",
            "value": "not_provided",
            "unit": None,
            "threshold": "manifest file required",
            "status": "needs_review",
            "severity": "info",
            "description": (
                "Rights manifest não fornecido. "
                "Policy decide se isso bloqueia."
            ),
            "reliability": "high",
        })
        return findings

    try:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        findings.append({
            "name": "Rights manifest",
            "value": "invalid",
            "unit": None,
            "threshold": "valid YAML",
            "status": "fail",
            "severity": "error",
            "description": f"Falha ao carregar manifest: {exc}",
            "reliability": "high",
        })
        return findings

    project = manifest.get("project", {}) or {}
    purpose = str(project.get("purpose", "")).lower()
    is_commercial = "commercial" in purpose
    assets = manifest.get("assets_used", []) or []

    if not assets:
        findings.append({
            "name": "Rights manifest",
            "value": "empty",
            "unit": None,
            "threshold": "at least 1 asset",
            "status": "needs_review",
            "severity": "info",
            "description": "Manifest declarado mas sem assets.",
            "reliability": "high",
        })
        return findings

    for asset in assets:
        asset_id = asset.get("asset_id", "?")
        license_type = str(asset.get("license", "")).upper()
        commercial_allowed = asset.get("commercial_use_allowed")
        attribution_req = bool(asset.get("attribution_required", False))
        attribution_text = asset.get("attribution_text", "")

        # Se commercial_use_allowed não foi declarado, inferir da licença
        if commercial_allowed is None:
            commercial_allowed = not any(
                license_type.startswith(p) for p in NC_LICENSE_PREFIXES
            )

        # Conflito: comercial + não permitido
        if is_commercial and not commercial_allowed:
            findings.append({
                "name": f"Rights — {asset.get('title', asset_id)}",
                "value": license_type,
                "unit": None,
                "threshold": "commercial_use_allowed=true",
                "status": "fail",
                "severity": "error",
                "description": (
                    f"Asset '{asset.get('title', asset_id)}' ({license_type}) "
                    "não permite uso comercial; projeto declarado como comercial."
                ),
                "asset_id": asset_id,
                "reliability": "high",
            })

        # Conflito: atribuição requerida mas ausente
        if attribution_req and not attribution_text:
            findings.append({
                "name": f"Rights — attribution for {asset_id}",
                "value": "missing",
                "unit": None,
                "threshold": "attribution_text required",
                "status": "fail",
                "severity": "error",
                "description": (
                    f"Asset '{asset_id}' exige atribuição mas attribution_text está vazio."
                ),
                "asset_id": asset_id,
                "reliability": "high",
            })

        # Licença desconhecida
        if license_type and license_type not in KNOWN_LICENSES:
            findings.append({
                "name": f"Rights — license for {asset_id}",
                "value": license_type,
                "unit": None,
                "threshold": f"one of {sorted(KNOWN_LICENSES)[:5]}...",
                "status": "needs_review",
                "severity": "info",
                "description": (
                    f"Licença '{license_type}' não reconhecida. Revisão manual necessária."
                ),
                "asset_id": asset_id,
                "reliability": "high",
            })

    # Se nenhum finding até aqui, manifest é válido
    if not findings:
        findings.append({
            "name": "Rights manifest",
            "value": "valid",
            "unit": None,
            "threshold": "no conflicts",
            "status": "pass",
            "severity": "info",
            "description": f"Manifest com {len(assets)} assets sem conflitos.",
            "reliability": "high",
        })

    return findings
