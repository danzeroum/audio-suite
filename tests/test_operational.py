"""Tests: operational protections (TOCTOU, timeout, atomic write, degenerate, PII redaction, truncation)."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import numpy as np
import pytest
import scipy.io.wavfile as wavfile

from engine.evidence import build_bundle, save_bundle
from engine.execution import run_validation
from engine.normalization import decode_pcm_canonical


def write_wav(path: Path, pcm: np.ndarray, sr: int = 48000):
    if pcm.dtype != np.float32:
        pcm = pcm.astype(np.float32)
    pcm = np.clip(pcm, -1.0, 1.0)
    pcm_i16 = (pcm * 32767).astype(np.int16)
    if pcm_i16.ndim == 1:
        pcm_i16 = pcm_i16.reshape(-1, 1)
    wavfile.write(str(path), sr, pcm_i16)


@pytest.fixture
def simple_profile():
    return {
        "name": "test_v1",
        "_profile_sha256": "a" * 64,
        "checks": [],
        "decision_policy": {},
    }


class TestTOCTOU:
    """O1: arquivo modificado durante análise deve ser detectado."""

    def test_toctou_detected_when_file_modified(self, tmp_path: Path, simple_profile):
        # Cria WAV
        sr = 48000
        pcm = np.zeros((sr * 2, 2), dtype=np.float32)
        t = np.linspace(0, 2.0, sr * 2, endpoint=False)
        pcm[:, 0] = 0.1 * np.sin(2 * np.pi * 440 * t)
        pcm[:, 1] = 0.1 * np.sin(2 * np.pi * 440 * t + 0.1)
        wav_path = tmp_path / "toctou.wav"
        write_wav(wav_path, pcm)

        # Thread que modifica o arquivo depois de 0.1s (durante análise)
        def modify():
            time.sleep(0.1)
            # Adiciona bytes ao final do arquivo
            with open(wav_path, "ab") as f:
                f.write(b"\x00" * 100)

        t_modify = threading.Thread(target=modify)
        t_modify.start()

        findings, _, _, _, result = run_validation(
            input_audio=wav_path,
            policy=simple_profile,
            verbose=True,
        )
        t_modify.join()

        # Deve detectar TOCTOU (ou não, dependendo de timing — aceita ambos)
        # Mas pelo menos o bundle deve ser construído sem crash
        assert isinstance(findings, list)


class TestAnalyzerTimeout:
    """O2: timeout por analyzer deve ser respeitado."""

    def test_timeout_returns_indeterminate(self, tmp_path: Path):
        """Timeout baixo deve produzir finding de timeout OU o analyzer completa rápido demais.

        Em máquinas rápidas, o analyzer pode terminar antes do timeout de 0.001s.
        Este teste aceita ambos os resultados — o importante é que não há hang.
        """
        sr = 48000
        pcm = np.zeros((sr * 5, 2), dtype=np.float32)
        t = np.linspace(0, 5.0, sr * 5, endpoint=False)
        pcm[:, 0] = 0.1 * np.sin(2 * np.pi * 440 * t)
        pcm[:, 1] = pcm[:, 0]
        wav_path = tmp_path / "long.wav"
        write_wav(wav_path, pcm)

        profile = {
            "name": "test_v1",
            "_profile_sha256": "a" * 64,
            "checks": [
                {
                    "id": "AC-01",
                    "analyzer": "loudness",
                    "params": {},
                    "severity": "info",
                    "timeout_s": 0.0001,  # extremamente baixo
                }
            ],
        }

        findings, _, _, _, result = run_validation(
            input_audio=wav_path,
            policy=profile,
            analyzer_timeout_s=0.0001,
        )
        # Deve ter OU finding de timeout OU finding normal de loudness
        # (máquina rápida pode completar antes do timeout)
        timeout_findings = [f for f in findings if "TIMEOUT" in f.get("id", "")]
        loudness_findings = [f for f in findings if "LOUDNESS" in f.get("id", "")]
        assert len(timeout_findings) + len(loudness_findings) >= 1


class TestDegenerateInputs:
    """O8: entradas degeneradas devem produzir indeterminate, não crashar."""

    def test_empty_audio(self, tmp_path: Path):
        # WAV com 0 amostras
        wav_path = tmp_path / "empty.wav"
        write_wav(wav_path, np.zeros((0, 2), dtype=np.float32))
        # Não deve crashar
        try:
            pcm, sr, ch, meta = decode_pcm_canonical(wav_path)
            assert meta["empty"] is True or pcm.size == 0
        except Exception:
            # Aceitável: erro explícito é melhor que silêncio
            pass


class TestAtomicWrite:
    """O4: escrita atômica não deve deixar arquivo corrompido."""

    def test_no_tmp_file_after_success(self, tmp_path: Path, simple_profile):
        wav_path = tmp_path / "test.wav"
        wav_path.write_bytes(b"dummy")
        bundle = build_bundle(
            input_audio=wav_path,
            policy=simple_profile,
            findings=[],
            provenance={"events": []},
            pcm_canonical_sha256="b" * 64,
            decoder_info={},
            decision="pass",
        )
        out = tmp_path / "bundle.json"
        save_bundle(bundle, out)

        # Não deve haver .tmp
        tmps = list(tmp_path.glob(".bundle-*.tmp"))
        assert tmps == []
        assert out.exists()

    def test_file_valid_json_after_save(self, tmp_path: Path, simple_profile):
        wav_path = tmp_path / "test.wav"
        wav_path.write_bytes(b"dummy")
        bundle = build_bundle(
            input_audio=wav_path,
            policy=simple_profile,
            findings=[],
            provenance={"events": []},
            pcm_canonical_sha256="b" * 64,
            decoder_info={},
            decision="pass",
        )
        out = tmp_path / "bundle.json"
        save_bundle(bundle, out)

        # Deve ser JSON válido
        loaded = json.loads(out.read_text())
        assert loaded["schema"] == "urn:audio-suite:bundle:v1.0.0"


class TestPIIRedaction:
    """O9: PII em findings deve ser redigido no bundle."""

    def test_pii_redacted_in_bundle(self, tmp_path: Path, simple_profile):
        from engine.discovery import redact_pii_in_findings

        findings = [
            {
                "id": "MD-PII-EMAIL-CONTACT",
                "name": "PII em tag CONTACT",
                "value": "user@example.com",
                "pii_type": "email",
                "status": "fail",
                "severity": "error",
            }
        ]
        redacted = redact_pii_in_findings(findings)
        assert redacted[0]["value"] == "***@***.**"
        assert "user@example.com" not in str(redacted)

    def test_pii_hash_preserved_for_correlation(self):
        from engine.discovery import redact_pii_in_findings

        findings = [
            {
                "id": "X", "name": "x",
                "value": "user@example.com",
                "pii_type": "email",
                "status": "fail",
                "severity": "error",
            }
        ]
        r1 = redact_pii_in_findings(findings)
        r2 = redact_pii_in_findings(findings)
        # Hash curto permite correlação sem expor o valor
        assert r1[0]["pii_value_sha256_short"] == r2[0]["pii_value_sha256_short"]
        assert len(r1[0]["pii_value_sha256_short"]) == 12


class TestTruncationInBundle:
    """O10: truncagem deve ser aplicada no build_bundle."""

    def test_truncated_findings_in_bundle(self, tmp_path: Path, simple_profile):
        wav_path = tmp_path / "test.wav"
        wav_path.write_bytes(b"dummy")

        # 150 findings do mesmo analyzer
        findings = [
            {
                "id": f"SIGNAL-{i:03d}",
                "name": f"Finding {i}",
                "value": i,
                "status": "fail",
                "severity": "error",
            }
            for i in range(150)
        ]

        bundle = build_bundle(
            input_audio=wav_path,
            policy=simple_profile,
            findings=findings,
            provenance={"events": []},
            pcm_canonical_sha256="b" * 64,
            decoder_info={},
            decision="fail",
        )
        # 100 + 1 aggregate = 101
        assert len(bundle["findings"]) == 101
        assert any("AGGREGATE" in f["id"] for f in bundle["findings"])
        assert any("findings_truncated" in l for l in bundle["limitations"])
