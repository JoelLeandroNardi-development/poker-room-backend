from ..domain.models import Bet
from ..domain.schemas import BetResponse

def bet_to_response(bet: Bet) -> BetResponse:
    return BetResponse(
        bet_id=bet.bet_id,
        round_id=bet.round_id,
        player_id=bet.player_id,
        action=bet.action,
        amount=bet.amount,
        created_at=bet.created_at,
    )