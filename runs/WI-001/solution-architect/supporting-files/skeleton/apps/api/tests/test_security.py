import base64
import os

import pytest
from sqlalchemy import func, select

from littleduck_api.bootstrap_admin import ensure_initial_admin
from littleduck_api.db import Database
from littleduck_api.models import Admin
from littleduck_api.security import ApiKeyCipher, PasswordHasher, ScryptParameters


def test_api_key_cipher_round_trip_without_committed_key() -> None:
    key = base64.b64encode(os.urandom(32)).decode()
    cipher = ApiKeyCipher(key)
    ciphertext, nonce = cipher.encrypt("example-api-key-value")

    assert b"example-api-key-value" not in ciphertext
    assert cipher.decrypt(ciphertext, nonce) == "example-api-key-value"


def test_api_key_cipher_rejects_invalid_key_length() -> None:
    with pytest.raises(ValueError):
        ApiKeyCipher(base64.b64encode(b"short").decode())


@pytest.mark.asyncio
async def test_admin_bootstrap_is_strong_hashed_and_idempotent() -> None:
    database = Database(
        os.environ.get(
            "TEST_DATABASE_URL",
            "postgresql+psycopg://littleduck_test:local-only@127.0.0.1:5432/littleduck_test",
        )
    )
    fast_hasher = PasswordHasher(ScryptParameters(n=2**10))
    try:
        async with database.sessions() as session, session.begin():
            await session.execute(Admin.__table__.delete())
        created = await ensure_initial_admin(
            database.sessions,
            username="admin",
            password="admin",
            hasher=fast_hasher,
        )
        async with database.sessions() as session:
            first = await session.scalar(select(Admin).where(Admin.username == "admin"))
            assert first is not None
            first_id = first.id
            first_hash = first.password_hash
            first_updated_at = first.updated_at
            assert first_hash != "admin"
            assert fast_hasher.verify("admin", first_hash)
            assert not fast_hasher.verify("wrong", first_hash)

        repeated = await ensure_initial_admin(
            database.sessions,
            username="admin",
            password="admin",
            hasher=fast_hasher,
        )
        async with database.sessions() as session:
            second = await session.scalar(select(Admin).where(Admin.username == "admin"))
            assert second is not None
            assert second.id == first_id
            assert second.password_hash == first_hash
            assert second.updated_at == first_updated_at
            assert await session.scalar(select(func.count()).select_from(Admin)) == 1
        assert created is True
        assert repeated is False
    finally:
        await database.dispose()
