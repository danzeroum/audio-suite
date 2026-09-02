"""Tests: analyzers/provenance (F1.4 + A3)."""
from __future__ import annotations

import json

from analyzers.provenance import run_analyzer


class TestProvenanceAnalyzer:
    def test_no_events_file_returns_needs_review(self, tmp_path):
        findings = run_analyzer(
            events_path=None,
            input_audio=None,
        )
        assert len(findings) == 1
        assert findings[0]["value"] == "not_provided"
        assert findings[0]["status"] == "needs_review"

    def test_nonexistent_events_file_returns_needs_review(self, tmp_path):
        findings = run_analyzer(
            events_path=tmp_path / "nonexistent.json",
            input_audio=None,
        )
        assert findings[0]["value"] == "not_provided"

    def test_invalid_json_returns_fail(self, tmp_path):
        path = tmp_path / "events.json"
        path.write_text("not json {")
        findings = run_analyzer(events_path=path, input_audio=None)
        assert findings[0]["value"] == "invalid"
        assert findings[0]["status"] == "fail"

    def test_empty_events_returns_gap(self, tmp_path):
        path = tmp_path / "events.json"
        path.write_text(json.dumps({"events": []}))
        findings = run_analyzer(events_path=path, input_audio=None)
        assert findings[0]["value"] == "gap"
        assert findings[0]["status"] == "needs_review"

    def test_valid_chain_returns_pass(self, tmp_path):
        events = {
            "events": [
                {
                    "event_type": "decode",
                    "input_sha256": "a" * 64,
                    "output_sha256": "b" * 64,
                    "decoder": "ffmpeg",
                    "timestamp": 1,
                },
                {
                    "event_type": "normalize",
                    "input_sha256": "b" * 64,  # matches previous output
                    "output_sha256": "c" * 64,
                    "decoder": "ffmpeg",
                    "timestamp": 2,
                },
            ]
        }
        path = tmp_path / "events.json"
        path.write_text(json.dumps(events))
        findings = run_analyzer(events_path=path, input_audio=None)
        assert findings[0]["value"] == "valid"
        assert findings[0]["status"] == "pass"
        assert findings[0]["events_count"] == 2

    def test_gap_in_chain_returns_gap(self, tmp_path):
        events = {
            "events": [
                {
                    "event_type": "decode",
                    "input_sha256": "a" * 64,
                    "output_sha256": "b" * 64,
                    "decoder": "ffmpeg",
                    "timestamp": 1,
                },
                {
                    "event_type": "normalize",
                    "input_sha256": "x" * 64,  # gap: não bate com "b"
                    "output_sha256": "c" * 64,
                    "decoder": "ffmpeg",
                    "timestamp": 2,
                },
            ]
        }
        path = tmp_path / "events.json"
        path.write_text(json.dumps(events))
        findings = run_analyzer(events_path=path, input_audio=None)
        assert findings[0]["value"] == "gap"
        assert findings[0]["gaps_count"] == 1

    def test_invalid_when_signature_required_and_missing(self, tmp_path):
        events = {
            "events": [
                {
                    "event_type": "decode",
                    "input_sha256": "a" * 64,
                    "output_sha256": "b" * 64,
                    "decoder": "ffmpeg",
                    "timestamp": 1,
                }
            ]
        }
        path = tmp_path / "events.json"
        path.write_text(json.dumps(events))
        findings = run_analyzer(
            events_path=path,
            input_audio=None,
            params={"require_signature": True},
        )
        assert findings[0]["value"] == "invalid"
        assert findings[0]["status"] == "fail"

    def test_input_audio_hash_mismatch_returns_invalid(self, tmp_path):
        events = {
            "events": [
                {
                    "event_type": "decode",
                    "input_sha256": "x" * 64,  # diferente do arquivo real
                    "output_sha256": "b" * 64,
                    "decoder": "ffmpeg",
                    "timestamp": 1,
                }
            ]
        }
        events_path = tmp_path / "events.json"
        events_path.write_text(json.dumps(events))

        # Cria arquivo de áudio dummy
        audio_path = tmp_path / "audio.wav"
        audio_path.write_bytes(b"dummy content")

        findings = run_analyzer(events_path=events_path, input_audio=audio_path)
        assert findings[0]["value"] == "invalid"
        assert findings[0]["status"] == "fail"

    def test_reliability_high(self, tmp_path):
        """Provenance é sempre high reliability (chain é objetiva)."""
        path = tmp_path / "events.json"
        path.write_text(json.dumps({"events": []}))
        findings = run_analyzer(events_path=path)
        assert findings[0]["reliability"] == "high"
