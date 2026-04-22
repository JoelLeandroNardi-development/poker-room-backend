from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.exceptions import StaleStateError
from ...domain.models import Round
from ..logging import get_logger

logger = get_logger("game-service.repository")

async def cas_update_round(
    db: AsyncSession,
    game_round: Round,
    expected_version: int,
) -> None:
    saved_autoflush = db.autoflush
    db.autoflush = False
    try:
        result = await db.execute(
            update(Round)
            .where(Round.round_id == game_round.round_id)
            .where(Round.state_version == expected_version)
            .values(
                pot_amount=game_round.pot_amount,
                current_highest_bet=game_round.current_highest_bet,
                minimum_raise_amount=game_round.minimum_raise_amount,
                acting_player_id=game_round.acting_player_id,
                last_aggressor_seat=game_round.last_aggressor_seat,
                is_action_closed=game_round.is_action_closed,
                state_version=game_round.state_version,
                street=game_round.street,
                status=game_round.status,
                completed_at=game_round.completed_at,
            )
        )
    finally:
        db.autoflush = saved_autoflush
    if result.rowcount == 0:
        logger.warning(
            "CAS conflict - stale version",
            round_id=game_round.round_id,
            expected_version=expected_version,
            attempted_version=game_round.state_version,
        )
        raise StaleStateError(
            f"Concurrent update on round {game_round.round_id}: "
            f"expected state_version={expected_version}"
        )