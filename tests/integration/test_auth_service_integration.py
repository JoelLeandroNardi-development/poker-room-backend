from __future__ import annotations

import os

import httpx
import pytest

from tests.service_loader import load_service_app_module

os.environ["AUTH_DB"] = "sqlite+aiosqlite:///:memory:"
os.environ["JWT_SECRET"] = "test-secret-key-for-auth-integration"
os.environ["BCRYPT_ROUNDS"] = "4"
os.environ["PASSWORD_RESET_EMAIL_BACKEND"] = "disabled"
os.environ["PASSWORD_RESET_INCLUDE_DEBUG_TOKEN"] = "true"

@pytest.fixture()
async def auth_app_modules():
    package_name = "auth_integration_app"
    db_module = load_service_app_module(
        "auth-service",
        "infrastructure/db",
        package_name=package_name,
        reload_modules=True,
    )
    load_service_app_module(
        "auth-service",
        "domain/models",
        package_name=package_name,
    )
    main_module = load_service_app_module(
        "auth-service",
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
async def test_auth_service_split_routes_register_login_and_reset(auth_app_modules):
    main_module, _db_module = auth_app_modules

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main_module.app),
        base_url="http://auth-service.test",
    ) as client:
        health = await client.get("/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok", "service": "auth-service"}

        register = await client.post(
            "/register",
            json={"email": "route-reset@example.com", "password": "old-password"},
        )
        assert register.status_code == 200

        login = await client.post(
            "/login",
            json={"email": "route-reset@example.com", "password": "old-password"},
        )
        assert login.status_code == 200
        assert login.json()["access_token"]

        forgot = await client.post(
            "/forgot-password",
            json={"email": "route-reset@example.com"},
        )
        assert forgot.status_code == 200
        reset_token = forgot.json()["debug_token"]

        reset = await client.post(
            "/reset-password",
            json={"token": reset_token, "new_password": "new-password"},
        )
        assert reset.status_code == 200
        assert reset.json() == {"ok": True, "debug_token": None}

        new_login = await client.post(
            "/login",
            json={"email": "route-reset@example.com", "password": "new-password"},
        )
        assert new_login.status_code == 200
        assert new_login.json()["refresh_token"]