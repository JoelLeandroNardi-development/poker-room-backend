from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..mappers import to_auth_user_response
from ...domain.models import AuthUser
from ...domain.schemas import AuthUserResponse, UpdateAuthUser
from ...infrastructure.password_hasher import password_hasher
from shared.core.db.crud import fetch_or_404

class AuthUserCommandService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def update_auth_user(
        self,
        user_id: int,
        data: UpdateAuthUser,
    ) -> AuthUserResponse:
        u = await fetch_or_404(
            self.db, AuthUser,
            filter_column=AuthUser.id,
            filter_value=user_id,
            detail="Auth user not found",
        )

        if data.password is not None:
            u.password = password_hasher.hash(data.password)

        if data.roles is not None:
            u.roles = data.roles

        await self.db.commit()
        await self.db.refresh(u)
        return to_auth_user_response(u)

    async def delete_auth_user(self, user_id: int) -> dict:
        u = await fetch_or_404(
            self.db, AuthUser,
            filter_column=AuthUser.id,
            filter_value=user_id,
            detail="Auth user not found",
        )

        await self.db.delete(u)
        await self.db.commit()

        return {"message": "deleted", "user_id": user_id}
