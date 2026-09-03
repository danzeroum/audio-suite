"""CORP-08 — corpus de defeito injetado com ground truth.

Cada caso injeta um defeito conhecido em um sinal limpo (seed-based, geradores
de `tests/fixtures/generators.py`) e anota `expected_findings: list[rule_id]` —
os rule_ids (CONTR-02) que um detector correto DEVE apontar.

Casos sem detector registrado hoje (ex.: DC offset) ficam com
`expected_findings: []` e `coverage_gap: true` — o score script reporta N/A e
o gap de cobertura fica visível nas métricas de release, em vez de esconder.

Todos os sinais são determinísticos: mesma seed → mesmos bytes (CORP-01.r).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from tests.fixtures.generators import SR, make_rng, wav_bytes


def _carrier(seed: int, dur_s: float = 2.0, amp: float = 0.3, sr: int = SR) -> np.ndarray:
    """Sinal limpo: senoide 440 Hz + ruído leve (seed-based)."""
    rng = make_rng(seed)
    t = np.arange(int(sr * dur_s)) / sr
    x = amp * np.sin(2 * np.pi * 440 * t)
    x += 0.01 * rng.standard_normal(len(t))
    return x.astype(np.float32)


# ---------------------------------------------------------------------------
# Injetores de defeito (cada um retorna float32 mono)
# ---------------------------------------------------------------------------
def inject_click(seed: int = 81) -> np.ndarray:
    """Click isolado de 1 amostra (amplitude isolada do teto de true peak)."""
    x = _carrier(seed)
    pos = int(SR * 1.0)
    # 0.7 → true peak ~ -3 dBTP (abaixo do ceiling -1): isola o click do
    # detector de true peak para o ground truth medir o detector certo.
    x[pos] = 0.7
    return x


def inject_dropout(seed: int = 82) -> np.ndarray:
    """Dropout de 60 ms (silêncio abrupto em meio ao sinal)."""
    x = _carrier(seed)
    s = int(SR * 0.8)
    e = s + int(SR * 0.06)
    x[s:e] = 0.0
    return x


def inject_repetition(seed: int = 83) -> np.ndarray:
    """Buffer stutter: bloco de 512 amostras repetido imediatamente."""
    x = _carrier(seed)
    s = int(SR * 1.0)
    L = 512
    block = x[s : s + L].copy()
    x[s + L : s + 2 * L] = block
    return x


def inject_clipping_sustained(seed: int = 84) -> np.ndarray:
    """Clipping sustentado: ganho 3x com hard clip em ±1.0 (amostras em full scale)."""
    x = _carrier(seed, amp=0.3)
    s = int(SR * 0.5)
    e = int(SR * 1.5)
    # clip em ±1.0 → amostras >= 0.99 (threshold default do detector de clipping)
    x[s:e] = np.clip(3.0 * x[s:e], -1.0, 1.0)
    return x


def inject_dc_offset(seed: int = 85) -> np.ndarray:
    """DC offset de 0.2 (sem detector registrado — coverage gap)."""
    x = _carrier(seed)
    return (x + 0.2).astype(np.float32)


def inject_gap(seed: int = 86) -> np.ndarray:
    """Gap: 250 ms de silêncio absoluto no meio do sinal (mais longo que dropout)."""
    x = _carrier(seed)
    s = int(SR * 0.7)
    e = s + int(SR * 0.25)
    x[s:e] = 0.0
    return x


# ---------------------------------------------------------------------------
# Registro de casos
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DefectCase:
    name: str
    defect_type: str
    description: str
    builder: Callable[[], np.ndarray]
    expected_findings: list[str] = field(default_factory=list)
    coverage_gap: bool = False  # True = nenhum detector registrado para o defeito
    notes: str = ""


#: Corpus canônico (≥ 6 tipos de defeito com ground truth)
CORPUS_CASES: list[DefectCase] = [
    DefectCase(
        name="click_1sample",
        defect_type="click",
        description="click de 1 amostra (0.95) em 1.0 s sobre carrier 440 Hz",
        builder=inject_click,
        expected_findings=["AS-DEF-001"],
    ),
    DefectCase(
        name="dropout_60ms",
        defect_type="dropout",
        description="dropout de 60 ms em 0.8 s sobre carrier 440 Hz",
        builder=inject_dropout,
        expected_findings=["AS-DEF-001"],
    ),
    DefectCase(
        name="repetition_512",
        defect_type="repetition",
        description="bloco de 512 amostras repetido (buffer stutter) em 1.0 s",
        builder=inject_repetition,
        expected_findings=["AS-DEF-001"],
    ),
    DefectCase(
        name="clipping_sustained",
        defect_type="clipping_sustained",
        description="ganho 3x com hard clip ±0.95 entre 0.5–1.5 s",
        builder=inject_clipping_sustained,
        expected_findings=["AS-PEAK-002", "AS-PEAK-001"],
    ),
    DefectCase(
        name="dc_offset_0.2",
        defect_type="dc_offset",
        description="DC offset de 0.2 sobre carrier 440 Hz",
        builder=inject_dc_offset,
        expected_findings=[],
        coverage_gap=True,
        notes="nenhum analyzer registrado detecta DC offset hoje (gap de cobertura documentado; recall N/A)",
    ),
    DefectCase(
        name="gap_250ms",
        defect_type="gap",
        description="gap de 250 ms de silêncio absoluto em 0.7 s",
        builder=inject_gap,
        expected_findings=["AS-DEF-001"],
    ),
]

CORPUS_CASES_BY_NAME = {c.name: c for c in CORPUS_CASES}


def render_case_wav(case: DefectCase, sr: int = SR) -> bytes:
    """Serializa o caso para WAV bytes (determinístico)."""
    return wav_bytes(case.builder(), sr, "PCM_16")
