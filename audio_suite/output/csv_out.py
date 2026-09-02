"""CSV output formatter (Fase 5.5)."""

from __future__ import annotations

import csv
from pathlib import Path

from ..models import Bundle

CSV_COLUMNS = [
    "analyzer",
    "check_id",
    "metric",
    "value",
    "unit",
    "status",
    "time_range_ms_start",
    "time_range_ms_end",
    "confidence",
    "message",
    "limitations",
    "method",
]


def bundle_to_csv(bundle: Bundle, *, output_path: str | Path | None = None) -> str:
    """Convert a bundle to CSV format.

    Returns the CSV string. If output_path is given, also writes to file.
    """
    import io

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(CSV_COLUMNS)

    for f in bundle.findings:
        tr = f.get("time_range_ms") or [None, None]
        writer.writerow(
            [
                f.get("analyzer", ""),
                f.get("check_id", ""),
                f.get("metric", ""),
                f.get("value", ""),
                f.get("unit", ""),
                f.get("status", ""),
                tr[0] if tr[0] is not None else "",
                tr[1] if tr[1] is not None else "",
                f.get("confidence", ""),
                f.get("message", ""),
                "; ".join(f.get("limitations", [])),
                f.get("method", ""),
            ]
        )

    csv_str = output.getvalue()
    if output_path is not None:
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(csv_str, encoding="utf-8")
    return csv_str
