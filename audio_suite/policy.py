"""Policy engine — profile loading, validation, severity escalation.

Per A3 (Decisão pertence ao profile) and A5 (--strict is overlay, not auto-fail):
  - The analyzer proposes a status based on the measurement.
  - The profile may carry explicit thresholds that the engine enforces.
  - The profile's `strict_overlay` block is applied ONLY when --strict is set,
    and it lists explicit status overrides (warning->fail etc.).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from jsonschema import ValidationError, validate

from .analyzers import all_analyzers
from .models import Finding, Profile, Status


class ProfileError(Exception):
    """Raised when a profile YAML fails validation."""


def load_profile(path: str | Path, *, strict: bool = False) -> Profile:
    """Load and validate a profile YAML file.

    Args:
        path: path to the .yaml file.
        strict: if True, merge the profile's `strict_overlay` block (if any)
                into the active policy. Does NOT auto-escalate warnings —
                only applies the explicit overlay rules.

    Inheritance (PROF-06.r): um profile pode declarar `extends: <caminho>`
    (relativo ao arquivo ou nome resolvível em `profiles/`). O pai é carregado
    recursivamente e o filho é mesclado por cima (deep-merge: params de
    analyzer são mesclados chave a chave; listas/escalares do filho vencem;
    strict_overlay e retention_policy do filho vencem como bloco).
    """
    p = Path(path)
    if not p.exists():
        # tenta resolver como nome de profile (profiles/<nome>.yaml) — PROF-06.r
        alt = Path(__file__).resolve().parent.parent / "profiles" / f"{p}.yaml"
        if alt.exists():
            p = alt
        else:
            raise ProfileError(f"profile not found: {path}")
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ProfileError(f"YAML parse error: {exc}") from exc

    if not isinstance(raw, dict):
        raise ProfileError("profile root must be a mapping")

    raw = _resolve_inheritance(raw, p)
    return validate_profile(raw, strict=strict)


def _resolve_inheritance(raw: dict, child_path: Path) -> dict:
    """Resolve `extends:` (PROF-06.r) com deep-merge filho-sobre-pai."""
    extends = raw.get("extends")
    if not extends:
        return raw
    if not isinstance(extends, str):
        raise ProfileError("'extends' deve ser o caminho/nome do profile pai")

    parent_path = Path(extends)
    if not parent_path.exists():
        # relativo ao arquivo filho
        rel = child_path.parent / f"{extends}.yaml"
        rel2 = child_path.parent / extends
        alt_name = Path(__file__).resolve().parent.parent / "profiles" / f"{extends}.yaml"
        for cand in (rel, rel2, alt_name):
            if cand.exists():
                parent_path = cand
                break
        else:
            raise ProfileError(f"extends: profile pai não encontrado: {extends}")

    try:
        parent_raw = yaml.safe_load(parent_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ProfileError(f"YAML parse error em {parent_path}: {exc}") from exc
    if not isinstance(parent_raw, dict):
        raise ProfileError(f"profile pai inválido: {parent_path}")
    parent_raw = _resolve_inheritance(parent_raw, parent_path)  # herança em cadeia

    merged = dict(parent_raw)
    for key, child_val in raw.items():
        if key == "extends":
            continue
        if key == "analyzers" and isinstance(child_val, dict) and isinstance(merged.get(key), dict):
            merged_analyzers = dict(merged[key])
            for aid, params in child_val.items():
                if isinstance(params, dict) and isinstance(merged_analyzers.get(aid), dict):
                    merged_params = dict(merged_analyzers[aid])
                    merged_params.update(params)
                    merged_analyzers[aid] = merged_params
                else:
                    merged_analyzers[aid] = params
            merged[key] = merged_analyzers
        else:
            merged[key] = child_val
    return merged


def validate_profile(raw: dict[str, Any], *, strict: bool = False) -> Profile:
    """Validate a raw profile dict (already parsed from YAML)."""
    if "name" not in raw or "version" not in raw:
        raise ProfileError("profile must have 'name' and 'version'")

    analyzers_raw = raw.get("analyzers", {})
    if not isinstance(analyzers_raw, dict):
        raise ProfileError("'analyzers' must be a mapping")

    # Validate each analyzer's params against its declared schema
    available = all_analyzers()
    validated: dict[str, dict[str, Any]] = {}
    for aid, params in analyzers_raw.items():
        if aid not in available:
            raise ProfileError(f"unknown analyzer '{aid}'; available: {sorted(available)}")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            raise ProfileError(f"params for '{aid}' must be a mapping")
        schema = available[aid].profile_schema()
        try:
            validate(instance=params, schema=schema)
        except ValidationError as exc:
            raise ProfileError(f"params for '{aid}' failed schema: {exc.message}") from exc
        validated[aid] = dict(params)

    strict_overlay = raw.get("strict_overlay", {})
    if not isinstance(strict_overlay, dict):
        raise ProfileError("strict_overlay must be a mapping")
    if strict and not strict_overlay:
        # Strict mode requested but no overlay declared — that's OK,
        # we just don't apply anything. Per A5: --strict is NOT auto-fail.
        pass

    retention = raw.get("retention_policy", {})
    if not isinstance(retention, dict):
        raise ProfileError("retention_policy must be a mapping")

    classification = raw.get("data_classification", "internal")
    if classification not in {"public", "internal", "confidential", "restricted"}:
        raise ProfileError("data_classification must be one of public/internal/confidential/restricted")

    return Profile(
        name=str(raw["name"]),
        version=str(raw["version"]),
        analyzers=validated,
        strict_overlay=strict_overlay if strict else {},
        retention_policy=retention,
        data_classification=classification,
        raw=raw,
    )


def apply_policy(finding: Finding, profile: Profile) -> Finding:
    """Apply profile-driven status escalation to a finding.

    The strict_overlay is a mapping of analyzer_id -> {metric -> new_status}.
    Example:
      strict_overlay:
        clipping:
          clipped_sample_pct: fail

    Per A5: --strict is NOT an auto-fail switch. The overlay only ESCALATES
    severity for findings that are already flagged (WARNING or NEEDS_REVIEW).
    A clean PASS stays PASS — the overlay means "if this metric produces a
    warning, treat it as fail", NOT "always fail this metric".
    """
    from .models import status_rank

    if not profile.is_strict():
        return finding
    # Only escalate findings that are already flagged (warning / needs_review).
    # PASS, NOT_APPLICABLE, INDETERMINATE are not escalated — they represent
    # "no problem" or "cannot determine", not "borderline problem".
    ESCALATABLE = {Status.WARNING, Status.NEEDS_REVIEW}
    if finding.status not in ESCALATABLE:
        return finding
    overlay = profile.strict_overlay.get(finding.analyzer, {})
    if not isinstance(overlay, dict):
        return finding
    new_status_str = overlay.get(finding.metric) or overlay.get("*")
    if new_status_str:
        try:
            new_status = Status(new_status_str)
        except ValueError:
            return finding
        # Only escalate (increase severity), never downgrade.
        if status_rank(new_status) > status_rank(finding.status):
            return finding.with_status(new_status)
    return finding
