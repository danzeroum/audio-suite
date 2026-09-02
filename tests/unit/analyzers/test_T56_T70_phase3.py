"""T-56 to T-70: Phase 3 (Stem, Pitch, ENF, Deepfake).

Most Phase 3 analyzers are deferred (require ML models / corpus). We test
the contract: they must NOT be registered yet, OR if registered, must
return NEEDS_REVIEW / INDETERMINATE (never auto-conclude).

These tests document the deferral and ensure that when these analyzers
ARE added, they comply with the principle of inference (rule 8).
"""

from __future__ import annotations

import pytest

from audio_suite.analyzers import all_analyzers, analyzer_ids


def test_phase3_analyzers_not_auto_registered():
    """Phase 3 analyzers (deepfake, ENF, pitch_stab, acoustic_fingerprint,
    stem_sep) are NOT in the default registry. Adding them requires corpus
    + model declaration per A2."""
    ids = set(analyzer_ids())
    deferred = {"deepfake", "enf_phase", "pitch_stab", "acoustic_context", "stem_sep", "acoustic_fingerprint"}
    for d in deferred:
        assert d not in ids, f"{d} should not be auto-registered without corpus/model"


def test_no_analyzer_claims_deepfake_detection():
    """Per rule 8 (inferência forense/ML): no analyzer may auto-conclude
    deepfake / authenticity. The ref_quality analyzer must not claim this."""
    for aid, analyzer in all_analyzers().items():
        assert "deepfake" not in analyzer.NAME.lower()
        assert "authentic" not in analyzer.NAME.lower()


def test_needs_review_status_available():
    """Status.NEEDS_REVIEW must be available for future ML analyzers."""
    from audio_suite.models import Status

    assert Status.NEEDS_REVIEW.value == "needs_review"


def test_indeterminate_status_available():
    """Status.INDETERMINATE for full-reference analyzers without reference."""
    from audio_suite.models import Status

    assert Status.INDETERMINATE.value == "indeterminate"


# Placeholder tests for when Phase 3 analyzers are added
@pytest.mark.skip(reason="stem_sep analyzer deferred to Phase 3 (requires corpus)")
def test_stem_sep_requires_reference():
    pass


@pytest.mark.skip(reason="enf analyzer deferred (experimental forensic)")
def test_enf_requires_minimum_duration():
    pass


@pytest.mark.skip(reason="deepfake analyzer deferred (opt-in ML, never auto-conclude)")
def test_deepfake_never_auto_fail():
    pass
