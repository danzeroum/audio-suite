"""CONTR-01..07: Contract tests — JSON Schema, rule IDs, severity, remediation."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from audio_suite.bundle import build_bundle
from audio_suite.decode import decode
from audio_suite.models import PCM, Finding, Profile, Status
from audio_suite.rule_ids import RULE_IDS, get_rule_id, get_severity

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "bundle-v1.json"


@pytest.fixture
def bundle_schema():
    return json.loads(SCHEMA_PATH.read_text())


@pytest.fixture
def sine_pcm():
    return decode(ROOT / "tests" / "fixtures" / "generated" / "sine_1k_mono.wav")


# CONTR-01: JSON Schema v1 validates all outputs
def test_CONTR01_bundle_validates_against_schema(sine_pcm, bundle_schema):
    findings = [
        Finding(
            check_id="t",
            analyzer="loudness",
            metric="integrated_loudness",
            value=-20.0,
            unit="LUFS",
            status=Status.PASS,
        ),
    ]
    profile = Profile(name="t", version="1", analyzers={})
    bundle = build_bundle(sine_pcm, profile, findings)
    bundle_dict = bundle.to_dict()
    # Should validate without errors
    jsonschema.validate(instance=bundle_dict, schema=bundle_schema)


def test_CONTR01_bundle_with_fail_validates(sine_pcm, bundle_schema):
    findings = [
        Finding(
            check_id="t",
            analyzer="clipping",
            metric="clipped_sample_pct",
            value=5.0,
            unit="%",
            status=Status.FAIL,
        ),
    ]
    profile = Profile(name="t", version="1", analyzers={})
    bundle = build_bundle(sine_pcm, profile, findings)
    jsonschema.validate(instance=bundle.to_dict(), schema=bundle_schema)


# CONTR-02: Rule IDs are stable and unique
def test_CONTR02_rule_ids_unique():
    ids = list(RULE_IDS.values())
    assert len(ids) == len(set(ids)), "Duplicate rule IDs found"


def test_CONTR02_rule_ids_format():
    for (analyzer, metric), rule_id in RULE_IDS.items():
        assert rule_id.startswith("AS-"), f"Rule ID {rule_id} doesn't start with AS-"
        parts = rule_id.split("-")
        assert len(parts) == 3, f"Rule ID {rule_id} should have format AS-CAT-NNN"


def test_CONTR02_bundle_contains_rule_ids(sine_pcm):
    findings = [
        Finding(
            check_id="t",
            analyzer="loudness",
            metric="integrated_loudness",
            value=-20.0,
            unit="LUFS",
            status=Status.PASS,
        ),
        Finding(
            check_id="t",
            analyzer="clipping",
            metric="clipped_sample_pct",
            value=5.0,
            unit="%",
            status=Status.FAIL,
        ),
    ]
    profile = Profile(name="t", version="1", analyzers={})
    bundle = build_bundle(sine_pcm, profile, findings)
    rule_ids_in_bundle = [f.get("rule_id") for f in bundle.findings if f.get("rule_id")]
    assert "AS-LOUD-001" in rule_ids_in_bundle
    assert "AS-PEAK-002" in rule_ids_in_bundle


# CONTR-03: Severity taxonomy
def test_CONTR03_severity_mapping():
    assert get_severity("pass") == "info"
    assert get_severity("warning") == "warning"
    assert get_severity("fail") == "error"
    assert get_severity("error") == "critical"
    assert get_severity("needs_review") == "warning"


def test_CONTR03_severity_in_bundle(sine_pcm):
    findings = [
        Finding(
            check_id="t",
            analyzer="clipping",
            metric="clipped_sample_pct",
            value=5.0,
            unit="%",
            status=Status.FAIL,
        ),
    ]
    profile = Profile(name="t", version="1", analyzers={})
    bundle = build_bundle(sine_pcm, profile, findings)
    assert bundle.findings[0]["severity"] == "error"


# CONTR-04: Remediation fields for error/critical
def test_CONTR04_remediation_for_fail(sine_pcm):
    findings = [
        Finding(
            check_id="t",
            analyzer="clipping",
            metric="clipped_sample_pct",
            value=5.0,
            unit="%",
            status=Status.FAIL,
        ),
    ]
    profile = Profile(name="t", version="1", analyzers={})
    bundle = build_bundle(sine_pcm, profile, findings)
    f = bundle.findings[0]
    assert "recommendation" in f
    assert "why_it_matters" in f
    assert len(f["recommendation"]) > 10


def test_CONTR04_no_remediation_for_pass(sine_pcm):
    findings = [
        Finding(
            check_id="t",
            analyzer="loudness",
            metric="integrated_loudness",
            value=-20.0,
            unit="LUFS",
            status=Status.PASS,
        ),
    ]
    profile = Profile(name="t", version="1", analyzers={})
    bundle = build_bundle(sine_pcm, profile, findings)
    f = bundle.findings[0]
    assert "recommendation" not in f


# CONTR-05: Uncertainty fields for probabilistic
def test_CONTR05_requires_human_review(sine_pcm):
    findings = [
        Finding(
            check_id="t",
            analyzer="deepfake",
            metric="synthetic_likeness_score",
            value=0.5,
            unit="0-1",
            status=Status.NEEDS_REVIEW,
            confidence=0.3,
        ),
    ]
    profile = Profile(name="t", version="1", analyzers={})
    bundle = build_bundle(sine_pcm, profile, findings)
    f = bundle.findings[0]
    assert f.get("requires_human_review") is True


# CONTR-06: No authenticity claims
def test_CONTR06_no_authenticity_in_findings(sine_pcm):
    findings = [
        Finding(
            check_id="t",
            analyzer="enf_phase",
            metric="phase_discontinuity_count",
            value=0.0,
            unit="events",
            status=Status.NEEDS_REVIEW,
            confidence=0.5,
        ),
    ]
    profile = Profile(name="t", version="1", analyzers={})
    bundle = build_bundle(sine_pcm, profile, findings)
    for f in bundle.findings:
        msg = f.get("message", "").lower()
        assert "is authentic" not in msg
        assert "is deepfake" not in msg
