"""Bundle: limitations obrigatórias (S4).

Lista fixa de limitations reconhecidas pela engine. A engine preenche
automaticamente as aplicáveis ao final da execução. O profile NÃO pode
suprimir limitations — elas são evidência de escopo.
"""
from __future__ import annotations

# Lista canônica de limitations reconhecidas (S4)
KNOWN_LIMITATIONS = frozenset([
    "fingerprint_not_run",
    "asr_not_run",
    "provenance_events_partial",
    "provenance_events_missing",
    "decoder_fallback_used",
    "profile_validation_skipped",
    "signature_unsigned",
    "analyzer_timeout",
    "nan_samples_sanitized",
    "empty_audio",
    "toctou_detected",
    "findings_truncated",
    "phase_skipped_mono",
    "rights_manifest_missing",
    "schema_unknown_version",
])


def is_known_limitation(name: str) -> bool:
    return name in KNOWN_LIMITATIONS or name.split(":", 1)[0] in KNOWN_LIMITATIONS


def collect_limitations(
    decoder_used: str,
    signature_status: str,
    has_nan_sanitized: bool = False,
    is_empty: bool = False,
    toctou_detected: bool = False,
    had_timeout: list[str] | None = None,
    truncated_analyzers: list[str] | None = None,
    phase_skipped_mono: bool = False,
    rights_manifest_missing: bool = False,
    provenance_partial: bool = False,
    fingerprint_run: bool = False,
    asr_run: bool = False,
) -> list[str]:
    """Coleta limitations aplicáveis com base no estado da execução."""
    out: list[str] = []

    if decoder_used != "ffmpeg":
        out.append("decoder_fallback_used")

    if signature_status == "unsigned":
        out.append("signature_unsigned")

    if has_nan_sanitized:
        out.append("nan_samples_sanitized")

    if is_empty:
        out.append("empty_audio")

    if toctou_detected:
        out.append("toctou_detected")

    if had_timeout:
        for analyzer_id in had_timeout:
            out.append(f"analyzer_timeout:{analyzer_id}")

    if truncated_analyzers:
        for analyzer_id in truncated_analyzers:
            out.append(f"findings_truncated:{analyzer_id}")

    if phase_skipped_mono:
        out.append("phase_skipped_mono")

    if rights_manifest_missing:
        out.append("rights_manifest_missing")

    if provenance_partial:
        out.append("provenance_events_partial")

    if not fingerprint_run:
        out.append("fingerprint_not_run")

    if not asr_run:
        out.append("asr_not_run")

    return out


def validate_limitations_list(limitations: list[str]) -> list[str]:
    """Valida que todas as limitations são conhecidas.

    Levanta ValueError se encontrar limitation desconhecida.
    """
    unknown = [lim for lim in limitations if not is_known_limitation(lim)]
    if unknown:
        raise ValueError(f"Limitations desconhecidas: {unknown}")
    return limitations
