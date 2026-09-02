"""Evidence bundle — deterministic, fingerprinted, optionally signed.

Determinism (CT-05):
  - Findings are sorted by (analyzer, check_id, time_range_ms)
  - Floats rounded to 6 decimals
  - No timestamps in the signed payload
  - measurement_fingerprint = sha256 of canonical JSON
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from . import __version__
from .models import PCM, Bundle, Finding, Profile, aggregate_status


def _canonicalize_findings(findings: list[Finding]) -> list[dict[str, Any]]:
    """Sort + round findings for deterministic JSON."""
    def sort_key(f: Finding) -> tuple:
        tr = f.time_range_ms if f.time_range_ms is not None else (-1.0, -1.0)
        return (f.analyzer, f.check_id, float(tr[0]), float(tr[1]))

    out: list[dict[str, Any]] = []
    for f in sorted(findings, key=sort_key):
        d = f.to_dict()
        # Round floats for determinism
        for k, v in list(d.items()):
            if isinstance(v, float):
                d[k] = round(v, 6)
            if isinstance(v, dict):
                d[k] = _round_floats(v)
            if isinstance(v, list):
                d[k] = [_round_floats(x) if isinstance(x, dict) else x for x in v]
        out.append(d)
    return out


def _round_floats(d: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in d.items():
        if isinstance(v, float):
            out[k] = round(v, 6)
        elif isinstance(v, dict):
            out[k] = _round_floats(v)
        elif isinstance(v, list):
            out[k] = [round(x, 6) if isinstance(x, float) else x for x in v]
        else:
            out[k] = v
    return out


def measurement_fingerprint(findings: list[dict[str, Any]]) -> str:
    """Stable SHA-256 of canonical findings JSON."""
    canonical = json.dumps(findings, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_bundle(
    audio: PCM,
    profile: Profile,
    findings: list[Finding],
    *,
    sign: bool = False,
    signing_key_path: str | None = None,
    audit: dict[str, Any] | None = None,
) -> Bundle:
    """Build the evidence bundle from analysis results."""
    canonical = _canonicalize_findings(findings)
    fp = measurement_fingerprint(canonical)

    subject = {
        "source_path": audio.source_path,
        "file_sha256": audio.file_sha256,
        "sample_rate_hz": audio.sample_rate,
        "channels": audio.channels,
        "channel_layout": audio.channel_layout,
        "frames": audio.n_frames,
        "duration_s": round(audio.duration_s, 4),
    }

    profile_meta = {
        "name": profile.name,
        "version": profile.version,
        "data_classification": profile.data_classification,
        "retention_policy": dict(profile.retention_policy),
        "strict": profile.is_strict(),
        "analyzers": sorted(profile.analyzers.keys()),
    }

    tool_meta = {
        "name": "audio-suite",
        "version": __version__,
        "schema_version": "1.0.0",
    }

    aggregate = aggregate_status([f.status for f in findings])

    signature = None
    if sign:
        from .security.signing import sign_payload
        try:
            signature = sign_payload(
                {
                    "tool": tool_meta,
                    "subject": subject,
                    "profile": profile_meta,
                    "findings": canonical,
                    "aggregate_status": aggregate.value,
                    "measurement_fingerprint": fp,
                },
                key_path=signing_key_path,
            )
        except Exception as exc:  # noqa: BLE001
            signature = {
                "algorithm": "Ed25519",
                "error": f"signing failed: {exc}",
                "signed": False,
            }

    return Bundle(
        schema_version="1.0.0",
        tool=tool_meta,
        subject=subject,
        profile=profile_meta,
        findings=canonical,
        aggregate_status=aggregate.value,
        measurement_fingerprint=fp,
        signature=signature,
    )


def bundle_to_json(bundle: Bundle, *, indent: int = 2) -> str:
    """Serialize bundle to deterministic JSON."""
    return json.dumps(bundle.to_dict(), sort_keys=True, indent=indent)
