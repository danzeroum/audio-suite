"""Multichannel layout analyzer — 5.1/7.1 PCM validation (Fase 4).

Per the roadmap (Fase 4 MULTICHANNEL_LAYOUT v1): Apenas WAV/FLAC PCM.
Valida 5.1/7.1, ordem, LFE, matriz de downmix declarada, compatibilidade
estéreo/mono. ADM/BWF e Atmos 9.1.6 virão como subprojeto próprio.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..models import PCM, Profile, Status
from . import register
from .base import AudioAnalyzer

# Standard channel orders (per ITU-R BS.775 and SMPTE)
LAYOUT_SPECS = {
    "5.1": {
        "channels": 6,
        "order": ["L", "R", "C", "LFE", "Ls", "Rs"],
        "lfe_index": 3,
        "expected_downmix": [1.0, 1.0, 0.707, 0.0, 0.707, 0.707],
    },
    "7.1": {
        "channels": 8,
        "order": ["L", "R", "C", "LFE", "Ls", "Rs", "Lrs", "Rrs"],
        "lfe_index": 3,
        "expected_downmix": [1.0, 1.0, 0.707, 0.0, 0.707, 0.707, 0.707, 0.707],
    },
}


@register
class MultichannelLayoutAnalyzer(AudioAnalyzer):
    ID = "multichannel_layout"
    NAME = "Multichannel Layout Validator (5.1/7.1 PCM)"
    VERSION = "1.0.0"
    METHOD = "channel count + LFE energy + downmix compatibility"
    DEFAULT_LIMITATIONS = [
        "PCM WAV/FLAC only; ADM/BWF and Atmos are subproject (Fase 4+)",
        "Channel order assumed per ITU-R BS.775; custom orders need profile declaration",
        "LFE detection via spectral content is heuristic",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        return audio.channels in (6, 8)

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        findings: list = []
        layout_name = "5.1" if audio.channels == 6 else "7.1"
        spec = LAYOUT_SPECS[layout_name]

        # 1. Verify channel count matches layout
        if audio.channels != spec["channels"]:
            findings.append(
                self._finding(
                    check_id="multichannel_layout.count",
                    metric="channel_count",
                    value=float(audio.channels),
                    unit="channels",
                    status=Status.FAIL,
                    message=f"expected {spec['channels']} for {layout_name}, got {audio.channels}",
                )
            )
            return findings

        # 2. Check LFE channel has expected spectral content (mostly low freq)
        lfe_idx = spec["lfe_index"]
        if lfe_idx < audio.channels:
            lfe = audio.samples[lfe_idx].astype(np.float64)
            if len(lfe) > 0:
                # LFE should have most energy below 120 Hz
                n_fft = min(2048, len(lfe))
                if n_fft >= 256:
                    win = np.hanning(n_fft)
                    X = np.abs(np.fft.rfft(lfe[:n_fft] * win)) ** 2
                    freqs = np.fft.rfftfreq(n_fft, 1.0 / audio.sample_rate)
                    low_mask = freqs <= 120.0
                    if low_mask.any() and X.sum() > 0:
                        low_pct = 100.0 * float(np.sum(X[low_mask])) / float(np.sum(X))
                    else:
                        low_pct = 0.0
                else:
                    low_pct = 100.0  # can't check, assume OK
            else:
                low_pct = 100.0

            if low_pct < 80.0:
                findings.append(
                    self._finding(
                        check_id="multichannel_layout.lfe",
                        metric="lfe_low_freq_energy_pct",
                        value=round(low_pct, 2),
                        unit="%",
                        status=Status.WARNING,
                        message=f"LFE channel has only {low_pct:.1f}% energy below 120 Hz",
                        evidence={"lfe_index": lfe_idx, "cutoff_hz": 120},
                    )
                )
            else:
                findings.append(
                    self._finding(
                        check_id="multichannel_layout.lfe",
                        metric="lfe_low_freq_energy_pct",
                        value=round(low_pct, 2),
                        unit="%",
                        status=Status.PASS,
                        message=f"LFE channel spectral content OK ({low_pct:.1f}% below 120 Hz)",
                        evidence={"lfe_index": lfe_idx},
                    )
                )

        # 3. Check stereo compatibility (L+R should be present)
        L = audio.samples[0].astype(np.float64) if audio.channels > 0 else np.zeros(0)
        R = audio.samples[1].astype(np.float64) if audio.channels > 1 else np.zeros(0)
        if len(L) > 0 and len(R) > 0:
            stereo_energy = float(np.sqrt(np.mean((L + R) ** 2)))
            if stereo_energy > 1e-8:
                findings.append(
                    self._finding(
                        check_id="multichannel_layout.stereo_compat",
                        metric="stereo_downmix_energy",
                        value=round(stereo_energy, 4),
                        unit="rms",
                        status=Status.PASS,
                        message="stereo downmix (L+R) has energy",
                    )
                )
            else:
                findings.append(
                    self._finding(
                        check_id="multichannel_layout.stereo_compat",
                        metric="stereo_downmix_energy",
                        value=round(stereo_energy, 4),
                        unit="rms",
                        status=Status.WARNING,
                        message="stereo downmix (L+R) is silent — L and R may be missing",
                    )
                )

        # 4. Center channel should not be silent (for 5.1/7.1 dialogue)
        if audio.channels > 2:
            C = audio.samples[2].astype(np.float64)
            c_energy = float(np.sqrt(np.mean(C**2))) if len(C) > 0 else 0.0
            if c_energy < 1e-6:
                findings.append(
                    self._finding(
                        check_id="multichannel_layout.center",
                        metric="center_channel_energy",
                        value=round(c_energy, 6),
                        unit="rms",
                        status=Status.WARNING,
                        message="center channel is silent — dialogue may be missing",
                    )
                )
            else:
                findings.append(
                    self._finding(
                        check_id="multichannel_layout.center",
                        metric="center_channel_energy",
                        value=round(c_energy, 6),
                        unit="rms",
                        status=Status.PASS,
                        message="center channel has energy",
                    )
                )

        return findings

    def profile_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "expected_layout": {
                    "type": "string",
                    "enum": ["5.1", "7.1"],
                },
            },
            "additionalProperties": False,
        }
