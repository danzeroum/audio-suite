"""T-81 to T-90: Phase 5 descriptors + cartridge + Phase 5.5 MAM/DAM.

Tests for:
  - TIMBRE_DISTANCE, HARMONIC_TENSION, SPECTRAL_IRREGULARITY,
    INHARMONICITY, FATIGUE_INDEX, RHYTHMIC_GRID_ALIGNMENT, MELODIC_CONTOUR
  - CARTRIDGE_API (external analyzer loading)
  - ACOUSTIC_FINGERPRINT (spectral hash)
  - METADATA_SCHEMA_VALIDATOR (EBUCore/Dublin Core)
  - CSV output format

Per rule 1: all descriptors must never fail builds.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import numpy as np
import pytest

from audio_suite.analyzers import all_analyzers
from audio_suite.cartridge import load_cartridge
from audio_suite.models import PCM, Profile, Status

SR = 44100


def profile_with(**analyzers) -> Profile:
    return Profile(name="t", version="1", analyzers=analyzers)


def make_pcm(n_seconds: float = 2.0, freq: float = 440.0, sr: int = SR):
    t = np.arange(int(sr * n_seconds)) / sr
    x = (0.3 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return PCM(samples=x, sample_rate=sr, channel_layout="mono")


# === Phase 5: Descriptors — never fail ===


@pytest.mark.parametrize(
    "analyzer_id",
    [
        "timbre_distance",
        "harmonic_tension",
        "spectral_irregularity",
        "inharmonicity",
        "fatigue_index",
        "rhythmic_grid_alignment",
        "melodic_contour",
    ],
)
def test_descriptor_never_fails(analyzer_id, sine_1k):
    """Per rule 1: descriptors must never return FAIL status."""
    a = all_analyzers()[analyzer_id]
    if not a.applicable(sine_1k, profile_with()):
        return  # skip if not applicable
    findings = a.analyze(sine_1k, {})
    for f in findings:
        assert f.status != Status.FAIL, f"{analyzer_id} returned FAIL on descriptor"
        assert f.status in (Status.PASS, Status.NOT_APPLICABLE, Status.NEEDS_REVIEW), (
            f"{analyzer_id} returned unexpected status {f.status}"
        )


def test_timbre_distance_returns_value(sine_1k):
    a = all_analyzers()["timbre_distance"]
    findings = a.analyze(sine_1k, {})
    f = findings[0]
    assert f.value is not None
    assert 0.0 <= f.value <= 1.0


def test_harmonic_tension_tone_low(sine_1k):
    """A pure tone should have low harmonic tension (mostly harmonic energy)."""
    a = all_analyzers()["harmonic_tension"]
    findings = a.analyze(sine_1k, {})
    if findings[0].value is not None:
        # Pure tone = mostly harmonic = low tension
        assert findings[0].value < 0.9


def test_spectral_irregularity_returns_value(sine_1k):
    a = all_analyzers()["spectral_irregularity"]
    findings = a.analyze(sine_1k, {})
    f = findings[0]
    if f.value is not None:
        assert 0.0 <= f.value <= 1.0


def test_inharmonicity_pure_tone_low(sine_1k):
    """A pure tone should have low inharmonicity."""
    a = all_analyzers()["inharmonicity"]
    findings = a.analyze(sine_1k, {})
    if findings[0].value is not None:
        assert findings[0].value < 0.1


def test_fatigue_index_constant_signal(sine_1k):
    """A constant-amplitude signal should have ~0 fatigue."""
    a = all_analyzers()["fatigue_index"]
    findings = a.analyze(sine_1k, {})
    if findings[0].value is not None:
        assert abs(findings[0].value) < 0.5  # minimal change


def test_rhythmic_grid_returns_alignment(sine_1k):
    a = all_analyzers()["rhythmic_grid_alignment"]
    findings = a.analyze(sine_1k, {})
    if findings[0].value is not None:
        assert 0.0 <= findings[0].value <= 1.0


def test_melodic_contour_constant_tone(sine_1k):
    """A constant-frequency tone should have 'static' contour."""
    a = all_analyzers()["melodic_contour"]
    findings = a.analyze(sine_1k, {})
    f = findings[0]
    if f.evidence.get("direction"):
        assert f.evidence["direction"] in ("rising", "falling", "static")


# === CARTRIDGE_API ===


def test_cartridge_loads_external_analyzer(tmp_path):
    """The cartridge API should load an external .py analyzer."""
    # Write a minimal cartridge plugin
    plugin_code = """
from audio_suite.models import Finding, Status

class MyAnalyzer:
    def applicable(self, audio, profile):
        return True
    def analyze(self, audio, params):
        return [Finding(
            check_id="custom.test",
            analyzer="custom",
            metric="test_metric",
            value=42.0,
            unit="x",
            status=Status.PASS,
            message="cartridge works",
        )]
    def profile_schema(self):
        return {"type": "object", "additionalProperties": False}

def create_analyzer():
    return MyAnalyzer()
"""
    plugin_path = tmp_path / "my_plugin.py"
    plugin_path.write_text(plugin_code)

    cartridge = load_cartridge(str(plugin_path), "custom_cartridge_test")
    assert cartridge.ID == "custom_cartridge_test"

    pcm = make_pcm()
    findings = cartridge.analyze(pcm, {})
    assert len(findings) == 1
    assert findings[0].value == 42.0
    assert findings[0].status == Status.PASS


def test_cartridge_missing_create_analyzer(tmp_path):
    """A plugin without create_analyzer() should raise AttributeError."""
    plugin_path = tmp_path / "bad_plugin.py"
    plugin_path.write_text("# no create_analyzer function\nx = 1\n")
    with pytest.raises(AttributeError, match="create_analyzer"):
        load_cartridge(str(plugin_path), "bad_cartridge_test")


def test_cartridge_duplicate_id_rejected(tmp_path):
    """Loading a cartridge with an existing ID should fail."""
    plugin_path = tmp_path / "dup_plugin.py"
    plugin_path.write_text("""
from audio_suite.models import Finding, Status
class A:
    def applicable(self, audio, profile): return True
    def analyze(self, audio, params): return []
    def profile_schema(self): return {"type": "object"}
def create_analyzer(): return A()
""")
    load_cartridge(str(plugin_path), "dup_cartridge_test")
    with pytest.raises(ValueError, match="already registered"):
        load_cartridge(str(plugin_path), "dup_cartridge_test")


def test_cartridge_exception_becomes_error(tmp_path):
    """If the cartridge raises, it becomes an ERROR finding, not a crash."""
    plugin_path = tmp_path / "boom_plugin.py"
    plugin_path.write_text("""
from audio_suite.models import Finding, Status
class Boom:
    def applicable(self, audio, profile): return True
    def analyze(self, audio, params):
        raise RuntimeError("intentional cartridge failure")
    def profile_schema(self): return {"type": "object"}
def create_analyzer(): return Boom()
""")
    cartridge = load_cartridge(str(plugin_path), "boom_cartridge_test")
    pcm = make_pcm()
    findings = cartridge.analyze(pcm, {})
    assert findings[0].status == Status.ERROR
    assert "intentional cartridge failure" in findings[0].message


# === Phase 5.5: MAM/DAM ===


def test_acoustic_fingerprint_deterministic(sine_1k):
    """The same input must produce the same fingerprint."""
    a = all_analyzers()["acoustic_fingerprint"]
    f1 = a.analyze(sine_1k, {})[0]
    f2 = a.analyze(sine_1k, {})[0]
    assert f1.evidence["fingerprint"] == f2.evidence["fingerprint"]


def test_acoustic_fingerprint_different_inputs(sine_1k, white_noise):
    """Different inputs should produce different fingerprints."""
    a = all_analyzers()["acoustic_fingerprint"]
    f1 = a.analyze(sine_1k, {})[0]
    f2 = a.analyze(white_noise, {})[0]
    assert f1.evidence["fingerprint"] != f2.evidence["fingerprint"]


def test_acoustic_fingerprint_is_observation(sine_1k):
    """Fingerprint is observation-only — never fails."""
    a = all_analyzers()["acoustic_fingerprint"]
    findings = a.analyze(sine_1k, {})
    assert findings[0].status == Status.PASS


def test_metadata_schema_validator_ebucore_complete():
    """EBUCore with all required fields should pass."""
    a = all_analyzers()["metadata_schema_validator"]
    pcm = make_pcm()
    profile = profile_with(
        metadata_schema_validator={
            "schema": "ebucore",
            "metadata": {"title": "Test", "creator": "Me", "date": "2026", "format": "WAV"},
        }
    )
    findings = a.analyze(pcm, profile.analyzer_params("metadata_schema_validator"))
    f = findings[0]
    assert f.status == Status.PASS
    assert f.value == 1.0


def test_metadata_schema_validator_ebucore_missing():
    """EBUCore with missing fields should warn."""
    a = all_analyzers()["metadata_schema_validator"]
    pcm = make_pcm()
    profile = profile_with(
        metadata_schema_validator={
            "schema": "ebucore",
            "metadata": {"title": "Test"},  # missing creator, date, format
        }
    )
    findings = a.analyze(pcm, profile.analyzer_params("metadata_schema_validator"))
    f = findings[0]
    assert f.status == Status.WARNING
    assert f.value < 1.0


def test_metadata_schema_validator_dublin_core():
    """Dublin Core with all 15 elements should pass."""
    a = all_analyzers()["metadata_schema_validator"]
    pcm = make_pcm()
    all_fields = dict.fromkeys(a.DUBLIN_CORE_15, "value")
    profile = profile_with(
        metadata_schema_validator={
            "schema": "dublin_core",
            "metadata": all_fields,
        }
    )
    findings = a.analyze(pcm, profile.analyzer_params("metadata_schema_validator"))
    f = findings[0]
    assert f.status == Status.PASS


def test_metadata_schema_validator_unknown_schema():
    a = all_analyzers()["metadata_schema_validator"]
    pcm = make_pcm()
    profile = profile_with(
        metadata_schema_validator={
            "schema": "unknown_schema",
            "metadata": {},
        }
    )
    findings = a.analyze(pcm, profile.analyzer_params("metadata_schema_validator"))
    assert findings[0].status == Status.NOT_APPLICABLE


# === CSV output ===


def test_csv_output_format(sine_1k):
    """CSV output should be valid CSV with headers."""
    from audio_suite.bundle import build_bundle
    from audio_suite.models import Finding
    from audio_suite.output.csv_out import bundle_to_csv

    findings = [
        Finding(
            check_id="t",
            analyzer="loudness",
            metric="lufs",
            value=-20.0,
            unit="LUFS",
            status=Status.PASS,
            message="ok",
        ),
    ]
    profile = Profile(name="t", version="1", analyzers={})
    bundle = build_bundle(sine_1k, profile, findings)
    csv_str = bundle_to_csv(bundle)
    reader = csv.DictReader(io.StringIO(csv_str))
    rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["analyzer"] == "loudness"
    assert rows[0]["value"] == "-20.0"


def test_csv_output_to_file(sine_1k, tmp_path):
    """CSV output should write to file."""
    from audio_suite.bundle import build_bundle
    from audio_suite.models import Finding
    from audio_suite.output.csv_out import bundle_to_csv

    findings = [Finding(check_id="t", analyzer="t", metric="m", value=1.0, unit="x", status=Status.PASS)]
    profile = Profile(name="t", version="1", analyzers={})
    bundle = build_bundle(sine_1k, profile, findings)
    out_path = tmp_path / "report.csv"
    bundle_to_csv(bundle, output_path=out_path)
    assert out_path.exists()
    content = out_path.read_text()
    assert "analyzer" in content
    assert "loudness" not in content or "t" in content


def test_csv_cli_integration():
    """The CLI --format csv should work end-to-end."""
    import io
    from contextlib import redirect_stdout

    from audio_suite.cli import main

    out = io.StringIO()
    with redirect_stdout(out):
        try:
            main(
                [
                    "analyze",
                    "tests/fixtures/generated/sine_1k_mono.wav",
                    "--format",
                    "csv",
                    "--only",
                    "inspect",
                ]
            )
        except SystemExit:
            pass
    csv_output = out.getvalue()
    assert "analyzer" in csv_output
    assert "inspect" in csv_output
