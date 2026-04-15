from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..mappers import to_auth_user_response
from ...domain.models import AuthUser
from ...domain.schemas import AuthUserResponse
from shared.core.db.crud import fetch_or_404

class AuthUserQueryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_users(self, limit: int, offset: int) -> list[AuthUserResponse]:
        res = await self.db.execute(
            select(AuthUser).order_by(AuthUser.id.asc()).limit(limit).offset(offset)
        )
        return [to_auth_user_response(u) for u in res.scalars().all()]

    async def get_by_id(self, user_id: int) -> AuthUserResponse:
        u = await fetch_or_404(
            self.db, AuthUser,
            filter_column=AuthUser.id,
            filter_value=user_id,
            detail="Auth user not found",
        )
        return to_auth_user_response(u)

    async def get_auth_user_by_email(self, email: str) -> AuthUserResponse:
        u = await fetch_or_404(
            self.db, AuthUser,
            filter_column=AuthUser.email,
            filter_value=email,
            detail="Auth user not found",
        )
        return to_auth_user_response(u)