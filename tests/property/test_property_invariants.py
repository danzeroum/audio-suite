"""Property-based tests (Hypothesis) for invariants."""
from __future__ import annotations

import hashlib

import numpy as np
import pytest
from hypothesis import given, settings, strategies as st
from hypothesis.extra.numpy import arrays

from audio_suite.decode import sha256_of_file
from audio_suite.models import PCM, Status, aggregate_status, status_rank
from audio_suite.bundle import measurement_fingerprint


# Property 1: Normalizing twice the same PCM doesn't change its identity
# (here we test that the PCM class is idempotent on construction)
@given(
    arrays(np.float32, shape=(1, 100),
           elements=st.floats(min_value=-1.0, max_value=1.0, width=32))
)
def test_pcm_construction_idempotent(samples):
    pcm1 = PCM(samples=samples, sample_rate=44100)
    # Re-wrap the same samples
    pcm2 = PCM(samples=pcm1.samples, sample_rate=pcm1.sample_rate)
    np.testing.assert_array_equal(pcm1.samples, pcm2.samples)
    assert pcm1.sample_rate == pcm2.sample_rate


# Property 2: sha256_of_file is deterministic
def test_sha256_deterministic(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"hello world")
    assert sha256_of_file(p) == sha256_of_file(p)
    assert len(sha256_of_file(p)) == 64


# Property 3: Altering one byte changes the sha256
def test_sha256_byte_change(tmp_path):
    p1 = tmp_path / "a.bin"
    p2 = tmp_path / "b.bin"
    p1.write_bytes(b"hello world")
    p2.write_bytes(b"hello world!")  # extra byte
    assert sha256_of_file(p1) != sha256_of_file(p2)


# Property 4: A more restrictive status never lowers the aggregate
@given(
    st.lists(
        st.sampled_from(list(Status)),
        min_size=0, max_size=20,
    )
)
def test_aggregate_monotonic(statuses):
    """Adding a more severe status must not decrease the aggregate."""
    base = aggregate_status(statuses)
    # Add a FAIL
    extended = statuses + [Status.FAIL]
    extended_agg = aggregate_status(extended)
    assert status_rank(extended_agg) >= status_rank(base)


# Property 5: measurement_fingerprint is deterministic and order-independent
# within the same content (we sort findings before fingerprinting, so
# the same findings in different orders must produce the same fingerprint).
def test_fingerprint_order_independent():
    from audio_suite.models import Finding
    f1 = Finding(check_id="a", analyzer="z", metric="m",
                 value=1.0, unit="x", status=Status.PASS)
    f2 = Finding(check_id="b", analyzer="a", metric="m",
                 value=2.0, unit="x", status=Status.WARNING)
    from audio_suite.bundle import _canonicalize_findings
    canon1 = _canonicalize_findings([f1, f2])
    canon2 = _canonicalize_findings([f2, f1])  # different input order
    assert measurement_fingerprint(canon1) == measurement_fingerprint(canon2)


# Property 6: NaN/Infinity never leaks into a finding's serialized output
@given(st.floats(allow_nan=True, allow_infinity=True))
def test_no_nan_in_finding(value):
    from audio_suite.models import Finding
    f = Finding(check_id="x", analyzer="t", metric="m",
                value=value, unit="x", status=Status.PASS)
    d = f.to_dict()
    if d["value"] is not None:
        assert not np.isnan(d["value"])
        assert not np.isinf(d["value"])


# Property 7: Tampered bundle fingerprint changes
def test_tamper_detection():
    """Changing any finding value changes the fingerprint."""
    from audio_suite.models import Finding
    f1 = Finding(check_id="a", analyzer="t", metric="m",
                 value=1.0, unit="x", status=Status.PASS)
    f2 = Finding(check_id="a", analyzer="t", metric="m",
                 value=2.0, unit="x", status=Status.PASS)
    from audio_suite.bundle import _canonicalize_findings
    fp1 = measurement_fingerprint(_canonicalize_findings([f1]))
    fp2 = measurement_fingerprint(_canonicalize_findings([f2]))
    assert fp1 != fp2
