"""Ed25519 signing for evidence bundles.

Per SG-01..SG-12: supports unsigned, local-key, CI-key modes; tamper
detection; safe failure when key missing.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey


def generate_keypair(output_dir: str | Path) -> tuple[Path, Path]:
    """Generate a new Ed25519 keypair and write to output_dir/{private,key}.key and .pub."""
    sk = SigningKey.generate()
    vk = sk.verify_key
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    priv_path = out / "signing.key"
    pub_path = out / "signing.pub"
    priv_path.write_bytes(bytes(sk))
    pub_path.write_bytes(bytes(vk))
    # Restrict private key permissions
    os.chmod(priv_path, 0o600)
    return priv_path, pub_path


def _load_signing_key(path: str | Path | None) -> SigningKey:
    if path is None:
        # Env var fallback
        env = os.environ.get("AUDIO_SUITE_SIGNING_KEY")
        if not env:
            raise RuntimeError("no signing key provided (set --signing-key or AUDIO_SUITE_SIGNING_KEY)")
        return SigningKey(base64.b64decode(env))
    p = Path(path)
    if not p.exists():
        raise RuntimeError(f"signing key not found: {path}")
    return SigningKey(p.read_bytes())


def sign_payload(payload: dict[str, Any], *, key_path: str | Path | None = None) -> dict[str, Any]:
    """Sign a payload dict with Ed25519. Returns signature metadata block."""
    sk = _load_signing_key(key_path)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sig = sk.sign(canonical)
    return {
        "algorithm": "Ed25519",
        "public_key": base64.b64encode(bytes(sk.verify_key)).decode("ascii"),
        "signature": base64.b64encode(sig.signature).decode("ascii"),
        "signed": True,
    }


def verify_payload(payload: dict[str, Any], signature_block: dict[str, Any]) -> bool:
    """Verify a signed payload. Returns True on success, False on any failure."""
    try:
        vk = VerifyKey(base64.b64decode(signature_block["public_key"]))
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        vk.verify(canonical, base64.b64decode(signature_block["signature"]))
        return True
    except (BadSignatureError, KeyError, ValueError):
        return False
