from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..helpers import get_user_by_email
from ...domain.constants import ErrorMessage, ResponseKey, TokenClaim, TokenType
from ...domain.models import AuthUser, AuthSession
from ...domain.schemas import Register, Login, RefreshRequest, LogoutRequest
from ...infrastructure.password_hasher import password_hasher
from ...infrastructure.password_reset_email import ConfiguredPasswordResetEmailSender, PasswordResetEmailSender
from ...infrastructure.token_service import JWTError, decode_token, hash_token, issue_token_pair
from shared.core.time import utc_now

class AuthAuthenticationCommandService:
    def __init__(
        self,
        db: AsyncSession,
        password_reset_email_sender: PasswordResetEmailSender | None = None,
    ):
        self.db = db
        self.password_reset_email_sender = (
            password_reset_email_sender or ConfiguredPasswordResetEmailSender()
        )

    async def register(self, data: Register) -> dict:
        existing = await get_user_by_email(self.db, data.email)
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
        user = await get_user_by_email(self.db, data.email)

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

        user = await get_user_by_email(self.db, str(sub))
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