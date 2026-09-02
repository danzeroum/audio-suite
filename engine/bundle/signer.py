"""Bundle: signer Ed25519 (F2.2 + A6 + S5).

Modos:
- unsigned: dev local
- local-key: chave em ~/.audio-suite/ed25519.pem
- ci-key: chave via env var AUDIO_SUITE_CI_KEY (base64)

API:
- generate_key(output_path)
- sign_bundle(bundle, mode, key_path) -> bundle com signature preenchida
- verify_bundle(bundle, key_dir=None) -> "valid" | "invalid" | "key_unknown" | "unsigned"
"""
from __future__ import annotations

import base64
import hashlib
import os
import time
from pathlib import Path
from typing import Any

from .fingerprint import canonical_json

SIGNATURE_ALGORITHM = "Ed25519"
KEY_ID_PREFIX_LOCAL = "ed25519:local:"
KEY_ID_PREFIX_CI = "ed25519:ci:"


# ---------------------------------------------------------------------------
# Geração de chaves (S5)
# ---------------------------------------------------------------------------

def generate_key(output_path: Path) -> Path:
    """Gera par de chaves Ed25519 e escreve a chave privada em PEM.

    Retorna o caminho do arquivo criado.
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            NoEncryption,
            PrivateFormat,
        )
    except ImportError as exc:
        raise RuntimeError(
            "cryptography não instalado. Instale com: pip install cryptography"
        ) from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    # Sem passphrase (lab/dev); usuário pode criptografar manualmente depois
    pem = key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption(),
    )
    output_path.write_bytes(pem)
    try:
        os.chmod(output_path, 0o600)
    except OSError:
        pass
    return output_path


def _load_private_key(key_path: Path):
    from cryptography.hazmat.primitives.serialization import (
        load_pem_private_key,
    )
    pem = key_path.read_bytes()
    return load_pem_private_key(pem, password=None)


def _load_public_key_from_private(key_path: Path):
    priv = _load_private_key(key_path)
    return priv.public_key()


def _public_key_fingerprint(key_path: Path) -> str:
    """key_id estável: hash da chave pública."""
    pub = _load_public_key_from_private(key_path)
    raw = pub.public_bytes(
        encoding=__import__("cryptography").hazmat.primitives.serialization.Encoding.Raw,
        format=__import__("cryptography").hazmat.primitives.serialization.PublicFormat.Raw,
    )
    return hashlib.sha256(raw).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Assinatura
# ---------------------------------------------------------------------------

def _canonical_payload_for_signature(bundle: dict[str, Any]) -> bytes:
    """Retorna os bytes canônicos cobertos pela assinatura.

    Importante: exclui o próprio campo `signature` do payload assinado.
    """
    payload = {k: v for k, v in bundle.items() if k != "signature"}
    return canonical_json(payload).encode("utf-8")


def sign_bundle(
    bundle: dict[str, Any],
    mode: str = "unsigned",
    key_path: Path | None = None,
    ci_context: str | None = None,
) -> dict[str, Any]:
    """Assina o bundle no modo especificado.

    mode:
    - "unsigned": não assina, apenas registra status.
    - "local-key": usa chave em key_path (default ~/.audio-suite/ed25519.pem).
    - "ci-key": usa chave via env AUDIO_SUITE_CI_KEY (base64 PEM).
    """
    if mode == "unsigned":
        bundle["signature"] = {
            "status": "unsigned",
            "algorithm": SIGNATURE_ALGORITHM,
            "reason": "Modo dev — sem assinatura.",
        }
        return bundle

    if mode == "local-key":
        if key_path is None:
            key_path = Path.home() / ".audio-suite" / "ed25519.pem"
        if not key_path.exists():
            raise FileNotFoundError(
                f"Chave local não encontrada em {key_path}. "
                "Gere com: audio-suite key generate"
            )
        priv = _load_private_key(key_path)
        key_id = KEY_ID_PREFIX_LOCAL + _public_key_fingerprint(key_path)
        payload = _canonical_payload_for_signature(bundle)
        sig = priv.sign(payload)
        bundle["signature"] = {
            "status": "signed-local",
            "algorithm": SIGNATURE_ALGORITHM,
            "key_id": key_id,
            "signature_b64": base64.b64encode(sig).decode("ascii"),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
        }
        return bundle

    if mode == "ci-key":
        env_val = os.environ.get("AUDIO_SUITE_CI_KEY")
        if not env_val:
            raise RuntimeError(
                "Modo ci-key requer env AUDIO_SUITE_CI_KEY (base64 PEM)."
            )
        try:
            pem = base64.b64decode(env_val)
        except Exception as exc:
            raise RuntimeError("AUDIO_SUITE_CI_KEY inválido (esperado base64)") from exc

        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        priv = load_pem_private_key(pem, password=None)

        # key_id inclui contexto do workflow (S5)
        context_part = ci_context or os.environ.get("GITHUB_REPOSITORY", "unknown")
        workflow_part = os.environ.get("GITHUB_WORKFLOW", "unknown")
        key_id = f"{KEY_ID_PREFIX_CI}{context_part}/{workflow_part}"

        payload = _canonical_payload_for_signature(bundle)
        sig = priv.sign(payload)
        bundle["signature"] = {
            "status": "signed-ci",
            "algorithm": SIGNATURE_ALGORITHM,
            "key_id": key_id,
            "signature_b64": base64.b64encode(sig).decode("ascii"),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
        }
        return bundle

    raise ValueError(f"Modo de assinatura desconhecido: {mode}")


# ---------------------------------------------------------------------------
# Verificação (A6)
# ---------------------------------------------------------------------------

def verify_bundle(
    bundle: dict[str, Any],
    trusted_keys_dir: Path | None = None,
) -> str:
    """Verifica a assinatura do bundle.

    Returns
    -------
    "valid" | "invalid" | "key_unknown" | "unsigned"
    """
    sig = bundle.get("signature", {})
    status = sig.get("status", "unsigned")

    if status == "unsigned":
        return "unsigned"

    key_id = sig.get("key_id", "")
    sig_b64 = sig.get("signature_b64")
    if not sig_b64 or not key_id:
        return "invalid"

    try:
        signature = base64.b64decode(sig_b64)
    except Exception:
        return "invalid"

    # Localiza chave pública confiável
    pub_key = _resolve_trusted_public_key(key_id, trusted_keys_dir)
    if pub_key is None:
        return "key_unknown"

    payload = _canonical_payload_for_signature(bundle)
    try:
        pub_key.verify(signature, payload)
        return "valid"
    except Exception:
        return "invalid"


def _resolve_trusted_public_key(key_id: str, trusted_keys_dir: Path | None):
    """Procura chave pública confiável por key_id."""
    if trusted_keys_dir is None:
        trusted_keys_dir = Path.home() / ".audio-suite" / "trusted-keys"
    if not trusted_keys_dir.exists():
        return None

    # key_id tem formato "ed25519:<scope>:<fingerprint16>"
    parts = key_id.split(":")
    if len(parts) < 3:
        return None
    fingerprint = parts[-1]

    candidate = trusted_keys_dir / f"{fingerprint}.pub"
    if not candidate.exists():
        return None

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.hazmat.primitives.serialization import (
        load_pem_public_key,
    )
    pub = load_pem_public_key(candidate.read_bytes())
    if not isinstance(pub, Ed25519PublicKey):
        return None
    return pub


def export_public_key(private_key_path: Path, output_path: Path) -> Path:
    """Exporta chave pública correspondente para diretório de chaves confiáveis."""
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        PublicFormat,
    )
    pub = _load_public_key_from_private(private_key_path)
    raw = pub.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(raw)
    return output_path


def key_id_from_private(private_key_path: Path) -> str:
    """Retorna o key_id que seria associado a uma assinatura local-key."""
    return KEY_ID_PREFIX_LOCAL + _public_key_fingerprint(private_key_path)
