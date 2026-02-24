import base64
import json
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


ENVELOPE_PREFIX = "enc::aes256gcm::"
KEY_ENV = "CREDENTIALS_AES256_GCM_KEY_B64"
KEY_ID_ENV = "CREDENTIALS_AES256_GCM_KEY_ID"
NONCE_SIZE = 12
TAG_SIZE = 16


class CredentialCryptoError(RuntimeError):
    pass


def _b64e(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _b64d(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value.encode("ascii"))
    except Exception as exc:
        raise CredentialCryptoError("invalid base64 in credential envelope") from exc


def _load_key() -> tuple[bytes, str]:
    key_b64 = (os.getenv(KEY_ENV, "") or "").strip()
    if not key_b64:
        raise CredentialCryptoError(f"missing encryption key env var: {KEY_ENV}")
    try:
        key = base64.urlsafe_b64decode(key_b64.encode("ascii"))
    except Exception as exc:
        raise CredentialCryptoError(f"invalid base64 in {KEY_ENV}") from exc
    if len(key) != 32:
        raise CredentialCryptoError(f"{KEY_ENV} must decode to exactly 32 bytes for AES-256-GCM")
    key_id = (os.getenv(KEY_ID_ENV, "") or "").strip() or "v1"
    return key, key_id


def _make_aad(context: str) -> bytes:
    return context.encode("utf-8")


def is_encrypted_credential(value: str | None) -> bool:
    return isinstance(value, str) and value.startswith(ENVELOPE_PREFIX)


def encrypt_credential(plaintext: str, *, context: str) -> str:
    if not isinstance(plaintext, str):
        raise CredentialCryptoError("credential value must be a string")
    key, key_id = _load_key()
    nonce = os.urandom(NONCE_SIZE)
    aesgcm = AESGCM(key)
    cipher_and_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), _make_aad(context))
    ciphertext = cipher_and_tag[:-TAG_SIZE]
    tag = cipher_and_tag[-TAG_SIZE:]
    envelope = {
        "v": 1,
        "alg": "AES-256-GCM",
        "kid": key_id,
        "ctx": context,
        "n": _b64e(nonce),
        "c": _b64e(ciphertext),
        "t": _b64e(tag),
    }
    return ENVELOPE_PREFIX + json.dumps(envelope, separators=(",", ":"), sort_keys=True)


def _parse_envelope(payload: str) -> dict[str, Any]:
    if not is_encrypted_credential(payload):
        raise CredentialCryptoError("value is not an encrypted credential envelope")
    raw = payload[len(ENVELOPE_PREFIX):]
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CredentialCryptoError("invalid JSON credential envelope") from exc
    if not isinstance(envelope, dict):
        raise CredentialCryptoError("invalid credential envelope format")
    return envelope


def decrypt_credential(
    payload: str,
    *,
    context: str,
    allow_plaintext_fallback: bool = False,
) -> str:
    if not is_encrypted_credential(payload):
        if allow_plaintext_fallback and isinstance(payload, str):
            return payload
        raise CredentialCryptoError("value is not encrypted")

    envelope = _parse_envelope(payload)
    if envelope.get("alg") != "AES-256-GCM":
        raise CredentialCryptoError("unsupported credential encryption algorithm")
    if envelope.get("v") != 1:
        raise CredentialCryptoError("unsupported credential envelope version")
    stored_context = envelope.get("ctx")
    if stored_context and stored_context != context:
        raise CredentialCryptoError("credential envelope context mismatch")

    nonce_b64 = envelope.get("n")
    ciphertext_b64 = envelope.get("c")
    tag_b64 = envelope.get("t")
    if not all(isinstance(v, str) for v in [nonce_b64, ciphertext_b64, tag_b64]):
        raise CredentialCryptoError("credential envelope is missing fields")

    nonce = _b64d(nonce_b64)
    ciphertext = _b64d(ciphertext_b64)
    tag = _b64d(tag_b64)
    if len(nonce) != NONCE_SIZE:
        raise CredentialCryptoError("invalid AES-GCM nonce size")
    if len(tag) != TAG_SIZE:
        raise CredentialCryptoError("invalid AES-GCM tag size")

    key, _key_id = _load_key()
    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext + tag, _make_aad(context))
    except Exception as exc:
        raise CredentialCryptoError("credential decryption failed") from exc
    try:
        return plaintext.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CredentialCryptoError("credential plaintext is not valid UTF-8") from exc
