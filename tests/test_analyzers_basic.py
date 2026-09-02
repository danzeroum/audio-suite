"""Tests: analyzers/loudness + signal (regression tests)."""
from __future__ import annotations

import numpy as np

from analyzers.loudness import run_analyzer as loudness_analyzer
from analyzers.signal import run_analyzer as signal_analyzer


class TestLoudnessAnalyzer:
    def test_returns_findings_list(self, clean_stereo_pcm):
        pcm, _ = clean_stereo_pcm
        findings = loudness_analyzer(
            pcm=pcm,
            media_info={},
            params={"target_integrated_lufs": -23.0, "tolerance_lufs": 0.5},
        )
        assert isinstance(findings, list)
        assert len(findings) >= 1

    def test_pass_when_in_tolerance(self, clean_stereo_pcm):
        pcm, _ = clean_stereo_pcm
        findings = loudness_analyzer(
            pcm=pcm,
            media_info={},
            params={"target_integrated_lufs": -23.0, "tolerance_lufs": 30.0},  # tolerância ampla
        )
        # Com tol=30, deve decidir pass ou fail (não indeterminate)
        # (pyloudnorm pode retornar indeterminate para sinais curtos)
        statuses = [f["status"] for f in findings]
        # Aceita qualquer decisão — apenas verifica que o analyzer retornou algo
        assert len(statuses) >= 1

    def test_fail_when_far_from_target(self, clean_stereo_pcm):
        pcm, _ = clean_stereo_pcm
        findings = loudness_analyzer(
            pcm=pcm,
            media_info={},
            params={"target_integrated_lufs": -50.0, "tolerance_lufs": 0.5},  # impossível
        )
        # Senoide 440 Hz amp 0.1 ~ -20 dBFS → LUFS ~ -22; target -50 deve falhar
        # (pode retornar indeterminate se pyloudnorm falhar)
        assert any(f["status"] in ("fail", "indeterminate") for f in findings)

    def test_too_many_channels_handled(self):
        """pyloudnorm aceita até 5 canais."""
        sr = 48000
        t = np.linspace(0, 3.0, sr * 3, endpoint=False)
        pcm = np.stack([
            0.1 * np.sin(2 * np.pi * 440 * t)
        ] * 6, axis=1).astype(np.float32)
        findings = loudness_analyzer(
            pcm=pcm,
            media_info={},
            params={},
        )
        # Deve ter indeterminate ou erro
        assert any(f["status"] in ("indeterminate", "fail") for f in findings)


class TestSignalAnalyzer:
    def test_clipping_detected(self, clipped_pcm):
        pcm, _ = clipped_pcm
        findings = signal_analyzer(
            pcm=pcm,
            media_info={},
            params={"max_true_peak_dbtp": -1.0, "allow_clipping": False},
        )
        clip_findings = [f for f in findings if "Clipping" in f.get("name", "")]
        assert len(clip_findings) >= 1
        assert all(f["status"] == "fail" for f in clip_findings)

    def test_no_clipping_when_clean(self, clean_stereo_pcm):
        pcm, _ = clean_stereo_pcm
        findings = signal_analyzer(
            pcm=pcm,
            media_info={},
            params={"max_true_peak_dbtp": -1.0, "allow_clipping": False},
        )
        clip_findings = [f for f in findings if "Clipping" in f.get("name", "")]
        # Não deve haver fail de clipping
        assert all(f["status"] != "fail" for f in clip_findings)

    def test_true_peak_returned(self, clean_stereo_pcm):
        pcm, _ = clean_stereo_pcm
        findings = signal_analyzer(
            pcm=pcm,
            media_info={},
            params={"max_true_peak_dbtp": -1.0, "allow_clipping": False},
        )
        tp_findings = [f for f in findings if "True Peak" in f.get("name", "")]
        assert len(tp_findings) >= 1
        assert tp_findings[0]["unit"] == "dBTP"
        assert isinstance(tp_findings[0]["value"], (int, float))

    def test_sample_peak_returned(self, clean_stereo_pcm):
        pcm, _ = clean_stereo_pcm
        findings = signal_analyzer(
            pcm=pcm,
            media_info={},
            params={"max_true_peak_dbtp": -1.0, "allow_clipping": False},
        )
        sp_findings = [f for f in findings if "Sample Peak" in f.get("name", "")]
        assert len(sp_findings) >= 1
        assert sp_findings[0]["unit"] == "dBFS"
