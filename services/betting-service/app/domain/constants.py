from __future__ import annotations

from enum import StrEnum


class BetAction(StrEnum):
    FOLD = "FOLD"
    CHECK = "CHECK"
    CALL = "CALL"
    RAISE = "RAISE"
    ALL_IN = "ALL_IN"


VALID_BET_ACTIONS = frozenset(action.value for action in BetAction)


class BetEventType(StrEnum):
    PLACED = "bet.placed"
    POT_UPDATED = "bet.pot_updated"


class GameEventType(StrEnum):
    ROUND_STARTED = "game.round_started"
    ROUND_COMPLETED = "game.round_completed"


class EventKey(StrEnum):
    EVENT_ID = "event_id"
    EVENT_TYPE = "event_type"
    DATA = "data"


class DataKey(StrEnum):
    BET_ID = "bet_id"
    ROUND_ID = "round_id"
    PLAYER_ID = "player_id"
    ACTION = "action"
    AMOUNT = "amount"
    POT_AMOUNT = "pot_amount"
    GAME_ID = "game_id"


class TableName(StrEnum):
    BETS = "bets"


class ErrorMessage(StrEnum):
    BET_NOT_FOUND = "Bet not found"
    INVALID_ACTION = "Invalid bet action"
    PLAYER_ALREADY_FOLDED = "Player has already folded this round"
    RAISE_AMOUNT_TOO_LOW = "Raise amount must be greater than 0"


class ResponseMessage(StrEnum):
    DELETED = "deleted"
