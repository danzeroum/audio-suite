"""audio-suite: acoustic analysis CLI.

The package is organized in layers:
  - models: immutable data classes (Finding, PCM, Bundle, Profile)
  - decode: audio container decoding into canonical PCM
  - engine: analyzer discovery and execution
  - policy: profile validation and severity escalation
  - analyzers: the acoustic analyzers themselves
  - output: JSON / SARIF / HTML formatters
  - security: Ed25519 signing, PII redaction, audit log
  - cli: the command-line entry point
"""
from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["__version__"]
