"""Cartridge API — C ABI-stable interface for external analyzers (Fase 5).

Per the roadmap (Fase 5 CARTRIDGE_API): Interface C ABI-stable para
analyzers externos (.so/.dll).

This is a Python implementation that loads external analyzer modules
via importlib. A true C ABI would use ctypes/cffi to load .so files;
this implementation provides the registration interface and a Python
plugin loader that can be extended to C in the future.

Usage:
    from audio_suite.cartridge import load_cartridge
    load_cartridge("/path/to/my_analyzer_plugin.py")
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from .analyzers import _REGISTRY, AudioAnalyzer
from .models import PCM, Finding, Profile, Status


class CartridgeAnalyzer(AudioAnalyzer):
    """Wrapper for an externally-loaded analyzer module.

    The module must define a `create_analyzer()` function that returns
    an object with `analyze(audio, params)`, `applicable(audio, profile)`,
    and `profile_schema()` methods.
    """

    def __init__(
        self,
        module_path: str,
        analyzer_id: str,
        name: str = "",
        version: str = "0.0.1",
        method: str = "cartridge",
    ):
        self._module_path = module_path
        self._analyzer_id = analyzer_id
        self._name = name or f"Cartridge: {Path(module_path).stem}"
        self._version = version
        self._method = method
        self._impl = None
        self._load()

    def _load(self):
        """Load the external module."""
        path = Path(self._module_path)
        if not path.exists():
            raise FileNotFoundError(f"cartridge not found: {self._module_path}")
        spec = importlib.util.spec_from_file_location(f"cartridge_{path.stem}", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load cartridge: {self._module_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if not hasattr(module, "create_analyzer"):
            raise AttributeError(f"cartridge {self._module_path} missing create_analyzer() function")
        self._impl = module.create_analyzer()

    @property
    def ID(self) -> str:  # type: ignore[override]
        return self._analyzer_id

    @property
    def NAME(self) -> str:  # type: ignore[override]
        return self._name

    @property
    def VERSION(self) -> str:  # type: ignore[override]
        return self._version

    @property
    def METHOD(self) -> str:  # type: ignore[override]
        return self._method

    @property
    def DEFAULT_LIMITATIONS(self) -> list[str]:  # type: ignore[override]
        return [
            "External cartridge analyzer — not audited by audio-suite core",
            "User assumes responsibility for cartridge correctness",
            "Cartridge runs in the same process; no sandboxing",
        ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        if self._impl is None:
            return False
        try:
            return bool(self._impl.applicable(audio, profile))
        except Exception:
            return False

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list[Finding]:
        if self._impl is None:
            return [
                Finding(
                    check_id=f"{self._analyzer_id}.error",
                    analyzer=self._analyzer_id,
                    metric="error",
                    value=None,
                    unit="enum",
                    status=Status.ERROR,
                    message="cartridge not loaded",
                )
            ]
        try:
            raw = self._impl.analyze(audio, params)
            # Convert dict findings to Finding objects if needed
            findings: list[Finding] = []
            for f in raw:
                if isinstance(f, Finding):
                    findings.append(f)
                elif isinstance(f, dict):
                    findings.append(
                        Finding(
                            check_id=f.get("check_id", "unknown"),
                            analyzer=self._analyzer_id,
                            metric=f.get("metric", "unknown"),
                            value=f.get("value"),
                            unit=f.get("unit", ""),
                            status=Status(f.get("status", "pass")),
                            message=f.get("message", ""),
                            evidence=f.get("evidence", {}),
                        )
                    )
                else:
                    findings.append(f)
            return findings
        except Exception as exc:
            return [
                Finding(
                    check_id=f"{self._analyzer_id}.error",
                    analyzer=self._analyzer_id,
                    metric="error",
                    value=None,
                    unit="enum",
                    status=Status.ERROR,
                    message=f"cartridge raised: {exc}",
                )
            ]

    def profile_schema(self) -> dict[str, Any]:
        if self._impl is None:
            return {"type": "object", "additionalProperties": True}
        try:
            schema = self._impl.profile_schema()
            if isinstance(schema, dict):
                return schema
        except Exception:
            pass
        return {"type": "object", "additionalProperties": True}


def load_cartridge(module_path: str, analyzer_id: str, **kwargs) -> CartridgeAnalyzer:
    """Load and register an external cartridge analyzer.

    Args:
        module_path: path to the .py file implementing the analyzer.
        analyzer_id: unique ID for the analyzer in the registry.
        **kwargs: passed to CartridgeAnalyzer (name, version, method).

    Returns:
        The registered CartridgeAnalyzer instance.

    Raises:
        FileNotFoundError: if module_path doesn't exist.
        ImportError: if the module can't be loaded.
        AttributeError: if the module doesn't define create_analyzer().
        ValueError: if analyzer_id is already registered.
    """
    if analyzer_id in _REGISTRY:
        raise ValueError(f"analyzer ID already registered: {analyzer_id}")
    cartridge = CartridgeAnalyzer(module_path, analyzer_id, **kwargs)
    _REGISTRY[analyzer_id] = cartridge
    return cartridge
