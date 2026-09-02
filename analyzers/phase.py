"""Analyzer: phase (correlação inter-canal) — F1.3 + A4.

Importante (A4):
- Correlação próxima de -1 é SINAL de possível inversão, não PROVA.
- Confiabilidade depende de: duração, energia por canal, conteúdo.
- NÃO hardcode `reliability: high`.
- Threshold e severidade vêm do profile, não do analyzer.
- `channel swap` ≠ polaridade invertida — não tratá-los como sinônimo.
"""
from __future__ import annotations

from typing import Any

import numpy as np


def run_analyzer(
    pcm: np.ndarray,
    media_info: dict[str, Any],
    params: dict[str, Any],
    verbose: bool = False,
) -> list[dict[str, Any]]:
    """Mede correlação inter-canal e detecta possível polaridade invertida.

    Params:
        min_correlation: float (default 0.9) — abaixo disso, alerta.
        min_energy: float (default 1e-5) — abaixo disso, ignora (silêncio).
        min_duration_s: float (default 0.5) — abaixo disso, not_applicable.
        sample_rate: int (default 48000).
    """
    findings: list[dict[str, Any]] = []

    # Pré-condição: precisa de 2+ canais
    if pcm.ndim != 2 or pcm.shape[1] < 2:
        findings.append({
            "name": "Phase correlation",
            "value": "not_applicable",
            "unit": None,
            "threshold": None,
            "status": "not_applicable",
            "severity": "info",
            "description": "Analyzer de fase requer estéreo (2+ canais). Pulado para mono.",
            "reliability": "high",
        })
        return findings

    sample_rate = int(params.get("sample_rate", media_info.get("sample_rate_hz", 48000)))
    min_duration_s = float(params.get("min_duration_s", 0.5))
    min_energy = float(params.get("min_energy", 1e-5))
    min_corr = float(params.get("min_correlation", 0.9))

    # Pré-condição: duração suficiente
    duration_s = pcm.shape[0] / float(sample_rate) if sample_rate > 0 else 0
    if duration_s < min_duration_s:
        findings.append({
            "name": "Phase correlation",
            "value": duration_s,
            "unit": "s",
            "threshold": f">= {min_duration_s}",
            "status": "not_applicable",
            "severity": "info",
            "description": f"Duração {duration_s:.3f}s insuficiente para análise de fase.",
            "reliability": "medium",
        })
        return findings

    # Pré-condição: energia suficiente
    left = pcm[:, 0]
    right = pcm[:, 1]
    energy_left = float(np.mean(left ** 2))
    energy_right = float(np.mean(right ** 2))
    if energy_left < min_energy or energy_right < min_energy:
        findings.append({
            "name": "Phase correlation",
            "value": max(energy_left, energy_right),
            "unit": "linear",
            "threshold": f">= {min_energy}",
            "status": "not_applicable",
            "severity": "info",
            "description": "Energia insuficiente (silêncio); análise de fase não aplicável.",
            "reliability": "high",
        })
        return findings

    # Correlação de Pearson entre canais
    # Normaliza para ter média 0
    left_centered = left - np.mean(left)
    right_centered = right - np.mean(right)
    denom = np.sqrt(np.sum(left_centered ** 2) * np.sum(right_centered ** 2))
    if denom == 0:
        correlation = 0.0
    else:
        correlation = float(np.sum(left_centered * right_centered) / denom)

    # Confiabilidade contextual (A4)
    # Maior duração + energia + correlação extrema → maior confiabilidade
    abs_corr = abs(correlation)
    if duration_s >= 3.0 and abs_corr >= 0.95:
        reliability = "high"
    elif duration_s >= 1.0:
        reliability = "medium"
    else:
        reliability = "low"

    # Status: política decide severidade; analyzer apenas reporta
    # Default: abaixo do threshold → fail (mas profile pode override)
    threshold_str = f">= {min_corr} (positiva) ou <= {-min_corr} (suspeita inversão)"
    if correlation <= -min_corr:
        status = "fail"
        description = (
            f"Correlação inter-canal = {correlation:.4f}. "
            "Sinal forte de possível inversão de polaridade — requer validação manual. "
            "Nota: correlação negativa pode ser intencional em conteúdo decorrelacionado."
        )
    elif abs_corr >= min_corr:
        status = "pass"
        description = (
            f"Correlação inter-canal = {correlation:.4f}. "
            "Canais coerentes; sem indicação de inversão."
        )
    else:
        status = "warning"
        description = (
            f"Correlação inter-canal = {correlation:.4f}. "
            "Decorrelação significativa — pode ser criativo (stereo wide) "
            "ou indicar problema. Verificar contexto."
        )

    findings.append({
        "name": "Phase correlation",
        "value": round(correlation, 6),
        "unit": "correlation",
        "threshold": threshold_str,
        "status": status,
        "severity": "info",  # profile pode elevar
        "description": description,
        "reliability": reliability,
        "method": "Pearson correlation between channels",
        "analysis_window_s": round(duration_s, 3),
        "energy_left": float(f"{energy_left:.6f}"),
        "energy_right": float(f"{energy_right:.6f}"),
    })

    # (Opcional) Verificar cancellation no downmix mono
    if abs_corr > 0.95 and correlation < 0:
        mono = (left + right) / 2.0
        mono_energy = float(np.mean(mono ** 2))
        if mono_energy < min_energy:
            findings.append({
                "name": "Phase cancellation on mono downmix",
                "value": mono_energy,
                "unit": "linear",
                "threshold": f">= {min_energy}",
                "status": "fail",
                "severity": "warning",
                "description": (
                    "Downmix mono produz sinal abaixo do limiar de energia. "
                    "Indica cancelamento de fase — conteúdo inaudível em mono."
                ),
                "reliability": "high",
            })

    return findings
