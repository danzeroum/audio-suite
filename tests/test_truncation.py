"""Tests: bundle/truncate (O10)."""
from __future__ import annotations

from engine.bundle.truncate import DEFAULT_MAX_PER_ANALYZER, truncate_findings


def make_finding(analyzer_id: str, idx: int, status: str = "fail", severity: str = "error"):
    return {
        "id": f"{analyzer_id}-{idx:03d}",
        "name": f"Finding {idx}",
        "value": idx,
        "status": status,
        "severity": severity,
    }


class TestTruncateFindings:
    def test_no_truncation_under_limit(self):
        findings = [make_finding("SIGNAL", i) for i in range(10)]
        out, overflow = truncate_findings(findings, max_per_analyzer=100)
        assert len(out) == 10
        assert overflow == {}

    def test_truncation_adds_aggregate(self):
        findings = [make_finding("SIGNAL", i) for i in range(150)]
        out, overflow = truncate_findings(findings, max_per_analyzer=100)
        assert len(out) == 101  # 100 + 1 aggregate
        assert overflow == {"SIGNAL": 50}
        # O aggregate tem que ser o último
        agg = out[-1]
        assert "AGGREGATE" in agg["id"]
        assert agg["value"] == 50
        assert agg["status"] == "fail"
        assert agg["severity"] == "error"

    def test_multiple_analyzers_independent(self):
        findings = (
            [make_finding("SIGNAL", i) for i in range(150)]
            + [make_finding("LOUDNESS", i) for i in range(50)]
        )
        out, overflow = truncate_findings(findings, max_per_analyzer=100)
        assert overflow == {"SIGNAL": 50}
        # 100 signal + 1 aggregate + 50 loudness = 151
        assert len(out) == 151

    def test_aggregate_severity_warning_when_no_fail(self):
        findings = [make_finding("MD", i, status="warning", severity="warning") for i in range(150)]
        out, overflow = truncate_findings(findings, max_per_analyzer=100)
        agg = out[-1]
        assert agg["status"] == "warning"
        assert agg["severity"] == "warning"

    def test_aggregate_severity_info_when_all_info(self):
        findings = [make_finding("MD", i, status="info", severity="info") for i in range(150)]
        out, overflow = truncate_findings(findings, max_per_analyzer=100)
        agg = out[-1]
        assert agg["status"] == "info"
        assert agg["severity"] == "info"

    def test_default_max_is_100(self):
        assert DEFAULT_MAX_PER_ANALYZER == 100

    def test_empty_findings(self):
        out, overflow = truncate_findings([])
        assert out == []
        assert overflow == {}

    def test_no_overflow_when_exactly_at_limit(self):
        findings = [make_finding("SIGNAL", i) for i in range(100)]
        out, overflow = truncate_findings(findings, max_per_analyzer=100)
        assert len(out) == 100
        assert overflow == {}

    def test_custom_max(self):
        findings = [make_finding("SIGNAL", i) for i in range(20)]
        out, overflow = truncate_findings(findings, max_per_analyzer=5)
        assert overflow == {"SIGNAL": 15}
        assert len(out) == 6  # 5 + 1 aggregate
