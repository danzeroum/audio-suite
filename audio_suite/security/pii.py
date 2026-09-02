"""PII redaction — replaces paths and known PII patterns in evidence."""
from __future__ import annotations

import re
from typing import Any

# Common PII patterns (best-effort, not exhaustive)
_PATTERNS = [
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[REDACTED:email]"),
    (re.compile(r"\b(?:\d[ -]*?){11,16}\b"), "[REDACTED:card]"),
    (re.compile(r"/(?:home|Users)/[^/]+"), "[REDACTED:userpath]"),
]


def redact_pii(value: Any) -> Any:
    """Recursively redact PII patterns from strings within a nested structure."""
    if isinstance(value, str):
        for pat, repl in _PATTERNS:
            value = pat.sub(repl, value)
        return value
    if isinstance(value, dict):
        return {k: redact_pii(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_pii(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact_pii(v) for v in value)
    return value
