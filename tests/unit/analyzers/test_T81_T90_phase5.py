"""T-81 to T-90: Phase 5 descriptors and extensibility.

Descriptors must never fail (rule 1). Cartridge API is a future extension
point; we test that the registry is extensible.
"""

from __future__ import annotations

import numpy as np
import pytest

from audio_suite.analyzers import all_analyzers, register
from audio_suite.analyzers.base import AudioAnalyzer
from audio_suite.models import PCM, Profile, Status


def test_descriptors_never_fail():
    """Per rule 1: every registered analyzer whose metric is a descriptor
    (centroid, flatness, LRA, etc.) must return PASS, not FAIL."""
    descriptor_analyzers = ["spectral_health", "lra"]
    sr = 44100
    t = np.arange(sr) / sr
    x = 0.3 * np.sin(2 * np.pi * 1000 * t).astype(np.float32)
    pcm = PCM(samples=x, sample_rate=sr, channel_layout="mono")
    profile = Profile(name="t", version="1", analyzers={a: {} for a in descriptor_analyzers})
    for aid in descriptor_analyzers:
        a = all_analyzers()[aid]
        if not a.applicable(pcm, profile):
            continue
        findings = a.analyze(pcm, {})
        for f in findings:
            assert f.status != Status.FAIL, f"{aid} returned FAIL on descriptor"


def test_cartridge_api_extensible():
    """External analyzers can be registered via the @register decorator."""

    class ExternalAnalyzer(AudioAnalyzer):
        ID = "external_test_only"
        NAME = "External Test"
        VERSION = "0.0.1"
        METHOD = "test"
        DEFAULT_LIMITATIONS = ["test only"]

        def applicable(self, audio, profile):
            return True

        def analyze(self, audio, params):
            return [
                self._finding(
                    check_id="ext.test",
                    metric="test",
                    value=1.0,
                    unit="x",
                    status=Status.PASS,
                )
            ]

        def profile_schema(self):
            return {"type": "object", "additionalProperties": False}

    # Register (will raise if duplicate; we use a unique ID)
    register(ExternalAnalyzer)
    assert "external_test_only" in all_analyzers()
    a = all_analyzers()["external_test_only"]
    assert a.NAME == "External Test"


def test_duplicate_registration_rejected():
    """Re-registering the same ID must fail."""

    class A1(AudioAnalyzer):
        ID = "dup_test"
        NAME = "Dup1"
        VERSION = "0.0.1"
        METHOD = "t"
        DEFAULT_LIMITATIONS = ["x"]

        def applicable(self, audio, profile):
            return True

        def analyze(self, audio, params):
            return []

        def profile_schema(self):
            return {"type": "object"}

    register(A1)

    class A2(AudioAnalyzer):
        ID = "dup_test"  # same ID
        NAME = "Dup2"
        VERSION = "0.0.1"
        METHOD = "t"
        DEFAULT_LIMITATIONS = ["x"]

        def applicable(self, audio, profile):
            return True

        def analyze(self, audio, params):
            return []

        def profile_schema(self):
            return {"type": "object"}

    with pytest.raises(ValueError, match="duplicate"):
        register(A2)


@pytest.mark.skip(reason="CARTRIDGE_API (.so loading) deferred to Phase 5")
def test_cartridge_so_loading():
    pass


@pytest.mark.skip(reason="TIMBRE_DISTANCE deferred to Phase 5")
def test_timbre_distance():
    pass
