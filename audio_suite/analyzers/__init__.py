"""Analyzer registry.

Importing this module triggers registration of all built-in analyzers.
External analyzers can be registered via the CARTRIDGE_API (Fase 5).
"""

from __future__ import annotations

from .base import AudioAnalyzer

_REGISTRY: dict[str, AudioAnalyzer] = {}


def register(cls: type[AudioAnalyzer]) -> type[AudioAnalyzer]:
    """Class decorator: instantiate and register an analyzer."""
    instance = cls()
    if not instance.ID:
        raise ValueError(f"{cls.__name__} has no ID")
    if instance.ID in _REGISTRY:
        raise ValueError(f"duplicate analyzer ID: {instance.ID}")
    _REGISTRY[instance.ID] = instance
    return cls


def get_analyzer(analyzer_id: str) -> AudioAnalyzer | None:
    return _REGISTRY.get(analyzer_id)


def all_analyzers() -> dict[str, AudioAnalyzer]:
    return dict(_REGISTRY)


def analyzer_ids() -> list[str]:
    return sorted(_REGISTRY.keys())


# Import side-effect: register built-in analyzers
from . import (
    acoustic_context,  # noqa: E402,F401
    binaural_compat,  # noqa: E402,F401
    chan_balance,  # noqa: E402,F401
    clipping,  # noqa: E402,F401
    codec_conf,  # noqa: E402,F401
    deepfake,  # noqa: E402,F401
    descriptors,  # noqa: E402,F401
    enf_phase,  # noqa: E402,F401
    glitch,  # noqa: E402,F401
    goniometer,  # noqa: E402,F401
    inspect_meta,  # noqa: E402,F401
    loop,  # noqa: E402,F401
    loudness,  # noqa: E402,F401
    lra,  # noqa: E402,F401
    mam_dam,  # noqa: E402,F401
    mono_compat,  # noqa: E402,F401
    multichannel_layout,  # noqa: E402,F401
    pitch_stab,  # noqa: E402,F401
    ref_quality,  # noqa: E402,F401
    resampling,  # noqa: E402,F401
    spatial_coherence,  # noqa: E402,F401
    spectral,  # noqa: E402,F401
    speech_intelligibility,  # noqa: E402,F401
    speech_rate,  # noqa: E402,F401
    stem_sep,  # noqa: E402,F401
    transient,  # noqa: E402,F401
    truepeak,  # noqa: E402,F401
    voice_artif,  # noqa: E402,F401
)
