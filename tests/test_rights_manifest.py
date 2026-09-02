"""Tests: analyzers/rights_manifest (F1.5)."""
from __future__ import annotations

from analyzers.rights_manifest import KNOWN_LICENSES, run_analyzer

VALID_MANIFEST = """\
project:
  name: "Test"
  purpose: non_commercial
  territory: BR

assets_used:
  - asset_id: "a1"
    title: "Track 1"
    licensor: "user@example.com"
    license: "CC-BY-4.0"
    commercial_use_allowed: true
    attribution_required: true
    attribution_text: "Track 1 by user (CC-BY 4.0)"
"""

NC_CONFLICT_MANIFEST = """\
project:
  name: "Commercial"
  purpose: commercial_campaign
  territory: BR

assets_used:
  - asset_id: "a1"
    title: "NC Sample"
    licensor: "user@example.com"
    license: "CC-BY-NC-4.0"
    commercial_use_allowed: false
    attribution_required: true
    attribution_text: "NC Sample by user (CC-BY-NC 4.0)"
"""

MISSING_ATTRIBUTION_MANIFEST = """\
project:
  name: "Test"
  purpose: educational

assets_used:
  - asset_id: "a1"
    title: "Track"
    license: "CC-BY-4.0"
    attribution_required: true
    attribution_text: ""
"""

UNKNOWN_LICENSE_MANIFEST = """\
project:
  name: "Test"
  purpose: personal

assets_used:
  - asset_id: "a1"
    title: "Track"
    license: "Weird-License-1.0"
    attribution_required: false
"""


class TestRightsManifest:
    def test_valid_manifest(self, tmp_path):
        path = tmp_path / "rights.yaml"
        path.write_text(VALID_MANIFEST)
        findings = run_analyzer(manifest_path=path)
        assert any(f["status"] == "pass" for f in findings)

    def test_nc_commercial_conflict(self, tmp_path):
        path = tmp_path / "rights.yaml"
        path.write_text(NC_CONFLICT_MANIFEST)
        findings = run_analyzer(manifest_path=path)
        nc_findings = [f for f in findings if "commercial" in f.get("description", "").lower() or "comercial" in f.get("description", "").lower()]
        assert len(nc_findings) >= 1
        assert all(f["status"] == "fail" for f in nc_findings)

    def test_missing_attribution(self, tmp_path):
        path = tmp_path / "rights.yaml"
        path.write_text(MISSING_ATTRIBUTION_MANIFEST)
        findings = run_analyzer(manifest_path=path)
        attr_findings = [f for f in findings if "attribution" in f.get("description", "").lower() or "atribuição" in f.get("description", "").lower()]
        assert len(attr_findings) >= 1
        assert all(f["status"] == "fail" for f in attr_findings)

    def test_unknown_license_needs_review(self, tmp_path):
        path = tmp_path / "rights.yaml"
        path.write_text(UNKNOWN_LICENSE_MANIFEST)
        findings = run_analyzer(manifest_path=path)
        unknown_findings = [f for f in findings if "não reconhecida" in f.get("description", "")]
        assert len(unknown_findings) >= 1
        assert all(f["status"] == "needs_review" for f in unknown_findings)

    def test_no_manifest_returns_needs_review(self, tmp_path):
        findings = run_analyzer(manifest_path=tmp_path / "nonexistent.yaml")
        assert findings[0]["value"] == "not_provided"
        assert findings[0]["status"] == "needs_review"

    def test_invalid_yaml_returns_fail(self, tmp_path):
        path = tmp_path / "rights.yaml"
        path.write_text("not: valid: yaml: {{{")
        findings = run_analyzer(manifest_path=path)
        assert findings[0]["value"] == "invalid"
        assert findings[0]["status"] == "fail"

    def test_empty_assets_returns_needs_review(self, tmp_path):
        path = tmp_path / "rights.yaml"
        path.write_text("""
project:
  name: "Test"
  purpose: personal
assets_used: []
""")
        findings = run_analyzer(manifest_path=path)
        assert findings[0]["value"] == "empty"
        assert findings[0]["status"] == "needs_review"

    def test_nc_license_inferred_when_commercial_use_allowed_omitted(self, tmp_path):
        """Se commercial_use_allowed não declarado, inferir da licença."""
        path = tmp_path / "rights.yaml"
        path.write_text("""
project:
  name: "Test"
  purpose: commercial_campaign
assets_used:
  - asset_id: "a1"
    title: "Track"
    license: "CC-BY-NC-4.0"
    attribution_required: false
""")
        findings = run_analyzer(manifest_path=path)
        assert any(f["status"] == "fail" for f in findings)

    def test_known_licenses_includes_common(self):
        assert "CC-BY-4.0" in KNOWN_LICENSES
        assert "CC-BY-NC-4.0" in KNOWN_LICENSES
        assert "MIT" in KNOWN_LICENSES
