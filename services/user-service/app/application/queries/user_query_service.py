from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..mappers import to_response
from ...domain.models import User
from ...domain.schemas import UserResponse
from shared.core.db.crud import fetch_or_404

class UserQueryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_users(self, limit: int, offset: int) -> list[UserResponse]:
        res = await self.db.execute(
            select(User).order_by(User.id.asc()).limit(limit).offset(offset)
        )
        return [to_response(u) for u in res.scalars().all()]

    async def get_user(self, email: str) -> UserResponse:
        u = await fetch_or_404(
            self.db, User,
            filter_column=User.email,
            filter_value=email,
            detail="User not found",
        )
        return to_response(u)