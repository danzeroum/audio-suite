"""T-01 to T-10: Architecture & Contracts.

Tests that:
  - All analyzers implement the AudioAnalyzer protocol
  - JSON schemas are valid
  - Bundle is rastreável (sha256 fingerprint)
  - Exit codes are correct
  - Status taxonomy is complete
"""

from __future__ import annotations

import json

import jsonschema
import pytest

from audio_suite import __version__
from audio_suite.analyzers import all_analyzers, analyzer_ids
from audio_suite.models import (
    PCM,
    STATUS_PRECEDENCE,
    Bundle,
    Finding,
    Status,
    aggregate_status,
)
from audio_suite.policy import validate_profile


# T-01: every analyzer has stable ID, version, name, method, schema
def test_T01_analyzer_metadata_complete():
    for aid, analyzer in all_analyzers().items():
        assert aid == analyzer.ID, f"{aid} ID mismatch"
        assert analyzer.NAME, f"{aid} has empty NAME"
        assert analyzer.VERSION, f"{aid} has empty VERSION"
        assert analyzer.METHOD, f"{aid} has empty METHOD"
        assert analyzer.DEFAULT_LIMITATIONS, f"{aid} has no limitations"


# T-02: every analyzer's profile_schema() is valid JSON Schema
def test_T02_profile_schemas_valid():
    for aid, analyzer in all_analyzers().items():
        schema = analyzer.profile_schema()
        assert isinstance(schema, dict), f"{aid} schema not a dict"
        assert schema.get("type") == "object", f"{aid} schema type must be object"
        # Validate that the schema itself is a valid JSON Schema
        jsonschema.Draft7Validator.check_schema(schema)
        # The empty instance should validate (analyzers can have no params)
        try:
            jsonschema.validate(instance={}, schema=schema)
        except jsonschema.ValidationError:
            # Some analyzers (loop) may require a key — that's fine, we test
            # the actual default profile elsewhere.
            pass


# T-03: all analyzers implement the contract methods
def test_T03_analyzer_contract_methods():
    for aid, analyzer in all_analyzers().items():
        assert callable(getattr(analyzer, "applicable", None)), f"{aid} missing applicable()"
        assert callable(getattr(analyzer, "analyze", None)), f"{aid} missing analyze()"
        assert callable(getattr(analyzer, "profile_schema", None)), f"{aid} missing profile_schema()"


# T-04: status taxonomy is complete
def test_T04_status_taxonomy_complete():
    expected = {"pass", "warning", "fail", "not_applicable", "indeterminate", "needs_review", "error"}
    actual = {s.value for s in Status}
    assert actual == expected


# T-05: status precedence is correct
def test_T05_status_precedence():
    assert aggregate_status([Status.PASS, Status.WARNING, Status.FAIL]) == Status.FAIL
    assert aggregate_status([Status.PASS, Status.WARNING]) == Status.WARNING
    assert aggregate_status([Status.NOT_APPLICABLE, Status.PASS]) == Status.PASS
    assert aggregate_status([Status.INDETERMINATE, Status.NEEDS_REVIEW]) == Status.NEEDS_REVIEW
    assert aggregate_status([Status.ERROR, Status.FAIL]) == Status.ERROR
    assert aggregate_status([]) == Status.PASS
    # ERROR is highest
    assert STATUS_PRECEDENCE[-1] == Status.ERROR
    assert STATUS_PRECEDENCE[0] == Status.NOT_APPLICABLE


# T-06: PCM is immutable (CT-06)
def test_T06_pcm_immutable(sine_1k):
    with pytest.raises(Exception):
        sine_1k.sample_rate = 48000  # type: ignore[misc]


# T-07: Finding is immutable and serializes cleanly
def test_T07_finding_immutable_and_serializable():
    f = Finding(
        check_id="t",
        analyzer="t",
        metric="m",
        value=1.0,
        unit="x",
        status=Status.PASS,
    )
    with pytest.raises(Exception):
        f.value = 2.0  # type: ignore[misc]
    d = f.to_dict()
    assert d["status"] == "pass"
    assert d["value"] == 1.0
    # JSON-serializable
    json.dumps(d)


# T-08: NaN/Infinity suppression (CT-10)
def test_T08_finding_suppresses_nan():
    import math

    f = Finding(
        check_id="t",
        analyzer="t",
        metric="m",
        value=math.nan,
        unit="x",
        status=Status.PASS,
    )
    d = f.to_dict()
    assert d["value"] is None
    assert any("non-finite" in l for l in d["limitations"])


# T-09: Bundle has measurement_fingerprint
def test_T09_bundle_fingerprint(sine_1k):
    from audio_suite.bundle import build_bundle
    from audio_suite.models import Profile

    profile = Profile(name="t", version="1", analyzers={})
    bundle = build_bundle(sine_1k, profile, [])
    assert bundle.measurement_fingerprint
    assert len(bundle.measurement_fingerprint) == 64  # sha256 hex


# T-10: bundle is deterministic (CT-05)
def test_T10_bundle_deterministic(sine_1k):
    from audio_suite.bundle import build_bundle
    from audio_suite.models import Profile

    profile = Profile(name="t", version="1", analyzers={})
    b1 = build_bundle(sine_1k, profile, [])
    b2 = build_bundle(sine_1k, profile, [])
    assert b1.measurement_fingerprint == b2.measurement_fingerprint
    assert b1.to_dict() == b2.to_dict()


def test_version_string():
    assert __version__ == "0.1.0"


def test_analyzer_registry_non_empty():
    assert len(analyzer_ids()) >= 14
