from uuid import uuid4
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.constants import ErrorMessage, ResponseKey, TokenClaim, TokenType
from ...domain.models import AuthUser, AuthSession, PasswordResetToken
from ...domain.schemas import (
    Register, Login, RefreshRequest, LogoutRequest,
    ForgotPasswordRequest, ResetPasswordRequest,
)
from ...infrastructure.password_hasher import password_hasher
from ...infrastructure.token_service import (
    JWTError, decode_token, generate_opaque_token, hash_token, issue_token_pair,
)
from shared.core.time import ensure_utc, utc_now

class AuthCommandService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(self, data: Register) -> dict:
        existing = await self._get_user_by_email(data.email)
        if existing:
            raise HTTPException(status_code=409, detail=ErrorMessage.EMAIL_ALREADY_EXISTS)

        user = AuthUser(
            email=data.email,
            password=password_hasher.hash(data.password),
            roles=data.roles,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        return {ResponseKey.MESSAGE: ErrorMessage.USER_REGISTERED, ResponseKey.ROLES: user.roles}

    async def login(self, data: Login) -> dict:
        user = await self._get_user_by_email(data.email)

        if not user or not password_hasher.verify(data.password, user.password):
            raise HTTPException(status_code=401, detail=ErrorMessage.INVALID_CREDENTIALS)

        now = utc_now()
        session_id = str(uuid4())
        tokens = issue_token_pair(
            user_email=user.email,
            roles=list(user.roles or []),
            session_id=session_id,
        )

        user.last_login_at = now
        self.db.add(
            AuthSession(
                id=session_id,
                user_id=user.id,
                refresh_token_hash=hash_token(tokens.refresh_token),
                expires_at=tokens.refresh_expires_at,
            )
        )
        await self.db.commit()

        return {
            ResponseKey.ACCESS_TOKEN: tokens.access_token,
            ResponseKey.REFRESH_TOKEN: tokens.refresh_token,
            ResponseKey.EXPIRES_IN: int((tokens.access_expires_at - now).total_seconds()),
        }

    async def refresh_tokens(self, data: RefreshRequest) -> dict:
        try:
            token_payload = decode_token(data.refresh_token)
        except JWTError:
            raise HTTPException(status_code=401, detail=ErrorMessage.INVALID_OR_EXPIRED_REFRESH_TOKEN)

        if token_payload.get(TokenClaim.TOKEN_TYPE) != TokenType.REFRESH:
            raise HTTPException(status_code=401, detail=ErrorMessage.INVALID_TOKEN_TYPE)

        sid = token_payload.get(TokenClaim.SESSION_ID)
        sub = token_payload.get(TokenClaim.SUBJECT)
        roles = token_payload.get(TokenClaim.ROLES) or []
        if not sid or not sub:
            raise HTTPException(status_code=401, detail=ErrorMessage.MALFORMED_REFRESH_TOKEN)

        session = await self.db.get(AuthSession, str(sid))
        if not session:
            raise HTTPException(status_code=401, detail=ErrorMessage.SESSION_NOT_FOUND)

        now = utc_now()
        if session.revoked_at is not None:
            raise HTTPException(status_code=401, detail=ErrorMessage.SESSION_REVOKED)
        if session.expires_at <= now:
            raise HTTPException(status_code=401, detail=ErrorMessage.SESSION_EXPIRED)
        if session.refresh_token_hash != hash_token(data.refresh_token):
            raise HTTPException(status_code=401, detail=ErrorMessage.INVALID_OR_EXPIRED_REFRESH_TOKEN)

        session.revoked_at = now

        user = await self._get_user_by_email(str(sub))
        if not user:
            raise HTTPException(status_code=401, detail=ErrorMessage.USER_NOT_FOUND)

        new_session_id = str(uuid4())
        tokens = issue_token_pair(
            user_email=user.email,
            roles=list(user.roles or roles),
            session_id=new_session_id,
        )

        self.db.add(
            AuthSession(
                id=new_session_id,
                user_id=user.id,
                refresh_token_hash=hash_token(tokens.refresh_token),
                expires_at=tokens.refresh_expires_at,
                last_seen_at=now,
            )
        )
        await self.db.commit()

        return {
            ResponseKey.ACCESS_TOKEN: tokens.access_token,
            ResponseKey.REFRESH_TOKEN: tokens.refresh_token,
            ResponseKey.EXPIRES_IN: int((tokens.access_expires_at - now).total_seconds()),
        }

    async def logout(self, data: LogoutRequest) -> dict:
        try:
            token_payload = decode_token(data.refresh_token)
        except JWTError:
            raise HTTPException(status_code=401, detail=ErrorMessage.INVALID_OR_EXPIRED_REFRESH_TOKEN)

        sid = token_payload.get(TokenClaim.SESSION_ID)
        if not sid:
            raise HTTPException(status_code=401, detail=ErrorMessage.MALFORMED_REFRESH_TOKEN)

        session = await self.db.get(AuthSession, str(sid))
        if not session:
            return {ResponseKey.OK: True}

        if session.refresh_token_hash != hash_token(data.refresh_token):
            raise HTTPException(status_code=401, detail=ErrorMessage.INVALID_OR_EXPIRED_REFRESH_TOKEN)

        if session.revoked_at is None:
            session.revoked_at = utc_now()
            await self.db.commit()

        return {ResponseKey.OK: True}

    async def forgot_password(self, data: ForgotPasswordRequest) -> dict:
        user = await self._get_user_by_email(data.email)
        if not user:
            return {ResponseKey.OK: True}

        now = utc_now()
        token = generate_opaque_token()
        self.db.add(
            PasswordResetToken(
                id=str(uuid4()),
                user_id=user.id,
                token_hash=hash_token(token),
                expires_at=now + timedelta(hours=1),
            )
        )
        await self.db.commit()

        return {
            ResponseKey.OK: True,
            ResponseKey.DEBUG_TOKEN: token,
        }

    async def reset_password(self, data: ResetPasswordRequest) -> dict:
        now = utc_now()
        reset_token = await self._get_reset_token(data.token)
        if (
            reset_token is None
            or reset_token.used_at is not None
            or ensure_utc(reset_token.expires_at) <= now
        ):
            raise HTTPException(status_code=401, detail=ErrorMessage.INVALID_OR_EXPIRED_RESET_TOKEN)

        user = await self.db.get(AuthUser, reset_token.user_id)
        if user is None:
            raise HTTPException(status_code=404, detail=ErrorMessage.USER_NOT_FOUND)

        user.password = password_hasher.hash(data.new_password)
        reset_token.used_at = now
        await self._revoke_active_sessions(user.id, now)

        await self.db.commit()

        return {ResponseKey.OK: True}

    async def _get_user_by_email(self, email: str) -> AuthUser | None:
        result = await self.db.execute(select(AuthUser).where(AuthUser.email == email))
        return result.scalar_one_or_none()

    async def _get_reset_token(self, token: str) -> PasswordResetToken | None:
        result = await self.db.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == hash_token(token)
            )
        )
        return result.scalar_one_or_none()

    async def _revoke_active_sessions(self, user_id: int, revoked_at: datetime) -> None:
        sessions = await self.db.execute(
            select(AuthSession).where(
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
            )
        )
        for session in sessions.scalars().all():
            session.revoked_at = revoked_at