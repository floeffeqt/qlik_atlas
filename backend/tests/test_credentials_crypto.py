import base64
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.credentials_crypto import (  # type: ignore
    CredentialCryptoError,
    decrypt_credential,
    encrypt_credential,
    is_encrypted_credential,
)
from app.models import Customer  # type: ignore


def _key_b64() -> str:
    return base64.urlsafe_b64encode(b"0123456789abcdef0123456789abcdef").decode("ascii")


def test_encrypt_decrypt_roundtrip(monkeypatch):
    monkeypatch.setenv("CREDENTIALS_AES256_GCM_KEY_B64", _key_b64())
    monkeypatch.setenv("CREDENTIALS_AES256_GCM_KEY_ID", "test-v1")

    payload = encrypt_credential("secret-value", context="customers.api_key")
    assert is_encrypted_credential(payload)

    plain = decrypt_credential(payload, context="customers.api_key")
    assert plain == "secret-value"


def test_tampered_ciphertext_fails(monkeypatch):
    monkeypatch.setenv("CREDENTIALS_AES256_GCM_KEY_B64", _key_b64())

    payload = encrypt_credential("secret-value", context="customers.api_key")
    prefix, raw_json = payload.split("::", 2)[0] + "::" + payload.split("::", 2)[1] + "::", payload.split("::", 2)[2]
    envelope = json.loads(raw_json)
    envelope["t"] = base64.urlsafe_b64encode(b"\x00" * 16).decode("ascii")
    tampered = prefix + json.dumps(envelope, separators=(",", ":"), sort_keys=True)

    with pytest.raises(CredentialCryptoError):
        decrypt_credential(tampered, context="customers.api_key")


def test_missing_key_fails_closed(monkeypatch):
    monkeypatch.delenv("CREDENTIALS_AES256_GCM_KEY_B64", raising=False)
    with pytest.raises(CredentialCryptoError):
        encrypt_credential("secret-value", context="customers.api_key")


def test_customer_model_encrypts_on_assignment_and_reads_back(monkeypatch):
    monkeypatch.setenv("CREDENTIALS_AES256_GCM_KEY_B64", _key_b64())
    customer = Customer(name="Acme", notes=None)
    customer.tenant_url = "https://tenant.example"
    customer.api_key = "qlik-secret-key"

    assert customer._tenant_url_encrypted != "https://tenant.example"
    assert customer._api_key_encrypted != "qlik-secret-key"
    assert is_encrypted_credential(customer._tenant_url_encrypted)
    assert is_encrypted_credential(customer._api_key_encrypted)
    assert customer.tenant_url == "https://tenant.example"
    assert customer.api_key == "qlik-secret-key"


def test_customer_model_legacy_plaintext_fallback(monkeypatch):
    monkeypatch.setenv("CREDENTIALS_AES256_GCM_KEY_B64", _key_b64())
    customer = Customer(name="Legacy", notes=None)
    customer._tenant_url_encrypted = "https://legacy.example"
    customer._api_key_encrypted = "legacy-key"

    assert customer.tenant_url == "https://legacy.example"
    assert customer.api_key == "legacy-key"
