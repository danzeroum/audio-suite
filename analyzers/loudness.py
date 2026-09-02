"""Analyzer: Loudness (LUFS) conforme EBU R 128."""
import numpy as np
from typing import Dict, Any, List
import pyloudnorm as pyln

def run_analyzer(
    pcm: np.ndarray,
    media_info: Dict[str, Any],
    params: Dict[str, Any],
    verbose: bool = False
) -> List[Dict]:
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
        if pcm_norm.ndim == 1:
            lufs = meter.integrated_loudness(pcm_norm)
        else:
            # pyloudnorm espera (channels, frames)
            pcm_t = pcm_norm.T
            lufs = meter.integrated_loudness(pcm_t)

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
            if pcm_norm.ndim == 1:
                st = meter.loudness(momentary=True, block_size=0.4)
                mt = meter.loudness(momentary=True, block_size=3.0)
            else:
                st = meter.loudness(pcm_t, momentary=True, block_size=0.4)
                mt = meter.loudness(pcm_t, momentary=True, block_size=3.0)
            findings.append({
                "name": "Momentary Loudness (3s)",
                "value": float(f"{mt:.2f}"),
                "unit": "LUFS",
                "status": "info",
                "severity": "info"
            })

    except Exception as e:
        findings.append({
            "name": "Loudness Measurement",
            "value": str(e),
            "status": "indeterminate",
            "severity": "error",
            "description": "Falha ao medir loudness"
        })

    return findings
