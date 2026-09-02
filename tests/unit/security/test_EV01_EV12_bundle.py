"""EV-01 to EV-12: Evidence bundle tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from audio_suite.bundle import build_bundle, bundle_to_json, measurement_fingerprint
from audio_suite.models import PCM, Finding, Profile, Status


@pytest.fixture
def simple_findings():
    return [
        Finding(
            check_id="a", analyzer="loudness", metric="lufs", value=-20.0, unit="LUFS", status=Status.PASS
        ),
        Finding(check_id="b", analyzer="clipping", metric="pct", value=0.5, unit="%", status=Status.WARNING),
    ]


def test_EV01_bundle_has_schema_version(sine_1k, simple_findings):
    profile = Profile(name="t", version="1", analyzers={})
    bundle = build_bundle(sine_1k, profile, simple_findings)
    assert bundle.schema_version == "1.0.0"


def test_EV02_bundle_fingerprint_stable(sine_1k, simple_findings):
    profile = Profile(name="t", version="1", analyzers={})
    b1 = build_bundle(sine_1k, profile, simple_findings)
    b2 = build_bundle(sine_1k, profile, simple_findings)
    assert b1.measurement_fingerprint == b2.measurement_fingerprint


def test_EV03_bundle_findings_sorted(sine_1k, simple_findings):
    profile = Profile(name="t", version="1", analyzers={})
    bundle = build_bundle(sine_1k, profile, simple_findings)
    analyzers = [f["analyzer"] for f in bundle.findings]
    assert analyzers == sorted(analyzers)


def test_EV04_bundle_floats_rounded(sine_1k):
    """All floats in findings must be rounded to 6 decimals for determinism."""
    f = Finding(check_id="a", analyzer="t", metric="m", value=0.123456789012345, unit="x", status=Status.PASS)
    profile = Profile(name="t", version="1", analyzers={})
    bundle = build_bundle(sine_1k, profile, [f])
    assert bundle.findings[0]["value"] == 0.123457  # 6 decimals


def test_EV05_bundle_aggregate_status(sine_1k, simple_findings):
    profile = Profile(name="t", version="1", analyzers={})
    bundle = build_bundle(sine_1k, profile, simple_findings)
    assert bundle.aggregate_status == "warning"  # 1 pass + 1 warning


def test_EV06_bundle_to_json_serializable(sine_1k, simple_findings):
    profile = Profile(name="t", version="1", analyzers={})
    bundle = build_bundle(sine_1k, profile, simple_findings)
    s = bundle_to_json(bundle)
    data = json.loads(s)
    assert "findings" in data
    assert "measurement_fingerprint" in data


def test_EV07_fingerprint_changes_on_value_change(sine_1k):
    """Tamper detection: changing a finding value must change the fingerprint."""
    f1 = Finding(check_id="a", analyzer="t", metric="m", value=1.0, unit="x", status=Status.PASS)
    f2 = Finding(check_id="a", analyzer="t", metric="m", value=2.0, unit="x", status=Status.PASS)
    profile = Profile(name="t", version="1", analyzers={})
    b1 = build_bundle(sine_1k, profile, [f1])
    b2 = build_bundle(sine_1k, profile, [f2])
    assert b1.measurement_fingerprint != b2.measurement_fingerprint


def test_EV08_bundle_subject_metadata(sine_1k, simple_findings):
    profile = Profile(name="t", version="1", analyzers={})
    bundle = build_bundle(sine_1k, profile, simple_findings)
    assert bundle.subject["file_sha256"] == sine_1k.file_sha256
    assert bundle.subject["sample_rate_hz"] == sine_1k.sample_rate
    assert bundle.subject["channels"] == sine_1k.channels


def test_EV09_bundle_profile_metadata(sine_1k, simple_findings):
    profile = Profile(name="t", version="1", analyzers={"loudness": {}, "clipping": {}})
    bundle = build_bundle(sine_1k, profile, simple_findings)
    assert bundle.profile["name"] == "t"
    assert "loudness" in bundle.profile["analyzers"]
    assert "clipping" in bundle.profile["analyzers"]


def test_EV10_bundle_unsigned_by_default(sine_1k, simple_findings):
    profile = Profile(name="t", version="1", analyzers={})
    bundle = build_bundle(sine_1k, profile, simple_findings)
    assert bundle.signature is None


def test_EV11_bundle_signed_when_requested(sine_1k, simple_findings, tmp_path):
    from audio_suite.security.signing import generate_keypair

    priv, pub = generate_keypair(tmp_path)
    profile = Profile(name="t", version="1", analyzers={})
    bundle = build_bundle(sine_1k, profile, simple_findings, sign=True, signing_key_path=str(priv))
    assert bundle.signature is not None
    assert bundle.signature["signed"] is True
    assert bundle.signature["algorithm"] == "Ed25519"
    assert "public_key" in bundle.signature
    assert "signature" in bundle.signature


def test_EV12_bundle_redactable(sine_1k):
    """PII redaction should remove user paths from subject.source_path."""
    from audio_suite.security.pii import redact_pii

    profile = Profile(name="t", version="1", analyzers={})
    bundle = build_bundle(sine_1k, profile, [])
    redacted = redact_pii(bundle.to_dict())
    # The source_path may contain /home/z/... which should be redacted
    sp = redacted["subject"]["source_path"]
    if "/home/" in sine_1k.source_path or "/Users/" in sine_1k.source_path:
        assert "[REDACTED:userpath]" in sp
