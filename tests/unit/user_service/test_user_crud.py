from __future__ import annotations

import os

import pytest

from tests.service_loader import load_service_app_module

os.environ.setdefault("USER_DB", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("RABBIT_URL", "amqp://guest:guest@localhost:5672/")
os.environ.setdefault("EXCHANGE_NAME", "test_exchange")


@pytest.fixture(scope="module")
def user_db_module():
    return load_service_app_module(
        "user-service", "infrastructure/db",
        package_name="user_test_app",
        reload_modules=True,
    )


@pytest.fixture(scope="module")
def user_models_module(user_db_module):
    return load_service_app_module(
        "user-service", "domain/models",
        package_name="user_test_app",
    )


@pytest.fixture(scope="module")
def user_cmd_module(user_models_module):
    return load_service_app_module(
        "user-service", "application/commands/user_command_service",
        package_name="user_test_app",
    )


@pytest.fixture(scope="module")
def user_query_module(user_models_module):
    return load_service_app_module(
        "user-service", "application/queries/user_query_service",
        package_name="user_test_app",
    )


@pytest.fixture(autouse=True)
async def _setup_tables(user_db_module, user_models_module):
    engine = user_db_module.engine
    async with engine.begin() as conn:
        await conn.run_sync(user_db_module.Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(user_db_module.Base.metadata.drop_all)


async def _create_user(user_db_module, user_models_module, *, email: str, display_name: str = "Test"):
    User = user_models_module.User
    async with user_db_module.SessionLocal() as db:
        u = User(email=email, display_name=display_name, first_name="First", last_name="Last")
        db.add(u)
        await db.commit()
        await db.refresh(u)
        return u


@pytest.mark.unit
class TestUserCommandService:
    async def test_create_user(self, user_db_module, user_cmd_module):
        from shared.schemas.users import CreateUser as _CreateUser

        async with user_db_module.SessionLocal() as db:
            svc = user_cmd_module.UserCommandService(db)
            result = await svc.create_user(
                _CreateUser(email="new@example.com", display_name="Player1", first_name="John", last_name="Doe")
            )
        assert result.email == "new@example.com"
        assert result.display_name == "Player1"

    async def test_create_duplicate_email_raises(self, user_db_module, user_models_module, user_cmd_module):
        from shared.schemas.users import CreateUser as _CreateUser
        from fastapi import HTTPException

        await _create_user(user_db_module, user_models_module, email="dup@example.com")

        async with user_db_module.SessionLocal() as db:
            svc = user_cmd_module.UserCommandService(db)
            with pytest.raises(HTTPException) as exc_info:
                await svc.create_user(
                    _CreateUser(email="dup@example.com", display_name="Dup", first_name="A", last_name="B")
                )
            assert exc_info.value.status_code == 409


@pytest.mark.unit
class TestUserQueryService:
    async def test_list_users(self, user_db_module, user_models_module, user_query_module):
        await _create_user(user_db_module, user_models_module, email="list1@example.com")
        await _create_user(user_db_module, user_models_module, email="list2@example.com")

        async with user_db_module.SessionLocal() as db:
            svc = user_query_module.UserQueryService(db)
            result = await svc.list_users()
        assert len(result) >= 2

    async def test_get_user_by_email(self, user_db_module, user_models_module, user_query_module):
        await _create_user(user_db_module, user_models_module, email="find@example.com", display_name="FindMe")

        async with user_db_module.SessionLocal() as db:
            svc = user_query_module.UserQueryService(db)
            result = await svc.get_user("find@example.com")
        assert result.email == "find@example.com"
        assert result.display_name == "FindMe"

    async def test_get_user_not_found(self, user_db_module, user_query_module):
        from fastapi import HTTPException

        async with user_db_module.SessionLocal() as db:
            svc = user_query_module.UserQueryService(db)
            with pytest.raises(HTTPException) as exc_info:
                await svc.get_user("nonexistent@example.com")
            assert exc_info.value.status_code == 404
