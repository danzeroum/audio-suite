"""Analyzer base class and protocol.

Every analyzer MUST subclass AudioAnalyzer and implement:
  - applicable(audio, profile) -> bool   (CT-03)
  - analyze(audio, params) -> list[Finding]
  - profile_schema() -> dict (JSON Schema)

The contract is enforced at discovery time: any subclass missing one of
these methods is rejected with a clear error (CT-01).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..models import PCM, Finding, Profile


class AudioAnalyzer(ABC):
    """Base class for all audio-suite analyzers.

    Subclasses set:
      ID: stable identifier used in profiles and findings (e.g. "glitch")
      NAME: human-readable name
      VERSION: semver string; bumped on algorithm change (CT-05 determinism)
      METHOD: short description of the algorithm
      DEFAULT_LIMITATIONS: list of known limitations (rule 5)
    """

    ID: str = ""
    NAME: str = ""
    VERSION: str = "0.1.0"
    METHOD: str = ""
    DEFAULT_LIMITATIONS: list[str] = []

    @abstractmethod
    def applicable(self, audio: PCM, profile: Profile) -> bool:
        """Return True if this analyzer applies to the audio + profile."""

    @abstractmethod
    def analyze(self, audio: PCM, params: dict[str, Any]) -> list[Finding]:
        """Run the analysis. Return a list of Finding."""

    @abstractmethod
    def profile_schema(self) -> dict[str, Any]:
        """JSON Schema for the analyzer's params block in the profile."""

    # Convenience: build a Finding with this analyzer's metadata pre-filled.
    def _finding(
        self,
        *,
        check_id: str,
        metric: str,
        value: float | None,
        unit: str,
        status,
        time_range_ms: tuple[float, float] | None = None,
        confidence: float | None = None,
        message: str = "",
        evidence: dict[str, Any] | None = None,
        extra_limitations: list[str] | None = None,
    ) -> Finding:
        from ..models import Status
        if isinstance(status, str):
            status = Status(status)
        limitations = list(self.DEFAULT_LIMITATIONS)
        if extra_limitations:
            limitations.extend(extra_limitations)
        return Finding(
            check_id=check_id,
            analyzer=self.ID,
            metric=metric,
            value=value,
            unit=unit,
            status=status,
            time_range_ms=time_range_ms,
            confidence=confidence,
            method=self.METHOD or f"{self.NAME} v{self.VERSION}",
            limitations=limitations,
            message=message,
            evidence=evidence or {},
        )
