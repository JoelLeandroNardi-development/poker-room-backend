from __future__ import annotations

import os
from urllib.parse import parse_qs, urlsplit

import pytest

os.environ.setdefault("AUTH_DB", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests")
os.environ.setdefault("BCRYPT_ROUNDS", "4")
os.environ.setdefault("PASSWORD_RESET_BASE_URL", "https://frontend.example/reset-password")
os.environ.setdefault("PASSWORD_RESET_EMAIL_BACKEND", "disabled")
os.environ.setdefault("PASSWORD_RESET_INCLUDE_DEBUG_TOKEN", "true")

from tests.service_loader import load_service_app_module

class RecordingResetEmailSender:
    def __init__(self):
        self.messages = []

    async def send_password_reset(self, *, email: str, reset_url: str) -> None:
        self.messages.append({"email": email, "reset_url": reset_url})

@pytest.fixture(scope="module")
def auth_pw_module():
    return load_service_app_module(
        "auth-service", "infrastructure/password_hasher",
        package_name="auth_test_app",
        reload_modules=True,
    )

@pytest.fixture(scope="module")
def auth_token_module(auth_pw_module):
    return load_service_app_module(
        "auth-service", "infrastructure/token_service",
        package_name="auth_test_app",
    )

@pytest.fixture(scope="module")
def auth_db_module(auth_token_module):
    return load_service_app_module(
        "auth-service", "infrastructure/db",
        package_name="auth_test_app",
    )

@pytest.fixture(scope="module")
def auth_models_module(auth_db_module):
    return load_service_app_module(
        "auth-service", "domain/models",
        package_name="auth_test_app",
    )

@pytest.fixture(scope="module")
def auth_command_module(auth_models_module):
    return load_service_app_module(
        "auth-service", "application/commands/auth_command_service",
        package_name="auth_test_app",
    )

@pytest.fixture(scope="module")
def auth_schema_module(auth_command_module):
    return load_service_app_module(
        "auth-service", "domain/schemas",
        package_name="auth_test_app",
    )

@pytest.fixture(autouse=True)
async def _setup_auth_tables(request, auth_db_module, auth_models_module):
    if "auth_command_module" not in request.fixturenames:
        yield
        return

    engine = auth_db_module.engine
    async with engine.begin() as conn:
        await conn.run_sync(auth_db_module.Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(auth_db_module.Base.metadata.drop_all)

@pytest.mark.unit
class TestPasswordHasher:
    def test_hash_returns_string(self, auth_pw_module):
        hasher = auth_pw_module.password_hasher
        hashed = hasher.hash("my_secret")
        assert isinstance(hashed, str)
        assert hashed != "my_secret"

    def test_verify_correct_password(self, auth_pw_module):
        hasher = auth_pw_module.password_hasher
        hashed = hasher.hash("correct_password")
        assert hasher.verify("correct_password", hashed) is True

    def test_verify_wrong_password(self, auth_pw_module):
        hasher = auth_pw_module.password_hasher
        hashed = hasher.hash("correct_password")
        assert hasher.verify("wrong_password", hashed) is False

    def test_verify_invalid_hash_returns_false(self, auth_pw_module):
        hasher = auth_pw_module.password_hasher
        assert hasher.verify("anything", "not-a-valid-hash") is False

    def test_different_passwords_produce_different_hashes(self, auth_pw_module):
        hasher = auth_pw_module.password_hasher
        h1 = hasher.hash("password_one")
        h2 = hasher.hash("password_two")
        assert h1 != h2

    def test_same_password_produces_different_hashes(self, auth_pw_module):
        hasher = auth_pw_module.password_hasher
        h1 = hasher.hash("same_password")
        h2 = hasher.hash("same_password")
        assert h1 != h2 

@pytest.mark.unit
class TestTokenService:
    def test_issue_token_pair(self, auth_token_module):
        pair = auth_token_module.issue_token_pair(
            user_email="test@example.com",
            roles=["user"],
            session_id="sess-123",
        )
        assert pair.access_token
        assert pair.refresh_token
        assert pair.access_token != pair.refresh_token

    def test_decode_access_token(self, auth_token_module):
        pair = auth_token_module.issue_token_pair(
            user_email="alice@example.com",
            roles=["user", "admin"],
            session_id="sess-456",
        )
        claims = auth_token_module.decode_token(pair.access_token)
        assert claims["sub"] == "alice@example.com"
        assert claims["roles"] == ["user", "admin"]
        assert claims["sid"] == "sess-456"

    def test_decode_refresh_token_has_type(self, auth_token_module):
        pair = auth_token_module.issue_token_pair(
            user_email="bob@example.com",
            roles=["user"],
            session_id="sess-789",
        )
        claims = auth_token_module.decode_token(pair.refresh_token)
        assert claims["typ"] == "refresh"

    def test_hash_token_deterministic(self, auth_token_module):
        h1 = auth_token_module.hash_token("some-token-value")
        h2 = auth_token_module.hash_token("some-token-value")
        assert h1 == h2
        assert len(h1) == 64

    def test_hash_token_different_inputs(self, auth_token_module):
        h1 = auth_token_module.hash_token("token-a")
        h2 = auth_token_module.hash_token("token-b")
        assert h1 != h2

    def test_generate_opaque_token(self, auth_token_module):
        t1 = auth_token_module.generate_opaque_token()
        t2 = auth_token_module.generate_opaque_token()
        assert isinstance(t1, str)
        assert len(t1) > 20
        assert t1 != t2

@pytest.mark.unit
class TestPasswordResetFlow:
    @pytest.mark.asyncio
    async def test_forgot_and_reset_password(self, auth_db_module, auth_command_module, auth_schema_module):
        async with auth_db_module.SessionLocal() as db:
            email_sender = RecordingResetEmailSender()
            svc = auth_command_module.AuthCommandService(
                db,
                password_reset_email_sender=email_sender,
            )
            await svc.register(auth_schema_module.Register(
                email="reset@example.com",
                password="old-password",
            ))

            forgot = await svc.forgot_password(
                auth_schema_module.ForgotPasswordRequest(email="reset@example.com")
            )
            assert forgot["ok"] is True
            assert forgot["debug_token"]
            assert email_sender.messages[0]["email"] == "reset@example.com"
            assert email_sender.messages[0]["reset_url"].startswith(
                "https://frontend.example/reset-password?token="
            )
            query = parse_qs(urlsplit(email_sender.messages[0]["reset_url"]).query)
            assert query["token"] == [forgot["debug_token"]]

            reset = await svc.reset_password(
                auth_schema_module.ResetPasswordRequest(
                    token=forgot["debug_token"],
                    new_password="new-password",
                )
            )
            assert reset == {"ok": True}

            login = await svc.login(auth_schema_module.Login(
                email="reset@example.com",
                password="new-password",
            ))
            assert login["access_token"]

    @pytest.mark.asyncio
    async def test_reset_token_is_single_use(self, auth_db_module, auth_command_module, auth_schema_module):
        from fastapi import HTTPException

        async with auth_db_module.SessionLocal() as db:
            svc = auth_command_module.AuthCommandService(db)
            await svc.register(auth_schema_module.Register(
                email="single-use@example.com",
                password="old-password",
            ))
            forgot = await svc.forgot_password(
                auth_schema_module.ForgotPasswordRequest(email="single-use@example.com")
            )
            payload = auth_schema_module.ResetPasswordRequest(
                token=forgot["debug_token"],
                new_password="new-password",
            )
            await svc.reset_password(payload)

            with pytest.raises(HTTPException) as exc:
                await svc.reset_password(payload)

        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_forgot_password_does_not_send_for_unknown_email(
        self,
        auth_db_module,
        auth_command_module,
        auth_schema_module,
    ):
        async with auth_db_module.SessionLocal() as db:
            email_sender = RecordingResetEmailSender()
            svc = auth_command_module.AuthCommandService(
                db,
                password_reset_email_sender=email_sender,
            )
            forgot = await svc.forgot_password(
                auth_schema_module.ForgotPasswordRequest(email="missing@example.com")
            )

        assert forgot == {"ok": True}
        assert email_sender.messages == []