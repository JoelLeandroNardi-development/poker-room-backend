from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..mappers import game_to_response, round_to_response
from ...domain.constants import (
    DataKey, ErrorMessage, GameEventType, GameStatus, RoundStatus,
)
from ...domain.events import build_event
from ...domain.models import Game, OutboxEvent, Round
from ...domain.schemas import (
    GameResponse, RoundResponse, StartGame,
    DeclareWinner, DeclareWinnerResponse,
    AdvanceBlindsResponse, EndGameResponse,
)
from ...infrastructure.repository import (
    count_rounds, get_active_game_for_room, get_active_round, get_latest_round,
)
from shared.core.outbox.helpers import add_outbox_event
from shared.core.db.crud import fetch_or_404

ROOM_SERVICE_URL = os.getenv("ROOM_SERVICE_URL", "http://room-service:8000")


class GameCommandService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _fetch_room_config(self, room_id: str) -> dict:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{ROOM_SERVICE_URL}/rooms/{room_id}")
            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail="Room not found")
            resp.raise_for_status()
            return resp.json()

    async def start_game(self, data: StartGame) -> GameResponse:
        existing = await get_active_game_for_room(self.db, data.room_id)
        if existing:
            raise HTTPException(status_code=409, detail=ErrorMessage.GAME_ALREADY_EXISTS)

        room_config = await self._fetch_room_config(data.room_id)
        room_data = room_config["room"]
        blind_levels = room_config.get("blind_levels", [])
        players = room_config.get("players", [])

        if not blind_levels:
            raise HTTPException(status_code=400, detail=ErrorMessage.NO_BLIND_LEVELS)

        starting_dealer_seat = room_config.get("starting_dealer_seat", 1)
        active_seats = sorted([p["seat_number"] for p in players if p["is_active"] and not p["is_eliminated"]])

        if len(active_seats) < 2:
            raise HTTPException(status_code=400, detail="At least 2 active players are required")

        dealer_seat, sb_seat, bb_seat = self._assign_positions(active_seats, starting_dealer_seat)

        game_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

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

    async def start_round(self, game_id: str) -> RoundResponse:
        game = await fetch_or_404(
            self.db, Game,
            filter_column=Game.game_id,
            filter_value=game_id,
            detail=ErrorMessage.GAME_NOT_FOUND,
        )

        if game.status != GameStatus.ACTIVE:
            raise HTTPException(status_code=400, detail=ErrorMessage.GAME_NOT_ACTIVE)

        existing_active = await get_active_round(self.db, game_id)
        if existing_active:
            raise HTTPException(status_code=409, detail="A round is already active")

        round_count = await count_rounds(self.db, game_id)
        round_number = round_count + 1

        room_config = await self._fetch_room_config(game.room_id)
        blind_levels = room_config.get("blind_levels", [])
        current_level = next(
            (bl for bl in blind_levels if bl["level"] == game.current_blind_level),
            blind_levels[0] if blind_levels else None,
        )

        if not current_level:
            raise HTTPException(status_code=400, detail=ErrorMessage.NO_BLIND_LEVELS)

        round_id = str(uuid.uuid4())

        game_round = Round(
            round_id=round_id,
            game_id=game_id,
            round_number=round_number,
            dealer_seat=game.current_dealer_seat,
            small_blind_seat=game.current_small_blind_seat,
            big_blind_seat=game.current_big_blind_seat,
            small_blind_amount=current_level["small_blind"],
            big_blind_amount=current_level["big_blind"],
            ante_amount=current_level.get("ante", 0),
            status=RoundStatus.ACTIVE,
            pot_amount=0,
        )
        self.db.add(game_round)

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
                DataKey.SMALL_BLIND_AMOUNT: current_level["small_blind"],
                DataKey.BIG_BLIND_AMOUNT: current_level["big_blind"],
                DataKey.ANTE_AMOUNT: current_level.get("ante", 0),
            },
        )
        add_outbox_event(self.db, OutboxEvent, event)

        await self.db.commit()
        await self.db.refresh(game_round)

        return round_to_response(game_round)

    async def declare_winner(self, round_id: str, data: DeclareWinner) -> DeclareWinnerResponse:
        game_round = await fetch_or_404(
            self.db, Round,
            filter_column=Round.round_id,
            filter_value=round_id,
            detail=ErrorMessage.ROUND_NOT_FOUND,
        )

        if game_round.status != RoundStatus.ACTIVE:
            raise HTTPException(status_code=400, detail=ErrorMessage.ROUND_NOT_ACTIVE)

        game_round.winner_player_id = data.winner_player_id
        game_round.status = RoundStatus.COMPLETED
        game_round.completed_at = datetime.now(timezone.utc)

        game = await fetch_or_404(
            self.db, Game,
            filter_column=Game.game_id,
            filter_value=game_round.game_id,
            detail=ErrorMessage.GAME_NOT_FOUND,
        )

        room_config = await self._fetch_room_config(game.room_id)
        active_seats = sorted([
            p["seat_number"]
            for p in room_config.get("players", [])
            if p["is_active"] and not p["is_eliminated"]
        ])

        if len(active_seats) >= 2:
            dealer_seat, sb_seat, bb_seat = self._rotate_positions(
                active_seats, game.current_dealer_seat
            )
            game.current_dealer_seat = dealer_seat
            game.current_small_blind_seat = sb_seat
            game.current_big_blind_seat = bb_seat

        event = build_event(
            GameEventType.ROUND_COMPLETED,
            {
                DataKey.GAME_ID: game_round.game_id,
                DataKey.ROOM_ID: game.room_id,
                DataKey.ROUND_ID: round_id,
                DataKey.WINNER_PLAYER_ID: data.winner_player_id,
                DataKey.POT_AMOUNT: game_round.pot_amount,
            },
        )
        add_outbox_event(self.db, OutboxEvent, event)

        await self.db.commit()
        await self.db.refresh(game_round)

        return DeclareWinnerResponse(
            round_id=game_round.round_id,
            winner_player_id=game_round.winner_player_id,
            pot_amount=game_round.pot_amount,
            status=game_round.status,
        )

    async def advance_blinds(self, game_id: str) -> AdvanceBlindsResponse:
        game = await fetch_or_404(
            self.db, Game,
            filter_column=Game.game_id,
            filter_value=game_id,
            detail=ErrorMessage.GAME_NOT_FOUND,
        )

        if game.status != GameStatus.ACTIVE:
            raise HTTPException(status_code=400, detail=ErrorMessage.GAME_NOT_ACTIVE)

        room_config = await self._fetch_room_config(game.room_id)
        blind_levels = room_config.get("blind_levels", [])
        max_level = max((bl["level"] for bl in blind_levels), default=1)

        if game.current_blind_level >= max_level:
            raise HTTPException(status_code=400, detail=ErrorMessage.MAX_BLIND_LEVEL_REACHED)

        new_level_num = game.current_blind_level + 1
        new_level = next((bl for bl in blind_levels if bl["level"] == new_level_num), None)
        if not new_level:
            raise HTTPException(status_code=400, detail=ErrorMessage.MAX_BLIND_LEVEL_REACHED)

        game.current_blind_level = new_level_num
        game.level_started_at = datetime.now(timezone.utc)

        event = build_event(
            GameEventType.BLINDS_INCREASED,
            {
                DataKey.GAME_ID: game_id,
                DataKey.ROOM_ID: game.room_id,
                DataKey.BLIND_LEVEL: new_level_num,
                DataKey.SMALL_BLIND_AMOUNT: new_level["small_blind"],
                DataKey.BIG_BLIND_AMOUNT: new_level["big_blind"],
                DataKey.ANTE_AMOUNT: new_level.get("ante", 0),
            },
        )
        add_outbox_event(self.db, OutboxEvent, event)

        await self.db.commit()

        return AdvanceBlindsResponse(
            game_id=game_id,
            new_blind_level=new_level_num,
            small_blind=new_level["small_blind"],
            big_blind=new_level["big_blind"],
            ante=new_level.get("ante", 0),
        )

    async def end_game(self, game_id: str) -> EndGameResponse:
        game = await fetch_or_404(
            self.db, Game,
            filter_column=Game.game_id,
            filter_value=game_id,
            detail=ErrorMessage.GAME_NOT_FOUND,
        )

        game.status = GameStatus.FINISHED

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
        if len(active_seats) == 2:
            if starting_dealer in active_seats:
                dealer_idx = active_seats.index(starting_dealer)
            else:
                dealer_idx = 0
            sb_idx = dealer_idx
            bb_idx = (dealer_idx + 1) % len(active_seats)
            return active_seats[dealer_idx], active_seats[sb_idx], active_seats[bb_idx]

        if starting_dealer in active_seats:
            dealer_idx = active_seats.index(starting_dealer)
        else:
            dealer_idx = 0

        sb_idx = (dealer_idx + 1) % len(active_seats)
        bb_idx = (dealer_idx + 2) % len(active_seats)
        return active_seats[dealer_idx], active_seats[sb_idx], active_seats[bb_idx]

    @staticmethod
    def _rotate_positions(active_seats: list[int], current_dealer: int) -> tuple[int, int, int]:
        if current_dealer in active_seats:
            current_idx = active_seats.index(current_dealer)
            new_dealer_idx = (current_idx + 1) % len(active_seats)
        else:
            new_dealer_idx = 0

        if len(active_seats) == 2:
            sb_idx = new_dealer_idx
            bb_idx = (new_dealer_idx + 1) % len(active_seats)
        else:
            sb_idx = (new_dealer_idx + 1) % len(active_seats)
            bb_idx = (new_dealer_idx + 2) % len(active_seats)

        return active_seats[new_dealer_idx], active_seats[sb_idx], active_seats[bb_idx]
