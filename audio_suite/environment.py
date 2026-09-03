"""Snapshot de ambiente (EVID-02.r+).

O snapshot captura TUDO que influencia o resultado numérico:
  - versões: python, numpy, scipy, soundfile
  - plataforma (OS/arch) — hash independe de caminhos locais
  - SHA-256 do profile YAML **resolvido** (com defaults dos schemas aplicados)
  - versão de cada analyzer do profile
  - backend DSP usado (`python` — reference implementation; campo existe para
    o futuro backend gated, VI.2 do Documento Mestre)

`environment_hash` = SHA-256 do JSON canônico do snapshot (sem o próprio hash).
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from typing import Any

from . import __version__
from .analyzers import all_analyzers
from .models import Profile


def resolve_profile_canonical(profile: Profile) -> dict[str, Any]:
    """Profile resolvido: params + defaults declarados nos schemas, canônico.

    O hash do profile resolvido cobre EXATAMENTE o que influencia a análise:
    nome/versão, classificação, e os parâmetros efetivos de cada analyzer
    (defaults explícitos no snapshot, não implícitos no código).
    """
    registry = all_analyzers()
    resolved_analyzers: dict[str, Any] = {}
    for aid, params in sorted(profile.analyzers.items()):
        merged: dict[str, Any] = {}
        analyzer = registry.get(aid)
        if analyzer is not None:
            schema = analyzer.profile_schema()
            for key, spec in (schema.get("properties") or {}).items():
                if "default" in spec:
                    merged[key] = spec["default"]
        merged.update(params)
        resolved_analyzers[aid] = merged
    return {
        "name": profile.name,
        "version": profile.version,
        "data_classification": profile.data_classification,
        "strict_overlay": dict(profile.strict_overlay),
        "retention_policy": dict(profile.retention_policy),
        "analyzers": resolved_analyzers,
    }


def resolved_profile_sha256(profile: Profile) -> str:
    canonical = json.dumps(resolve_profile_canonical(profile), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _version_of(module_name: str) -> str:
    try:
        module = __import__(module_name)
        return str(getattr(module, "__version__", "unknown"))
    except Exception:
        return "unavailable"


def snapshot_environment(profile: Profile | None = None) -> dict[str, Any]:
    """Snapshot completo do ambiente de execução (EVID-02.r+)."""
    analyzer_versions: dict[str, str] = {}
    if profile is not None:
        registry = all_analyzers()
        for aid in sorted(profile.analyzers):
            analyzer = registry.get(aid)
            if analyzer is not None:
                analyzer_versions[aid] = analyzer.VERSION

    env: dict[str, Any] = {
        "tool_version": __version__,
        "python_version": sys.version.split()[0],
        "numpy_version": _version_of("numpy"),
        "scipy_version": _version_of("scipy"),
        "soundfile_version": _version_of("soundfile"),
        "platform": platform.platform(terse=True),
        "dsp_backend": "python",
        "analyzer_versions": analyzer_versions,
    }
    if profile is not None:
        env["resolved_profile_sha256"] = resolved_profile_sha256(profile)
        env["resolved_profile"] = resolve_profile_canonical(profile)
    env["environment_hash"] = hashlib.sha256(
        json.dumps(env, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return env


def build_reproduction_command(
    *,
    source_path: str,
    profile_path: str | None = None,
    fmt: str = "json",
    only: list[str] | None = None,
    skip: list[str] | None = None,
    resample: int | None = None,
) -> str:
    """Comando exato para re-executar a análise (EVID-07).

    Determinístico: flags em ordem fixa; flags não usadas são omitidas.
    Não inclui `--output` (destino não é semântica da análise) nem `--strict`
    (flag de dupla semântica: overlay E verificação EVID-08; o estado strict
    do overlay fica registrado em `profile.strict` no próprio bundle). Sem
    essas exclusões, a identidade byte a byte do EVID-08 entre dois runs com
    o mesmo manifesto seria impossível.
    """
    parts = ["audio-suite", "analyze", str(source_path)]
    if profile_path:
        parts += ["--profile", str(profile_path)]
    parts += ["--format", fmt]
    if only:
        parts += ["--only", ",".join(only)]
    if skip:
        parts += ["--skip", ",".join(skip)]
    if resample is not None:
        parts += ["--resample", str(resample)]
    return " ".join(parts)
