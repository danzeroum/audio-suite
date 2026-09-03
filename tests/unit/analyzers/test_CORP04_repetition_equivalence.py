"""CORP-04: equivalência comportamental da otimização do detector de repetição.

O scan original de `_detect_repetition` era um loop Python O(n×L) (~4,6 s por
fixture de 3 s), inviabilizando o orçamento da suíte Golden Master (< 90 s).
A versão vetorizada (somatório deslizante de igualdades elementares) precisa
produzir EXATAMENTE os mesmos eventos — o Golden Master congela o comportamento,
não o algoritmo. Este arquivo guarda a implementação de referência e prova a
equivalência em sinais adversariais.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from audio_suite.analyzers.glitch import GlitchAnalyzer  # noqa: E402


def _reference_scan(x: np.ndarray, min_len: int) -> list[tuple[int, int]]:
    """Implementação de referência (loop Python original, pré-otimização)."""
    events: list[tuple[int, int]] = []
    n = len(x)
    L = min_len
    while min(4096, n // 2) >= L:
        i = 0
        while i + 2 * L <= n:
            a = x[i : i + L]
            b = x[i + L : i + 2 * L]
            diff = float(np.max(np.abs(a - b)))
            if diff < 1e-6:
                events.append((i, L))
                i += 2 * L
            else:
                i += 1
        L *= 2
    return events


def _adversarial_cases() -> dict[str, np.ndarray]:
    rng = np.random.Generator(np.random.PCG64(7))
    return {
        "noise": rng.standard_normal(132300),
        "sine": 0.3 * np.sin(2 * np.pi * 440 * np.arange(132300) / 44100),
        "silence": np.zeros(132300),
        "repeat32": np.tile(np.arange(32, dtype=np.float64), 4000),
        "repeat_boundary": np.concatenate([np.zeros(4095), np.ones(1), np.zeros(4095), np.full(1, 2.0)]),
        "mixed": np.concatenate([np.zeros(5000), rng.standard_normal(5000), np.zeros(5000)]),
        "quantized": np.round(rng.standard_normal(132300) * 100) / 100,
        "tiny": np.array([0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 1.0, 1.0]),
    }


def test_repetition_detector_matches_reference_scan():
    for name, x in _adversarial_cases().items():
        new = GlitchAnalyzer._detect_repetition(x, 32)
        ref = _reference_scan(x, 32)
        assert new == ref, f"detector divergiu da referência no caso {name!r}"


def test_repetition_detector_is_fast_enough_for_gm_budget():
    """TEST-05 (informal): scan em ruído de 3 s deve custar < 200 ms."""
    rng = np.random.Generator(np.random.PCG64(7))
    x = rng.standard_normal(132300)
    t0 = time.time()
    GlitchAnalyzer._detect_repetition(x, 32)
    elapsed = time.time() - t0
    assert elapsed < 0.2, f"scan de repetição lento demais: {elapsed:.2f}s"
