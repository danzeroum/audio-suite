"""Tests: bundle/signer (Ed25519 — F2.2 + A6 + S5)."""
from __future__ import annotations

import base64
from pathlib import Path

import pytest

from engine.bundle.signer import (
    KEY_ID_PREFIX_LOCAL,
    generate_key,
    key_id_from_private,
    sign_bundle,
    verify_bundle,
)


@pytest.fixture
def tmp_keypair(tmp_path: Path):
    """Gera par de chaves temporário."""
    key_path = tmp_path / "ed25519.pem"
    generate_key(key_path)
    return key_path


@pytest.fixture
def trusted_keys_dir(tmp_path: Path):
    d = tmp_path / "trusted"
    d.mkdir()
    return d


@pytest.fixture
def sample_bundle():
    return {
        "schema": "urn:audio-suite:bundle:v1.0.0",
        "subject": {"path": "/tmp/x.wav", "file_sha256": "a" * 64},
        "execution": {"suite_version": "0.2.0-beta", "status": "completed"},
        "findings": [],
        "decision": "pass",
        "signature": {},  # será preenchido
    }


class TestGenerateKey:
    def test_generates_pem(self, tmp_keypair):
        assert tmp_keypair.exists()
        content = tmp_keypair.read_bytes()
        assert b"PRIVATE KEY" in content

    def test_key_id_stable(self, tmp_keypair):
        id1 = key_id_from_private(tmp_keypair)
        id2 = key_id_from_private(tmp_keypair)
        assert id1 == id2
        assert id1.startswith(KEY_ID_PREFIX_LOCAL)


class TestSignBundle:
    def test_unsigned_mode(self, sample_bundle):
        signed = sign_bundle(sample_bundle, mode="unsigned")
        assert signed["signature"]["status"] == "unsigned"

    def test_local_key_signing(self, sample_bundle, tmp_keypair):
        signed = sign_bundle(sample_bundle, mode="local-key", key_path=tmp_keypair)
        sig = signed["signature"]
        assert sig["status"] == "signed-local"
        assert sig["algorithm"] == "Ed25519"
        assert sig["key_id"].startswith(KEY_ID_PREFIX_LOCAL)
        assert "signature_b64" in sig
        assert "timestamp" in sig
        assert "payload_sha256" in sig

    def test_local_key_missing_raises(self, sample_bundle, tmp_path):
        with pytest.raises(FileNotFoundError):
            sign_bundle(sample_bundle, mode="local-key", key_path=tmp_path / "nonexistent.pem")

    def test_ci_key_requires_env(self, sample_bundle, monkeypatch):
        monkeypatch.delenv("AUDIO_SUITE_CI_KEY", raising=False)
        with pytest.raises(RuntimeError, match="AUDIO_SUITE_CI_KEY"):
            sign_bundle(sample_bundle, mode="ci-key")

    def test_ci_key_with_env(self, sample_bundle, tmp_keypair, monkeypatch):
        # Codifica chave PEM em base64
        pem_bytes = tmp_keypair.read_bytes()
        b64 = base64.b64encode(pem_bytes).decode("ascii")
        monkeypatch.setenv("AUDIO_SUITE_CI_KEY", b64)
        monkeypatch.setenv("GITHUB_REPOSITORY", "test/repo")
        monkeypatch.setenv("GITHUB_WORKFLOW", "ci")
        signed = sign_bundle(sample_bundle, mode="ci-key")
        assert signed["signature"]["status"] == "signed-ci"
        assert "test/repo" in signed["signature"]["key_id"]

    def test_unknown_mode_raises(self, sample_bundle):
        with pytest.raises(ValueError):
            sign_bundle(sample_bundle, mode="invalid-mode")


class TestVerifyBundle:
    def test_unsigned_returns_unsigned(self, sample_bundle):
        signed = sign_bundle(sample_bundle, mode="unsigned")
        result = verify_bundle(signed)
        assert result == "unsigned"

    def test_valid_signature(self, sample_bundle, tmp_keypair, trusted_keys_dir):
        # Exporta chave pública
        from engine.bundle.signer import export_public_key
        export_public_key(tmp_keypair, trusted_keys_dir / f"{key_id_from_private(tmp_keypair).split(':')[-1]}.pub")

        signed = sign_bundle(sample_bundle, mode="local-key", key_path=tmp_keypair)
        result = verify_bundle(signed, trusted_keys_dir=trusted_keys_dir)
        assert result == "valid"

    def test_invalid_signature(self, sample_bundle, tmp_keypair, trusted_keys_dir):
        from engine.bundle.signer import export_public_key
        export_public_key(tmp_keypair, trusted_keys_dir / f"{key_id_from_private(tmp_keypair).split(':')[-1]}.pub")

        signed = sign_bundle(sample_bundle, mode="local-key", key_path=tmp_keypair)
        # Adultera um byte
        signed["decision"] = "fail"  # mudou conteúdo sem re-assinar
        result = verify_bundle(signed, trusted_keys_dir=trusted_keys_dir)
        assert result == "invalid"

    def test_key_unknown(self, sample_bundle, tmp_keypair, trusted_keys_dir):
        # Não exporta chave pública
        signed = sign_bundle(sample_bundle, mode="local-key", key_path=tmp_keypair)
        result = verify_bundle(signed, trusted_keys_dir=trusted_keys_dir)
        assert result == "key_unknown"

    def test_corrupt_signature_b64(self, sample_bundle, tmp_keypair, trusted_keys_dir):
        from engine.bundle.signer import export_public_key
        export_public_key(tmp_keypair, trusted_keys_dir / f"{key_id_from_private(tmp_keypair).split(':')[-1]}.pub")

        signed = sign_bundle(sample_bundle, mode="local-key", key_path=tmp_keypair)
        # Corrompe a assinatura
        signed["signature"]["signature_b64"] = base64.b64encode(b"corrupt").decode("ascii")
        result = verify_bundle(signed, trusted_keys_dir=trusted_keys_dir)
        assert result == "invalid"
