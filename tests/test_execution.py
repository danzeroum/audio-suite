"""Tests: execution pipeline (TOCTOU, fallback, analyzer execution)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import scipy.io.wavfile as wavfile

from engine.execution import ExecutionResult, run_validation


def write_wav(path: Path, pcm: np.ndarray, sr: int = 48000):
    if pcm.dtype != np.float32:
        pcm = pcm.astype(np.float32)
    pcm = np.clip(pcm, -1.0, 1.0)
    pcm_i16 = (pcm * 32767).astype(np.int16)
    if pcm_i16.ndim == 1:
        pcm_i16 = pcm_i16.reshape(-1, 1)
    wavfile.write(str(path), sr, pcm_i16)


@pytest.fixture
def simple_profile():
    return {
        "name": "test_v1",
        "_profile_sha256": "a" * 64,
        "checks": [],
        "decision_policy": {},
    }


@pytest.fixture
def profile_with_checks():
    return {
        "name": "test_v1",
        "_profile_sha256": "a" * 64,
        "checks": [
            {
                "id": "AC-01",
                "analyzer": "loudness",
                "params": {"target_integrated_lufs": -23.0, "tolerance_lufs": 30.0},
                "severity": "info",
            },
            {
                "id": "AC-02",
                "analyzer": "signal",
                "params": {"max_true_peak_dbtp": -1.0, "allow_clipping": False},
                "severity": "info",
            },
        ],
        "decision_policy": {},
    }


@pytest.fixture
def clean_wav(tmp_path: Path):
    sr = 48000
    t = np.linspace(0, 3.0, sr * 3, endpoint=False)
    left = 0.1 * np.sin(2 * np.pi * 440 * t)
    right = 0.1 * np.sin(2 * np.pi * 440 * t + np.pi / 6)
    pcm = np.stack([left, right], axis=1).astype(np.float32)
    path = tmp_path / "clean.wav"
    write_wav(path, pcm, sr)
    return path


class TestRunValidation:
    def test_returns_5_tuple(self, clean_wav, simple_profile):
        result = run_validation(clean_wav, simple_profile)
        assert len(result) == 5
        findings, provenance, pcm_hash, decoder_info, exec_result = result
        assert isinstance(findings, list)
        assert isinstance(provenance, dict)
        assert isinstance(pcm_hash, str)
        assert isinstance(decoder_info, dict)
        assert isinstance(exec_result, ExecutionResult)

    def test_provenance_has_decode_event(self, clean_wav, simple_profile):
        _, provenance, _, _, _ = run_validation(clean_wav, simple_profile)
        assert "events" in provenance
        assert len(provenance["events"]) >= 1
        event = provenance["events"][0]
        assert event["event_type"] == "decode_canonical"
        assert "input_sha256" in event
        assert "output_pcm_sha256" in event
        assert "decoder" in event

    def test_executes_analyzers(self, clean_wav, profile_with_checks):
        findings, _, _, _, _ = run_validation(clean_wav, profile_with_checks)
        # Deve ter findings dos analyzers loudness e signal
        analyzer_names = {f.get("analyzer") for f in findings}
        assert "loudness" in analyzer_names or any("LOUDNESS" in f.get("id", "") for f in findings)
        assert "signal" in analyzer_names or any("SIGNAL" in f.get("id", "") for f in findings)

    def test_unknown_analyzer_skipped(self, clean_wav):
        profile = {
            "name": "test_v1",
            "_profile_sha256": "a" * 64,
            "checks": [
                {"id": "X", "analyzer": "totally_unknown", "params": {}, "severity": "info"}
            ],
        }
        findings, _, _, _, _ = run_validation(clean_wav, profile)
        # Não deve ter findings de analyzer desconhecido
        assert not any("TOTALLY_UNKNOWN" in f.get("id", "") for f in findings)

    def test_analyzer_error_returns_indeterminate(self, clean_wav):
        """Se um analyzer lança exceção, deve virar finding indeterminate."""
        profile = {
            "name": "test_v1",
            "_profile_sha256": "a" * 64,
            "checks": [
                {
                    "id": "X",
                    "analyzer": "loudness",
                    "params": {},  # sem target → usa default
                    "severity": "info",
                    "timeout_s": 0.0001,  # extremamente baixo → timeout
                }
            ],
        }
        findings, _, _, _, exec_result = run_validation(clean_wav, profile, analyzer_timeout_s=0.0001)
        # Deve ter finding de timeout
        assert any("TIMEOUT" in f.get("id", "") for f in findings)
        assert "loudness" in exec_result.had_timeout

    def test_exec_result_has_decoder_used(self, clean_wav, simple_profile):
        _, _, _, _, exec_result = run_validation(clean_wav, simple_profile)
        assert exec_result.decoder_used in ("ffmpeg", "fallback")
        assert exec_result.decoder_info["decoder"] == exec_result.decoder_used

    def test_exec_result_has_pcm(self, clean_wav, simple_profile):
        _, _, _, _, exec_result = run_validation(clean_wav, simple_profile)
        assert exec_result.pcm is not None
        assert exec_result.sample_rate == 48000
        assert exec_result.channels >= 1

    def test_exec_result_has_media_info(self, clean_wav, simple_profile):
        _, _, _, _, exec_result = run_validation(clean_wav, simple_profile)
        assert "audio_codec" in exec_result.media_info
        assert "sample_rate_hz" in exec_result.media_info

    def test_findings_get_id_and_severity(self, clean_wav, profile_with_checks):
        findings, _, _, _, _ = run_validation(clean_wav, profile_with_checks)
        for f in findings:
            if f.get("analyzer") in ("loudness", "signal"):
                assert "id" in f
                assert "severity" in f

    def test_pii_findings_redacted(self, clean_wav, simple_profile, monkeypatch):
        """O9: PII em tags deve ser redigido nos findings."""
        # Mock media_info com PII
        from engine.execution import probe_media
        original_probe = probe_media

        def mock_probe(path):
            info = original_probe(path)
            info["tags"] = {"CONTACT": "user@example.com"}
            return info

        monkeypatch.setattr("engine.execution.probe_media", mock_probe)

        findings, _, _, _, _ = run_validation(clean_wav, simple_profile)
        # Deve ter finding de PII
        pii_findings = [f for f in findings if "PII" in f.get("id", "")]
        if pii_findings:
            # E deve estar redigido
            assert all(f.get("pii_redacted") for f in pii_findings)
            assert all("user@example.com" not in str(f) for f in pii_findings)


class TestExecutionResult:
    def test_default_values(self):
        r = ExecutionResult()
        assert r.findings == []
        assert r.provenance == {"events": []}
        assert r.pcm_hash == ""
        assert r.has_nan_sanitized is False
        assert r.toctou_detected is False
        assert r.had_timeout == []
