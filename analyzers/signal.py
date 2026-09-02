"""Analyzer: True peak, sample peak, clipping detection."""
import numpy as np
from typing import Dict, Any, List
import math

def run_analyzer(
    pcm: np.ndarray,
    media_info: Dict[str, Any],
    params: Dict[str, Any],
    verbose: bool = False
) -> List[Dict]:
    """
    Mede true peak (dBTP), sample peak (dBFS) e detecta clipping.
    Params: max_true_peak_dbtp (float), allow_clipping (bool)
    """
    findings = []

    # True peak detection com oversampling ×4
    def true_peak_dbtp(pcm_arr: np.ndarray) -> float:
        """Estima true peak em dBTP via oversampling."""
        # Se stereo → usar canal mais alto
        if pcm_arr.ndim == 2:
            # pyloudnorm style: (ch, frames)
            channels = pcm_arr.T
            peaks = []
            for ch in channels:
                tp = true_peak_channel(ch)
                peaks.append(tp)
            return max(peaks) if peaks else -float('inf')
        else:
            return true_peak_channel(pcm_arr)

    def true_peak_channel(ch_arr: np.ndarray) -> float:
        import scipy.signal
        # Oversampling ×4 via polyphase
        up, down = 4, 1
        # Filtra antes de upsample para evitar aliasing
        # Filtro passa-baixa com cutoff Nyquist/4
        try:
            # scipy.signal.resample_poly faz upsampling + anti-aliasing
            upsampled = scipy.signal.resample_poly(ch_arr, up, down, window=('kaiser', 8))
            max_val = np.max(np.abs(upsampled))
            if max_val == 0:
                return -140.0  # silêncio
            return 20 * math.log10(max_val)
        except Exception:
            # fallback: sample peak
            return 20 * math.log10(np.max(np.abs(ch_arr)) + 1e-12)

    # Sample peak (dBFS, linear 0..1)
    def sample_peak_dbfs(ch_arr: np.ndarray) -> float:
        max_val = np.max(np.abs(ch_arr))
        if max_val == 0:
            return -140.0
        return 20 * math.log10(max_val)

    # True peak
    try:
        # Se PCM já está em float32 com range [-1, 1] → ok
        # Se não → normalizar
        max_abs = np.max(np.abs(pcm))
        if max_abs > 1.0:
            pcm_norm = pcm / max_abs
        else:
            pcm_norm = pcm.copy()

        tp_dbtp = true_peak_dbtp(pcm_norm)
        # True peak em dBTP: referência é 0 dBTP = full scale
        # Então tp_dbtp já está na escala correta

        max_tp = params.get("max_true_peak_dbtp", -1.0)
        status_tp = "pass" if tp_dbtp <= max_tp else "fail"

        findings.append({
            "name": "True Peak",
            "value": float(f"{tp_dbtp:.2f}"),
            "unit": "dBTP",
            "threshold": f"<= {max_tp}",
            "status": status_tp,
            "severity": "error" if status_tp == "fail" else "info",
            "description": "True peak (oversampling ×4) — detecta inter-sample peaks"
        })

        # Sample peak (dBFS)
        if pcm_norm.ndim == 2:
            sp_dbfs = max(sample_peak_dbfs(ch) for ch in pcm_norm.T)
        else:
            sp_dbfs = sample_peak_dbfs(pcm_norm)

        findings.append({
            "name": "Sample Peak",
            "value": float(f"{sp_dbfs:.2f}"),
            "unit": "dBFS",
            "threshold": "<= 0.0",
            "status": "pass" if sp_dbfs <= 0.0 else "fail",
            "severity": "warning" if sp_dbfs > 0.0 else "info"
        })

        # Clipping detection
        allow_clipping = params.get("allow_clipping", False)
        # Clipping = amostra exatamente em ±1.0 (ou próximo de full scale)
        tol = 1e-6
        if pcm_norm.ndim == 2:
            clipped = np.any(np.abs(pcm_norm) >= (1.0 - tol))
        else:
            clipped = np.any(np.abs(pcm_norm) >= (1.0 - tol))

        if clipped and not allow_clipping:
            findings.append({
                "name": "Clipping",
                "value": "Detected",
                "unit": None,
                "threshold": "None allowed",
                "status": "fail",
                "severity": "error",
                "description": "Amostras atingiram full scale (clipping)"
            })
        elif clipped and allow_clipping:
            findings.append({
                "name": "Clipping",
                "value": "Allowed by policy",
                "status": "warning",
                "severity": "warning"
            })

        # DC offset (opcional, info)
        if pcm_norm.ndim == 2:
            for i, ch in enumerate(pcm_norm.T):
                dc = np.mean(ch)
                if abs(dc) > 1e-3:
                    findings.append({
                        "name": f"DC Offset (canal {i+1})",
                        "value": float(f"{dc:.6f}"),
                        "unit": "linear",
                        "status": "warning" if abs(dc) > 0.01 else "info",
                        "severity": "warning" if abs(dc) > 0.01 else "info"
                    })
        else:
            dc = np.mean(pcm_norm)
            if abs(dc) > 1e-3:
                findings.append({
                    "name": "DC Offset",
                    "value": float(f"{dc:.6f}"),
                    "unit": "linear",
                    "status": "warning" if abs(dc) > 0.01 else "info",
                    "severity": "warning" if abs(dc) > 0.01 else "info"
                })

    except Exception as e:
        findings.append({
            "name": "Signal Analyzer",
            "value": str(e),
            "status": "indeterminate",
            "severity": "error",
            "description": "Falha na medição de true peak / clipping"
        })

    return findings
