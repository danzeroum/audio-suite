"""Tests: bundle/fingerprint (A2 + O5)."""
from __future__ import annotations

from engine.bundle.fingerprint import (
    canonical_json,
    compute_bundle_sha256,
    compute_measurement_fingerprint,
    quantize_findings,
    quantize_value,
)


class TestQuantize:
    def test_quantize_lufs(self):
        # 0.01 epsilon → 2 decimal places
        v = quantize_value(-22.34567, "LUFS")
        assert abs(v - (-22.35)) < 0.01  # within epsilon

    def test_quantize_dbtp(self):
        v = quantize_value(-1.234, "dBTP")
        assert abs(v - (-1.23)) < 0.05

    def test_quantize_no_unit(self):
        v = quantize_value(0.123456789, None)
        assert abs(v - 0.12345679) < 1e-7

    def test_quantize_non_numeric(self):
        assert quantize_value("hello", "LUFS") == "hello"
        assert quantize_value(None, "LUFS") is None

    def test_quantize_int(self):
        assert quantize_value(42, None) == 42.0

    def test_quantize_findings_preserves_non_value_fields(self):
        findings = [{"id": "X", "name": "n", "value": -22.34567, "unit": "LUFS", "status": "pass"}]
        q = quantize_findings(findings)
        assert q[0]["id"] == "X"
        assert q[0]["name"] == "n"
        assert abs(q[0]["value"] - (-22.35)) < 0.01
        assert q[0]["status"] == "pass"


class TestCanonicalJSON:
    def test_sorted_keys(self):
        out = canonical_json({"b": 1, "a": 2})
        assert out == '{"a":2,"b":1}'

    def test_no_whitespace(self):
        out = canonical_json({"a": 1})
        assert " " not in out

    def test_deterministic_across_orders(self):
        d1 = {"a": 1, "b": 2}
        d2 = {"b": 2, "a": 1}
        assert canonical_json(d1) == canonical_json(d2)


class TestMeasurementFingerprint:
    def test_deterministic_same_input(self):
        findings = [{"id": "X", "name": "n", "value": -23.0, "unit": "LUFS", "status": "pass"}]
        fp1 = compute_measurement_fingerprint(
            "a" * 64, "b" * 64, "c" * 64, "test_v1", "0.2.0-beta", findings, "ffmpeg", 48000
        )
        fp2 = compute_measurement_fingerprint(
            "a" * 64, "b" * 64, "c" * 64, "test_v1", "0.2.0-beta", findings, "ffmpeg", 48000
        )
        assert fp1 == fp2
        assert fp1.startswith("sha256:")

    def test_changes_with_findings(self):
        findings1 = [{"id": "X", "name": "n", "value": -23.0, "unit": "LUFS", "status": "pass"}]
        findings2 = [{"id": "X", "name": "n", "value": -22.0, "unit": "LUFS", "status": "fail"}]
        fp1 = compute_measurement_fingerprint("a" * 64, "b" * 64, "c" * 64, "p", "v", findings1, "ffmpeg", 48000)
        fp2 = compute_measurement_fingerprint("a" * 64, "b" * 64, "c" * 64, "p", "v", findings2, "ffmpeg", 48000)
        assert fp1 != fp2

    def test_changes_with_profile(self):
        findings = []
        fp1 = compute_measurement_fingerprint("a" * 64, "b" * 64, "c" * 64, "p1", "v", findings, "ffmpeg", 48000)
        fp2 = compute_measurement_fingerprint("a" * 64, "b" * 64, "c" * 64, "p2", "v", findings, "ffmpeg", 48000)
        assert fp1 != fp2

    def test_independent_of_finding_order(self):
        """Fingerprint não muda se ordem dos findings mudar (sort)."""
        f1 = [{"id": "A", "value": 1.0}, {"id": "B", "value": 2.0}]
        f2 = [{"id": "B", "value": 2.0}, {"id": "A", "value": 1.0}]
        fp1 = compute_measurement_fingerprint("a", "b", "c", "p", "v", f1, "ffmpeg", 48000)
        fp2 = compute_measurement_fingerprint("a", "b", "c", "p", "v", f2, "ffmpeg", 48000)
        assert fp1 == fp2

    def test_float_quantization_in_fingerprint(self):
        """Pequenas diferenças abaixo do epsilon não mudam fingerprint (O5)."""
        f1 = [{"id": "X", "value": -23.0001, "unit": "LUFS"}]
        f2 = [{"id": "X", "value": -23.0002, "unit": "LUFS"}]
        fp1 = compute_measurement_fingerprint("a", "b", "c", "p", "v", f1, "ffmpeg", 48000)
        fp2 = compute_measurement_fingerprint("a", "b", "c", "p", "v", f2, "ffmpeg", 48000)
        # Ambos quantizam para -23.00
        assert fp1 == fp2


class TestBundleSha256:
    def test_deterministic(self):
        bundle = {"a": 1, "b": 2, "signature": {"status": "unsigned"}}
        h1 = compute_bundle_sha256(bundle)
        h2 = compute_bundle_sha256(bundle)
        assert h1 == h2

    def test_changes_with_content(self):
        b1 = {"a": 1, "signature": {"status": "unsigned"}}
        b2 = {"a": 2, "signature": {"status": "unsigned"}}
        assert compute_bundle_sha256(b1) != compute_bundle_sha256(b2)
