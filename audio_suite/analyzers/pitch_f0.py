"""Descritor de altura — F0 mediana sobre quadros vozeados (AS-DESC-008).

Complementa o ``pitch_stab``: aquele mede *estabilidade* (drift, wow,
flutter) e não decide vozeamento — todo quadro com amplitude recebe uma
F0, inclusive consoante, respiração e ruído. Em fala, isso faz o drift
medir o salto entre vozeado e não-vozeado, não a voz: nos filmes do
estúdio dos Guardiões ele deu 4.851–5.456 cents para TODOS os falantes.

Este descritor responde a outra pergunta — *em que altura esta voz fala?*
— e por isso precisa separar o que é vozeado:

  - F0 por quadro via YIN (de Cheveigné & Kawahara, 2002): função de
    diferença + diferença média normalizada cumulativa (CMNDF), primeiro
    mínimo abaixo do limiar absoluto, refinado por interpolação
    parabólica. A CMNDF é o que protege contra erro de oitava: o período
    verdadeiro é o primeiro vale profundo, mesmo com o fundamental
    atenuado.
  - Vozeamento explícito: quadro sem vale abaixo do limiar é NÃO vozeado
    (NaN), e não entra na estatística.
  - Gate de energia relativo ao quadro mais forte: quadro muito abaixo
    dele é silêncio, fora do denominador da fração vozeada.

Descritivo (R1): termina só em pass (observation), not_applicable ou
indeterminate — nunca fail. Numpy puro (R2+).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ..models import PCM, Profile, Status
from . import register
from .base import AudioAnalyzer

#: Quadros processados por lote na FFT (memória limitada em faixas longas)
_LOTE = 256

#: Piso absoluto de RMS abaixo do qual o sinal inteiro é silêncio (≈ −100 dBFS)
_RMS_PISO = 1e-5


def _quadros(x: np.ndarray, n: int, hop: int) -> np.ndarray:
    """Janelas de ``n`` amostras a cada ``hop`` (view, sem cópia)."""
    n_quadros = (len(x) - n) // hop + 1
    if n_quadros <= 0:
        return np.empty((0, n))
    return np.lib.stride_tricks.sliding_window_view(x, n)[::hop][:n_quadros]


def _cmndf(quadros: np.ndarray, w: int, tau_max: int) -> np.ndarray:
    """CMNDF de YIN para cada quadro (linhas), lags 0..tau_max.

    d(τ) = Σ_{j<w} (s_j − s_{j+τ})² = E₀ + E_τ − 2·r(τ), com r(τ) pela FFT
    e as energias por soma acumulada — vetorizado sobre os quadros.
    """
    n = quadros.shape[1]
    tamanho = 1 << int(np.ceil(np.log2(n + w)))
    a = np.fft.rfft(quadros[:, :w], tamanho, axis=1)
    b = np.fft.rfft(quadros, tamanho, axis=1)
    r = np.fft.irfft(np.conj(a) * b, tamanho, axis=1)[:, : tau_max + 1]
    acum = np.concatenate([np.zeros((quadros.shape[0], 1)), np.cumsum(quadros**2, axis=1)], axis=1)
    taus = np.arange(tau_max + 1)
    e_tau = acum[:, taus + w] - acum[:, taus]
    d = np.maximum(e_tau[:, :1] + e_tau - 2.0 * r, 0.0)
    d[:, 0] = 0.0
    soma = np.cumsum(d[:, 1:], axis=1)
    cm = np.ones_like(d)
    cm[:, 1:] = d[:, 1:] * taus[1:] / np.maximum(soma, 1e-20)
    return cm


def rastrear_f0(
    x: np.ndarray,
    sr: int,
    fmin: float = 60.0,
    fmax: float = 500.0,
    janela_ms: float = 40.0,
    hop_ms: float = 10.0,
    limiar: float = 0.15,
    gate_db: float = -40.0,
) -> tuple[np.ndarray, np.ndarray]:
    """F0 por quadro (Hz; NaN = não vozeado) e máscara de quadros ativos.

    Ativo = RMS do quadro acima de ``gate_db`` relativo ao quadro mais
    forte e acima do piso absoluto. Quadro inativo nunca é vozeado.
    """
    w = int(round(sr * janela_ms / 1000.0))
    hop = max(1, int(round(sr * hop_ms / 1000.0)))
    tau_min = max(2, int(np.floor(sr / fmax)))
    tau_max = int(np.ceil(sr / fmin))
    quadros = _quadros(np.asarray(x, dtype=np.float64), w + tau_max, hop)
    n_q = quadros.shape[0]
    f0 = np.full(n_q, np.nan)
    if n_q == 0:
        return f0, np.zeros(0, dtype=bool)

    rms = np.sqrt(np.mean(quadros[:, :w] ** 2, axis=1))
    referencia = float(np.max(rms))
    ativo = (rms > _RMS_PISO) & (rms >= referencia * 10.0 ** (gate_db / 20.0))

    for ini in range(0, n_q, _LOTE):
        idx = np.nonzero(ativo[ini : ini + _LOTE])[0] + ini
        if len(idx) == 0:
            continue
        lote = quadros[idx] - np.mean(quadros[idx, :w], axis=1, keepdims=True)
        cm = _cmndf(lote, w, tau_max)
        faixa = cm[:, tau_min : tau_max + 1]
        abaixo = faixa < limiar
        tem = abaixo.any(axis=1)
        primeiro = np.argmax(abaixo, axis=1)
        for k in np.nonzero(tem)[0]:
            t = int(primeiro[k]) + tau_min
            # desce até o fundo do vale (YIN, passo 4)
            while t + 1 <= tau_max and cm[k, t + 1] < cm[k, t]:
                t += 1
            tau = float(t)
            if tau_min < t < tau_max:
                a, b, c = cm[k, t - 1], cm[k, t], cm[k, t + 1]
                den = a - 2.0 * b + c
                if abs(den) > 1e-12:
                    tau = t + 0.5 * (a - c) / den
            f0[idx[k]] = sr / tau
    return f0, ativo


@register
class PitchF0Analyzer(AudioAnalyzer):
    ID = "pitch_f0"
    NAME = "F0 mediana (altura da voz, quadros vozeados)"
    VERSION = "1.0.0"
    METHOD = "YIN (CMNDF, limiar absoluto) + gate de energia; mediana/p10/p90 sobre quadros vozeados"
    DEFAULT_LIMITATIONS = [
        "Descritor — nunca reprova (R1)",
        "Monofônico: em polifonia/mistura a F0 é de quem domina o quadro",
        "Faixa de busca fmin..fmax limita o que pode ser medido (padrão 60–500 Hz, voz falada)",
        "Vozeamento por limiar absoluto da CMNDF: fricativas sonoras podem entrar ou sair",
    ]

    def applicable(self, audio: PCM, profile: Profile) -> bool:
        return audio.n_frames >= audio.sample_rate // 4  # ao menos 250 ms

    def analyze(self, audio: PCM, params: dict[str, Any]) -> list:
        fmin = float(params.get("fmin_hz", 60.0))
        fmax = float(params.get("fmax_hz", 500.0))
        limiar = float(params.get("yin_threshold", 0.15))
        gate_db = float(params.get("gate_db", -40.0))
        min_vozeados = int(params.get("min_voiced_frames", 10))
        hop_ms = 10.0

        x = audio.mono_mix().astype(np.float64)
        f0, ativo = rastrear_f0(x, audio.sample_rate, fmin=fmin, fmax=fmax, limiar=limiar, gate_db=gate_db)
        vozeado = np.isfinite(f0)
        n_total, n_ativo, n_voz = len(f0), int(ativo.sum()), int(vozeado.sum())
        base = {
            "n_frames": n_total,
            "n_active_frames": n_ativo,
            "n_voiced_frames": n_voz,
            "hop_ms": hop_ms,
            "fmin_hz": fmin,
            "fmax_hz": fmax,
            "yin_threshold": limiar,
            "gate_db": gate_db,
        }

        if n_ativo == 0:
            return [
                self._finding(
                    check_id="pitch_f0.median",
                    metric="f0_median_hz",
                    value=None,
                    unit="Hz",
                    status=Status.NOT_APPLICABLE,
                    message="nenhum quadro acima do gate de energia (silêncio)",
                    evidence=base,
                )
            ]
        if n_voz < min_vozeados:
            return [
                self._finding(
                    check_id="pitch_f0.median",
                    metric="f0_median_hz",
                    value=None,
                    unit="Hz",
                    status=Status.INDETERMINATE,
                    message=(
                        f"sinal presente mas só {n_voz} quadro(s) vozeado(s) "
                        f"(mínimo {min_vozeados}) — sem altura definida para medir"
                    ),
                    evidence={**base, "voiced_fraction": round(n_voz / n_ativo, 4)},
                )
            ]

        v = f0[vozeado]
        p10, p25, p50, p75, p90 = (float(q) for q in np.percentile(v, [10, 25, 50, 75, 90]))
        fracao = n_voz / n_ativo
        return [
            self._finding(
                check_id="pitch_f0.median",
                metric="f0_median_hz",
                value=round(p50, 2),
                unit="Hz",
                status=Status.PASS,
                confidence=round(min(1.0, fracao), 3),
                message=(
                    f"F0 mediana {p50:.1f} Hz (p10–p90 {p10:.1f}–{p90:.1f} Hz), "
                    f"{100 * fracao:.0f}% dos quadros ativos vozeados"
                ),
                evidence={
                    **base,
                    "f0_p10_hz": round(p10, 2),
                    "f0_p25_hz": round(p25, 2),
                    "f0_p75_hz": round(p75, 2),
                    "f0_p90_hz": round(p90, 2),
                    "f0_iqr_hz": round(p75 - p25, 2),
                    "f0_p10_p90_semitones": round(12.0 * float(np.log2(p90 / p10)), 3),
                    "voiced_fraction": round(fracao, 4),
                },
            )
        ]

    def profile_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "fmin_hz": {"type": "number", "exclusiveMinimum": 0, "default": 60.0},
                "fmax_hz": {"type": "number", "exclusiveMinimum": 0, "default": 500.0},
                "yin_threshold": {"type": "number", "exclusiveMinimum": 0, "maximum": 1, "default": 0.15},
                "gate_db": {"type": "number", "maximum": 0, "default": -40.0},
                "min_voiced_frames": {"type": "integer", "minimum": 1, "default": 10},
            },
            "additionalProperties": False,
        }
