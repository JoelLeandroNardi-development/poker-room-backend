from ..domain.models import Game, Round
from ..domain.schemas import GameResponse, RoundResponse


def game_to_response(game: Game) -> GameResponse:
    return GameResponse(
        game_id=game.game_id,
        room_id=game.room_id,
        status=game.status,
        current_blind_level=game.current_blind_level,
        level_started_at=game.level_started_at,
        current_dealer_seat=game.current_dealer_seat,
        current_small_blind_seat=game.current_small_blind_seat,
        current_big_blind_seat=game.current_big_blind_seat,
        created_at=game.created_at,
    )


def round_to_response(game_round: Round) -> RoundResponse:
    return RoundResponse(
        round_id=game_round.round_id,
        game_id=game_round.game_id,
        round_number=game_round.round_number,
        dealer_seat=game_round.dealer_seat,
        small_blind_seat=game_round.small_blind_seat,
        big_blind_seat=game_round.big_blind_seat,
        small_blind_amount=game_round.small_blind_amount,
        big_blind_amount=game_round.big_blind_amount,
        ante_amount=game_round.ante_amount,
        status=game_round.status,
        winner_player_id=game_round.winner_player_id,
        pot_amount=game_round.pot_amount,
        created_at=game_round.created_at,
        completed_at=game_round.completed_at,
    )
