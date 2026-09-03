"""EVID-08 — `--frozen-manifest` (+ `--strict`): reprodutibilidade forte de laudo.

O "manifesto congelado" é um bundle JSON emitido anteriormente. Analisar o
mesmo arquivo sob o mesmo ambiente deve reproduzi-lo:

- `--frozen-manifest <bundle.json>` (pré-check, antes de executar): recusa se
  a versão da tool, de qualquer analyzer, o hash do profile resolvido ou o
  `environment_hash` divergirem — **erro nomeia o campo divergente**.
- `--strict` (complemento do --frozen-manifest, pós-run): exige ainda
  identidade byte a byte do bundle produzido vs. congelado, **exceto** campos
  explicitamente declarados não-determinísticos; campo não declarado divergente
  → recusa nomeando o caminho JSON.

Campos declarados não-determinísticos (versão do schema 1.0.0):
  - `subject.source_path` (caminho local depende da máquina)
  - `signature` (envolve chave privada e timestamp de uso)

Exit code: 65 (EX_DATAERR, sysexits) — `FROZEN_MANIFEST_MISMATCH`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .environment import snapshot_environment
from .models import Profile

#: Campos que PODEM divergir entre runs byte-idênticos (declarados no schema).
#: Todos embutem identidade local do filesystem (caminho do arquivo analisado):
#: o conteúdo acústico do laudo (findings, fingerprint, environment, profile)
#: permanece byte-idêntico.
DECLARED_NONDETERMINISTIC_FIELDS: tuple[str, ...] = (
    "subject.source_path",
    "signature",
    "reproduction_command",
)


@dataclass(frozen=True)
class FrozenDivergence:
    field_path: str
    frozen: Any
    current: Any

    def message(self) -> str:
        return (
            f"frozen manifest diverges at '{self.field_path}': "
            f"frozen={self.frozen!r} current={self.current!r}"
        )


def _mask(path: str) -> bool:
    """Path mascarado se igual a (ou dentro de) campo declarado não-determinístico."""
    return any(
        path == declared or path.startswith(declared + ".") for declared in DECLARED_NONDETERMINISTIC_FIELDS
    )


def _flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, dict):
                out.update(_flatten(v, p))
            else:
                out[p] = v
    else:
        out[prefix] = obj
    return out


def precheck_frozen_manifest(frozen: dict[str, Any], profile: Profile) -> list[FrozenDivergence]:
    """Pré-check: tool version, analyzer versions, profile hash, env hash."""
    current = snapshot_environment(profile)
    divergences: list[FrozenDivergence] = []

    def _cmp(path: str, frozen_v: Any, current_v: Any) -> None:
        if frozen_v != current_v:
            divergences.append(FrozenDivergence(path, frozen_v, current_v))

    frozen_env = frozen.get("environment") or {}

    _cmp("tool.version", (frozen.get("tool") or {}).get("version"), current["tool_version"])
    _cmp(
        "environment.resolved_profile_sha256",
        frozen_env.get("resolved_profile_sha256"),
        current.get("resolved_profile_sha256"),
    )
    _cmp("environment.environment_hash", frozen_env.get("environment_hash"), current["environment_hash"])

    frozen_versions = frozen_env.get("analyzer_versions") or {}
    current_versions = current.get("analyzer_versions") or {}
    for aid in sorted(set(frozen_versions) | set(current_versions)):
        _cmp(f"environment.analyzer_versions.{aid}", frozen_versions.get(aid), current_versions.get(aid))

    return divergences


def verify_byte_identity(frozen: dict[str, Any], actual: dict[str, Any]) -> list[FrozenDivergence]:
    """Pós-run (--strict): bundle atual deve ser idêntico ao congelado.

    Campos declarados não-determinísticos são mascarados antes da comparação.
    Campos não declarados que divergem (ou que somem/aparecem) são violação.
    """
    f_flat = _flatten(json.loads(json.dumps(frozen, sort_keys=True, default=str)))
    a_flat = _flatten(json.loads(json.dumps(actual, sort_keys=True, default=str)))
    divergences: list[FrozenDivergence] = []

    for path in sorted(set(f_flat) | set(a_flat)):
        if _mask(path):
            continue  # declarado não-determinístico: divergência permitida
        if path not in a_flat:
            divergences.append(FrozenDivergence(path, f_flat[path], "<ausente no bundle atual>"))
        elif path not in f_flat:
            divergences.append(FrozenDivergence(path, "<ausente no congelado>", a_flat[path]))
        elif f_flat[path] != a_flat[path]:
            divergences.append(FrozenDivergence(path, f_flat[path], a_flat[path]))
    return divergences


def format_divergences(divergences: list[FrozenDivergence], limit: int = 5) -> str:
    shown = [d.message() for d in divergences[:limit]]
    extra = f" … (+{len(divergences) - limit} campos)" if len(divergences) > limit else ""
    return "; ".join(shown) + extra
