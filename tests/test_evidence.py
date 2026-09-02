"""Tests: evidence (build_bundle + save_bundle + atomic write + schema validation)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.evidence import build_bundle, save_bundle, validate_bundle_against_schema


@pytest.fixture
def simple_policy():
    return {
        "name": "test_v1",
        "_profile_sha256": "a" * 64,
        "_profile_path": "/tmp/test_v1.yaml",
        "checks": [],
        "decision_policy": {},
    }


@pytest.fixture
def simple_findings():
    return [
        {
            "id": "AC-01",
            "name": "Loudness",
            "value": -23.0,
            "unit": "LUFS",
            "threshold": "-23.0 ± 0.5",
            "status": "pass",
            "severity": "info",
            "description": "OK",
        }
    ]


class TestBuildBundle:
    def test_basic_structure(self, tmp_path: Path, simple_policy, simple_findings):
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"dummy content for hash")

        bundle = build_bundle(
            input_audio=audio,
            policy=simple_policy,
            findings=simple_findings,
            provenance={"events": []},
            pcm_canonical_sha256="b" * 64,
            decoder_info={"decoder": "ffmpeg", "ffmpeg_version": "7.0"},
            decision="pass",
        )

        assert bundle["schema"] == "urn:audio-suite:bundle:v1.0.0"
        assert bundle["schema_version"] == "1.0.0"
        assert bundle["subject"]["file_sha256"] != ""
        assert bundle["execution"]["suite_version"] == "audio-suite/0.2.0-beta"
        assert bundle["decision"] == "pass"
        assert "findings" in bundle
        assert "limitations" in bundle
        assert "measurement_fingerprint" in bundle
        assert "signature" in bundle
        assert "bundle_sha256" in bundle

    def test_limitations_auto_collected(self, tmp_path: Path, simple_policy):
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"dummy")

        bundle = build_bundle(
            input_audio=audio,
            policy=simple_policy,
            findings=[],
            provenance={"events": []},
            pcm_canonical_sha256="b" * 64,
            decoder_info={"decoder": "fallback"},
            decision="pass",
            decoder_used="fallback",
            signature_mode="unsigned",
        )
        assert "signature_unsigned" in bundle["limitations"]
        assert "decoder_fallback_used" in bundle["limitations"]
        assert "asr_not_run" in bundle["limitations"]
        assert "fingerprint_not_run" in bundle["limitations"]

    def test_toctou_limitation_added(self, tmp_path: Path, simple_policy):
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"dummy")
        bundle = build_bundle(
            input_audio=audio,
            policy=simple_policy,
            findings=[],
            provenance={"events": []},
            pcm_canonical_sha256="b" * 64,
            decoder_info={},
            decision="pass",
            toctou_detected=True,
        )
        assert "toctou_detected" in bundle["limitations"]

    def test_unsigned_signature_default(self, tmp_path: Path, simple_policy):
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"dummy")
        bundle = build_bundle(
            input_audio=audio,
            policy=simple_policy,
            findings=[],
            provenance={"events": []},
            pcm_canonical_sha256="b" * 64,
            decoder_info={},
            decision="pass",
        )
        assert bundle["signature"]["status"] == "unsigned"


class TestSaveBundleAtomic:
    def test_atomic_write_creates_file(self, tmp_path: Path, simple_policy, simple_findings):
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"dummy")
        bundle = build_bundle(
            input_audio=audio,
            policy=simple_policy,
            findings=simple_findings,
            provenance={"events": []},
            pcm_canonical_sha256="b" * 64,
            decoder_info={},
            decision="pass",
        )
        out = tmp_path / "bundle.json"
        save_bundle(bundle, out)
        assert out.exists()
        loaded = json.loads(out.read_text())
        assert loaded["schema"] == "urn:audio-suite:bundle:v1.0.0"

    def test_no_tmp_file_left(self, tmp_path: Path, simple_policy):
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"dummy")
        bundle = build_bundle(
            input_audio=audio,
            policy=simple_policy,
            findings=[],
            provenance={"events": []},
            pcm_canonical_sha256="b" * 64,
            decoder_info={},
            decision="pass",
        )
        out = tmp_path / "subdir" / "bundle.json"
        save_bundle(bundle, out)
        # Não deve haver arquivos .tmp no diretório pai
        tmps = list(out.parent.glob(".bundle-*.tmp"))
        assert tmps == []

    def test_creates_parent_dir(self, tmp_path: Path, simple_policy):
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"dummy")
        bundle = build_bundle(
            input_audio=audio,
            policy=simple_policy,
            findings=[],
            provenance={"events": []},
            pcm_canonical_sha256="b" * 64,
            decoder_info={},
            decision="pass",
        )
        out = tmp_path / "deep" / "nested" / "bundle.json"
        save_bundle(bundle, out)
        assert out.exists()


class TestSchemaValidation:
    def test_valid_bundle_passes(self, tmp_path: Path, simple_policy, simple_findings):
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"dummy")
        bundle = build_bundle(
            input_audio=audio,
            policy=simple_policy,
            findings=simple_findings,
            provenance={"events": []},
            pcm_canonical_sha256="b" * 64,
            decoder_info={},
            decision="pass",
        )
        # Não deve levantar
        validate_bundle_against_schema(bundle)

    def test_missing_required_field_raises(self):
        bad_bundle = {"schema": "x"}  # sem subject, execution, etc.
        with pytest.raises(ValueError):
            validate_bundle_against_schema(bad_bundle)

    def test_invalid_status_raises(self, tmp_path: Path, simple_policy):
        audio = tmp_path / "test.wav"
        audio.write_bytes(b"dummy")
        bundle = build_bundle(
            input_audio=audio,
            policy=simple_policy,
            findings=[],
            provenance={"events": []},
            pcm_canonical_sha256="b" * 64,
            decoder_info={},
            decision="pass",
        )
        bundle["findings"].append({
            "id": "X", "name": "n", "status": "totally_invalid_status"
        })
        with pytest.raises(ValueError):
            validate_bundle_against_schema(bundle)
