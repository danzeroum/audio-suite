"""Policy engine: carrega profiles YAML, valida schema mínimo, aplica lockfile (O6)."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Lockfile de profiles (O6)
# ---------------------------------------------------------------------------

def _find_repo_root() -> Path:
    """Encontra raiz do repo procurando por 'registry/profiles.lock.yaml'."""
    candidates = [
        Path(__file__).resolve().parents[1],  # source: engine/policy.py → [1] = repo
        Path.cwd(),
    ]
    for cand in candidates:
        if (cand / "registry" / "profiles.lock.yaml").exists():
            return cand
    return Path.cwd()


_REPO_ROOT = _find_repo_root()
LOCKFILE_PATH = _REPO_ROOT / "registry" / "profiles.lock.yaml"

VERSION_SUFFIX_RE = re.compile(r"_v(\d+)$")


def load_lockfile() -> dict[str, str]:
    """Carrega registry/profiles.lock.yaml se existir."""
    if not LOCKFILE_PATH.exists():
        return {}
    try:
        with open(LOCKFILE_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return {entry["name"]: entry["sha256"] for entry in data.get("profiles", [])}
    except Exception:
        return {}


def save_lockfile(entries: dict[str, str]) -> None:
    """Persiste lockfile."""
    LOCKFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "profiles": [
            {"name": name, "sha256": sha} for name, sha in sorted(entries.items())
        ]
    }
    with open(LOCKFILE_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, sort_keys=True)


# ---------------------------------------------------------------------------
# Carregamento de profile
# ---------------------------------------------------------------------------

def load_policy_profile(profile_path: Path) -> dict[str, Any]:
    """Carrega um profile YAML e valida schema mínimo + lockfile (O6)."""
    with open(profile_path, encoding="utf-8") as f:
        policy = yaml.safe_load(f)

    if not isinstance(policy, dict):
        raise ValueError("Profile deve ser um objeto YAML")

    if not policy.get("name"):
        raise ValueError("Profile deve conter 'name'")
    if "checks" not in policy:
        raise ValueError("Profile deve conter 'checks' (pode ser lista vazia)")

    name = policy["name"]
    if not VERSION_SUFFIX_RE.search(name):
        raise ValueError(
            f"Profile '{name}' deve terminar com sufixo _vN (ex.: broadcast_ebu_r128_v1)"
        )

    with open(profile_path, "rb") as f:
        content = f.read()
    sha = hashlib.sha256(content).hexdigest()
    policy["_profile_sha256"] = sha
    policy["_profile_path"] = str(profile_path)

    # O6: valida contra lockfile se existir
    lockfile = load_lockfile()
    if lockfile:
        registered = lockfile.get(name)
        # Ignora placeholders TBD_*
        if registered and not registered.startswith("TBD"):
            if registered != sha:
                raise ValueError(
                    f"Profile '{name}' tem sha256 diferente do lockfile. "
                    f"Bump do sufixo _vN é obrigatório quando o conteúdo muda. "
                    f"lockfile={registered[:12]}... atual={sha[:12]}..."
                )

    return policy


def apply_policy(findings: list[dict[str, Any]], policy: dict[str, Any]) -> str:
    """Avalia findings contra policy e retorna decisão.

    Regras:
    - Qualquer finding com severity=error E status=fail → 'fail'
    - Caso contrário, se há status=indeterminate → 'indeterminate'
    - Caso contrário, se há status=needs_review → 'needs_review'
    - Caso contrário, se há status=warning → 'warning'
    - Caso contrário → 'pass'
    """
    decision = "pass"
    has_warning = False
    has_indeterminate = False
    has_needs_review = False

    for finding in findings:
        severity = finding.get("severity", "info")
        status = finding.get("status", "pass")

        if severity == "error" and status == "fail":
            return "fail"
        if status == "indeterminate":
            has_indeterminate = True
        if status == "needs_review":
            has_needs_review = True
        if status == "warning":
            has_warning = True

    if has_indeterminate:
        return "indeterminate"
    if has_needs_review:
        return "needs_review"
    if has_warning:
        return "warning"
    return decision


# ---------------------------------------------------------------------------
# Utilitários para registrar/bump de profiles
# ---------------------------------------------------------------------------

def register_profile_in_lockfile(profile_path: Path) -> None:
    """Adiciona ou atualiza um profile no lockfile (para uso manual/dev)."""
    lockfile = load_lockfile()
    policy = load_policy_profile(profile_path)
    lockfile[policy["name"]] = policy["_profile_sha256"]
    save_lockfile(lockfile)
