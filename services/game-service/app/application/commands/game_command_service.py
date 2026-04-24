from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from ..action_helpers import append_ledger_entry
from ..mappers import (
    game_to_response, round_to_response, payout_to_response, round_player_to_response,
)
from ...domain.constants import (
    DataKey, ErrorMessage, GameEventType, GameStatus, LedgerEntryType,
    RoundStatus, Street, StreetAdvanceAction,
)
from ...domain.events import build_event
from ...domain.exceptions import (
    AlreadyAtShowdown, GameAlreadyExists, GameNotActive, NotFound,
    PayoutEmpty, PayoutExceedsPot, PayoutMismatch, RoundNotActive,
    RoundStartNotAllowed,
)
from ...domain.models import Game, OutboxEvent, Round, RoundPlayer, RoundPayout
from ...domain.engine.payout_validation import validate_payouts_against_side_pots
from ...domain.schemas import (
    GameResponse, RoundResponse, StartGame, StartRoundRequest, DeclareWinner, DeclareWinnerResponse, ResolveHandRequest, 
    ResolveHandResponse, AdvanceBlindsResponse, AdvanceStreetResponse, EndGameResponse,
)
from ...domain.engine.blind_posting import SeatPlayer, post_blinds_and_antes
from ...domain.engine.positions import assign_positions, rotate_positions
from ...domain.integration.room_adapter import BlindLevelConfig, RoomConfig
from ...domain.rules import NO_LIMIT_HOLDEM
from ...domain.engine.street_progression import PlayerSeat, evaluate_street_end
from ...infrastructure.repositories.game_repository import fetch_or_raise, get_active_game_for_room
from ...infrastructure.repositories.round_repository import get_active_round, count_rounds, get_round_players
from ...infrastructure.room_config import (
    fetch_room_config_http, load_room_snapshot, save_room_snapshot,
    mark_room_active_http, mark_room_finished_http,
    sync_room_snapshot_players_from_round,
)
from shared.core.outbox.helpers import add_outbox_event
from shared.core.db.session import atomic

class GameCommandService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def start_game(self, data: StartGame) -> GameResponse:
        existing = await get_active_game_for_room(self.db, data.room_id)
        if existing:
            raise GameAlreadyExists(ErrorMessage.GAME_ALREADY_EXISTS)

        room_config = await fetch_room_config_http(data.room_id)

        if not room_config.blind_levels:
            raise NotFound(ErrorMessage.NO_BLIND_LEVELS)

        active_seats = room_config.active_seats

        if len(active_seats) < 2:
            raise GameNotActive(ErrorMessage.ACTIVE_PLAYERS_REQUIRED)

        dealer_seat, sb_seat, bb_seat = self._assign_positions(
            active_seats, room_config.starting_dealer_seat,
        )

        game_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        async with atomic(self.db):
            game = Game(
                game_id=game_id,
                room_id=data.room_id,
                status=GameStatus.ACTIVE,
                current_blind_level=1,
                level_started_at=now,
                current_dealer_seat=dealer_seat,
                current_small_blind_seat=sb_seat,
                current_big_blind_seat=bb_seat,
            )
            self.db.add(game)

            await save_room_snapshot(self.db, game_id, room_config)
            await mark_room_active_http(data.room_id)

            event = build_event(
                GameEventType.STARTED,
                {
                    DataKey.GAME_ID: game_id,
                    DataKey.ROOM_ID: data.room_id,
                    DataKey.DEALER_SEAT: dealer_seat,
                    DataKey.SMALL_BLIND_SEAT: sb_seat,
                    DataKey.BIG_BLIND_SEAT: bb_seat,
                    DataKey.BLIND_LEVEL: 1,
                },
            )
            add_outbox_event(self.db, OutboxEvent, event)

        await self.db.commit()
        await self.db.refresh(game)

        return game_to_response(game)

    async def start_round(self, game_id: str, data: StartRoundRequest) -> RoundResponse:
        game = await fetch_or_raise(
            self.db, Game,
            filter_column=Game.game_id,
            filter_value=game_id,
            detail=ErrorMessage.GAME_NOT_FOUND,
        )

        if game.status != GameStatus.ACTIVE:
            raise GameNotActive(ErrorMessage.GAME_NOT_ACTIVE)

        existing_active = await get_active_round(self.db, game_id)
        if existing_active:
            raise GameNotActive(ErrorMessage.ROUND_ALREADY_ACTIVE)

        round_count = await count_rounds(self.db, game_id)
        round_number = round_count + 1

        room_config = await load_room_snapshot(self.db, game_id)
        current_level = room_config.blind_level(game.current_blind_level)
        if current_level is None and room_config.blind_levels:
            current_level = room_config.blind_levels[0]

        if not current_level:
            raise NotFound(ErrorMessage.NO_BLIND_LEVELS)

        self._require_round_start_authorized(game, room_config, data)

        round_id = str(uuid.uuid4())

        small_blind = current_level.small_blind
        big_blind = current_level.big_blind
        ante = self._ante_amount(room_config, current_level)

        active_players = room_config.active_players

        active_seats = [p.seat_number for p in active_players]
        bb_seat = game.current_big_blind_seat
        if bb_seat in active_seats:
            bb_idx = active_seats.index(bb_seat)
            first_to_act_idx = (bb_idx + 1) % len(active_seats)
        else:
            first_to_act_idx = 0

        first_to_act_seat = active_seats[first_to_act_idx]

        seat_players = [
            SeatPlayer(
                player_id=p.player_id,
                seat_number=p.seat_number,
                stack=p.chip_count,
            )
            for p in active_players
        ]

        posting = post_blinds_and_antes(
            players=seat_players,
            small_blind_seat=game.current_small_blind_seat,
            big_blind_seat=game.current_big_blind_seat,
            small_blind_amount=small_blind,
            big_blind_amount=big_blind,
            ante_amount=ante,
        )

        async with atomic(self.db):
            game_round = Round(
                round_id=round_id,
                game_id=game_id,
                round_number=round_number,
                dealer_seat=game.current_dealer_seat,
                small_blind_seat=game.current_small_blind_seat,
                big_blind_seat=game.current_big_blind_seat,
                small_blind_amount=small_blind,
                big_blind_amount=big_blind,
                ante_amount=ante,
                status=RoundStatus.ACTIVE,
                pot_amount=0,
                street=Street.PRE_FLOP,
                current_highest_bet=big_blind,
                minimum_raise_amount=big_blind,
                is_action_closed=False,
                engine_version=NO_LIMIT_HOLDEM.engine_version,
            )
            self.db.add(game_round)

            round_players: list[RoundPlayer] = []
            first_acting_player_id: str | None = None

            for pp in posting.players:
                rp = RoundPlayer(
                    round_id=round_id,
                    player_id=pp.player_id,
                    seat_number=pp.seat_number,
                    stack_remaining=pp.stack_remaining,
                    committed_this_street=pp.committed_this_street,
                    committed_this_hand=pp.committed_this_hand,
                    has_folded=False,
                    is_all_in=pp.is_all_in,
                    is_active_in_hand=True,
                )
                round_players.append(rp)

                if pp.seat_number == first_to_act_seat:
                    first_acting_player_id = pp.player_id

            game_round.acting_player_id = first_acting_player_id
            game_round.pot_amount = posting.pot_total
            game_round.current_highest_bet = posting.current_highest_bet

            # Persist the parent round before adding rows that reference round_id.
            await self.db.flush()
            self.db.add_all(round_players)

            for pp in posting.players:
                if pp.committed_this_hand <= 0:
                    continue
                if pp.seat_number == game.current_small_blind_seat:
                    entry_type = LedgerEntryType.BLIND_POSTED
                    detail = {"role": "SB"}
                elif pp.seat_number == game.current_big_blind_seat:
                    entry_type = LedgerEntryType.BLIND_POSTED
                    detail = {"role": "BB"}
                else:
                    entry_type = LedgerEntryType.ANTE_POSTED
                    detail = {}
                append_ledger_entry(
                    self.db,
                    round_id=round_id,
                    entry_type=entry_type,
                    player_id=pp.player_id,
                    amount=pp.committed_this_hand,
                    detail=detail if detail else None,
                )

            event = build_event(
                GameEventType.ROUND_STARTED,
                {
                    DataKey.GAME_ID: game_id,
                    DataKey.ROOM_ID: game.room_id,
                    DataKey.ROUND_ID: round_id,
                    DataKey.ROUND_NUMBER: round_number,
                    DataKey.DEALER_SEAT: game.current_dealer_seat,
                    DataKey.SMALL_BLIND_SEAT: game.current_small_blind_seat,
                    DataKey.BIG_BLIND_SEAT: game.current_big_blind_seat,
                    DataKey.SMALL_BLIND_AMOUNT: small_blind,
                    DataKey.BIG_BLIND_AMOUNT: big_blind,
                    DataKey.ANTE_AMOUNT: ante,
                },
            )
            add_outbox_event(self.db, OutboxEvent, event)

        await self.db.commit()
        await self.db.refresh(game_round)

        return round_to_response(game_round, round_players)

    async def resolve_hand(self, round_id: str, data: ResolveHandRequest) -> ResolveHandResponse:
        game_round = await fetch_or_raise(
            self.db, Round,
            filter_column=Round.round_id,
            filter_value=round_id,
            detail=ErrorMessage.ROUND_NOT_FOUND,
        )

        if game_round.status != RoundStatus.ACTIVE:
            raise RoundNotActive(ErrorMessage.ROUND_NOT_ACTIVE)

        if not data.payouts:
            raise PayoutEmpty(ErrorMessage.PAYOUT_EMPTY)

        total_paid = sum(
            w.amount for pot in data.payouts for w in pot.winners
        )
        if total_paid > game_round.pot_amount:
            raise PayoutExceedsPot(ErrorMessage.PAYOUT_TOTAL_EXCEEDS_POT)

        for pot in data.payouts:
            pot_winner_total = sum(w.amount for w in pot.winners)
            if pot_winner_total != pot.amount:
                raise PayoutMismatch(
                    f"Pot {pot.pot_index} winners total {pot_winner_total} != pot amount {pot.amount}"
                )

        round_players = await get_round_players(self.db, round_id)
        player_map = {rp.player_id: rp for rp in round_players}

        payout_dicts = [
            {
                "pot_index": pot.pot_index,
                "amount": pot.amount,
                "winners": [
                    {"player_id": w.player_id, "amount": w.amount}
                    for w in pot.winners
                ],
            }
            for pot in data.payouts
        ]
        validate_payouts_against_side_pots(
            round_players, payout_dicts, game_round.pot_amount,
        )

        game = await fetch_or_raise(
            self.db, Game,
            filter_column=Game.game_id,
            filter_value=game_round.game_id,
            detail=ErrorMessage.GAME_NOT_FOUND,
        )

        payout_summary = [
            {
                "pot_index": pot.pot_index,
                "pot_type": pot.pot_type,
                "amount": pot.amount,
                "winners": [
                    {"player_id": w.player_id, "amount": w.amount}
                    for w in pot.winners
                ],
            }
            for pot in data.payouts
        ]

        payout_rows: list[RoundPayout] = []

        async with atomic(self.db):
            for pot in data.payouts:
                for winner in pot.winners:
                    row = RoundPayout(
                        round_id=round_id,
                        pot_index=pot.pot_index,
                        pot_type=pot.pot_type,
                        player_id=winner.player_id,
                        amount=winner.amount,
                    )
                    self.db.add(row)
                    payout_rows.append(row)

                    rp = player_map.get(winner.player_id)
                    if rp is not None:
                        rp.stack_remaining += winner.amount

                    append_ledger_entry(
                        self.db,
                        round_id=round_id,
                        entry_type=LedgerEntryType.PAYOUT_AWARDED,
                        player_id=winner.player_id,
                        amount=winner.amount,
                        detail={
                            "pot_index": pot.pot_index,
                            "pot_type": pot.pot_type,
                        },
                    )

            game_round.status = RoundStatus.COMPLETED
            game_round.street = Street.SHOWDOWN
            game_round.acting_player_id = None
            game_round.is_action_closed = True
            game_round.completed_at = datetime.now(timezone.utc)
            game_round.state_version = (game_round.state_version or 1) + 1

            append_ledger_entry(
                self.db,
                round_id=round_id,
                entry_type=LedgerEntryType.ROUND_COMPLETED,
                player_id=None,
                amount=game_round.pot_amount,
            )

            active_seats = await sync_room_snapshot_players_from_round(
                self.db,
                game_id=game_round.game_id,
                round_players=round_players,
            )

            if len(active_seats) >= 2:
                dealer_seat, sb_seat, bb_seat = self._rotate_positions(
                    active_seats, game.current_dealer_seat
                )
                game.current_dealer_seat = dealer_seat
                game.current_small_blind_seat = sb_seat
                game.current_big_blind_seat = bb_seat
            else:
                game.status = GameStatus.FINISHED

            event = build_event(
                GameEventType.ROUND_COMPLETED,
                {
                    DataKey.GAME_ID: game_round.game_id,
                    DataKey.ROOM_ID: game.room_id,
                    DataKey.ROUND_ID: round_id,
                    DataKey.POT_AMOUNT: game_round.pot_amount,
                    DataKey.PAYOUTS: payout_summary,
                },
            )
            add_outbox_event(self.db, OutboxEvent, event)

            if game.status == GameStatus.FINISHED:
                finished_event = build_event(
                    GameEventType.FINISHED,
                    {
                        DataKey.GAME_ID: game.game_id,
                        DataKey.ROOM_ID: game.room_id,
                        DataKey.STATUS: GameStatus.FINISHED,
                    },
                )
                add_outbox_event(self.db, OutboxEvent, finished_event)

        await self.db.commit()
        await self.db.refresh(game_round)

        return ResolveHandResponse(
            round_id=game_round.round_id,
            status=game_round.status,
            pot_amount=game_round.pot_amount,
            payouts=[payout_to_response(p) for p in payout_rows],
        )

    async def advance_street(self, round_id: str) -> AdvanceStreetResponse:
        game_round = await fetch_or_raise(
            self.db, Round,
            filter_column=Round.round_id,
            filter_value=round_id,
            detail=ErrorMessage.ROUND_NOT_FOUND,
        )

        if game_round.status != RoundStatus.ACTIVE:
            raise RoundNotActive(ErrorMessage.ROUND_NOT_ACTIVE)

        if game_round.street == Street.SHOWDOWN:
            raise AlreadyAtShowdown(ErrorMessage.ALREADY_AT_SHOWDOWN)

        round_players = await get_round_players(self.db, round_id)
        player_seats = [
            PlayerSeat(
                player_id=rp.player_id,
                seat_number=rp.seat_number,
                has_folded=rp.has_folded,
                is_all_in=rp.is_all_in,
                is_active_in_hand=rp.is_active_in_hand,
            )
            for rp in round_players
        ]

        result = evaluate_street_end(
            current_street=game_round.street,
            dealer_seat=game_round.dealer_seat,
            big_blind_seat=game_round.big_blind_seat,
            players=player_seats,
        )

        async with atomic(self.db):
            if result.action == StreetAdvanceAction.SETTLE_HAND:
                game_round.is_action_closed = True
                game_round.acting_player_id = None

            elif result.action == StreetAdvanceAction.SHOWDOWN:
                game_round.street = Street.SHOWDOWN
                game_round.is_action_closed = True
                game_round.acting_player_id = None
                game_round.current_highest_bet = 0
                for rp in round_players:
                    rp.committed_this_street = 0

            elif result.action == StreetAdvanceAction.NEXT_STREET:
                game_round.street = result.next_street
                game_round.current_highest_bet = 0
                game_round.minimum_raise_amount = game_round.big_blind_amount
                game_round.acting_player_id = result.acting_player_id
                game_round.is_action_closed = False
                game_round.last_aggressor_seat = None
                for rp in round_players:
                    rp.committed_this_street = 0

            game_round.state_version = (game_round.state_version or 1) + 1

            event = build_event(
                GameEventType.STREET_ADVANCED,
                {
                    DataKey.GAME_ID: game_round.game_id,
                    DataKey.ROUND_ID: round_id,
                    DataKey.STATUS: result.action,
                },
            )
            add_outbox_event(self.db, OutboxEvent, event)

        await self.db.commit()
        await self.db.refresh(game_round)

        return AdvanceStreetResponse(
            action=result.action,
            round_id=game_round.round_id,
            game_id=game_round.game_id,
            street=game_round.street,
            acting_player_id=game_round.acting_player_id,
            current_highest_bet=game_round.current_highest_bet,
            minimum_raise_amount=game_round.minimum_raise_amount,
            is_action_closed=game_round.is_action_closed,
            winning_player_id=result.winning_player_id,
            players=[round_player_to_response(rp) for rp in round_players],
        )

    async def declare_winner(self, round_id: str, data: DeclareWinner) -> DeclareWinnerResponse:
        game_round = await fetch_or_raise(
            self.db, Round,
            filter_column=Round.round_id,
            filter_value=round_id,
            detail=ErrorMessage.ROUND_NOT_FOUND,
        )

        request = ResolveHandRequest(
            payouts=[{
                "pot_index": 0,
                "pot_type": "main",
                "amount": game_round.pot_amount,
                "winners": [{"player_id": data.winner_player_id, "amount": game_round.pot_amount}],
            }]
        )
        result = await self.resolve_hand(round_id, request)
        return DeclareWinnerResponse(
            round_id=result.round_id,
            winner_player_id=data.winner_player_id,
            pot_amount=result.pot_amount,
            status=result.status,
        )

    async def advance_blinds(self, game_id: str) -> AdvanceBlindsResponse:
        game = await fetch_or_raise(
            self.db, Game,
            filter_column=Game.game_id,
            filter_value=game_id,
            detail=ErrorMessage.GAME_NOT_FOUND,
        )

        if game.status != GameStatus.ACTIVE:
            raise GameNotActive(ErrorMessage.GAME_NOT_ACTIVE)

        room_config = await load_room_snapshot(self.db, game_id)
        max_level = max((bl.level for bl in room_config.blind_levels), default=1)

        if game.current_blind_level >= max_level:
            raise GameNotActive(ErrorMessage.MAX_BLIND_LEVEL_REACHED)

        new_level_num = game.current_blind_level + 1
        new_level = room_config.blind_level(new_level_num)
        if not new_level:
            raise GameNotActive(ErrorMessage.MAX_BLIND_LEVEL_REACHED)

        async with atomic(self.db):
            game.current_blind_level = new_level_num
            game.level_started_at = datetime.now(timezone.utc)

            event = build_event(
                GameEventType.BLINDS_INCREASED,
                {
                    DataKey.GAME_ID: game_id,
                    DataKey.ROOM_ID: game.room_id,
                    DataKey.BLIND_LEVEL: new_level_num,
                    DataKey.SMALL_BLIND_AMOUNT: new_level.small_blind,
                    DataKey.BIG_BLIND_AMOUNT: new_level.big_blind,
                    DataKey.ANTE_AMOUNT: self._ante_amount(room_config, new_level),
                },
            )
            add_outbox_event(self.db, OutboxEvent, event)

        await self.db.commit()

        return AdvanceBlindsResponse(
            game_id=game_id,
            new_blind_level=new_level_num,
            small_blind=new_level.small_blind,
            big_blind=new_level.big_blind,
            ante=self._ante_amount(room_config, new_level),
        )

    async def end_game(self, game_id: str) -> EndGameResponse:
        game = await fetch_or_raise(
            self.db, Game,
            filter_column=Game.game_id,
            filter_value=game_id,
            detail=ErrorMessage.GAME_NOT_FOUND,
        )

        async with atomic(self.db):
            game.status = GameStatus.FINISHED
            await mark_room_finished_http(game.room_id)

            event = build_event(
                GameEventType.FINISHED,
                {
                    DataKey.GAME_ID: game_id,
                    DataKey.ROOM_ID: game.room_id,
                    DataKey.STATUS: GameStatus.FINISHED,
                },
            )
            add_outbox_event(self.db, OutboxEvent, event)

        await self.db.commit()

        return EndGameResponse(game_id=game_id, status=GameStatus.FINISHED)

    @staticmethod
    def _assign_positions(active_seats: list[int], starting_dealer: int) -> tuple[int, int, int]:
        return assign_positions(active_seats, starting_dealer)

    @staticmethod
    def _rotate_positions(active_seats: list[int], current_dealer: int) -> tuple[int, int, int]:
        return rotate_positions(active_seats, current_dealer)

    @staticmethod
    def _ante_amount(room_config: RoomConfig, blind_level: BlindLevelConfig) -> int:
        return blind_level.ante if room_config.antes_enabled else 0

    @staticmethod
    def _require_round_start_authorized(
        game: Game,
        room_config: RoomConfig,
        data: StartRoundRequest,
    ) -> None:
        if data.started_by_controller:
            return

        button_seat = game.current_dealer_seat
        button_player = next(
            (player for player in room_config.active_players if player.seat_number == button_seat),
            None,
        )
        if button_player and data.started_by_player_id == button_player.player_id:
            return

        raise RoundStartNotAllowed(ErrorMessage.ROUND_START_NOT_ALLOWED)