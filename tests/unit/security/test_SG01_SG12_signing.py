"""SG-01 to SG-12: Ed25519 signing tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from audio_suite.security.pii import redact_pii
from audio_suite.security.signing import (
    generate_keypair,
    sign_payload,
    verify_payload,
)


def test_SG01_generate_keypair(tmp_path):
    priv, pub = generate_keypair(tmp_path)
    assert priv.exists()
    assert pub.exists()
    assert priv.stat().st_size == 32  # Ed25519 private key seed
    assert pub.stat().st_size == 32   # Ed25519 public key


def test_SG02_sign_and_verify(tmp_path):
    priv, pub = generate_keypair(tmp_path)
    payload = {"a": 1, "b": [2, 3]}
    sig = sign_payload(payload, key_path=str(priv))
    assert sig["signed"] is True
    assert verify_payload(payload, sig) is True


def test_SG03_tamper_detection(tmp_path):
    """Modifying any signed field must fail verification."""
    priv, pub = generate_keypair(tmp_path)
    payload = {"a": 1}
    sig = sign_payload(payload, key_path=str(priv))
    tampered = {"a": 2}
    assert verify_payload(tampered, sig) is False


def test_SG04_unsigned_mode_safe():
    """When no key is provided and env var unset, signing raises (safe failure)."""
    import os
    # Ensure env var is not set
    old = os.environ.pop("AUDIO_SUITE_SIGNING_KEY", None)
    try:
        with pytest.raises(RuntimeError, match="no signing key"):
            sign_payload({"a": 1})
    finally:
        if old:
            os.environ["AUDIO_SUITE_SIGNING_KEY"] = old


def test_SG05_env_var_key():
    """Signing key can be provided via AUDIO_SUITE_SIGNING_KEY env var."""
    import base64
    import os

    from nacl.signing import SigningKey
    sk = SigningKey.generate()
    env_value = base64.b64encode(bytes(sk)).decode("ascii")
    old = os.environ.get("AUDIO_SUITE_SIGNING_KEY")
    os.environ["AUDIO_SUITE_SIGNING_KEY"] = env_value
    try:
        sig = sign_payload({"a": 1})
        assert sig["signed"] is True
        assert verify_payload({"a": 1}, sig) is True
    finally:
        if old is not None:
            os.environ["AUDIO_SUITE_SIGNING_KEY"] = old
        else:
            os.environ.pop("AUDIO_SUITE_SIGNING_KEY", None)


def test_SG06_signature_block_format(tmp_path):
    priv, pub = generate_keypair(tmp_path)
    sig = sign_payload({"x": "y"}, key_path=str(priv))
    assert sig["algorithm"] == "Ed25519"
    assert "public_key" in sig
    assert "signature" in sig
    # base64 decodable
    import base64
    base64.b64decode(sig["public_key"])
    base64.b64decode(sig["signature"])


def test_SG07_verify_rejects_bad_signature(tmp_path):
    """A wrong signature must fail, not crash."""
    priv, pub = generate_keypair(tmp_path)
    payload = {"a": 1}
    sig = sign_payload(payload, key_path=str(priv))
    # Corrupt the signature
    bad_sig = dict(sig)
    bad_sig["signature"] = "AAAA" + sig["signature"][4:]
    assert verify_payload(payload, bad_sig) is False


def test_SG08_verify_rejects_missing_fields():
    assert verify_payload({}, {}) is False
    assert verify_payload({}, {"public_key": "x"}) is False


def test_SG09_key_file_permissions(tmp_path):
    """Private key file should have 0600 permissions."""
    import os
    priv, pub = generate_keypair(tmp_path)
    mode = priv.stat().st_mode & 0o777
    assert mode == 0o600, f"private key has mode {oct(mode)}"


def test_SG10_pii_redact_email():
    out = redact_pii({"contact": "user@example.com"})
    assert out["contact"] == "[REDACTED:email]"


def test_SG11_pii_redact_userpath():
    out = redact_pii({"path": "/home/john/audio/file.wav"})
    assert "[REDACTED:userpath]" in out["path"]


def test_SG12_pii_redact_recursive():
    out = redact_pii({
        "a": {"b": ["user@foo.com", "normal"]},
        "c": ("/Users/jane/x",),
    })
    assert out["a"]["b"][0] == "[REDACTED:email]"
    assert "[REDACTED:userpath]" in out["c"][0]
