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
        # EVID-08: caminhos locais são dependentes de máquina — findings devem
        # descrever o ÁUDIO, não o filesystem. O caminho canônico fica em
        # subject.source_path (campo declarado não-determinístico). Sem isso,
        # o measurement_fingerprint não é estável entre máquinas/caminhos.
        if isinstance(d.get("evidence"), dict):
            d["evidence"].pop("source_path", None)
        # Enrich with stable rule_id (CONTR-02)
        from .rule_ids import get_rule_id, get_severity

        rule_id = get_rule_id(f.analyzer, f.metric)
        if rule_id:
            d["rule_id"] = rule_id
        # Enrich with severity (CONTR-03)
        d["severity"] = get_severity(f.status.value)
        # Enrich with remediation for error/critical (CONTR-04)
        if d["severity"] in ("error", "critical"):
            d.setdefault("recommendation", _get_recommendation(f))
            d.setdefault("why_it_matters", _get_why_it_matters(f))
        # Enrich with uncertainty for probabilistic (CONTR-05)
        if f.confidence is not None and f.confidence < 0.9:
            d["requires_human_review"] = f.status.value in ("needs_review", "indeterminate")
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


_REMEDIATION_TEMPLATES: dict[str, tuple[str, str]] = {
    "clipping": (
        "Reduce input gain before the ADC or apply a brickwall limiter at -1 dBTP.",
        "Clipping introduces irreversible harmonic distortion.",
    ),
    "glitch": (
        "Re-export from the source project, checking for buffer underruns.",
        "Digital glitches indicate transport or processing errors.",
    ),
    "true_peak": (
        "Apply a true-peak limiter with ceiling at -1.0 dBTP.",
        "Inter-sample peaks above -1 dBTP can cause DAC clipping.",
    ),
    "mono_compat": (
        "Check for phase issues. Use a correlation meter and fix polarity.",
        "Mono compatibility loss degrades mono playback systems.",
    ),
    "channel_balance": (
        "Verify channel routing and gain staging. Re-pan or adjust gains.",
        "Channel imbalance sounds off-center on stereo playback.",
    ),
    "loop": (
        "Apply a crossfade at the loop boundary or align to zero crossing.",
        "Loop discontinuity causes audible clicks at the loop boundary.",
    ),
}


def _get_recommendation(f: Finding) -> str:
    t = _REMEDIATION_TEMPLATES.get(f.analyzer)
    return t[0] if t else f"Review the {f.analyzer} finding and consult documentation."


def _get_why_it_matters(f: Finding) -> str:
    t = _REMEDIATION_TEMPLATES.get(f.analyzer)
    return t[1] if t else f"The {f.analyzer} analyzer detected a potential quality issue."


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
    reproduction_command: str | None = None,
) -> Bundle:
    """Build the evidence bundle from analysis results.

    EVID-02.r+: inclui snapshot de ambiente (versões, platform, hash do profile
    resolvido, versões de analyzers, backend DSP). EVID-07: reproduction_command
    quando fornecido pelo chamador.
    """
    from .environment import snapshot_environment

    canonical = _canonicalize_findings(findings)
    fp = measurement_fingerprint(canonical)
    environment = snapshot_environment(profile)

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
                    "environment": environment,
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
        environment=environment,
        reproduction_command=reproduction_command,
    )


def bundle_to_json(bundle: Bundle, *, indent: int = 2) -> str:
    """Serialize bundle to deterministic JSON."""
    return json.dumps(bundle.to_dict(), sort_keys=True, indent=indent)
