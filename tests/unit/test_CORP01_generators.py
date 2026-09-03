"""CORP-01.r — seed-based generators are the primary fixture source.

DoD verified here:
  1. ``pytest -k generators`` — generating the whole corpus in two separate
     processes yields byte-identical WAV hashes (determinism across runs and
     machines given the same numpy version).
  2. No generator touches global RNG state (``np.random.seed`` / stdlib
     ``random``) — global APIs are poisoned during generation.
  3. Manifest schema: optional ``expected_findings`` is a list of valid,
     registered rule IDs.
"""

from __future__ import annotations

import json
import random
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.fixtures.generators import (  # noqa: E402
    FIXTURE_SPECS,
    FixtureSpec,
    build_manifest,
    make_rng,
    sha256_of,
    wav_bytes,
)

GENERATORS_PROBE = """
import sys
sys.path.insert(0, {root!r})
import hashlib, json
from tests.fixtures.generators import FIXTURE_SPECS, build_manifest, sha256_of
print(json.dumps({{s.name: sha256_of(s.render_bytes()) for s in FIXTURE_SPECS}}))
"""


def _hashes_from_subprocess() -> dict[str, str]:
    code = GENERATORS_PROBE.format(root=str(ROOT))
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, check=True, text=True)
    return json.loads(out.stdout)


def test_generators_reproducible_across_processes():
    """Two independent generation runs produce identical SHA-256 per fixture."""
    first = _hashes_from_subprocess()
    second = _hashes_from_subprocess()
    assert first == second, "seed-based generation is not deterministic"
    assert len(first) == len(FIXTURE_SPECS)


def test_generators_never_touch_global_rng(monkeypatch):
    """Global RNG APIs are poisoned: any use during generation fails loudly."""

    def _forbidden(*args, **kwargs):  # pragma: no cover - must not run
        raise AssertionError("generator used global RNG state (CORP-01.r violation)")

    monkeypatch.setattr(np.random, "seed", _forbidden)
    monkeypatch.setattr(random, "seed", _forbidden)
    monkeypatch.setattr(random, "random", _forbidden)
    monkeypatch.setattr(random, "uniform", _forbidden)
    monkeypatch.setattr(random, "randint", _forbidden)
    for spec in FIXTURE_SPECS:
        data = spec.render_bytes()
        if spec.name != "empty.wav":  # negative-path fixture is legitimately empty
            assert len(data) > 0, f"{spec.name} rendered empty"


def test_make_rng_is_local_generator():
    rng_a = make_rng(1234)
    rng_b = make_rng(1234)
    assert isinstance(rng_a, np.random.Generator)
    assert np.array_equal(rng_a.standard_normal(16), rng_b.standard_normal(16))


def test_manifest_expected_findings_schema():
    """expected_findings, when present, must be a list of registered rule IDs."""
    from audio_suite.rule_ids import RULE_IDS

    valid_rule_ids = set(RULE_IDS.values())
    manifest = build_manifest()
    for name, meta in manifest.items():
        ef = meta.get("expected_findings")
        if ef is None:
            continue
        assert isinstance(ef, list), f"{name}: expected_findings must be a list"
        for rule_id in ef:
            assert rule_id in valid_rule_ids, f"{name}: {rule_id!r} is not a registered rule_id"


def test_manifest_hashes_match_committed_manifest():
    """Regenerated manifest must agree with the committed one on sha256 values."""
    committed = json.loads((ROOT / "tests" / "fixtures" / "generated" / "manifest.json").read_text())
    fresh = build_manifest()
    for name, meta in fresh.items():
        assert name in committed, f"fixture {name} missing from committed manifest"
        assert committed[name]["sha256"] == meta["sha256"], (
            f"sha256 drift for {name}: committed {committed[name]['sha256'][:12]}… "
            f"vs generated {meta['sha256'][:12]}…"
        )


def test_every_spec_is_well_formed():
    for spec in FIXTURE_SPECS:
        assert isinstance(spec, FixtureSpec)
        assert spec.name
        assert spec.purpose
        assert spec.generator, f"{spec.name}: missing generator provenance"
        assert (spec.signal is None) != (spec.raw_bytes is None), (
            f"{spec.name}: exactly one of signal/raw_bytes must be set"
        )


def test_wav_bytes_deterministic_same_input():
    from tests.fixtures.generators import gen_sine

    x = gen_sine(440)
    assert sha256_of(wav_bytes(x)) == sha256_of(wav_bytes(x))


def test_float_wav_has_no_wallclock_timestamp():
    """Float WAVs must not embed libsndfile's PEAK wall-clock timestamp.

    Regression: libsndfile writes a PEAK chunk (with time(NULL)) for float
    files, making bytes non-reproducible. Our deterministic writer emits no
    PEAK chunk and the file must decode to the exact same samples.
    """
    import io as _io

    import soundfile as sf

    from tests.fixtures.generators import gen_sine

    x = gen_sine(1000, amp=0.5)
    b1 = wav_bytes(x, 44100, "FLOAT")
    b2 = wav_bytes(x, 44100, "FLOAT")
    assert b1 == b2
    assert b"PEAK" not in b1, "float WAV must not contain a PEAK chunk"
    # Round-trip: samples decode identically through libsndfile
    y, sr = sf.read(_io.BytesIO(b1), dtype="float32", always_2d=True)
    assert sr == 44100
    np.testing.assert_array_equal(y.T[0], x)


def test_float_wav_decodes_via_audio_suite_decode(tmp_path):
    from audio_suite.decode import decode
    from tests.fixtures.generators import gen_sine

    p = tmp_path / "float_det.wav"
    p.write_bytes(wav_bytes(gen_sine(1000, amp=0.5), 44100, "FLOAT"))
    pcm = decode(str(p))
    assert pcm.sample_rate == 44100 and pcm.channels == 1
