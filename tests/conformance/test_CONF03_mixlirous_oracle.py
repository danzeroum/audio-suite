"""CONF-03.r — mixlirous (loudness Rust) como oráculo adicional na matriz.

Padrão CONS do Documento Mestre: **divergência entre oráculos é investigação,
não erro automático**. Este teste:
  1. gera o mesmo corpus de loudness dos oráculos Python (sinais seed-based
     com níveis conhecidos, mesmo dos testes CONF-02);
  2. roda o CLI Rust do mixlirous via subprocess (SEM dependência de código —
     apenas comparação de resultados numéricos);
  3. escreve a matriz oráculo-a-oráculo em `test-results/oracle-matrix.json`
     (artifact de CI), marcando divergências como `needs_investigation`.

O teste é **skip por default** (o CLI Rust não é dependência do repo Python):
configure `MIXLIROUS_CLI=/caminho/do/binário` (ou deixe `mixlirous` no PATH)
para habilitar a coluna adicional. Em CI, o job `conformance-oracle` roda com
`continue-on-error` e publica o artifact da matriz.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from audio_suite.analyzers.loudness import compute_loudness_lufs  # noqa: E402
from audio_suite.models import PCM  # noqa: E402
from tests.fixtures.generators import make_rng, wav_bytes  # noqa: E402

SR = 44100


def _mixlirous_binary() -> str | None:
    env = os.environ.get("MIXLIROUS_CLI")
    if env and (Path(env).exists() or shutil.which(env)):
        return env
    found = shutil.which("mixlirous")
    return found


def _oracle_corpus() -> list[tuple[str, np.ndarray, float]]:
    """Corpus de calibração de loudness (seed-based, níveis conhecidos).

    Mesma família de sinais dos testes CONF-02: senos com nível alvo
    conhecido + ruído (para exercitar o gating), silêncio.
    """
    cases: list[tuple[str, np.ndarray, float]] = []
    t = np.arange(SR * 3) / SR
    for target_dbfs in (-23.0, -18.0, -14.0, -10.0):
        amp = 10 ** (target_dbfs / 20)
        x = (amp * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
        cases.append((f"sine_1k_{target_dbfs:+.0f}dbfs", x, amp))
    # ruído moderado (gating relativo)
    rng = make_rng(77)
    noise = (0.2 * rng.standard_normal(SR * 3)).astype(np.float32)
    cases.append(("noise_0.2", noise, 0.2))
    return cases


def _run_mixlirous(binary: str, wav_path: Path) -> dict:
    """Invoca o CLI do mixlirous e normaliza a saída.

    Convenção (documentada; ajuste MIXLIROUS_ARGS se o CLI divergir):
      mixlirous loudness <arquivo> [--json]
    Saída esperada: JSON com integrated/lufs (campos procurados em ordem:
    integrated_lufs, integrated, lufs, loudness_lufs).
    """
    extra = os.environ.get("MIXLIROUS_ARGS", "").split() if os.environ.get("MIXLIROUS_ARGS") else []
    cmd = [binary, *extra, "loudness", str(wav_path), "--json"]
    proc = subprocess.run(cmd, capture_output=True, timeout=120)
    if proc.returncode != 0:
        return {
            "ok": False,
            "error": f"exit {proc.returncode}: {proc.stderr.decode('utf-8', 'replace')[:400]}",
        }
    out = proc.stdout.decode("utf-8", "replace")
    try:
        payload = json.loads(out)
    except json.JSONDecodeError:
        return {"ok": False, "error": f"saída não-JSON: {out[:200]}"}
    value = None
    for key in ("integrated_lufs", "integrated", "lufs", "loudness_lufs", "loudness"):
        if isinstance(payload, dict) and key in payload:
            value = payload[key]
            break
    if value is None:
        return {"ok": False, "error": f"JSON sem campo de loudness: {str(payload)[:200]}"}
    return {"ok": True, "lufs": float(value), "raw": payload}


@pytest.mark.skipif(
    _mixlirous_binary() is None, reason="MIXLIROUS_CLI não configurado (oráculo Rust ausente)"
)
def test_CONF03_mixlirous_oracle_matrix(tmp_path):
    binary = _mixlirous_binary()
    rows: list[dict] = []
    divergences: list[dict] = []

    for name, samples, _amp in _oracle_corpus():
        wav = tmp_path / f"{name}.wav"
        wav.write_bytes(wav_bytes(samples, SR, "PCM_16"))
        audio = PCM(samples=samples.reshape(1, -1), sample_rate=SR)
        python_lufs = round(float(compute_loudness_lufs(audio)), 3)
        rust = _run_mixlirous(binary, wav)

        row = {
            "case": name,
            "python_lufs": python_lufs,
            "mixlirous": rust,
        }
        if rust.get("ok"):
            delta = round(float(rust["lufs"]) - python_lufs, 3)
            row["delta_lufs"] = delta
            # CONS: divergência é investigação, não erro automático.
            # Limiar de investigação: 0.5 LU (bem acima do ruído metrológico).
            if abs(delta) > 0.5:
                row["status"] = "needs_investigation"
                divergences.append(row)
            else:
                row["status"] = "consistent"
        else:
            row["status"] = "oracle_error"
        rows.append(row)

    matrix = {
        "schema": "audio-suite/oracle-matrix@1",
        "oracles": ["python (audio_suite)", "mixlirous Rust (CLI)"],
        "policy": "CONS: divergência entre oráculos é investigação, não erro automático",
        "investigation_threshold_lu": 0.5,
        "rows": rows,
        "summary": {
            "consistent": sum(1 for r in rows if r["status"] == "consistent"),
            "needs_investigation": len(divergences),
            "oracle_error": sum(1 for r in rows if r["status"] == "oracle_error"),
        },
    }

    out_dir = ROOT / "test-results"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "oracle-matrix.json").write_text(json.dumps(matrix, indent=2, ensure_ascii=False))

    # A asserção é sobre a INTEGRIDADE da matriz, não sobre concordância
    # numérica (divergência → needs_investigation, publicado; CONS).
    assert len(rows) == len(_oracle_corpus())
    for r in rows:
        assert r["status"] in ("consistent", "needs_investigation", "oracle_error")
    if divergences:
        print(
            "\nCONF-03.r: divergências entre oráculos marcadas para investigação "
            f"(ver test-results/oracle-matrix.json): {[d['case'] for d in divergences]}"
        )
