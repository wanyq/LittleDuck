import base64
import os

import pytest

from littleduck_api.security import ApiKeyCipher


def test_api_key_cipher_round_trip_without_committed_key() -> None:
    key = base64.b64encode(os.urandom(32)).decode()
    cipher = ApiKeyCipher(key)
    ciphertext, nonce = cipher.encrypt("example-api-key-value")

    assert b"example-api-key-value" not in ciphertext
    assert cipher.decrypt(ciphertext, nonce) == "example-api-key-value"


def test_api_key_cipher_rejects_invalid_key_length() -> None:
    with pytest.raises(ValueError):
        ApiKeyCipher(base64.b64encode(b"short").decode())
