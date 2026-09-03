"""Stable rule IDs for all analyzers (CONTR-02).

Rule IDs are stable identifiers that external integrations can depend on.
They follow the pattern AS-<CATEGORY>-<NUMBER> where:
  LOUD = loudness
  PEAK = true peak / clipping
  DEF  = defects (glitch, dropout)
  CHAN = channel / phase
  SPEC = spectral descriptors
  REF  = reference quality
  VOX  = voice / speech
  FORE = forensic (ENF, deepfake)
  SPAT = spatial / multichannel
  META = metadata / container
  DESC = descriptors (never fail)

Changing a rule ID is a breaking change that requires a major version bump.
"""

from __future__ import annotations

# Mapping: (analyzer_id, metric) -> rule_id
RULE_IDS: dict[tuple[str, str], str] = {
    # Loudness
    ("loudness", "integrated_loudness"): "AS-LOUD-001",
    # True peak
    ("true_peak", "true_peak"): "AS-PEAK-001",
    # Clipping
    ("clipping", "clipped_sample_pct"): "AS-PEAK-002",
    # Defects
    ("glitch", "glitch_event_count"): "AS-DEF-001",
    ("loop", "loop_amplitude_jump"): "AS-DEF-002",
    # Channel / phase
    ("mono_compat", "max_band_loss"): "AS-CHAN-001",
    ("channel_balance", "delta_lufs"): "AS-CHAN-002",
    ("spatial_coherence", "max_off_diag_correlation"): "AS-CHAN-003",
    ("binaural_compat", "lateral_low_energy_db"): "AS-CHAN-004",
    ("goniometer", "mean_correlation"): "AS-CHAN-005",
    ("multichannel_layout", "lfe_low_freq_energy_pct"): "AS-CHAN-006",
    # Spectral
    ("spectral_health", "spectral_centroid"): "AS-SPEC-001",
    ("spectral_irregularity", "spectral_irregularity"): "AS-SPEC-002",
    ("resampling", "aliasing_level_db"): "AS-SPEC-003",
    # Reference quality
    ("ref_quality", "stoi_proxy"): "AS-REF-001",
    ("ref_quality", "visqol_proxy"): "AS-REF-002",
    ("ref_quality", "si_sdr_db"): "AS-REF-003",
    ("stem_sep", "si_sdr_db"): "AS-REF-004",
    ("stem_sep", "leakage_pct"): "AS-REF-005",
    # Voice / speech
    ("voice_artifacts", "artifact_frame_count"): "AS-VOX-001",
    ("speech_intelligibility", "stoi_proxy_no_ref"): "AS-VOX-002",
    ("speech_rate", "syllables_per_second"): "AS-VOX-003",
    ("pitch_stab", "pitch_drift_cents"): "AS-VOX-004",
    ("transient", "attack_time_ms"): "AS-VOX-005",
    ("acoustic_context", "scene_change_count"): "AS-VOX-006",
    ("acoustic_context", "reverberation_time"): "AS-VOX-007",
    ("acoustic_context", "noise_floor_db"): "AS-VOX-008",
    # Forensic (always needs_review)
    ("enf_phase", "phase_discontinuity_count"): "AS-FORE-001",
    ("deepfake", "synthetic_likeness_score"): "AS-FORE-002",
    # Metadata
    ("codec_conf", "compliance_status"): "AS-META-001",
    ("inspect", "metadata"): "AS-META-002",
    ("acoustic_fingerprint", "fingerprint_sha256"): "AS-META-003",
    ("metadata_schema_validator", "schema_completeness"): "AS-META-004",
    # Descriptors (never fail)
    ("timbre_distance", "timbre_distance"): "AS-DESC-001",
    ("harmonic_tension", "harmonic_tension"): "AS-DESC-002",
    ("fatigue_index", "fatigue_index"): "AS-DESC-003",
    ("rhythmic_grid_alignment", "rhythmic_grid_alignment"): "AS-DESC-004",
    ("melodic_contour", "melodic_contour_direction"): "AS-DESC-005",
    ("inharmonicity", "inharmonicity"): "AS-DESC-006",
    ("lra", "loudness_range"): "AS-DESC-007",
}


def get_rule_id(analyzer: str, metric: str) -> str | None:
    """Get the stable rule ID for an analyzer+metric pair."""
    return RULE_IDS.get((analyzer, metric))


def rule_id_class(rule_id: str) -> str:
    """Classificação estrutural do rule_id (PROF-08.r).

    - "descriptive": AS-DESC-* — nunca causa fail (R1)
    - "forensic": AS-FORE-* — nunca conclui autenticidade (R8); needs_review
    - "objective": demais — pode escalar via profile
    """
    if rule_id.startswith("AS-DESC-"):
        return "descriptive"
    if rule_id.startswith("AS-FORE-"):
        return "forensic"
    return "objective"


# Severity mapping (CONTR-03)
SEVERITY_MAP: dict[str, str] = {
    "pass": "info",
    "warning": "warning",
    "fail": "error",
    "error": "critical",
    "needs_review": "warning",
    "indeterminate": "info",
    "not_applicable": "info",
}


def get_severity(status: str) -> str:
    """Map a Finding status to a severity level."""
    return SEVERITY_MAP.get(status, "info")
