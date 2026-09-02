"""Analyzer: Loudness (LUFS) conforme EBU R 128."""
from typing import Any

import numpy as np
import pyloudnorm as pyln


def run_analyzer(
    pcm: np.ndarray,
    media_info: dict[str, Any],
    params: dict[str, Any],
    verbose: bool = False
) -> list[dict]:
    """
    Mede loudness integrado e compara com target do profile.
    Params esperados: target_integrated_lufs (float), tolerance_lufs (float)
    """
    findings = []

    # pyloudnorm espera mono ou stereo, PCM float32 [-1, 1]
    # Se PCM já está em float32 com range arbitrário → normalizar para -1..1
    pcm_norm = pcm.copy()
    max_abs = np.max(np.abs(pcm_norm))
    if max_abs > 0:
        pcm_norm = pcm_norm / max_abs

    # pyloudnorm mede em LUFS integrado (EBU R128)
    try:
        # pyloudnorm's meter mede diretamente:
        meter = pyln.Meter(48000, block_size=400)  # block_size=400ms conforme EBU R128
        # pyloudnorm aceita: mono como (frames,) ou (1, frames); stereo como (channels, frames)
        if pcm_norm.ndim == 1:
            data_for_meter = pcm_norm
        elif pcm_norm.ndim == 2:
            if pcm_norm.shape[1] > 5:
                raise ValueError("pyloudnorm suporta no máximo 5 canais")
            # Transpõe para (channels, frames)
            data_for_meter = pcm_norm.T
        else:
            raise ValueError(f"PCM com dims inesperado: {pcm_norm.ndim}")

        lufs = meter.integrated_loudness(data_for_meter)
        # pyloudnorm retorna -inf para silêncio
        if not np.isfinite(lufs):
            findings.append({
                "name": "Integrated Loudness (LUFS)",
                "value": None,
                "unit": "LUFS",
                "threshold": f"{params.get('target_integrated_lufs', -23.0)} ± {params.get('tolerance_lufs', 0.5)}",
                "status": "indeterminate",
                "severity": "info",
                "description": "Loudness não pôde ser medido (possível silêncio ou sinal muito baixo)."
            })
            return findings

        target = params.get("target_integrated_lufs", -23.0)
        tol = params.get("tolerance_lufs", 0.5)
        status = "pass" if abs(lufs - target) <= tol else "fail"

        findings.append({
            "name": "Integrated Loudness (LUFS)",
            "value": float(f"{lufs:.2f}"),
            "unit": "LUFS",
            "threshold": f"{target} ± {tol}",
            "status": status,
            "severity": "error" if status == "fail" else "info",
            "description": f"Loudness integrado medido vs. target EBU R 128 ({target} LUFS)"
        })

        # Short-term e momentary (opcional, para debug)
        if verbose:
            try:
                mt = meter.momentary_loudness(data_for_meter)
                findings.append({
                    "name": "Momentary Loudness",
                    "value": float(f"{np.mean(mt):.2f}"),
                    "unit": "LUFS",
                    "status": "info",
                    "severity": "info"
                })
            except Exception:
                pass  # informational only

    except Exception as e:
        findings.append({
            "name": "Loudness Measurement",
            "value": str(e),
            "status": "indeterminate",
            "severity": "error",
            "description": "Falha ao medir loudness"
        })

    return findings
