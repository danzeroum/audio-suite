"""Bundle: versionamento semântico de schemas (S1 + O7).

- Versão do bundle segue semver: v1.0.0, v1.1.0, v2.0.0.
- URN resolvível: urn:audio-suite:bundle:v1.0.0
- registry.json mapeia URN → path + sha256 do schema.
- CLI rejeita versão superior à suportada; warning para versão menor.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# Versão suportada por esta engine
SUPPORTED_BUNDLE_VERSION = "1.0.0"
SUPPORTED_BUNDLE_URN = f"urn:audio-suite:bundle:v{SUPPORTED_BUNDLE_VERSION}"


def _find_repo_root() -> Path:
    """Encontra a raiz do repo procurando por 'contracts/registry.json'.

    Necessário porque instalações editable (.egg-link) podem ter __file__
    apontando para o diretório site-packages em vez do source tree.
    """
    # Tenta path relativo ao arquivo source
    # engine/bundle/schema_version.py → parents[0]=bundle, [1]=engine, [2]=repo
    candidates = [
        Path(__file__).resolve().parents[2],
        Path(__file__).resolve().parents[3],  # fallback para layouts diferentes
        Path.cwd(),  # cwd atual
    ]
    for cand in candidates:
        if (cand / "contracts" / "registry.json").exists():
            return cand
    # Fallback: usa cwd (vai funcionar se CI roda do repo root)
    return Path.cwd()


_REPO_ROOT = _find_repo_root()
SCHEMA_REGISTRY_PATH = _REPO_ROOT / "contracts" / "registry.json"

SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def parse_semver(version: str) -> tuple[int, int, int]:
    """Extrai (major, minor, patch) de uma string semver."""
    m = SEMVER_RE.match(version)
    if not m:
        raise ValueError(f"Versão semver inválida: {version}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def urn_from_version(version: str) -> str:
    return f"urn:audio-suite:bundle:v{version}"


def version_from_urn(urn: str) -> str | None:
    """Extrai a versão de uma URN, ou None se não reconhecida."""
    m = re.match(r"^urn:audio-suite:bundle:v(\d+\.\d+\.\d+)$", urn)
    return m.group(1) if m else None


def check_version_compatibility(bundle_urn: str) -> tuple[str, str]:
    """Verifica compatibilidade da versão do bundle.

    Returns
    -------
    (status, message)
        status: "ok" | "warn_older" | "reject_newer" | "unknown"
    """
    version = version_from_urn(bundle_urn)
    if version is None:
        return "unknown", f"URN não reconhecida: {bundle_urn}"

    try:
        major, minor, patch = parse_semver(version)
        s_major, s_minor, s_patch = parse_semver(SUPPORTED_BUNDLE_VERSION)
    except ValueError as exc:
        return "unknown", str(exc)

    if major > s_major:
        return "reject_newer", (
            f"Bundle versão {version} é superior à suportada "
            f"{SUPPORTED_BUNDLE_VERSION}. Atualize a engine."
        )
    if major < s_major:
        return "warn_older", (
            f"Bundle versão {version} é major anterior à suportada "
            f"{SUPPORTED_BUNDLE_VERSION}. Compatibilidade não garantida."
        )
    if minor > s_minor or (minor == s_minor and patch > s_patch):
        return "warn_older", (
            f"Bundle versão {version} é patch/minor superior. "
            f"Engine suporta até {SUPPORTED_BUNDLE_VERSION}; campos novos podem ser ignorados."
        )
    return "ok", f"Versão compatível: {version}"


def load_schema_registry() -> dict[str, Any]:
    """Carrega contracts/registry.json (URN → path + sha256)."""
    if not SCHEMA_REGISTRY_PATH.exists():
        return {"schemas": []}
    return json.loads(SCHEMA_REGISTRY_PATH.read_text(encoding="utf-8"))


def resolve_schema(urn: str) -> Path | None:
    """Resolve uma URN para um caminho de schema local (O7).

    Retorna path absoluto baseado na raiz do repo, independente do cwd.
    """
    registry = load_schema_registry()
    for entry in registry.get("schemas", []):
        if entry.get("urn") == urn:
            # entry["path"] é relativo à raiz do repo (ex.: "contracts/audio-run-1.0.json")
            return _REPO_ROOT / entry["path"]
    return None
