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
    """
    p = Path(path)
    if not p.exists():
        raise ProfileError(f"profile not found: {path}")
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ProfileError(f"YAML parse error: {exc}") from exc

    if not isinstance(raw, dict):
        raise ProfileError("profile root must be a mapping")

    return validate_profile(raw, strict=strict)


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
            raise ProfileError(
                f"unknown analyzer '{aid}'; available: {sorted(available)}"
            )
        if params is None:
            params = {}
        if not isinstance(params, dict):
            raise ProfileError(f"params for '{aid}' must be a mapping")
        schema = available[aid].profile_schema()
        try:
            validate(instance=params, schema=schema)
        except ValidationError as exc:
            raise ProfileError(
                f"params for '{aid}' failed schema: {exc.message}"
            ) from exc
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
        raise ProfileError(
            "data_classification must be one of public/internal/confidential/restricted"
        )

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
