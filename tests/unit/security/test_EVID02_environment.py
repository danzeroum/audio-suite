"""EVID-02.r+ — snapshot de ambiente ampliado no bundle/SARIF.

Verifica: SHA-256 do profile YAML resolvido (com defaults), environment_hash,
versão de cada analyzer e backend DSP (`python` — reference implementation;
o campo existe para o futuro gated, VI.2).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from audio_suite.environment import (  # noqa: E402
    resolve_profile_canonical,
    resolved_profile_sha256,
    snapshot_environment,
)
from audio_suite.models import PCM  # noqa: E402
from audio_suite.policy import load_profile  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "generated"


@pytest.fixture(scope="module")
def profile():
    return load_profile(ROOT / "audio_suite" / "default_profile.yaml")


@pytest.fixture(scope="module")
def bundle(profile):
    from audio_suite.bundle import build_bundle

    audio = PCM(samples=np.zeros((1, 4410), dtype=np.float32), sample_rate=44100)
    return build_bundle(audio, profile, findings=[])


def test_resolved_profile_hash_is_deterministic(profile):
    h1 = resolved_profile_sha256(profile)
    h2 = resolved_profile_sha256(profile)
    assert h1 == h2
    assert len(h1) == 64


def test_resolved_profile_applies_schema_defaults(profile):
    """min_lufs/max_lufs têm default nos schemas — aparecem no resolved."""
    resolved = resolve_profile_canonical(profile)
    loud = resolved["analyzers"]["loudness"]
    assert "min_lufs" in loud and "max_lufs" in loud
    assert loud["min_lufs"] == -24.0 and loud["max_lufs"] == -16.0


def test_environment_snapshot_fields(profile, bundle):
    env = snapshot_environment(profile)
    for key in (
        "tool_version",
        "python_version",
        "numpy_version",
        "scipy_version",
        "soundfile_version",
        "platform",
        "dsp_backend",
        "analyzer_versions",
        "resolved_profile_sha256",
        "resolved_profile",
        "environment_hash",
    ):
        assert key in env, f"snapshot sem {key}"
    assert env["dsp_backend"] == "python", "backend reference é python (VI.2)"
    assert env["analyzer_versions"]["loudness"]
    # environment_hash é o sha256 do snapshot canônico sem o próprio hash
    without = {k: v for k, v in env.items() if k != "environment_hash"}
    expected = hashlib.sha256(json.dumps(without, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert env["environment_hash"] == expected


def test_bundle_carries_environment(profile, bundle):
    assert bundle.environment is not None
    assert bundle.environment["environment_hash"] == snapshot_environment(profile)["environment_hash"]
    d = bundle.to_dict()
    assert d["environment"]["resolved_profile_sha256"] == resolved_profile_sha256(profile)


def test_profile_change_changes_resolved_hash(profile):
    """Um parâmetro diferente → hash do profile resolvido diferente."""
    from audio_suite.models import Profile

    raw = json.loads(json.dumps(resolve_profile_canonical(profile)))
    raw["analyzers"]["loudness"]["min_lufs"] = -30.0
    other = Profile(
        name=raw["name"],
        version=raw["version"],
        analyzers=raw["analyzers"],
        strict_overlay=raw["strict_overlay"],
        retention_policy=raw["retention_policy"],
        data_classification="internal",
    )
    assert resolved_profile_sha256(other) != resolved_profile_sha256(profile)


def test_sarif_carries_environment(profile, bundle):
    from audio_suite.output.sarif import bundle_to_sarif

    sarif = bundle_to_sarif(bundle)
    props = sarif["runs"][0]["properties"]
    assert props["environment_hash"] == bundle.environment["environment_hash"]
    assert props["dsp_backend"] == "python"
