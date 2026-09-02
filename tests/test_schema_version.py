"""Tests: bundle/schema_version (S1 + O7)."""
from __future__ import annotations

import pytest

from engine.bundle.schema_version import (
    SUPPORTED_BUNDLE_URN,
    SUPPORTED_BUNDLE_VERSION,
    check_version_compatibility,
    load_schema_registry,
    parse_semver,
    resolve_schema,
    urn_from_version,
    version_from_urn,
)


class TestSemver:
    def test_parse_valid(self):
        assert parse_semver("1.0.0") == (1, 0, 0)
        assert parse_semver("2.3.7") == (2, 3, 7)

    def test_parse_invalid(self):
        with pytest.raises(ValueError):
            parse_semver("1.0")
        with pytest.raises(ValueError):
            parse_semver("v1.0.0")
        with pytest.raises(ValueError):
            parse_semver("1.0.0-beta")

    def test_urn_from_version(self):
        assert urn_from_version("1.0.0") == "urn:audio-suite:bundle:v1.0.0"

    def test_version_from_urn(self):
        assert version_from_urn("urn:audio-suite:bundle:v1.0.0") == "1.0.0"
        assert version_from_urn("urn:audio-suite:bundle:v2.5.3") == "2.5.3"
        assert version_from_urn("urn:invalid:v1.0.0") is None
        assert version_from_urn("not a urn") is None


class TestCompatibility:
    def test_same_version_ok(self):
        status, _ = check_version_compatibility(SUPPORTED_BUNDLE_URN)
        assert status == "ok"

    def test_newer_minor_warns(self):
        # Constrói urn com minor superior
        major, minor, patch = parse_semver(SUPPORTED_BUNDLE_VERSION)
        newer_urn = urn_from_version(f"{major}.{minor+1}.{patch}")
        status, msg = check_version_compatibility(newer_urn)
        assert status == "warn_older"
        assert "superior" in msg

    def test_newer_major_rejects(self):
        major, _, _ = parse_semver(SUPPORTED_BUNDLE_VERSION)
        newer_urn = urn_from_version(f"{major+1}.0.0")
        status, msg = check_version_compatibility(newer_urn)
        assert status == "reject_newer"
        assert "superior" in msg

    def test_older_major_warns(self):
        major, _, _ = parse_semver(SUPPORTED_BUNDLE_VERSION)
        if major > 1:
            older_urn = urn_from_version(f"{major-1}.0.0")
            status, _ = check_version_compatibility(older_urn)
            assert status == "warn_older"

    def test_unknown_urn(self):
        status, _msg = check_version_compatibility("urn:other:v1.0.0")
        assert status == "unknown"


class TestSchemaRegistry:
    def test_load_registry(self):
        reg = load_schema_registry()
        assert "schemas" in reg
        # Deve ter pelo menos 3 schemas (bundle, finding, provenance)
        assert len(reg["schemas"]) >= 3

    def test_resolve_known_schema(self):
        urn = SUPPORTED_BUNDLE_URN
        path = resolve_schema(urn)
        assert path is not None
        assert path.name == "audio-run-1.0.json"

    def test_resolve_unknown_schema(self):
        path = resolve_schema("urn:audio-suite:bundle:v9.9.9")
        assert path is None
