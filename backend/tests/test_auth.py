import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app import models  # noqa: F401
from app.core.database import Base, get_db
from app.main import app

TEST_DB = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine(TEST_DB, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_register_and_login(client):
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": "test@example.com", "password": "secret12", "display_name": "Tester"},
    )
    assert reg.status_code == 200

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "secret12"},
    )
    assert login.status_code == 200
    assert "access_token" in login.json()


@pytest.mark.asyncio
async def test_create_project(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "p@example.com", "password": "secret12", "display_name": "P"},
    )
    login = await client.post("/api/v1/auth/login", json={"email": "p@example.com", "password": "secret12"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post("/api/v1/projects", json={"name": "Demo"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Demo"
