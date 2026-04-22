from __future__ import annotations
from enum import StrEnum

class TableName(StrEnum):
    AUTH_USERS = "auth_users"
    AUTH_SESSIONS = "auth_sessions"
    PASSWORD_RESET_TOKENS = "password_reset_tokens"

class ForeignKeyName(StrEnum):
    AUTH_USERS_ID = "auth_users.id"

class TokenClaim(StrEnum):
    SUBJECT = "sub"
    ROLES = "roles"
    ISSUED_AT = "iat"
    EXPIRES_AT = "exp"
    JWT_ID = "jti"
    SESSION_ID = "sid"
    TOKEN_TYPE = "typ"

class TokenType(StrEnum):
    REFRESH = "refresh"

class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"

class ErrorMessage(StrEnum):
    EMAIL_ALREADY_EXISTS = "Email already exists"
    USER_REGISTERED = "User registered"
    INVALID_CREDENTIALS = "Invalid credentials"
    INVALID_OR_EXPIRED_REFRESH_TOKEN = "Invalid or expired refresh token"
    INVALID_TOKEN_TYPE = "Invalid token type"
    MALFORMED_REFRESH_TOKEN = "Malformed refresh token"
    SESSION_NOT_FOUND = "Session not found"
    SESSION_REVOKED = "Session revoked"
    SESSION_EXPIRED = "Session expired"
    USER_NOT_FOUND = "User not found"
    PASSWORD_RESET_REQUESTED = "Password reset requested"
    PASSWORD_RESET_COMPLETE = "Password reset complete"
    INVALID_OR_EXPIRED_RESET_TOKEN = "Invalid or expired reset token"

class ResponseKey(StrEnum):
    MESSAGE = "message"
    ROLES = "roles"
    ACCESS_TOKEN = "access_token"
    REFRESH_TOKEN = "refresh_token"
    EXPIRES_IN = "expires_in"
    OK = "ok"
    EMAIL = "email"
    DEBUG_TOKEN = "debug_token"
