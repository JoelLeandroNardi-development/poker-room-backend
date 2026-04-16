from __future__ import annotations

import os

import pytest

os.environ.setdefault("AUTH_DB", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests")
os.environ.setdefault("BCRYPT_ROUNDS", "4")

from tests.service_loader import load_service_app_module

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