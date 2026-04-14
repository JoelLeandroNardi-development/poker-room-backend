from __future__ import annotations

from enum import StrEnum


class GameStatus(StrEnum):
    WAITING = "WAITING"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    FINISHED = "FINISHED"


class RoundStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"


class GameEventType(StrEnum):
    STARTED = "game.started"
    ROUND_STARTED = "game.round_started"
    ROUND_COMPLETED = "game.round_completed"
    BLINDS_INCREASED = "game.blinds_increased"
    FINISHED = "game.finished"


class RoomEventType(StrEnum):
    CREATED = "room.created"
    PLAYER_JOINED = "room.player_joined"
    PLAYER_ELIMINATED = "room.player_eliminated"


class BetEventType(StrEnum):
    POT_UPDATED = "bet.pot_updated"


class EventKey(StrEnum):
    EVENT_ID = "event_id"
    EVENT_TYPE = "event_type"
    DATA = "data"


class DataKey(StrEnum):
    GAME_ID = "game_id"
    ROOM_ID = "room_id"
    ROUND_ID = "round_id"
    ROUND_NUMBER = "round_number"
    DEALER_SEAT = "dealer_seat"
    SMALL_BLIND_SEAT = "small_blind_seat"
    BIG_BLIND_SEAT = "big_blind_seat"
    SMALL_BLIND_AMOUNT = "small_blind_amount"
    BIG_BLIND_AMOUNT = "big_blind_amount"
    ANTE_AMOUNT = "ante_amount"
    BLIND_LEVEL = "blind_level"
    WINNER_PLAYER_ID = "winner_player_id"
    POT_AMOUNT = "pot_amount"
    STATUS = "status"


class TableName(StrEnum):
    GAMES = "games"
    ROUNDS = "rounds"


class ErrorMessage(StrEnum):
    GAME_NOT_FOUND = "Game not found"
    ROUND_NOT_FOUND = "Round not found"
    GAME_NOT_ACTIVE = "Game is not in ACTIVE status"
    ROUND_NOT_ACTIVE = "Round is not in ACTIVE status"
    NO_ACTIVE_ROUND = "No active round found"
    GAME_ALREADY_EXISTS = "An active game already exists for this room"
    NO_BLIND_LEVELS = "No blind levels configured for this room"
    MAX_BLIND_LEVEL_REACHED = "Already at the maximum blind level"


class ResponseMessage(StrEnum):
    DELETED = "deleted"
