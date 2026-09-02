"""Core data models for audio-suite.

All models are immutable dataclasses (frozen=True) so analyzers cannot mutate
shared state — this is a hard requirement from CT-06 (Não mutação).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

import numpy as np


# ---------------------------------------------------------------------------
# Status taxonomy (CT-14: policy separation — analyzer returns measurement,
# profile decides final status, but the analyzer proposes a status that the
# policy may escalate).
# ---------------------------------------------------------------------------
class Status(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"
    INDETERMINATE = "indeterminate"
    NEEDS_REVIEW = "needs_review"
    ERROR = "error"


# Precedence used when aggregating multiple findings into a bundle-level
# verdict. Higher index = higher severity. ERROR always wins.
STATUS_PRECEDENCE: tuple[Status, ...] = (
    Status.NOT_APPLICABLE,
    Status.PASS,
    Status.INDETERMINATE,
    Status.NEEDS_REVIEW,
    Status.WARNING,
    Status.FAIL,
    Status.ERROR,
)


def status_rank(s: Status) -> int:
    return STATUS_PRECEDENCE.index(s)


def aggregate_status(statuses: list[Status]) -> Status:
    """Return the most severe status from a list."""
    if not statuses:
        return Status.PASS
    return max(statuses, key=status_rank)


# ---------------------------------------------------------------------------
# Canonical PCM representation
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PCM:
    """Canonical mono/stereo/multichannel PCM.

    Attributes:
        samples: float32 array shape (n_channels, n_frames) or (n_frames,) for mono.
                 Always normalized to [-1, 1) regardless of source bit depth.
        sample_rate: integer Hz.
        channels: number of channels (derived from samples.shape).
        channel_layout: optional label like "mono", "stereo", "5.1".
        file_sha256: sha256 of the source file bytes (empty if synthesized).
        source_path: original file path (may be empty for in-memory PCM).
        provenance: dict with decoder metadata (codec, bit_depth, etc.).
    """

    samples: np.ndarray
    sample_rate: int
    channel_layout: str = "mono"
    file_sha256: str = ""
    source_path: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Enforce float32 and at least 2D shape (channels, frames)
        if self.samples.dtype != np.float32:
            object.__setattr__(self, "samples", self.samples.astype(np.float32, copy=False))
        if self.samples.ndim == 1:
            object.__setattr__(self, "samples", self.samples.reshape(1, -1))

    @property
    def channels(self) -> int:
        return int(self.samples.shape[0])

    @property
    def n_frames(self) -> int:
        return int(self.samples.shape[1])

    @property
    def duration_s(self) -> float:
        return self.n_frames / self.sample_rate if self.sample_rate > 0 else 0.0

    @property
    def is_mono(self) -> bool:
        return self.channels == 1

    @property
    def is_stereo(self) -> bool:
        return self.channels == 2

    def channel(self, idx: int = 0) -> np.ndarray:
        """Return a single channel as 1-D float32 array."""
        return self.samples[idx]

    def mono_mix(self) -> np.ndarray:
        """Simple mono mixdown (mean across channels). NOT ITU-compliant —
        for downmix policy use the profile's downmix matrix via MonoCompat."""
        if self.channels == 1:
            return self.samples[0]
        return self.samples.mean(axis=0)


# ---------------------------------------------------------------------------
# Finding: the atomic unit an analyzer produces
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Finding:
    """A single measurement or defect observation.

    Conforms to the Analyzer contract: every finding carries its own
    applicability, method, limitations and (for probabilistic analyzers)
    a confidence value.
    """

    check_id: str
    analyzer: str
    metric: str
    value: float | None
    unit: str
    status: Status
    time_range_ms: tuple[float, float] | None = None
    confidence: float | None = None
    method: str = ""
    limitations: list[str] = field(default_factory=list)
    message: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        # Convert tuple to list for JSON
        if self.time_range_ms is not None:
            d["time_range_ms"] = list(self.time_range_ms)
        # Ensure no NaN/Infinity leak into JSON (CT-10)
        if self.value is not None and not np.isfinite(self.value):
            d["value"] = None
            d["limitations"] = list(d.get("limitations", [])) + [
                "original value was non-finite (NaN/Inf) and was suppressed"
            ]
        return d

    def with_status(self, new_status: Status) -> Finding:
        return Finding(
            check_id=self.check_id,
            analyzer=self.analyzer,
            metric=self.metric,
            value=self.value,
            unit=self.unit,
            status=new_status,
            time_range_ms=self.time_range_ms,
            confidence=self.confidence,
            method=self.method,
            limitations=list(self.limitations),
            message=self.message,
            evidence=dict(self.evidence),
        )


# ---------------------------------------------------------------------------
# Profile / Policy
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Profile:
    """A validated analysis profile.

    The profile is the single source of truth for:
      - which analyzers to run (analyzers dict)
      - per-analyzer parameters
      - severity thresholds (when does warning become fail)
      - the strict overlay policy (--strict)
      - retention / governance metadata
    """

    name: str
    version: str
    analyzers: dict[str, dict[str, Any]]
    strict_overlay: dict[str, Any] = field(default_factory=dict)
    retention_policy: dict[str, Any] = field(default_factory=dict)
    data_classification: str = "internal"
    raw: dict[str, Any] = field(default_factory=dict)

    def analyzer_params(self, analyzer_id: str) -> dict[str, Any]:
        return dict(self.analyzers.get(analyzer_id, {}))

    def is_strict(self) -> bool:
        return bool(self.strict_overlay)


# ---------------------------------------------------------------------------
# Evidence Bundle
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Bundle:
    """The signed evidence bundle produced by a run.

    Determinism (CT-05): the same inputs + analyzer versions must produce
    byte-identical JSON. We sort keys, round floats, and exclude timestamps
    from the signed payload.
    """

    schema_version: str
    tool: dict[str, Any]
    subject: dict[str, Any]
    profile: dict[str, Any]
    findings: list[dict[str, Any]]
    aggregate_status: str
    measurement_fingerprint: str
    signature: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool": self.tool,
            "subject": self.subject,
            "profile": self.profile,
            "findings": self.findings,
            "aggregate_status": self.aggregate_status,
            "measurement_fingerprint": self.measurement_fingerprint,
            "signature": self.signature,
        }


# ---------------------------------------------------------------------------
# Exit codes (CLI-01..CLI-20)
# ---------------------------------------------------------------------------
class ExitCode:
    OK = 0
    FINDING = 1  # analysis ran, at least one fail-level finding
    INVALID_PROFILE = 2  # profile YAML failed validation
    INVALID_INPUT = 3  # input audio could not be decoded / missing
    USAGE = 64  # CLI usage error (sysexits.h EX_USAGE)
