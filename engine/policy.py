"""Gerenciador de profiles de política versionados."""
import yaml
import hashlib
from pathlib import Path
from typing import Dict, Any

def load_policy_profile(profile_path: Path) -> Dict[str, Any]:
    """Carrega um profile YAML e retorna com hash incluído."""
    with open(profile_path, "r", encoding="utf-8") as f:
        policy = yaml.safe_load(f)

    # Valida schema mínimo
    if not policy.get("name") or not policy.get("checks"):
        raise ValueError("Profile deve conter 'name' e 'checks'")

    # Calcula hash do conteúdo bruto (para rastreabilidade)
    with open(profile_path, "rb") as f:
        content = f.read()
    policy["_profile_sha256"] = hashlib.sha256(content).hexdigest()

    return policy

def apply_policy(findings: list, policy: dict) -> str:
    """Avalia findings contra policy e retorna decisão."""
    decision = "pass"
    for finding in findings:
        severity = finding.get("severity", "info")
        status = finding.get("status", "pass")

        if severity == "error" and status == "fail":
            return "fail"
        if status == "indeterminate":
            decision = "indeterminate"

    return decision
