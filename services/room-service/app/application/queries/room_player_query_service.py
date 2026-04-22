from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ..mappers import player_to_response
from ...domain.constants import ErrorMessage
from ...domain.models import RoomPlayer
from ...domain.schemas import RoomPlayerResponse
from shared.core.db.crud import fetch_or_404

class RoomPlayerQueryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_player(self, player_id: str) -> RoomPlayerResponse:
        player = await fetch_or_404(
            self.db, RoomPlayer,
            filter_column=RoomPlayer.player_id,
            filter_value=player_id,
            detail=ErrorMessage.PLAYER_NOT_FOUND,
        )
        return player_to_response(player)