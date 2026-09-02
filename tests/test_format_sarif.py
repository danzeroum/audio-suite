"""Tests: cli_formats/sarif (F2.1)."""
from __future__ import annotations

from engine.cli_formats.sarif import bundle_to_sarif


def make_bundle(findings=None):
    return {
        "schema": "urn:audio-suite:bundle:v1.0.0",
        "subject": {"path": "/tmp/test.wav", "file_sha256": "a" * 64},
        "execution": {
            "suite_version": "0.2.0-beta",
            "status": "completed",
            "timestamp": "2026-09-01T12:00:00Z",
        },
        "findings": findings or [],
        "decision": "fail" if findings else "pass",
        "signature": {"status": "unsigned"},
    }


class TestSarifOutput:
    def test_basic_structure(self):
        bundle = make_bundle()
        sarif = bundle_to_sarif(bundle)
        assert sarif["version"] == "2.1.0"
        assert sarif["$schema"].endswith("sarif-2.1.0.json")
        assert len(sarif["runs"]) == 1
        run = sarif["runs"][0]
        assert run["tool"]["driver"]["name"] == "audio-suite"

    def test_findings_to_results(self):
        bundle = make_bundle(findings=[
            {
                "id": "AC-01",
                "name": "Loudness",
                "value": -10.0,
                "unit": "LUFS",
                "threshold": "-23.0 ± 0.5",
                "status": "fail",
                "severity": "error",
                "analyzer": "loudness",
                "description": "Loudness acima do target",
            }
        ])
        sarif = bundle_to_sarif(bundle)
        run = sarif["runs"][0]
        assert len(run["results"]) == 1
        r = run["results"][0]
        assert r["ruleId"] == "AC-01"
        assert r["level"] == "error"
        assert r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "/tmp/test.wav"

    def test_severity_mapping(self):
        bundle = make_bundle(findings=[
            {"id": "X1", "name": "n", "status": "fail", "severity": "error", "description": ""},
            {"id": "X2", "name": "n", "status": "warning", "severity": "warning", "description": ""},
            {"id": "X3", "name": "n", "status": "pass", "severity": "info", "description": ""},
        ])
        sarif = bundle_to_sarif(bundle)
        levels = [r["level"] for r in sarif["runs"][0]["results"]]
        assert "error" in levels
        assert "warning" in levels

    def test_rules_deduplicated(self):
        bundle = make_bundle(findings=[
            {"id": "AC-01", "name": "n", "status": "fail", "severity": "error", "description": ""},
            {"id": "AC-01", "name": "n", "status": "fail", "severity": "error", "description": ""},
        ])
        sarif = bundle_to_sarif(bundle)
        run = sarif["runs"][0]
        assert len(run["tool"]["driver"]["rules"]) == 1  # deduplicated
        assert len(run["results"]) == 2

    def test_properties_include_analyzer(self):
        bundle = make_bundle(findings=[
            {"id": "X", "name": "n", "status": "fail", "severity": "error", "analyzer": "loudness", "description": ""},
        ])
        sarif = bundle_to_sarif(bundle)
        r = sarif["runs"][0]["results"][0]
        assert r["properties"]["analyzer"] == "loudness"

    def test_invocations_present(self):
        bundle = make_bundle()
        sarif = bundle_to_sarif(bundle)
        run = sarif["runs"][0]
        assert "invocations" in run
        assert run["invocations"][0]["executionSuccessful"] is True

    def test_no_findings(self):
        bundle = make_bundle()
        sarif = bundle_to_sarif(bundle)
        assert sarif["runs"][0]["results"] == []

    def test_information_uri(self):
        bundle = make_bundle()
        sarif = bundle_to_sarif(bundle)
        assert "github.com/danzeroum/audio-suite" in sarif["runs"][0]["tool"]["driver"]["informationUri"]
