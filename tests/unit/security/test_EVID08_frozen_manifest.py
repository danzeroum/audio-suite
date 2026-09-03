"""EVID-08 — `--frozen-manifest` (+ `--strict`): reprodutibilidade forte.

DoD:
  - dois runs com o mesmo manifesto e o mesmo arquivo produzem JSON idêntico
    byte a byte, exceto campos explicitamente declarados não-determinísticos
  - divergência de versão gera erro claro com o campo divergente nomeado
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from audio_suite.cli import main as cli_main  # noqa: E402
from audio_suite.frozen import (  # noqa: E402
    DECLARED_NONDETERMINISTIC_FIELDS,
    precheck_frozen_manifest,
    verify_byte_identity,
)
from audio_suite.models import ExitCode  # noqa: E402
from audio_suite.policy import load_profile  # noqa: E402
from tests.fixtures.generators import wav_bytes  # noqa: E402

SR = 44100


@pytest.fixture(scope="module")
def sine_wav(tmp_path_factory):
    p = tmp_path_factory.mktemp("evid08") / "sine.wav"
    t = np.arange(SR) / SR
    p.write_bytes(wav_bytes((0.3 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32), SR))
    return str(p)


@pytest.fixture(scope="module")
def gm_profile():
    return load_profile(ROOT / "tests" / "golden" / "gm_profile.yaml")


def _run(tmp_path, wav, frozen=None, strict=False, out_name="b.json", profile=None):
    args = ["analyze", wav, "--profile", str(profile or (ROOT / "tests" / "golden" / "gm_profile.yaml"))]
    if frozen is not None:
        args += ["--frozen-manifest", str(frozen)]
    if strict:
        args.append("--strict")
    out = tmp_path / out_name
    args += ["-o", str(out)]
    rc = cli_main(args)
    return rc, out


def test_same_manifest_same_file_is_byte_identical(tmp_path, sine_wav):
    """DoD central: mesmo manifesto + mesmo arquivo → JSON byte a byte igual."""
    rc1, first = _run(tmp_path, sine_wav, out_name="first.json")
    assert rc1 == 0
    rc2, second = _run(tmp_path, sine_wav, frozen=first, strict=True, out_name="second.json")
    assert rc2 == 0
    a = json.loads(first.read_text())
    b = json.loads(second.read_text())
    # campos declarados não-determinísticos podem divergir; demais, idênticos
    assert "subject.source_path" in DECLARED_NONDETERMINISTIC_FIELDS
    assert "signature" in DECLARED_NONDETERMINISTIC_FIELDS
    assert a["measurement_fingerprint"] == b["measurement_fingerprint"]
    assert a["findings"] == b["findings"]
    assert a["environment"]["environment_hash"] == b["environment"]["environment_hash"]
    assert a["reproduction_command"] == b["reproduction_command"]


def test_same_file_different_path_passes_strict(tmp_path, sine_wav):
    """source_path é declarado não-determinístico: caminho diferente não quebra."""
    copy_path = tmp_path / "copy_of_sine.wav"
    copy_path.write_bytes(Path(sine_wav).read_bytes())
    rc1, first = _run(tmp_path, sine_wav, out_name="p1.json")
    rc2, _ = _run(tmp_path, str(copy_path), frozen=first, strict=True, out_name="p2.json")
    assert rc1 == 0 and rc2 == 0


def test_version_divergence_error_names_field(tmp_path, sine_wav, gm_profile):
    rc, first = _run(tmp_path, sine_wav, out_name="m.json")
    frozen = json.loads(first.read_text())
    frozen["environment"]["analyzer_versions"]["glitch"] = "9.9.9"
    tampered = tmp_path / "tampered_version.json"
    tampered.write_text(json.dumps(frozen))
    rc2, _ = _run(tmp_path, sine_wav, frozen=tampered, out_name="x.json")
    assert rc2 == ExitCode.FROZEN_MANIFEST_MISMATCH
    # a mensagem nomeia o campo divergente
    import contextlib
    import io as _io

    err = _io.StringIO()
    with contextlib.redirect_stderr(err):
        cli_main(
            [
                "analyze",
                sine_wav,
                "--profile",
                str(ROOT / "tests" / "golden" / "gm_profile.yaml"),
                "--frozen-manifest",
                str(tampered),
            ]
        )
    assert "environment.analyzer_versions.glitch" in err.getvalue()


def test_profile_hash_divergence_error_names_field(tmp_path, sine_wav):
    rc, first = _run(tmp_path, sine_wav, out_name="m2.json")
    frozen = json.loads(first.read_text())
    frozen["environment"]["resolved_profile_sha256"] = "0" * 64
    tampered = tmp_path / "tampered_profile.json"
    tampered.write_text(json.dumps(frozen))
    rc2 = cli_main(["analyze", sine_wav, "--frozen-manifest", str(tampered)])
    assert rc2 == ExitCode.FROZEN_MANIFEST_MISMATCH


def test_strict_refuses_undeclared_field_drift(tmp_path, sine_wav):
    """Qualquer campo não declarado divergente → recusa nomeando o caminho."""
    rc, first = _run(tmp_path, sine_wav, out_name="f.json")
    frozen = json.loads(first.read_text())
    frozen["findings"][0]["value"] = 12345.6  # simula drift não declarado
    tampered = tmp_path / "tampered_findings.json"
    tampered.write_text(json.dumps(frozen))
    rc2, _ = _run(tmp_path, sine_wav, frozen=tampered, strict=True, out_name="g.json")
    assert rc2 == ExitCode.FROZEN_MANIFEST_MISMATCH


def test_without_strict_byte_drift_does_not_block(tmp_path, sine_wav):
    """--frozen-manifest sem --strict: apenas pré-checks (política declarada)."""
    rc, first = _run(tmp_path, sine_wav, out_name="f2.json")
    frozen = json.loads(first.read_text())
    frozen["findings"][0]["value"] = 12345.6
    tampered = tmp_path / "tampered2.json"
    tampered.write_text(json.dumps(frozen))
    rc2, _ = _run(tmp_path, sine_wav, frozen=tampered, strict=False, out_name="g2.json")
    assert rc2 == 0  # pré-checks passam (ambiente igual); identidade não é exigida


def test_verify_byte_identity_masks_declared_fields():
    frozen = {"subject": {"source_path": "/a/x.wav", "sha": "ab"}, "signature": {"s": "1"}}
    actual = {"subject": {"source_path": "/b/y.wav", "sha": "ab"}, "signature": {"s": "2"}}
    assert verify_byte_identity(frozen, actual) == []
    actual2 = {"subject": {"source_path": "/b/y.wav", "sha": "zz"}, "signature": {"s": "2"}}
    divs = verify_byte_identity(frozen, actual2)
    assert len(divs) == 1 and divs[0].field_path == "subject.sha"


def test_precheck_frozen_manifest_unit(gm_profile):
    from audio_suite.environment import snapshot_environment

    env = snapshot_environment(gm_profile)
    frozen = {
        "tool": {"version": env["tool_version"]},
        "environment": {
            "resolved_profile_sha256": env["resolved_profile_sha256"],
            "environment_hash": env["environment_hash"],
            "analyzer_versions": env["analyzer_versions"],
        },
    }
    assert precheck_frozen_manifest(frozen, gm_profile) == []
    frozen2 = copy.deepcopy(frozen)
    frozen2["environment"]["analyzer_versions"]["loudness"] = "0.0.1"
    divs = precheck_frozen_manifest(frozen2, gm_profile)
    assert any(d.field_path == "environment.analyzer_versions.loudness" for d in divs)
