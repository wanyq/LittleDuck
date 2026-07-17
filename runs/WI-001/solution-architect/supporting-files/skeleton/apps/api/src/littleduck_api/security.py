import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class ApiKeyCipher:
    def __init__(self, base64_key: str) -> None:
        key = base64.b64decode(base64_key, validate=True)
        if len(key) != 32:
            raise ValueError("API key encryption key must decode to exactly 32 bytes")
        self._cipher = AESGCM(key)

    def encrypt(self, plaintext: str) -> tuple[bytes, bytes]:
        nonce = os.urandom(12)
        ciphertext = self._cipher.encrypt(nonce, plaintext.encode("utf-8"), b"littleduck:v1")
        return ciphertext, nonce

    def decrypt(self, ciphertext: bytes, nonce: bytes) -> str:
        plaintext = self._cipher.decrypt(nonce, ciphertext, b"littleduck:v1")
        return plaintext.decode("utf-8")
