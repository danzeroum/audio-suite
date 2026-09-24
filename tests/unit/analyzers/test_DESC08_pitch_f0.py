"""AS-DESC-008 — descritor pitch_f0 (F0 mediana sobre quadros vozeados).

Verificação (não validação): o descritor mede Hz certos em sinal de F0
conhecida, gerado seed-based (CORP-01.r). Tolerâncias do critério de
aceite da frente: 120 ± 2 Hz e 220 ± 3 Hz.

R1: descritivo — silêncio e ruído terminam em not_applicable/indeterminate,
nunca fail.
"""

from __future__ import annotations

import numpy as np
import pytest

from audio_suite.analyzers import all_analyzers
from audio_suite.models import PCM, Profile, Status
from audio_suite.rule_ids import get_rule_id, rule_id_class
from tests.fixtures.generators import gen_harmonic, gen_silence, gen_speech_like, gen_white_noise

SR = 48000


def _medir(x: np.ndarray, sr: int = SR, **params):
    analyzer = all_analyzers()["pitch_f0"]
    pcm = PCM(samples=x.astype(np.float32), sample_rate=sr)
    assert analyzer.applicable(pcm, Profile(name="t", version="0", analyzers={}))
    findings = analyzer.analyze(pcm, params)
    assert len(findings) == 1
    f = findings[0]
    assert f.check_id == "pitch_f0.median"
    assert f.metric == "f0_median_hz"
    return f


@pytest.mark.parametrize(("f0", "tol"), [(120.0, 2.0), (220.0, 3.0)])
def test_tom_harmonico_mede_f0_conhecida(f0, tol):
    f = _medir(gen_harmonic(f0, sr=SR, seed=11))
    assert f.status == Status.PASS
    assert abs(f.value - f0) <= tol
    assert f.evidence["voiced_fraction"] > 0.95


@pytest.mark.parametrize("sr", [22050, 44100, 48000])
def test_tom_120_independe_da_taxa(sr):
    f = _medir(gen_harmonic(120.0, sr=sr, seed=3), sr=sr)
    assert abs(f.value - 120.0) <= 2.0


@pytest.mark.parametrize(("f0", "tol"), [(120.0, 2.0), (220.0, 3.0)])
def test_fundamental_atenuado_20db_sem_erro_de_oitava(f0, tol):
    """Fundamental 20 dB abaixo: o período continua T — nem 2·F0, nem F0/2."""
    f = _medir(gen_harmonic(f0, sr=SR, fund_db=-20.0, seed=5))
    assert abs(f.value - f0) <= tol
    # nenhum quadro caiu na oitava vizinha
    assert f.evidence["f0_p10_hz"] > f0 * 2 ** (-6 / 12)
    assert f.evidence["f0_p90_hz"] < f0 * 2 ** (6 / 12)


def test_varredura_exponencial_acompanha_percentis():
    """Varredura 150→300 Hz: mediana na média geométrica, p10/p90 nos 10%/90% do tempo."""
    f = _medir(gen_harmonic(150.0, sr=SR, dur_s=3.0, f1_hz=300.0, seed=9))
    assert f.status == Status.PASS
    esperado = {"mediana": 150 * 2**0.5, "p10": 150 * 2**0.1, "p90": 150 * 2**0.9}
    medido = {"mediana": f.value, "p10": f.evidence["f0_p10_hz"], "p90": f.evidence["f0_p90_hz"]}
    for k, v in esperado.items():
        # 25 cents: janela de 40 ms em varredura de 1 oitava / 3 s
        assert abs(1200 * np.log2(medido[k] / v)) < 25, (k, medido[k], v)
    assert abs(f.evidence["f0_p10_p90_semitones"] - 9.6) < 0.5


def test_silencio_nao_aplicavel_nunca_fail():
    f = _medir(gen_silence(sr=SR, dur_s=2.0))
    assert f.status == Status.NOT_APPLICABLE
    assert f.value is None


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_ruido_branco_indeterminado_nunca_fail(seed):
    f = _medir(gen_white_noise(sr=SR, dur_s=2.0, seed=seed))
    assert f.status == Status.INDETERMINATE
    assert f.value is None
    assert f.status not in (Status.FAIL, Status.ERROR)


def test_speech_like_do_corpus_mede_o_pulso_de_150hz():
    f = _medir(gen_speech_like(sr=44100), sr=44100)
    assert abs(f.value - 150.0) <= 3.0


def test_determinismo_byte_a_byte():
    x = gen_harmonic(173.0, sr=SR, fund_db=-6.0, seed=21)
    a, b = _medir(x), _medir(x.copy())
    assert a.value == b.value
    assert a.evidence == b.evidence


def test_curto_demais_nao_aplicavel():
    analyzer = all_analyzers()["pitch_f0"]
    pcm = PCM(samples=np.zeros(SR // 10, dtype=np.float32), sample_rate=SR)
    assert not analyzer.applicable(pcm, Profile(name="t", version="0", analyzers={}))


def test_rule_id_descritivo():
    rid = get_rule_id("pitch_f0", "f0_median_hz")
    assert rid == "AS-DESC-008"
    assert rule_id_class(rid) == "descriptive"
