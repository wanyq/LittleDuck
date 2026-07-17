import base64
import hmac
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt


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


@dataclass(frozen=True)
class ScryptParameters:
    length: int = 32
    n: int = 2**15
    r: int = 8
    p: int = 1


class PasswordHasher:
    """Memory-hard password hashing for the explicit MVP bootstrap account."""

    def __init__(self, parameters: ScryptParameters | None = None) -> None:
        self._parameters = parameters or ScryptParameters()

    def hash(self, password: str) -> str:
        salt = os.urandom(16)
        derived = self._derive(password, salt)
        parameters = self._parameters
        return "$".join(
            (
                "scrypt",
                str(parameters.n),
                str(parameters.r),
                str(parameters.p),
                base64.b64encode(salt).decode("ascii"),
                base64.b64encode(derived).decode("ascii"),
            )
        )

    def verify(self, password: str, encoded: str) -> bool:
        try:
            algorithm, n, r, p, salt_value, expected_value = encoded.split("$", 5)
            if algorithm != "scrypt":
                return False
            parameters = ScryptParameters(n=int(n), r=int(r), p=int(p))
            salt = base64.b64decode(salt_value, validate=True)
            expected = base64.b64decode(expected_value, validate=True)
            actual = self._derive(password, salt, parameters)
        except (ValueError, TypeError):
            return False
        return hmac.compare_digest(actual, expected)

    def _derive(
        self,
        password: str,
        salt: bytes,
        parameters: ScryptParameters | None = None,
    ) -> bytes:
        selected = parameters or self._parameters
        return Scrypt(
            salt=salt,
            length=selected.length,
            n=selected.n,
            r=selected.r,
            p=selected.p,
        ).derive(password.encode("utf-8"))
