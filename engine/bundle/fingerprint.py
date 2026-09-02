"""Bundle: fingerprint canônico + quantização de floats (A2 + O5).

Reprodutibilidade ≠ bundle idêntico:
- bundle_sha256: hash do bundle completo (inclui timestamps, run_id, assinatura)
- measurement_fingerprint: hash de uma representação canônica contendo apenas
  dados estáveis: file_sha256, pcm_canonical_sha256, profile_sha256, versões
  dos analyzers, parâmetros e findings QUANTIZADOS.

Float determinismo (O5): findings numéricos são arredondados à precisão
declarada antes de entrar no fingerprint.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

# Precisão de quantização por unidade (O5)
QUANTIZATION_EPSILON: dict[str, float] = {
    "LUFS": 0.01,
    "dBTP": 0.05,
    "dBFS": 0.05,
    "linear": 1e-6,
    "correlation": 1e-4,
}

DEFAULT_EPSILON = 1e-6


def quantize_value(value: Any, unit: str | None) -> Any:
    """Quantiza um valor float de acordo com a unidade."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return value
    if unit is None:
        return round(float(value), 8)
    eps = QUANTIZATION_EPSILON.get(unit, DEFAULT_EPSILON)
    # Arredonda para o número de casas decimais que respeita epsilon
    decimals = max(0, -int(__import__("math").floor(__import__("math").log10(eps))))
    return round(float(value), decimals)


def quantize_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Retorna uma cópia dos findings com valores numéricos quantizados."""
    out: list[dict[str, Any]] = []
    for f in findings:
        nf = dict(f)
        if "value" in nf:
            nf["value"] = quantize_value(nf["value"], nf.get("unit"))
        out.append(nf)
    return out


def canonical_json(obj: Any) -> str:
    """Serialização JSON canônica (sorted keys, sem whitespace)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_measurement_fingerprint(
    file_sha256: str,
    pcm_canonical_sha256: str,
    profile_sha256: str,
    profile_name: str,
    suite_version: str,
    findings: list[dict[str, Any]],
    decoder_used: str,
    sample_rate_hz: int,
) -> str:
    """Computa fingerprint determinístico da medição (exclui voláteis)."""
    canonical = {
        "file_sha256": file_sha256,
        "pcm_canonical_sha256": pcm_canonical_sha256,
        "profile_sha256": profile_sha256,
        "profile_name": profile_name,
        "suite_version": suite_version,
        "decoder_used": decoder_used,
        "sample_rate_hz": sample_rate_hz,
        "findings": sorted(
            quantize_findings(findings),
            key=lambda f: canonical_json(f),
        ),
    }
    payload = canonical_json(canonical)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_bundle_sha256(bundle: dict[str, Any]) -> str:
    """Hash do bundle completo serializado canonicamente."""
    return "sha256:" + hashlib.sha256(
        canonical_json(bundle).encode("utf-8")
    ).hexdigest()
