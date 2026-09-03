"""EVID-07 — `reproduction_command` no JSON/SARIF.

O campo carrega o comando exato para re-executar aquela análise, incluindo
semente/flags quando aplicáveis (determinístico, ordem fixa de flags).
"""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from audio_suite.cli import main as cli_main  # noqa: E402
from audio_suite.environment import build_reproduction_command  # noqa: E402
from audio_suite.models import PCM  # noqa: E402
from audio_suite.policy import load_profile  # noqa: E402
from tests.fixtures.generators import wav_bytes  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "generated"


@pytest.fixture(scope="module")
def sine_wav(tmp_path_factory):
    p = tmp_path_factory.mktemp("evid07") / "sine.wav"
    t = np.arange(44100) / 44100
    p.write_bytes(wav_bytes((0.3 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32), 44100))
    return p


def test_reproduction_command_is_deterministic_and_ordered():
    kwargs = dict(
        source_path="x.wav",
        profile_path="p.yaml",
        strict=True,
        fmt="json",
        output="o.json",
        only=["a", "b"],
        skip=None,
        resample=None,
    )
    c1 = build_reproduction_command(**kwargs)
    c2 = build_reproduction_command(**kwargs)
    assert c1 == c2
    assert (
        c1 == "audio-suite analyze x.wav --profile p.yaml --format json --strict --only a,b --output o.json"
    )


def test_reproduction_command_omits_unused_flags():
    cmd = build_reproduction_command(source_path="x.wav")
    assert cmd == "audio-suite analyze x.wav --format json"
    assert "--strict" not in cmd and "--only" not in cmd


def test_reproduction_command_is_shell_executable_form(sine_wav):
    """O comando é válido por shlex e aponta para o mesmo arquivo."""
    cmd = build_reproduction_command(source_path=str(sine_wav))
    tokens = shlex.split(cmd)
    assert tokens[0] == "audio-suite" and tokens[1] == "analyze"
    assert str(sine_wav) in tokens


def test_bundle_json_carries_reproduction_command(sine_wav, tmp_path):
    out = tmp_path / "bundle.json"
    rc = cli_main(["analyze", str(sine_wav), "--format", "json", "-o", str(out)])
    assert rc == 0
    bundle = json.loads(out.read_text())
    cmd = bundle["reproduction_command"]
    assert cmd.startswith("audio-suite analyze")
    assert str(sine_wav) in cmd
    assert "--format json" in cmd
    # o comando embutido é consistente com os argumentos usados
    assert "--output" in cmd  # -o foi usado


def test_bundle_json_no_output_flag_when_stdout(sine_wav, tmp_path, capsys):
    rc = cli_main(["analyze", str(sine_wav), "--format", "json"])
    assert rc == 0
    bundle = json.loads(capsys.readouterr().out)
    assert "--output" not in bundle["reproduction_command"]
    assert bundle["reproduction_command"].endswith("--format json")


def test_sarif_carries_reproduction_command(sine_wav, tmp_path):
    out = tmp_path / "bundle.sarif"
    rc = cli_main(["analyze", str(sine_wav), "--format", "sarif", "-o", str(out)])
    assert rc == 0
    sarif = json.loads(out.read_text())
    cmd = sarif["runs"][0]["properties"]["reproduction_command"]
    assert cmd and cmd.startswith("audio-suite analyze")
    assert "--format sarif" in cmd
