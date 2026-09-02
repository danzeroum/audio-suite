"""JSON output."""
from __future__ import annotations

import json
from pathlib import Path

from ..models import Bundle, Finding


def findings_to_json(findings: list[Finding], *, indent: int = 2) -> str:
    return json.dumps(
        [f.to_dict() for f in findings],
        sort_keys=True,
        indent=indent,
    )


def bundle_to_json_file(bundle: Bundle, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(bundle.to_dict(), sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return p
