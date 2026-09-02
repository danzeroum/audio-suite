"""Testes dos analyzers críticos."""
import numpy as np
import pytest
from analyzers.loudness import run_analyzer as loudness_analyzer
from analyzers.signal import run_analyzer as signal_analyzer

def test_loudness_pass():
    # Senoide em amplitude que deve estar perto de -23 LUFS
    frames = 48000 * 3
    t = np.linspace(0, 3, frames, endpoint=False)
    pcm = np.sin(2 * np.pi * 440 * t).reshape(-1, 1) * 0.1
    findings = loudness_analyzer(
        pcm=pcm,
        media_info={},
        params={"target_integrated_lufs": -23.0, "tolerance_lufs": 0.5},
        verbose=False
    )
    assert any(f["status"] == "pass" for f in findings), findings

def test_signal_clipping():
    # Senoide com clipping
    frames = 48000 * 1
    t = np.linspace(0, 1, frames, endpoint=False)
    pcm = np.sin(2 * np.pi * 440 * t).reshape(-1, 1) * 1.5
    pcm = np.clip(pcm, -1.0, 1.0)
    findings = signal_analyzer(
        pcm=pcm,
        media_info={},
        params={"max_true_peak_dbtp": -1.0, "allow_clipping": False},
        verbose=False
    )
    assert any(f["name"] == "Clipping" and f["status"] == "fail" for f in findings), findings
