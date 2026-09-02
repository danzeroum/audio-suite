"""Phase 5 descriptor analyzers — all return observation/needs_review.

Per the roadmap (Fase 5): Nenhum analyzer descritivo gera `fail` por padrão.
All return `observation` (Status.PASS by design) or `needs_review`.

Descriptors:
  - TIMBRE_DISTANCE: spectral distance between segments
  - HARMONIC_TENSION: harmonic complexity measure
  - RHYTHMIC_GRID_ALIGNMENT: beat grid regularity
  - MELODIC_CONTOUR: pitch contour shape descriptor
  - FATIGUE_INDEX: spectral fatigue indicator (high-frequency energy loss over time)
  - SPECTRAL_IRREGULARITY: peak-to-valley ratio in spectrum
  - INHARMONICITY: deviation from harmonic series
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..models import PCM, Profile, Status
from . import register
from .base import AudioAnalyzer


def _stft_mag(x: np.ndarray, sr: int, n_fft: int = 2048, hop: int = 512) -> tuple[np.ndarray, np.ndarray]:
    from scipy.signal import get_window

    if len(x) < n_fft:
        x = np.pad(x, (0, n_fft - len(x)))
    win = get_window("hann", n_fft)
    frames = []
    for i in range(0, len(x) - n_fft + 1, hop):
        frames.append(x[i : i + n_fft] * win)
    if not frames:
        return np.array([]), np.array([])
    S = np.abs(np.fft.rfft(np.stack(frames), axis=1))
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
    return S, freqs


def _pitch_track_autocorr(
    x: np.ndarray, sr: int, frame_ms: float = 50, hop_ms: float = 25, fmin: float = 50.0, fmax: float = 2000.0
) -> np.ndarray:
    """Track pitch via autocorrelation (local copy to avoid cross-branch dep)."""
    frame = int(sr * frame_ms / 1000)
    hop = int(sr * hop_ms / 1000)
    lag_min = int(sr / fmax)
    lag_max = int(sr / fmin)
    if lag_max >= frame:
        lag_max = frame - 1
    if lag_min < 1:
        lag_min = 1
    n_frames = max(0, (len(x) - frame) // hop + 1)
    f0 = np.full(n_frames, np.nan)
    for i in range(n_frames):
        seg = x[i * hop : i * hop + frame]
        seg = seg - np.mean(seg)
        if np.max(np.abs(seg)) < 1e-6:
            continue
        corr = np.correlate(seg, seg, mode="full")[frame - 1 :]
        corr = corr / (corr[0] + 1e-12)
        if lag_max < lag_min or lag_max >= len(corr):
            continue
        search = corr[lag_min : lag_max + 1]
        if len(search) == 0:
            continue
        peak = int(np.argmax(search))
        if 0 < peak < len(search) - 1:
            a, b, c = search[peak - 1], search[peak], search[peak + 1]
            denom = a - 2 * b + c
            if abs(denom) > 1e-12:
                peak = peak + 0.5 * (a - c) / denom
        lag = lag_min + peak
        if lag > 0:
            f0[i] = sr / lag
    return f0


# === TIMBRE_DISTANCE ===


@register
class TimbreDistanceAnalyzer(AudioAnalyzer):
    ID = "timbre_distance"
    NAME = "Timbre Distance (spectral segment distance)"
    VERSION = "1.0.0"
    METHOD = "MFCC-like cepstral distance between first and last third"
    DEFAULT_LIMITATIONS = [
        "Descriptor — never fails builds (rule 1)",
        "Distance is relative to the signal itself, not a reference",
        "MFCC-like features are simplified (no mel filterbank)",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        return audio.n_frames >= 8192

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        x = audio.mono_mix().astype(np.float64)
        n = len(x)
        first = x[: n // 3]
        last = x[2 * n // 3 :]
        S1, _ = _stft_mag(first, audio.sample_rate)
        S2, _ = _stft_mag(last, audio.sample_rate)
        if S1.size == 0 or S2.size == 0:
            return [
                self._finding(
                    check_id="timbre_distance.descriptor",
                    metric="timbre_distance",
                    value=None,
                    unit="0-1",
                    status=Status.NOT_APPLICABLE,
                    message="signal too short for timbre distance",
                )
            ]
        # Mean spectrum per segment, normalized
        m1 = S1.mean(axis=0)
        m2 = S2.mean(axis=0)
        m1 = m1 / (np.linalg.norm(m1) + 1e-12)
        m2 = m2 / (np.linalg.norm(m2) + 1e-12)
        # Cosine distance = 1 - cosine similarity
        distance = 1.0 - float(np.dot(m1, m2))
        distance = max(0.0, min(1.0, distance))

        return [
            self._finding(
                check_id="timbre_distance.descriptor",
                metric="timbre_distance",
                value=round(distance, 4),
                unit="0-1",
                status=Status.PASS,  # descriptor — never fails
                confidence=0.8,
                message=f"timbre distance {distance:.3f} (observation)",
                evidence={"segment": "first_third vs last_third"},
                extra_limitations=["status=pass by design; descriptors do not fail builds"],
            )
        ]

    def profile_schema(self) -> dict[str, Any]:
        return {"type": "object", "additionalProperties": False}


# === HARMONIC_TENSION ===


@register
class HarmonicTensionAnalyzer(AudioAnalyzer):
    ID = "harmonic_tension"
    NAME = "Harmonic Tension (non-harmonic energy ratio)"
    VERSION = "1.0.0"
    METHOD = "ratio of energy at non-harmonic frequencies to harmonic"
    DEFAULT_LIMITATIONS = [
        "Descriptor — never fails builds",
        "F0 estimation via autocorrelation; may fail on polyphonic content",
        "Tension is a perceptual proxy, not a music-theoretic measure",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        return audio.n_frames >= 4096

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        x = audio.mono_mix().astype(np.float64)

        f0 = _pitch_track_autocorr(x, audio.sample_rate)
        valid = f0[np.isfinite(f0)]
        if len(valid) < 4:
            return [
                self._finding(
                    check_id="harmonic_tension.descriptor",
                    metric="harmonic_tension",
                    value=None,
                    unit="0-1",
                    status=Status.NOT_APPLICABLE,
                    message="not enough voiced frames",
                )
            ]
        mean_f0 = float(np.median(valid))
        S, freqs = _stft_mag(x, audio.sample_rate)
        if S.size == 0:
            return [
                self._finding(
                    check_id="harmonic_tension.descriptor",
                    metric="harmonic_tension",
                    value=None,
                    unit="0-1",
                    status=Status.NOT_APPLICABLE,
                    message="spectrogram empty",
                )
            ]
        # Harmonic bins: multiples of mean_f0
        harmonic_mask = np.zeros(len(freqs), dtype=bool)
        for h in range(1, 10):
            f_target = h * mean_f0
            if f_target > freqs[-1]:
                break
            idx = int(np.argmin(np.abs(freqs - f_target)))
            # Width of ±1 bin
            for di in range(-1, 2):
                if 0 <= idx + di < len(freqs):
                    harmonic_mask[idx + di] = True
        mean_spec = S.mean(axis=0)
        e_harmonic = float(np.sum(mean_spec[harmonic_mask] ** 2))
        e_total = float(np.sum(mean_spec**2)) + 1e-12
        tension = 1.0 - (e_harmonic / e_total)
        tension = float(np.clip(tension, 0.0, 1.0))

        return [
            self._finding(
                check_id="harmonic_tension.descriptor",
                metric="harmonic_tension",
                value=round(tension, 4),
                unit="0-1",
                status=Status.PASS,
                confidence=0.6,
                message=f"harmonic tension {tension:.3f} (observation)",
                evidence={"mean_f0_hz": round(mean_f0, 2), "n_harmonics": 9},
            )
        ]

    def profile_schema(self) -> dict[str, Any]:
        return {"type": "object", "additionalProperties": False}


# === SPECTRAL_IRREGULARITY ===


@register
class SpectralIrregularityAnalyzer(AudioAnalyzer):
    ID = "spectral_irregularity"
    NAME = "Spectral Irregularity (peak-to-valley)"
    VERSION = "1.0.0"
    METHOD = "ratio of valley to peak energy in spectrum"
    DEFAULT_LIMITATIONS = ["Descriptor — never fails builds"]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        return audio.n_frames >= 2048

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        x = audio.mono_mix().astype(np.float64)
        S, _ = _stft_mag(x, audio.sample_rate)
        if S.size == 0:
            return [
                self._finding(
                    check_id="spectral_irregularity.descriptor",
                    metric="spectral_irregularity",
                    value=None,
                    unit="0-1",
                    status=Status.NOT_APPLICABLE,
                    message="spectrogram empty",
                )
            ]
        mean_spec = S.mean(axis=0)
        # Peaks vs valleys: difference between consecutive bins
        diff = np.abs(np.diff(mean_spec))
        irregularity = float(np.mean(diff) / (np.mean(mean_spec) + 1e-12))
        irregularity = float(np.clip(irregularity, 0.0, 1.0))

        return [
            self._finding(
                check_id="spectral_irregularity.descriptor",
                metric="spectral_irregularity",
                value=round(irregularity, 4),
                unit="0-1",
                status=Status.PASS,
                confidence=0.85,
                message=f"spectral irregularity {irregularity:.3f} (observation)",
            )
        ]

    def profile_schema(self) -> dict[str, Any]:
        return {"type": "object", "additionalProperties": False}


# === INHARMMONICITY ===


@register
class InharmonicityAnalyzer(AudioAnalyzer):
    ID = "inharmonicity"
    NAME = "Inharmonicity (harmonic series deviation)"
    VERSION = "1.0.0"
    METHOD = "deviation of partials from integer-multiple F0"
    DEFAULT_LIMITATIONS = [
        "Descriptor — never fails builds",
        "Requires stable F0; polyphonic content not supported",
        "Inspired by piano-string inharmonicity; not calibrated for general audio",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        return audio.n_frames >= 4096

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        x = audio.mono_mix().astype(np.float64)

        f0 = _pitch_track_autocorr(x, audio.sample_rate)
        valid = f0[np.isfinite(f0)]
        if len(valid) < 4:
            return [
                self._finding(
                    check_id="inharmonicity.descriptor",
                    metric="inharmonicity",
                    value=None,
                    unit="0-1",
                    status=Status.NOT_APPLICABLE,
                    message="not enough voiced frames",
                )
            ]
        mean_f0 = float(np.median(valid))
        # Get spectrum
        n_fft = 8192
        if len(x) < n_fft:
            n_fft = len(x)
        win = np.hanning(n_fft)
        X = np.abs(np.fft.rfft(x[:n_fft] * win)) ** 2
        freqs = np.fft.rfftfreq(n_fft, 1.0 / audio.sample_rate)
        # Find partial peaks at expected harmonic positions
        deviations = []
        for h in range(2, 8):
            f_expected = h * mean_f0
            if f_expected > freqs[-1]:
                break
            # Search in a window around expected
            window = 5.0  # Hz
            mask = (freqs >= f_expected - window) & (freqs <= f_expected + window)
            if not mask.any():
                continue
            peak_idx = int(np.argmax(X[mask]))
            f_actual = freqs[mask][peak_idx]
            if f_expected > 0:
                dev = abs(f_actual - f_expected) / f_expected
                deviations.append(dev)
        if not deviations:
            return [
                self._finding(
                    check_id="inharmonicity.descriptor",
                    metric="inharmonicity",
                    value=None,
                    unit="0-1",
                    status=Status.NOT_APPLICABLE,
                    message="no harmonics found",
                )
            ]
        inharmonicity = float(np.mean(deviations))
        inharmonicity = float(np.clip(inharmonicity, 0.0, 1.0))

        return [
            self._finding(
                check_id="inharmonicity.descriptor",
                metric="inharmonicity",
                value=round(inharmonicity, 6),
                unit="0-1",
                status=Status.PASS,
                confidence=0.65,
                message=f"inharmonicity {inharmonicity:.4f} (observation)",
                evidence={
                    "mean_f0_hz": round(mean_f0, 2),
                    "n_harmonics_checked": len(deviations),
                },
            )
        ]

    def profile_schema(self) -> dict[str, Any]:
        return {"type": "object", "additionalProperties": False}


# === FATIGUE_INDEX ===


@register
class FatigueIndexAnalyzer(AudioAnalyzer):
    ID = "fatigue_index"
    NAME = "Fatigue Index (high-freq energy loss over time)"
    VERSION = "1.0.0"
    METHOD = "ratio of high-freq energy in last third vs first third"
    DEFAULT_LIMITATIONS = [
        "Descriptor — never fails builds",
        "Fatigue is a proxy; may indicate mastering compression, not listener fatigue",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        return audio.n_frames >= 8192

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        x = audio.mono_mix().astype(np.float64)
        n = len(x)
        first = x[: n // 3]
        last = x[2 * n // 3 :]

        # High-freq energy (> 4 kHz)
        def hf_energy(seg):
            if len(seg) < 256:
                return 0.0
            n_fft = min(2048, len(seg))
            win = np.hanning(n_fft)
            X = np.abs(np.fft.rfft(seg[:n_fft] * win)) ** 2
            freqs = np.fft.rfftfreq(n_fft, 1.0 / audio.sample_rate)
            hf = freqs >= 4000
            if not hf.any():
                return 0.0
            return float(np.sum(X[hf]))

        e_first = hf_energy(first)
        e_last = hf_energy(last)
        if e_first <= 0:
            return [
                self._finding(
                    check_id="fatigue_index.descriptor",
                    metric="fatigue_index",
                    value=None,
                    unit="0-1",
                    status=Status.NOT_APPLICABLE,
                    message="no high-frequency energy in first third",
                )
            ]
        # Fatigue = how much HF energy decreased (1 = total loss, 0 = no change, negative = increase)
        fatigue = float(np.clip(1.0 - (e_last / e_first), -1.0, 1.0))

        return [
            self._finding(
                check_id="fatigue_index.descriptor",
                metric="fatigue_index",
                value=round(fatigue, 4),
                unit="0-1",
                status=Status.PASS,
                confidence=0.6,
                message=f"fatigue index {fatigue:.3f} (observation)",
                evidence={
                    "hf_energy_first": round(e_first, 4),
                    "hf_energy_last": round(e_last, 4),
                    "cutoff_hz": 4000,
                },
            )
        ]

    def profile_schema(self) -> dict[str, Any]:
        return {"type": "object", "additionalProperties": False}


# === RHYTHMIC_GRID_ALIGNMENT ===


@register
class RhythmicGridAnalyzer(AudioAnalyzer):
    ID = "rhythmic_grid_alignment"
    NAME = "Rhythmic Grid Alignment (onset regularity)"
    VERSION = "1.0.0"
    METHOD = "CV of inter-onset intervals"
    DEFAULT_LIMITATIONS = [
        "Descriptor — never fails builds",
        "Onset detection via envelope derivative; simple heuristic",
        "Does not estimate BPM or time signature",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        return audio.n_frames >= audio.sample_rate * 2

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        x = audio.mono_mix().astype(np.float64)
        # Envelope
        from scipy.signal import hilbert

        env = np.abs(hilbert(x))
        # Onset detection
        diff = np.diff(env)
        threshold = float(np.percentile(diff[diff > 0], 99)) if np.any(diff > 0) else 0
        if threshold <= 0:
            return [
                self._finding(
                    check_id="rhythmic_grid.descriptor",
                    metric="rhythmic_grid_alignment",
                    value=None,
                    unit="0-1",
                    status=Status.NOT_APPLICABLE,
                    message="no onsets detected",
                )
            ]
        above = diff > threshold
        # Find onset positions
        rising = np.diff(above.astype(np.int8))
        onset_positions = np.where(rising == 1)[0]
        if len(onset_positions) < 4:
            return [
                self._finding(
                    check_id="rhythmic_grid.descriptor",
                    metric="rhythmic_grid_alignment",
                    value=None,
                    unit="0-1",
                    status=Status.NOT_APPLICABLE,
                    message="not enough onsets for grid analysis",
                )
            ]
        # Inter-onset intervals
        ioi = np.diff(onset_positions)
        mean_ioi = float(np.mean(ioi))
        cv = float(np.std(ioi) / (mean_ioi + 1e-12))  # coefficient of variation
        # Alignment = 1 - normalized CV (lower CV = more regular = higher alignment)
        alignment = float(np.clip(1.0 - cv, 0.0, 1.0))

        return [
            self._finding(
                check_id="rhythmic_grid.descriptor",
                metric="rhythmic_grid_alignment",
                value=round(alignment, 4),
                unit="0-1",
                status=Status.PASS,
                confidence=0.55,
                message=f"rhythmic grid alignment {alignment:.3f} (observation)",
                evidence={
                    "n_onsets": len(onset_positions),
                    "mean_ioi_samples": round(mean_ioi, 2),
                    "cv": round(cv, 4),
                },
            )
        ]

    def profile_schema(self) -> dict[str, Any]:
        return {"type": "object", "additionalProperties": False}


# === MELODIC_CONTOUR ===


@register
class MelodicContourAnalyzer(AudioAnalyzer):
    ID = "melodic_contour"
    NAME = "Melodic Contour (pitch trajectory shape)"
    VERSION = "1.0.0"
    METHOD = "F0 contour direction + range"
    DEFAULT_LIMITATIONS = [
        "Descriptor — never fails builds",
        "Requires monophonic pitched content",
        "Contour is simplified to direction (rising/falling/static)",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        return audio.n_frames >= audio.sample_rate

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        x = audio.mono_mix().astype(np.float64)

        f0 = _pitch_track_autocorr(x, audio.sample_rate)
        valid = f0[np.isfinite(f0)]
        if len(valid) < 8:
            return [
                self._finding(
                    check_id="melodic_contour.descriptor",
                    metric="melodic_contour_direction",
                    value=None,
                    unit="enum",
                    status=Status.NOT_APPLICABLE,
                    message="not enough voiced frames",
                )
            ]
        # Direction: linear regression slope
        t = np.arange(len(valid))
        slope = float(np.polyfit(t, valid, 1)[0])
        if slope > 5:
            direction = "rising"
        elif slope < -5:
            direction = "falling"
        else:
            direction = "static"
        # Range in semitones
        f_min = float(np.min(valid))
        f_max = float(np.max(valid))
        if f_min > 0:
            range_st = 12 * np.log2(f_max / f_min)
        else:
            range_st = 0.0

        return [
            self._finding(
                check_id="melodic_contour.descriptor",
                metric="melodic_contour_direction",
                value=None,
                unit="enum",
                status=Status.PASS,
                confidence=0.6,
                message=f"melodic contour: {direction}, range {range_st:.1f} semitones",
                evidence={
                    "direction": direction,
                    "slope_hz_per_frame": round(slope, 4),
                    "range_semitones": round(float(range_st), 2),
                    "f0_min_hz": round(f_min, 2),
                    "f0_max_hz": round(f_max, 2),
                },
            )
        ]

    def profile_schema(self) -> dict[str, Any]:
        return {"type": "object", "additionalProperties": False}
