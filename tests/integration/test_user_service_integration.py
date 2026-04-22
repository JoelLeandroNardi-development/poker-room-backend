from __future__ import annotations

import os

import httpx
import pytest

from tests.service_loader import load_service_app_module

os.environ["USER_DB"] = "sqlite+aiosqlite:///:memory:"
os.environ["RABBIT_URL"] = "amqp://guest:guest@localhost:5672/"
os.environ["EXCHANGE_NAME"] = "test_exchange"

@pytest.fixture()
async def user_app_modules():
    package_name = "user_integration_app"
    db_module = load_service_app_module(
        "user-service",
        "infrastructure/db",
        package_name=package_name,
        reload_modules=True,
    )
    load_service_app_module(
        "user-service",
        "domain/models",
        package_name=package_name,
    )
    main_module = load_service_app_module(
        "user-service",
        "main",
        package_name=package_name,
    )

    async with db_module.engine.begin() as conn:
        await conn.run_sync(db_module.Base.metadata.create_all)

    yield main_module, db_module

    async with db_module.engine.begin() as conn:
        await conn.run_sync(db_module.Base.metadata.drop_all)
    await db_module.engine.dispose()

@pytest.mark.integration
@pytest.mark.asyncio
async def test_user_service_split_routes_crud_flow(user_app_modules):
    main_module, _db_module = user_app_modules

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main_module.app),
        base_url="http://user-service.test",
    ) as client:
        health = await client.get("/health")
        assert health.status_code == 200
        assert health.json()["service"] == "user-service"

        create = await client.post(
            "/users",
            json={
                "email": "route-user@example.com",
                "display_name": "Route User",
                "first_name": "Route",
                "last_name": "User",
            },
        )
        assert create.status_code == 200
        assert create.json()["email"] == "route-user@example.com"

        duplicate = await client.post(
            "/users",
            json={
                "email": "route-user@example.com",
                "display_name": "Duplicate",
                "first_name": "Dupe",
                "last_name": "User",
            },
        )
        assert duplicate.status_code == 409

        listed = await client.get("/users")
        assert listed.status_code == 200
        assert [user["email"] for user in listed.json()] == ["route-user@example.com"]

        fetched = await client.get("/users/route-user@example.com")
        assert fetched.status_code == 200
        assert fetched.json()["display_name"] == "Route User"

        updated = await client.put(
            "/users/route-user@example.com",
            json={"display_name": "Updated User"},
        )
        assert updated.status_code == 200
        assert updated.json()["display_name"] == "Updated User"
        assert updated.json()["first_name"] == "Route"

        deleted = await client.delete("/users/route-user@example.com")
        assert deleted.status_code == 200
        assert deleted.json()["email"] == "route-user@example.com"

        missing = await client.get("/users/route-user@example.com")
        assert missing.status_code == 404