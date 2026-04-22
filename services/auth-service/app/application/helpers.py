from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.models import AuthUser, AuthSession, PasswordResetToken
from ..infrastructure.token_service import hash_token
    
async def get_user_by_email(db: AsyncSession, email: str) -> AuthUser | None:
    result = await db.execute(select(AuthUser).where(AuthUser.email == email))
    return result.scalar_one_or_none()

async def get_reset_token(db: AsyncSession, token: str) -> PasswordResetToken | None:
    result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == hash_token(token)
        )
    )
    return result.scalar_one_or_none()

async def revoke_active_sessions(db: AsyncSession, user_id: int, revoked_at: datetime) -> None:
    sessions = await db.execute(
        select(AuthSession).where(
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
        )
    )
    for session in sessions.scalars().all():
        session.revoked_at = revoked_at