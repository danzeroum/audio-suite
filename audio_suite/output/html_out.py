"""HTML output — accessible (WCAG 2.1 AA target) per Fase 2.5."""
from __future__ import annotations

from pathlib import Path

from ..models import Bundle, Status

_STATUS_COLORS = {
    Status.PASS: "#16a34a",
    Status.WARNING: "#d97706",
    Status.FAIL: "#dc2626",
    Status.NOT_APPLICABLE: "#6b7280",
    Status.INDETERMINATE: "#6b7280",
    Status.NEEDS_REVIEW: "#7c3aed",
    Status.ERROR: "#b91c1c",
}


def bundle_to_html(bundle: Bundle, *, output_path: str | Path | None = None) -> str:
    if hasattr(bundle, "to_dict"):
        b = bundle.to_dict()
    else:
        b = bundle
    findings = b["findings"]
    rows = []
    for f in findings:
        status = Status(f["status"])
        color = _STATUS_COLORS.get(status, "#6b7280")
        tr_ms = f.get("time_range_ms")
        time_str = f"[{tr_ms[0]:.1f}, {tr_ms[1]:.1f}] ms" if tr_ms else "—"
        value_str = (
            f"{f['value']:.4g} {f['unit']}" if f.get("value") is not None else "—"
        )
        rows.append(f"""
        <tr>
          <td scope="row"><code>{f['analyzer']}</code></td>
          <td><code>{f['check_id']}</code></td>
          <td>{f.get('metric', '—')}</td>
          <td>{value_str}</td>
          <td>{time_str}</td>
          <td><span class="badge" style="background:{color}">{status.value}</span></td>
          <td>{f.get('message', '')}</td>
        </tr>""")

    aggregate = Status(b["aggregate_status"])
    agg_color = _STATUS_COLORS.get(aggregate, "#6b7280")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>audio-suite report — {b['subject'].get('source_path', 'in-memory')}</title>
  <style>
    body {{ font-family: system-ui, -apple-system, sans-serif; margin: 2rem; color: #1f2937; }}
    h1, h2 {{ color: #111827; }}
    .summary {{ background: #f3f4f6; padding: 1rem 1.5rem; border-radius: 8px; margin-bottom: 1.5rem; }}
    .badge {{ color: white; padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.85rem; font-weight: 600; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ text-align: left; padding: 0.5rem 0.75rem; border-bottom: 1px solid #e5e7eb; vertical-align: top; }}
    th {{ background: #f9fafb; font-weight: 600; }}
    tr:hover td {{ background: #fafafa; }}
    code {{ font-family: ui-monospace, SFMono-Regular, monospace; font-size: 0.9em; background: #f3f4f6; padding: 0.1rem 0.3rem; border-radius: 3px; }}
    a {{ color: #2563eb; }}
    .meta {{ color: #6b7280; font-size: 0.85rem; }}
  </style>
</head>
<body>
  <h1>audio-suite report</h1>
  <p class="meta">
    Tool: {b['tool']['name']} v{b['tool']['version']} ·
    Profile: {b['profile']['name']} v{b['profile']['version']} ·
    Fingerprint: <code>{b['measurement_fingerprint'][:16]}…</code>
  </p>

  <div class="summary" role="region" aria-label="Summary">
    <h2 style="margin-top:0">Aggregate status: <span class="badge" style="background:{agg_color}">{aggregate.value}</span></h2>
    <p><strong>Subject:</strong> <code>{b['subject'].get('source_path', 'in-memory')}</code></p>
    <p><strong>SHA-256:</strong> <code>{b['subject'].get('file_sha256', '—')}</code></p>
    <p><strong>Duration:</strong> {b['subject'].get('duration_s', 0)} s · <strong>Sample rate:</strong> {b['subject'].get('sample_rate_hz', 0)} Hz · <strong>Channels:</strong> {b['subject'].get('channels', 0)}</p>
    <p><strong>Findings:</strong> {len(findings)}</p>
  </div>

  <h2>Findings</h2>
  <table>
    <thead>
      <tr>
        <th scope="col">Analyzer</th>
        <th scope="col">Check</th>
        <th scope="col">Metric</th>
        <th scope="col">Value</th>
        <th scope="col">Time range</th>
        <th scope="col">Status</th>
        <th scope="col">Message</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
</body>
</html>"""

    if output_path is not None:
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(html, encoding="utf-8")
    return html
