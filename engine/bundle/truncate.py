"""Bundle: truncagem de findings (O10).

Para áudios longos (podcast, audiobook), findings de clipping podem ter
milhares de ocorrências. Define limite por analyzer e agrega o excedente.
"""
from __future__ import annotations

from typing import Any

DEFAULT_MAX_PER_ANALYZER = 100


def truncate_findings(
    findings: list[dict[str, Any]],
    max_per_analyzer: int = DEFAULT_MAX_PER_ANALYZER,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Trunca findings por analyzer e adiciona finding agregador se exceder.

    Returns
    -------
    (truncated_findings, overflow_map)
        overflow_map: {analyzer_id: count_of_overflow}
    """
    # Agrupa por analyzer (via id prefix antes do '-')
    groups: dict[str, list[dict[str, Any]]] = {}
    for f in findings:
        analyzer_id = (f.get("id", "") or "").split("-", 1)[0] or "UNKNOWN"
        groups.setdefault(analyzer_id, []).append(f)

    out: list[dict[str, Any]] = []
    overflow: dict[str, int] = {}

    for analyzer_id, group in groups.items():
        if len(group) <= max_per_analyzer:
            out.extend(group)
            continue

        # Mantém os primeiros N
        out.extend(group[:max_per_analyzer])
        overflow_count = len(group) - max_per_analyzer
        overflow[analyzer_id] = overflow_count

        # Finding agregador
        # Determina o status/severity dominante
        statuses = [g.get("status", "info") for g in group]
        severities = [g.get("severity", "info") for g in group]

        if "fail" in statuses:
            agg_status = "fail"
            agg_severity = "error" if "error" in severities else "warning"
        elif "warning" in statuses:
            agg_status = "warning"
            agg_severity = "warning"
        else:
            agg_status = "info"
            agg_severity = "info"

        out.append({
            "id": f"{analyzer_id}-AGGREGATE-OVERFLOW",
            "name": f"{analyzer_id} — additional findings (aggregated)",
            "value": overflow_count,
            "unit": "count",
            "threshold": f"max {max_per_analyzer} per analyzer",
            "status": agg_status,
            "severity": agg_severity,
            "description": (
                f"{overflow_count} findings adicionais deste analyzer foram "
                f"agregados por exceder o limite de {max_per_analyzer}."
            ),
        })

    return out, overflow
