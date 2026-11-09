"""Tests marked `db` need PostgreSQL at DATABASE_URL and skip without it."""
import asyncio
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://aqua:aqua@localhost:5432/aqua_test")
os.environ.setdefault("JWT_SECRET", "test-only-secret-that-is-long-enough-for-validation")

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import delete, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.database import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    Device,
    Organization,
    Plan,
    Telemetry,
    User,
)

BACKEND = Path(__file__).resolve().parents[1] / "backend"


async def _database_available(url: str) -> bool:
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def migrated_database() -> str:
    url = os.environ["DATABASE_URL"]
    if not asyncio.run(_database_available(url)):
        pytest.skip("PostgreSQL is not available")
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, check=True
    )
    return url


@pytest_asyncio.fixture
async def sessions(migrated_database):
    engine = create_async_engine(migrated_database, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        for model in (Telemetry, Device, Organization, User, Plan):
            await session.execute(delete(model))
        await session.commit()
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def client(sessions):
    async def override():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()
