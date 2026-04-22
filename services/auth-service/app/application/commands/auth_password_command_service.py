from uuid import uuid4
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..helpers import get_user_by_email, get_reset_token, revoke_active_sessions
from ...domain.constants import ErrorMessage, ResponseKey
from ...domain.models import AuthUser, PasswordResetToken
from ...domain.schemas import ForgotPasswordRequest, ResetPasswordRequest
from ...infrastructure.password_hasher import password_hasher
from ...infrastructure import config
from ...infrastructure.password_reset_email import (
    ConfiguredPasswordResetEmailSender, EmailDeliveryError,
    PasswordResetEmailSender, build_password_reset_url,
)
from ...infrastructure.token_service import generate_opaque_token, hash_token
from shared.core.time import ensure_utc, utc_now

class AuthPasswordCommandService:
    def __init__(
        self,
        db: AsyncSession,
        password_reset_email_sender: PasswordResetEmailSender | None = None,
    ):
        self.db = db
        self.password_reset_email_sender = (
            password_reset_email_sender or ConfiguredPasswordResetEmailSender()
        )

    async def forgot_password(self, data: ForgotPasswordRequest) -> dict:
        user = await get_user_by_email(self.db, data.email)
        if not user:
            return {ResponseKey.OK: True}

        now = utc_now()
        token = generate_opaque_token()
        self.db.add(
            PasswordResetToken(
                id=str(uuid4()),
                user_id=user.id,
                token_hash=hash_token(token),
                expires_at=now + timedelta(minutes=config.PASSWORD_RESET_TOKEN_TTL_MIN),
            )
        )

        try:
            await self.password_reset_email_sender.send_password_reset(
                email=user.email,
                reset_url=build_password_reset_url(token),
            )
        except EmailDeliveryError:
            await self.db.rollback()
            raise HTTPException(
                status_code=503,
                detail=ErrorMessage.PASSWORD_RESET_EMAIL_FAILED,
            )

        await self.db.commit()

        response = {ResponseKey.OK: True}
        if config.PASSWORD_RESET_INCLUDE_DEBUG_TOKEN:
            response[ResponseKey.DEBUG_TOKEN] = token
        return response

    async def reset_password(self, data: ResetPasswordRequest) -> dict:
        now = utc_now()
        reset_token = await get_reset_token(self.db, data.token)
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
        await revoke_active_sessions(self.db, user.id, now)

        await self.db.commit()

        return {ResponseKey.OK: True}