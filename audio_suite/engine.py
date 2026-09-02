"""Execution engine — discovers analyzers, runs them, collects findings.

Key invariants:
  - CT-02: invalid profile fails before analysis
  - CT-03: inapplicable analyzers return NOT_APPLICABLE (not silent skip)
  - CT-05: deterministic given same inputs + versions
  - CT-06: analyzers cannot mutate the PCM (frozen dataclass)
  - CT-13: exceptions become ERROR findings, not crashes
  - CT-14: analyzer returns measurement; policy decides final status
"""

from __future__ import annotations

import traceback

from .analyzers import all_analyzers
from .models import PCM, Finding, Profile, Status
from .policy import apply_policy


def run_analyzers(
    audio: PCM,
    profile: Profile,
    *,
    only: list[str] | None = None,
    skip: list[str] | None = None,
) -> list[Finding]:
    """Run all applicable analyzers from the profile against `audio`.

    Args:
        audio: canonical PCM (already decoded).
        profile: validated Profile.
        only: if set, only run these analyzer IDs.
        skip: if set, skip these analyzer IDs.

    Returns:
        List of Findings (with policy applied).
    """
    registry = all_analyzers()
    available_ids = set(registry.keys())

    selected = list(profile.analyzers.keys())
    if only:
        selected = [a for a in selected if a in only]
    if skip:
        selected = [a for a in selected if a not in skip]

    findings: list[Finding] = []
    for aid in selected:
        if aid not in available_ids:
            # Already rejected at profile validation time, but double-check
            findings.append(
                Finding(
                    check_id=f"{aid}.missing",
                    analyzer=aid,
                    metric="error",
                    value=None,
                    unit="enum",
                    status=Status.ERROR,
                    message=f"analyzer '{aid}' is not registered",
                    method="engine",
                )
            )
            continue

        analyzer = registry[aid]
        params = profile.analyzer_params(aid)

        # CT-03: applicability check
        try:
            applicable = analyzer.applicable(audio, profile)
        except Exception as exc:
            findings.append(_error_finding(aid, "applicable()", exc))
            continue

        if not applicable:
            findings.append(
                Finding(
                    check_id=f"{aid}.applicability",
                    analyzer=aid,
                    metric="applicability",
                    value=None,
                    unit="enum",
                    status=Status.NOT_APPLICABLE,
                    method=analyzer.METHOD,
                    message=f"analyzer '{aid}' not applicable to this input",
                    limitations=list(analyzer.DEFAULT_LIMITATIONS),
                )
            )
            continue

        # CT-13: run analysis with timeout (ENG-01), capture exceptions as ERROR
        timeout_s = params.get("_timeout_s", 60.0) if isinstance(params, dict) else 60.0
        raw_findings = _run_with_timeout(analyzer, audio, params, timeout_s, aid, findings)

        # CT-14: apply policy (escalation)
        for f in raw_findings:
            findings.append(apply_policy(f, profile))

    return findings


def _run_with_timeout(analyzer, audio, params, timeout_s, aid, findings):
    """Run analyzer.analyze with a timeout. On timeout, append ERROR finding (ENG-01)."""
    import signal

    def _timeout_handler(signum, frame):
        raise TimeoutError(f"analyzer '{aid}' exceeded {timeout_s}s timeout")

    old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
    signal.setitimer(signal.ITIMER_REAL, float(timeout_s))
    try:
        result = analyzer.analyze(audio, params)
    except TimeoutError as exc:
        findings.append(
            Finding(
                check_id=f"{aid}.timeout",
                analyzer=aid,
                metric="error",
                value=None,
                unit="enum",
                status=Status.ERROR,
                method=f"engine::timeout({timeout_s}s)",
                message=str(exc),
                limitations=["analyzer timed out; result is unreliable"],
            )
        )
        return []
    except Exception as exc:
        findings.append(_error_finding(aid, "analyze()", exc))
        return []
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)
    return result


def _error_finding(analyzer_id: str, where: str, exc: Exception) -> Finding:
    return Finding(
        check_id=f"{analyzer_id}.error",
        analyzer=analyzer_id,
        metric="error",
        value=None,
        unit="enum",
        status=Status.ERROR,
        method=f"engine::{where}",
        message=f"{type(exc).__name__}: {exc}",
        evidence={
            "traceback": traceback.format_exc(limit=3),
        },
        limitations=["analyzer raised an exception; result is unreliable"],
    )
