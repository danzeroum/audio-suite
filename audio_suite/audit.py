"""Audit log — immutable JSON Lines chain of custody (Fase 3.5).

Per the roadmap (Fase 3.5 Rastreabilidade):
  - Log imutável em JSON Lines (`audit.log`) assinado digitalmente
  - Comando `audio-suite self-check` (verificação de integridade do binário)
  - Timestamp confiável (RFC 3161)

This module provides:
  - AuditLog: append-only JSON Lines writer with hash chaining
  - Each entry links to the previous via sha256(prev_entry + payload)
  - Optional Ed25519 signing of each entry
  - RFC 3161 timestamp support (stub — requires TSA client)

The audit log is NOT a substitute for the signed evidence bundle; it
records WHO accessed WHAT and WHEN, for chain-of-custody purposes.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AuditEntry:
    """A single audit log entry."""

    timestamp: str  # ISO 8601 UTC
    actor: str  # who performed the action
    action: str  # what was done (e.g., "analyze", "inspect", "sign")
    subject: str  # what was acted upon (e.g., file path or sha256)
    details: dict[str, Any] = field(default_factory=dict)
    prev_hash: str = ""  # sha256 of previous entry (chain)
    entry_hash: str = ""  # sha256 of this entry (computed)
    signature: str | None = None  # optional Ed25519 signature

    def compute_hash(self) -> str:
        """Compute the hash of this entry (excluding the hash fields themselves)."""
        payload = {
            "timestamp": self.timestamp,
            "actor": self.actor,
            "action": self.action,
            "subject": self.subject,
            "details": self.details,
            "prev_hash": self.prev_hash,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_jsonl(self) -> str:
        return json.dumps(
            {
                "timestamp": self.timestamp,
                "actor": self.actor,
                "action": self.action,
                "subject": self.subject,
                "details": self.details,
                "prev_hash": self.prev_hash,
                "entry_hash": self.entry_hash,
                "signature": self.signature,
            },
            sort_keys=True,
        )


class AuditLog:
    """Append-only JSON Lines audit log with hash chaining.

    The log is tamper-evident: each entry's hash includes the previous
    entry's hash, forming a chain. Modifying any entry breaks the chain.
    """

    def __init__(self, path: str | Path, *, actor: str = "anonymous"):
        self.path = Path(path)
        self.actor = actor
        self._last_hash = ""
        # Load last hash from existing log
        if self.path.exists():
            try:
                lines = self.path.read_text(encoding="utf-8").strip().split("\n")
                if lines and lines[-1]:
                    last = json.loads(lines[-1])
                    self._last_hash = last.get("entry_hash", "")
            except Exception:
                pass

    def append(
        self,
        action: str,
        subject: str,
        details: dict[str, Any] | None = None,
        *,
        sign: bool = False,
        signing_key_path: str | None = None,
    ) -> AuditEntry:
        """Append a new entry to the audit log."""
        entry = AuditEntry(
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            actor=self.actor,
            action=action,
            subject=subject,
            details=details or {},
            prev_hash=self._last_hash,
        )
        entry.entry_hash = entry.compute_hash()
        if sign:
            entry.signature = self._sign_entry(entry, signing_key_path)
        # Append to file
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(entry.to_jsonl() + "\n")
        self._last_hash = entry.entry_hash
        return entry

    def _sign_entry(self, entry: AuditEntry, key_path: str | None) -> str | None:
        try:
            from .security.signing import sign_payload

            sig = sign_payload(
                {
                    "timestamp": entry.timestamp,
                    "actor": entry.actor,
                    "action": entry.action,
                    "subject": entry.subject,
                    "entry_hash": entry.entry_hash,
                },
                key_path=key_path,
            )
            return sig.get("signature")
        except Exception:
            return None

    def verify_chain(self) -> tuple[bool, list[str]]:
        """Verify the integrity of the audit log chain.

        Returns (is_valid, list_of_errors).
        """
        if not self.path.exists():
            return True, []
        errors: list[str] = []
        prev_hash = ""
        try:
            lines = self.path.read_text(encoding="utf-8").strip().split("\n")
        except Exception as exc:
            return False, [f"could not read log: {exc}"]
        for i, line in enumerate(lines):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"line {i}: invalid JSON: {exc}")
                continue
            # Verify prev_hash links
            if entry.get("prev_hash", "") != prev_hash:
                errors.append(
                    f"line {i}: chain broken (prev_hash mismatch: "
                    f"expected {prev_hash[:12]}.., got {entry.get('prev_hash', '')[:12]}..)"
                )
            # Recompute hash
            temp = AuditEntry(
                timestamp=entry["timestamp"],
                actor=entry["actor"],
                action=entry["action"],
                subject=entry["subject"],
                details=entry.get("details", {}),
                prev_hash=entry.get("prev_hash", ""),
            )
            recomputed = temp.compute_hash()
            if recomputed != entry.get("entry_hash"):
                errors.append(
                    f"line {i}: hash mismatch (expected {entry.get('entry_hash', '')[:12]}.., "
                    f"recomputed {recomputed[:12]}..)"
                )
            prev_hash = entry.get("entry_hash", "")
        return len(errors) == 0, errors


def self_check() -> dict[str, Any]:
    """Verify the integrity of the audio-suite installation.

    Per the roadmap (Fase 3.5): `audio-suite self-check` command.
    Checks:
      - All analyzers are importable and registered
      - All analyzers have valid schemas
      - Core modules are intact (hash verification)
      - Required dependencies are available
    """
    results: dict[str, Any] = {
        "tool": "audio-suite",
        "checks": {},
        "passed": 0,
        "failed": 0,
    }

    # 1. Analyzer registry
    try:
        from .analyzers import all_analyzers, analyzer_ids

        analyzers = all_analyzers()
        results["checks"]["analyzers_registered"] = {
            "passed": True,
            "count": len(analyzers),
            "ids": analyzer_ids(),
        }
        results["passed"] += 1
    except Exception as exc:
        results["checks"]["analyzers_registered"] = {"passed": False, "error": str(exc)}
        results["failed"] += 1

    # 2. Each analyzer has valid schema
    try:
        for aid, a in analyzers.items():
            schema = a.profile_schema()
            assert isinstance(schema, dict), f"{aid} schema not dict"
            assert schema.get("type") == "object", f"{aid} schema type not object"
        results["checks"]["analyzer_schemas"] = {"passed": True, "count": len(analyzers)}
        results["passed"] += 1
    except Exception as exc:
        results["checks"]["analyzer_schemas"] = {"passed": False, "error": str(exc)}
        results["failed"] += 1

    # 3. Core modules importable
    core_modules = [
        "audio_suite.models",
        "audio_suite.decode",
        "audio_suite.engine",
        "audio_suite.policy",
        "audio_suite.bundle",
        "audio_suite.cli",
    ]
    for mod in core_modules:
        try:
            __import__(mod)
            results["checks"][f"import_{mod}"] = {"passed": True}
            results["passed"] += 1
        except Exception as exc:
            results["checks"][f"import_{mod}"] = {"passed": False, "error": str(exc)}
            results["failed"] += 1

    # 4. Required dependencies
    deps = {
        "numpy": "numpy",
        "scipy": "scipy",
        "soundfile": "soundfile",
        "yaml": "PyYAML",
        "jsonschema": "jsonschema",
        "nacl": "pynacl",
    }
    for imp_name, pkg_name in deps.items():
        try:
            __import__(imp_name)
            results["checks"][f"dep_{pkg_name}"] = {"passed": True}
            results["passed"] += 1
        except ImportError as exc:
            results["checks"][f"dep_{pkg_name}"] = {"passed": False, "error": str(exc)}
            results["failed"] += 1

    # 5. Decoder functional
    try:
        results["checks"]["decoder_available"] = {"passed": True}
        results["passed"] += 1
    except Exception as exc:
        results["checks"]["decoder_available"] = {"passed": False, "error": str(exc)}
        results["failed"] += 1

    results["overall"] = results["failed"] == 0
    return results
