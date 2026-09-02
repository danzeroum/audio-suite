"""Tests: discovery (probe + PII detection + redaction)."""
from __future__ import annotations

from engine.discovery import (
    detect_pii_in_tags,
    probe_media,
    probe_media_fallback,
    redact_pii_in_findings,
)


class TestDetectPII:
    def test_email_detected(self):
        tags = {"CONTACT": "user@example.com"}
        findings = detect_pii_in_tags(tags)
        assert len(findings) == 1
        assert findings[0]["pii_type"] == "email"
        assert findings[0]["status"] == "fail"
        assert findings[0]["severity"] == "error"

    def test_phone_detected(self):
        tags = {"PHONE": "+55 11 98765-4321"}
        findings = detect_pii_in_tags(tags)
        assert len(findings) >= 1
        pii_types = {f["pii_type"] for f in findings}
        assert "phone" in pii_types

    def test_cpf_detected(self):
        tags = {"DOC": "123.456.789-09"}
        findings = detect_pii_in_tags(tags)
        assert any(f["pii_type"] == "cpf" for f in findings)

    def test_no_pii_returns_empty(self):
        tags = {"ARTIST": "John Doe", "ALBUM": "Best Of"}
        assert detect_pii_in_tags(tags) == []

    def test_empty_tags(self):
        assert detect_pii_in_tags({}) == []

    def test_multiple_pii_in_one_tag(self):
        tags = {"INFO": "email: a@b.com, phone: +55 11 1234-5678"}
        findings = detect_pii_in_tags(tags)
        assert len(findings) >= 2


class TestRedactPII:
    def test_email_redacted(self):
        findings = [
            {"id": "X", "name": "x", "value": "user@example.com", "pii_type": "email", "status": "fail"}
        ]
        redacted = redact_pii_in_findings(findings)
        assert redacted[0]["value"] == "***@***.**"
        assert redacted[0]["pii_redacted"] is True
        assert "pii_value_sha256_short" in redacted[0]

    def test_phone_redacted(self):
        findings = [
            {"id": "X", "name": "x", "value": "+55 11 98765-4321", "pii_type": "phone", "status": "fail"}
        ]
        redacted = redact_pii_in_findings(findings)
        assert "+" in redacted[0]["value"]
        assert "98765" not in redacted[0]["value"]

    def test_non_pii_findings_untouched(self):
        findings = [
            {"id": "X", "name": "x", "value": -23.5, "unit": "LUFS", "status": "pass"}
        ]
        redacted = redact_pii_in_findings(findings)
        assert redacted[0]["value"] == -23.5
        assert "pii_redacted" not in redacted[0]

    def test_redaction_is_deterministic(self):
        findings = [
            {"id": "X", "name": "x", "value": "user@example.com", "pii_type": "email", "status": "fail"}
        ]
        r1 = redact_pii_in_findings(findings)
        r2 = redact_pii_in_findings(findings)
        assert r1[0]["pii_value_sha256_short"] == r2[0]["pii_value_sha256_short"]

    def test_original_value_not_preserved(self):
        """Garante que o valor original não está presente após redação."""
        findings = [
            {"id": "X", "name": "x", "value": "secret@email.com", "pii_type": "email", "status": "fail"}
        ]
        redacted = redact_pii_in_findings(findings)
        # Não deve haver referência ao email original em nenhum campo
        serialized = str(redacted)
        assert "secret@email.com" not in serialized


class TestProbeMedia:
    def test_probe_wav(self, tmp_wav_factory, clean_stereo_pcm):
        pcm, sr = clean_stereo_pcm
        path = tmp_wav_factory("test.wav", pcm, sr)
        info = probe_media(path)
        assert info["audio_codec"] == "pcm_s16le"
        assert info["sample_rate_hz"] == 48000
        assert info["channels"] == 2
        assert info["duration_s"] > 2.9

    def test_probe_fallback_wav(self, tmp_wav_factory, clean_stereo_pcm):
        pcm, sr = clean_stereo_pcm
        path = tmp_wav_factory("test.wav", pcm, sr)
        info = probe_media_fallback(path)
        assert info["sample_rate_hz"] == 48000
        assert info["channels"] == 2
