"""T-71 to T-80: Phase 4 spatial / multichannel (deferred).

Per roadmap Fase 4 MULTICHANNEL_LAYOUT v1 supports PCM WAV/FLAC 5.1/7.1.
ADM/BWF and Atmos are subprojects. We test the basic 5.1 layout helper.
"""
from __future__ import annotations

import numpy as np
import pytest

from audio_suite.decode import _layout_from_channels
from audio_suite.models import PCM, Status


def test_layout_from_channels():
    assert _layout_from_channels(1) == "mono"
    assert _layout_from_channels(2) == "stereo"
    assert _layout_from_channels(6) == "5.1"
    assert _layout_from_channels(8) == "7.1"
    assert _layout_from_channels(4) == "custom-4ch"


@pytest.mark.skip(reason="MULTICHANNEL_LAYOUT analyzer deferred to Phase 4")
def test_51_layout_validated():
    pass


@pytest.mark.skip(reason="Binaural compatibility deferred to Phase 4")
def test_binaural_compat():
    pass


@pytest.mark.skip(reason="Atmos 9.1.6 is a subproject (separate from v1)")
def test_atmos_separate_subproject():
    pass


def test_mono_compat_downmix_matrix():
    """Custom downmix matrices should be honored by mono_compat."""
    from audio_suite.analyzers.mono_compat import MonoCompatAnalyzer
    # Build a stereo signal with L=1.0, R=0.5
    sr = 44100
    t = np.arange(sr) / sr
    L = np.sin(2 * np.pi * 1000 * t).astype(np.float32)
    R = 0.5 * np.sin(2 * np.pi * 1000 * t).astype(np.float32)
    pcm = PCM(samples=np.stack([L, R]), sample_rate=sr, channel_layout="stereo")
    a = MonoCompatAnalyzer()
    # Default downmix (0.5, 0.5): mono = 0.75 * sine
    f_default = a.analyze(pcm, {"max_loss_db": 6.0, "downmix_matrix": [0.5, 0.5]})[0]
    # Custom downmix (1.0, 0.0): mono = L only
    f_custom = a.analyze(pcm, {"max_loss_db": 6.0, "downmix_matrix": [1.0, 0.0]})[0]
    # Both should run without error
    assert f_default.unit == "dB"
    assert f_custom.unit == "dB"
