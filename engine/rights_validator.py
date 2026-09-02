"""Valida rights manifest declarativo."""
from pathlib import Path

import yaml


def validate_rights_manifest(manifest_path: Path) -> list[dict]:
    """Verifica conflitos entre propósito e licenças."""
    findings = []
    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = yaml.safe_load(f)

        purpose = manifest.get("project", {}).get("purpose", "")
        assets = manifest.get("assets_used", [])

        for asset in assets:
            license_type = asset.get("license", "").upper()
            attribution_req = asset.get("attribution_required", False)
            attribution_text = asset.get("attribution_text", "")

            # Conflito: uso comercial + licença NC
            if purpose.lower() == "commercial_campaign" and "NC" in license_type:
                findings.append({
                    "id": f"GO-NC-{asset.get('asset_id', '00')}",
                    "name": f"Uso comercial proibido — licença {license_type}",
                    "value": license_type,
                    "threshold": "commercial_campaign",
                    "status": "fail",
                    "severity": "error",
                    "description": f"Asset '{asset.get('title', '')}' ({license_type}) não permite uso comercial. Projeto declarado como comercial."
                })

            # Conflito: atribuição exigida mas ausente
            if attribution_req and not attribution_text:
                findings.append({
                    "id": f"GO-ATTR-{asset.get('asset_id', '00')}",
                    "name": "Atribuição ausente",
                    "value": asset.get("title", ""),
                    "status": "fail",
                    "severity": "error",
                    "description": "Asset com licença que exige atribuição, mas campo attribution_text está vazio."
                })

    except Exception as e:
        findings.append({
            "id": "GO-RIGHTS-ERR",
            "name": "Rights Manifest Validator — erro",
            "value": str(e),
            "status": "indeterminate",
            "severity": "error"
        })

    return findings
