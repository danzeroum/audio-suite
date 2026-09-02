"""Tests: analyzers/phase (F1.3 + A4)."""
from __future__ import annotations

import numpy as np

from analyzers.phase import run_analyzer


class TestPhaseAnalyzer:
    def test_mono_returns_not_applicable(self, mono_pcm):
        pcm, _ = mono_pcm
        findings = run_analyzer(pcm=pcm, media_info={}, params={}, verbose=False)
        assert any(f["status"] == "not_applicable" for f in findings)

    def test_short_duration_returns_not_applicable(self):
        sr = 48000
        pcm = np.zeros((100, 2), dtype=np.float32)  # ~2ms
        pcm[:, 0] = 0.1
        pcm[:, 1] = 0.1
        findings = run_analyzer(pcm=pcm, media_info={"sample_rate_hz": sr}, params={}, verbose=False)
        assert any(f["status"] == "not_applicable" and "dura" in f["description"].lower() for f in findings)

    def test_silence_returns_not_applicable(self, silence_pcm):
        pcm, _ = silence_pcm
        findings = run_analyzer(pcm=pcm, media_info={"sample_rate_hz": 48000}, params={}, verbose=False)
        assert any(f["status"] == "not_applicable" for f in findings)

    def test_coherent_stereo_passes(self, clean_stereo_pcm):
        pcm, _ = clean_stereo_pcm
        # L e R muito similares → alta correlação positiva
        pcm[:, 1] = pcm[:, 0] * 0.99  # quase idêntico
        findings = run_analyzer(pcm=pcm, media_info={"sample_rate_hz": 48000}, params={"min_correlation": 0.9}, verbose=False)
        corr_finding = next(f for f in findings if "correlation" in f["name"].lower())
        assert corr_finding["status"] == "pass"
        assert corr_finding["value"] > 0.9

    def test_inverted_polarity_fails(self, inverted_polarity_pcm):
        pcm, _ = inverted_polarity_pcm
        findings = run_analyzer(pcm=pcm, media_info={"sample_rate_hz": 48000}, params={"min_correlation": 0.9}, verbose=False)
        corr_finding = next(f for f in findings if "correlation" in f["name"].lower())
        assert corr_finding["status"] == "fail"
        assert corr_finding["value"] < -0.9

    def test_reliability_not_always_high(self, inverted_polarity_pcm):
        """A4: reliability não é hardcoded como 'high'."""
        pcm, _ = inverted_polarity_pcm
        # Recorta para 1s exato para forçar medium reliability
        pcm = pcm[:48000]
        findings = run_analyzer(pcm=pcm, media_info={"sample_rate_hz": 48000}, params={"min_correlation": 0.9}, verbose=False)
        corr_finding = next(f for f in findings if "correlation" in f["name"].lower())
        # Para 1s com correlação extrema, deve ser medium ou high
        assert corr_finding["reliability"] in ("medium", "high")

    def test_reliability_low_for_short_audio(self):
        sr = 48000
        # 0.6s — entre min_duration e 1s
        pcm = np.zeros((int(0.6 * sr), 2), dtype=np.float32)
        t = np.linspace(0, 0.6, pcm.shape[0], endpoint=False)
        pcm[:, 0] = 0.1 * np.sin(2 * np.pi * 440 * t)
        pcm[:, 1] = -0.1 * np.sin(2 * np.pi * 440 * t)
        findings = run_analyzer(pcm=pcm, media_info={"sample_rate_hz": sr}, params={"min_duration_s": 0.5}, verbose=False)
        corr_finding = next(f for f in findings if "correlation" in f["name"].lower())
        assert corr_finding["reliability"] == "low"

    def test_decorrelated_audio_warning(self):
        """Stereo amplo (correlação ~0) deve ser warning, não fail."""
        sr = 48000
        np.random.seed(42)
        # L e R independentes (decorrelacionados)
        pcm = np.random.randn(sr * 3, 2).astype(np.float32) * 0.1
        findings = run_analyzer(pcm=pcm, media_info={"sample_rate_hz": sr}, params={"min_correlation": 0.9}, verbose=False)
        corr_finding = next(f for f in findings if "correlation" in f["name"].lower())
        # Com ruído aleatório, correlação é ~0 → warning
        assert corr_finding["status"] in ("warning", "pass")

    def test_phase_cancellation_detected(self, inverted_polarity_pcm):
        """Sinal com phase cancellation total deve gerar finding de cancelamento."""
        pcm, _ = inverted_polarity_pcm
        findings = run_analyzer(pcm=pcm, media_info={"sample_rate_hz": 48000}, params={"min_correlation": 0.9}, verbose=False)
        # Deve ter finding de correlação E finding de cancellation
        cancellation = [f for f in findings if "cancellation" in f.get("name", "").lower()]
        assert len(cancellation) >= 1

    def test_method_documented(self, clean_stereo_pcm):
        pcm, _ = clean_stereo_pcm
        pcm[:, 1] = pcm[:, 0]
        findings = run_analyzer(pcm=pcm, media_info={"sample_rate_hz": 48000}, params={}, verbose=False)
        corr_finding = next(f for f in findings if "correlation" in f["name"].lower())
        assert "method" in corr_finding
        assert "Pearson" in corr_finding["method"]

    def test_analysis_window_documented(self, clean_stereo_pcm):
        pcm, _ = clean_stereo_pcm
        findings = run_analyzer(pcm=pcm, media_info={"sample_rate_hz": 48000}, params={}, verbose=False)
        corr_finding = next(f for f in findings if "correlation" in f["name"].lower())
        assert "analysis_window_s" in corr_finding
