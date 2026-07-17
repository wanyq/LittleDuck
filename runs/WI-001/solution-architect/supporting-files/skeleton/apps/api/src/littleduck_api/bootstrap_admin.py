import asyncio
import uuid

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .config import Settings
from .db import Database
from .models import Admin
from .security import PasswordHasher


async def ensure_initial_admin(
    sessions: async_sessionmaker[AsyncSession],
    *,
    username: str,
    password: str,
    hasher: PasswordHasher | None = None,
) -> bool:
    selected_hasher = hasher or PasswordHasher()
    password_hash = selected_hasher.hash(password)
    statement = (
        insert(Admin)
        .values(id=uuid.uuid4(), username=username, password_hash=password_hash)
        .on_conflict_do_nothing(index_elements=[Admin.username])
        .returning(Admin.id)
    )
    async with sessions() as session, session.begin():
        created_id = await session.scalar(statement)
    return created_id is not None


async def _run() -> None:
    settings = Settings()
    database = Database(settings.database_url)
    try:
        created = await ensure_initial_admin(
            database.sessions,
            username=settings.bootstrap_admin_username,
            password=settings.bootstrap_admin_password,
        )
    finally:
        await database.dispose()
    print("initial admin created" if created else "initial admin already exists")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
