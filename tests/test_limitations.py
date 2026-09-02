"""Tests: bundle/limitations (S4)."""
from __future__ import annotations

import pytest

from engine.bundle.limitations import (
    KNOWN_LIMITATIONS,
    collect_limitations,
    is_known_limitation,
    validate_limitations_list,
)


class TestKnownLimitations:
    def test_all_known(self):
        assert "fingerprint_not_run" in KNOWN_LIMITATIONS
        assert "asr_not_run" in KNOWN_LIMITATIONS
        assert "signature_unsigned" in KNOWN_LIMITATIONS
        assert "toctou_detected" in KNOWN_LIMITATIONS
        assert len(KNOWN_LIMITATIONS) >= 15

    def test_is_known(self):
        assert is_known_limitation("signature_unsigned")
        assert is_known_limitation("analyzer_timeout:loudness")  # com sufixo
        assert not is_known_limitation("unknown_limitation")


class TestCollectLimitations:
    def test_default_unsigned(self):
        ls = collect_limitations(
            decoder_used="ffmpeg",
            signature_status="unsigned",
        )
        assert "signature_unsigned" in ls
        assert "decoder_fallback_used" not in ls

    def test_fallback_decoder(self):
        ls = collect_limitations(
            decoder_used="fallback",
            signature_status="unsigned",
        )
        assert "decoder_fallback_used" in ls
        assert "signature_unsigned" in ls

    def test_nan_sanitized(self):
        ls = collect_limitations(
            decoder_used="ffmpeg",
            signature_status="signed-local",
            has_nan_sanitized=True,
        )
        assert "nan_samples_sanitized" in ls
        assert "signature_unsigned" not in ls

    def test_empty_audio(self):
        ls = collect_limitations(
            decoder_used="ffmpeg",
            signature_status="signed-local",
            is_empty=True,
        )
        assert "empty_audio" in ls

    def test_toctou(self):
        ls = collect_limitations(
            decoder_used="ffmpeg",
            signature_status="signed-local",
            toctou_detected=True,
        )
        assert "toctou_detected" in ls

    def test_timeout_per_analyzer(self):
        ls = collect_limitations(
            decoder_used="ffmpeg",
            signature_status="signed-local",
            had_timeout=["loudness", "signal"],
        )
        assert "analyzer_timeout:loudness" in ls
        assert "analyzer_timeout:signal" in ls

    def test_truncation_per_analyzer(self):
        ls = collect_limitations(
            decoder_used="ffmpeg",
            signature_status="signed-local",
            truncated_analyzers=["signal"],
        )
        assert "findings_truncated:signal" in ls

    def test_phase_skipped_mono(self):
        ls = collect_limitations(
            decoder_used="ffmpeg",
            signature_status="signed-local",
            phase_skipped_mono=True,
        )
        assert "phase_skipped_mono" in ls

    def test_rights_manifest_missing(self):
        ls = collect_limitations(
            decoder_used="ffmpeg",
            signature_status="signed-local",
            rights_manifest_missing=True,
        )
        assert "rights_manifest_missing" in ls

    def test_provenance_partial(self):
        ls = collect_limitations(
            decoder_used="ffmpeg",
            signature_status="signed-local",
            provenance_partial=True,
        )
        assert "provenance_events_partial" in ls

    def test_fingerprint_not_run_default(self):
        """Por padrão, fingerprint não roda (é stub)."""
        ls = collect_limitations(
            decoder_used="ffmpeg",
            signature_status="signed-local",
            fingerprint_run=False,
        )
        assert "fingerprint_not_run" in ls

    def test_asr_not_run_default(self):
        ls = collect_limitations(
            decoder_used="ffmpeg",
            signature_status="signed-local",
            asr_run=False,
        )
        assert "asr_not_run" in ls


class TestValidateLimitationsList:
    def test_all_known_passes(self):
        validate_limitations_list(["signature_unsigned", "asr_not_run"])

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="desconhecidas"):
            validate_limitations_list(["signature_unsigned", "totally_unknown"])

    def test_with_suffix_allowed(self):
        validate_limitations_list(["analyzer_timeout:loudness"])
