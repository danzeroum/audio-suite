"""CT-01 to CT-15: Cross-cutting tests mandatory for every analyzer."""

from __future__ import annotations

import copy
import json

import numpy as np
import pytest

from audio_suite.analyzers import all_analyzers
from audio_suite.engine import run_analyzers
from audio_suite.models import PCM, Finding, Profile, Status

SR = 44100


def make_pcm(n_seconds: float = 1.0, channels: int = 1, sr: int = SR, freq: float = 1000.0):
    t = np.arange(int(sr * n_seconds)) / sr
    x = (0.3 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    if channels > 1:
        x = np.stack([x] * channels)
    return PCM(
        samples=x, sample_rate=sr, channel_layout={1: "mono", 2: "stereo"}.get(channels, f"{channels}ch")
    )


# CT-01: every analyzer is registered with ID, version, name, method, schema
def test_CT01_registration_metadata():
    for aid, a in all_analyzers().items():
        assert aid == a.ID
        assert a.NAME and a.VERSION and a.METHOD
        assert isinstance(a.profile_schema(), dict)


# CT-02: invalid profile fails before analysis
def test_CT02_invalid_profile_fails_early():
    from audio_suite.policy import validate_profile

    with pytest.raises(Exception):
        validate_profile(
            {
                "name": "t",
                "version": "1",
                "analyzers": {"nonexistent_analyzer": {}},
            }
        )


# CT-03: inapplicable analyzer returns NOT_APPLICABLE
def test_CT03_inapplicable_returns_status(sine_1k):
    profile = Profile(name="t", version="1", analyzers={"mono_compat": {}})
    findings = run_analyzers(sine_1k, profile)
    assert len(findings) == 1
    assert findings[0].status == Status.NOT_APPLICABLE


# CT-04: missing reference returns structured error (not crash)
def test_CT04_missing_reference(sine_1k):
    profile = Profile(
        name="t",
        version="1",
        analyzers={"ref_quality": {"mode": "speech-full-ref", "reference_path": "/nonexistent.wav"}},
    )
    findings = run_analyzers(sine_1k, profile)
    assert len(findings) == 1
    assert findings[0].status == Status.ERROR


# CT-05: determinism — same input, same output
def test_CT05_determinism(sine_1k):
    profile = Profile(
        name="t",
        version="1",
        analyzers={
            "loudness": {},
            "true_peak": {},
            "clipping": {},
            "spectral_health": {},
            "inspect": {},
        },
    )
    f1 = run_analyzers(sine_1k, profile)
    f2 = run_analyzers(sine_1k, profile)
    assert len(f1) == len(f2)
    for a, b in zip(f1, f2):
        assert a.analyzer == b.analyzer
        assert a.metric == b.metric
        assert a.value == b.value
        assert a.status == b.status


# CT-06: analyzer does not mutate PCM
def test_CT06_no_mutation(sine_1k):
    samples_before = sine_1k.samples.copy()
    profile = Profile(
        name="t",
        version="1",
        analyzers={
            "loudness": {},
            "clipping": {},
            "glitch": {},
            "spectral_health": {},
            "inspect": {},
        },
    )
    run_analyzers(sine_1k, profile)
    np.testing.assert_array_equal(sine_1k.samples, samples_before)


# CT-07: multi-channel coverage
def test_CT07_multichannel():
    for ch in [1, 2]:
        pcm = make_pcm(channels=ch)
        profile = Profile(
            name="t",
            version="1",
            analyzers={
                "loudness": {},
                "clipping": {},
                "spectral_health": {},
            },
        )
        findings = run_analyzers(pcm, profile)
        assert len(findings) > 0


# CT-08: sample rate coverage (8 kHz, 44.1 kHz, 48 kHz, 96 kHz)
def test_CT08_sample_rates():
    for sr in [8000, 22050, 44100, 48000, 96000]:
        pcm = make_pcm(sr=sr)
        profile = Profile(name="t", version="1", analyzers={"loudness": {}})
        findings = run_analyzers(pcm, profile)
        assert findings[0].status in {s for s in Status}


# CT-09: very short, long, silence
def test_CT09_durations():
    # Very short
    pcm = PCM(samples=np.zeros(100, dtype=np.float32), sample_rate=SR)
    profile = Profile(name="t", version="1", analyzers={"loudness": {}})
    findings = run_analyzers(pcm, profile)
    # Should not crash; loudness returns -70 or similar
    assert len(findings) == 1
    # Silence
    pcm_sil = PCM(samples=np.zeros(SR, dtype=np.float32), sample_rate=SR)
    findings = run_analyzers(pcm_sil, profile)
    assert findings[0].value == -70.0


# CT-10: no NaN or Infinity in findings
def test_CT10_no_nan_inf(sine_1k):
    profile = Profile(
        name="t",
        version="1",
        analyzers={
            "loudness": {},
            "true_peak": {},
            "clipping": {},
            "spectral_health": {},
            "lra": {},
            "glitch": {},
            "resampling": {},
            "transient": {},
            "voice_artifacts": {},
            "inspect": {},
            "codec_conf": {},
        },
    )
    findings = run_analyzers(sine_1k, profile)
    for f in findings:
        d = f.to_dict()

        # Recursive NaN check
        def _check(obj):
            if isinstance(obj, float):
                assert not np.isnan(obj), f"NaN in {f.analyzer}/{f.check_id}"
                assert not np.isinf(obj), f"Inf in {f.analyzer}/{f.check_id}"
            elif isinstance(obj, dict):
                for v in obj.values():
                    _check(v)
            elif isinstance(obj, list):
                for v in obj:
                    _check(v)

        _check(d)


# CT-11: temporal findings declare time_range_ms
def test_CT11_temporal_findings_have_range(click_500ms):
    profile = Profile(name="t", version="1", analyzers={"glitch": {}})
    findings = run_analyzers(click_500ms, profile)
    ch_findings = [f for f in findings if f.check_id.startswith("glitch.channel")]
    for f in ch_findings:
        # Glitch findings may have time_range_ms=None at the top level,
        # but events in evidence must have time_range_ms
        events = f.evidence.get("events", [])
        for ev in events:
            assert "time_range_ms" in ev, f"event missing time_range_ms: {ev}"


# CT-12: limitations are registered
def test_CT12_limitations_present():
    for aid, a in all_analyzers().items():
        assert len(a.DEFAULT_LIMITATIONS) > 0, f"{aid} has no limitations"


# CT-13: exceptions become ERROR findings
def test_CT13_exceptions_become_error():
    """An analyzer that raises must produce an ERROR finding, not a crash."""
    from audio_suite.analyzers import _REGISTRY
    from audio_suite.analyzers.base import AudioAnalyzer

    class BoomAnalyzer(AudioAnalyzer):
        ID = "boom_test"
        NAME = "Boom"
        VERSION = "0.0.1"
        METHOD = "raises"
        DEFAULT_LIMITATIONS = ["always raises"]

        def applicable(self, audio, profile):
            return True

        def analyze(self, audio, params):
            raise RuntimeError("intentional boom")

        def profile_schema(self):
            return {"type": "object", "additionalProperties": False}

    _REGISTRY["boom_test"] = BoomAnalyzer()
    try:
        pcm = make_pcm()
        profile = Profile(name="t", version="1", analyzers={"boom_test": {}})
        findings = run_analyzers(pcm, profile)
        assert len(findings) == 1
        assert findings[0].status == Status.ERROR
        assert "intentional boom" in findings[0].message
    finally:
        del _REGISTRY["boom_test"]


# CT-14: policy separation — analyzer returns measurement, profile decides
def test_CT14_policy_separation(sine_1k):
    """The clipping analyzer returns FAIL when threshold is exceeded;
    the strict_overlay can escalate WARNING -> FAIL but not the reverse."""
    from audio_suite.models import Finding
    from audio_suite.policy import apply_policy

    # A WARNING finding
    f = Finding(
        check_id="x",
        analyzer="clipping",
        metric="clipped_sample_pct",
        value=0.5,
        unit="%",
        status=Status.WARNING,
    )
    # Profile with strict_overlay that escalates this metric to fail
    profile_strict = Profile(
        name="t",
        version="1",
        analyzers={},
        strict_overlay={"clipping": {"clipped_sample_pct": "fail"}},
    )
    escalated = apply_policy(f, profile_strict)
    assert escalated.status == Status.FAIL
    # Profile without strict_overlay must NOT escalate
    profile_loose = Profile(name="t", version="1", analyzers={})
    same = apply_policy(f, profile_loose)
    assert same.status == Status.WARNING


# CT-15: regression — every bug fix gets a fixture + test (structural test)
def test_CT15_regression_test_infrastructure():
    """Ensure fixtures/manifest.json exists and is loadable."""
    import json
    from pathlib import Path

    manifest_path = Path(__file__).resolve().parents[2] / "fixtures" / "generated" / "manifest.json"
    assert manifest_path.exists(), "fixtures manifest missing; run scripts/gen_fixtures.py"
    manifest = json.loads(manifest_path.read_text())
    assert len(manifest) >= 20
    # Every fixture has a sha256
    for name, meta in manifest.items():
        assert "sha256" in meta
        assert len(meta["sha256"]) == 64
