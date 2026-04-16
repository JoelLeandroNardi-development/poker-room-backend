from ..domain.models import Bet, Game, Round, RoundPlayer, RoundPayout, HandLedgerEntry
from ..domain.schemas import (
    GameResponse, RoundResponse, RoundPlayerResponse, PayoutResponse,
    LedgerEntryResponse, HandStateResponse, PlayerSnapshotResponse,
)
from ..domain.hand_ledger import HandState
from shared.schemas.bets import BetResponse

def bet_to_response(bet: Bet) -> BetResponse:
    return BetResponse(
        bet_id=bet.bet_id,
        round_id=bet.round_id,
        player_id=bet.player_id,
        action=bet.action,
        amount=bet.amount,
        created_at=bet.created_at,
    )

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
        hands_played=game.hands_played,
        hands_at_current_level=game.hands_at_current_level,
        created_at=game.created_at,
    )

def round_player_to_response(rp: RoundPlayer) -> RoundPlayerResponse:
    return RoundPlayerResponse(
        player_id=rp.player_id,
        seat_number=rp.seat_number,
        stack_remaining=rp.stack_remaining,
        committed_this_street=rp.committed_this_street,
        committed_this_hand=rp.committed_this_hand,
        has_folded=rp.has_folded,
        is_all_in=rp.is_all_in,
        is_active_in_hand=rp.is_active_in_hand,
    )

def payout_to_response(p: RoundPayout) -> PayoutResponse:
    return PayoutResponse(
        pot_index=p.pot_index,
        pot_type=p.pot_type,
        player_id=p.player_id,
        amount=p.amount,
    )

def round_to_response(
    game_round: Round,
    players: list[RoundPlayer] | None = None,
    payouts: list[RoundPayout] | None = None,
) -> RoundResponse:
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
        pot_amount=game_round.pot_amount,
        street=game_round.street,
        acting_player_id=game_round.acting_player_id,
        current_highest_bet=game_round.current_highest_bet,
        minimum_raise_amount=game_round.minimum_raise_amount,
        is_action_closed=game_round.is_action_closed,
        players=[round_player_to_response(p) for p in (players or [])],
        payouts=[payout_to_response(p) for p in (payouts or [])],
        created_at=game_round.created_at,
        completed_at=game_round.completed_at,
    )

def ledger_entry_to_response(entry: HandLedgerEntry) -> LedgerEntryResponse:
    return LedgerEntryResponse(
        entry_id=entry.entry_id,
        round_id=entry.round_id,
        entry_type=entry.entry_type,
        player_id=entry.player_id,
        amount=entry.amount,
        detail=entry.detail,
        original_entry_id=entry.original_entry_id,
        dealer_id=entry.dealer_id,
        created_at=entry.created_at,
    )

def hand_state_to_response(round_id: str, state: HandState) -> HandStateResponse:
    return HandStateResponse(
        round_id=round_id,
        pot_total=state.pot_total,
        is_completed=state.is_completed,
        is_reopened=state.is_reopened,
        reversed_entry_ids=sorted(state.reversed_entry_ids),
        payout_corrections=state.payout_corrections,
        entry_count=state.entry_count,
        players=[
            PlayerSnapshotResponse(
                player_id=ps.player_id,
                stack_adjustment=ps.stack_adjustment,
                total_committed=ps.total_committed,
                total_won=ps.total_won,
            )
            for ps in state.players.values()
        ],
    )
