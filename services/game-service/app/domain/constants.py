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

class Street(StrEnum):
    PRE_FLOP = "PRE_FLOP"
    FLOP = "FLOP"
    TURN = "TURN"
    RIVER = "RIVER"
    SHOWDOWN = "SHOWDOWN"

class StreetAdvanceAction(StrEnum):
    NEXT_STREET = "NEXT_STREET"
    SETTLE_HAND = "SETTLE_HAND"
    SHOWDOWN = "SHOWDOWN"

class LedgerEntryType(StrEnum):
    BLIND_POSTED = "BLIND_POSTED"
    ANTE_POSTED = "ANTE_POSTED"
    BET_PLACED = "BET_PLACED"
    STREET_DEALT = "STREET_DEALT"
    PAYOUT_AWARDED = "PAYOUT_AWARDED"
    ROUND_COMPLETED = "ROUND_COMPLETED"
    ACTION_REVERSED = "ACTION_REVERSED"
    STACK_ADJUSTED = "STACK_ADJUSTED"
    HAND_REOPENED = "HAND_REOPENED"
    PAYOUT_CORRECTED = "PAYOUT_CORRECTED"

CORRECTION_ENTRY_TYPES = frozenset({
    LedgerEntryType.ACTION_REVERSED,
    LedgerEntryType.STACK_ADJUSTED,
    LedgerEntryType.HAND_REOPENED,
    LedgerEntryType.PAYOUT_CORRECTED,
})

class BetAction(StrEnum):
    FOLD = "FOLD"
    CHECK = "CHECK"
    CALL = "CALL"
    BET = "BET"
    RAISE = "RAISE"
    ALL_IN = "ALL_IN"

VALID_BET_ACTIONS = frozenset(action.value for action in BetAction)

class GameEventType(StrEnum):
    STARTED = "game.started"
    ROUND_STARTED = "game.round_started"
    ROUND_COMPLETED = "game.round_completed"
    STREET_ADVANCED = "game.street_advanced"
    BLINDS_INCREASED = "game.blinds_increased"
    CORRECTION_APPLIED = "game.correction_applied"
    BET_PLACED = "bet.placed"
    FINISHED = "game.finished"

class EventKey(StrEnum):
    EVENT_ID = "event_id"
    EVENT_TYPE = "event_type"
    DATA = "data"

class DataKey(StrEnum):
    GAME_ID = "game_id"
    ROOM_ID = "room_id"
    ROUND_ID = "round_id"
    PLAYER_ID = "player_id"
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
    PAYOUTS = "payouts"
    STATUS = "status"
    BET_ID = "bet_id"
    ACTION = "action"
    AMOUNT = "amount"

class TableName(StrEnum):
    GAMES = "games"
    ROUNDS = "rounds"
    ROUND_PLAYERS = "round_players"
    ROUND_PAYOUTS = "round_payouts"
    BETS = "bets"
    HAND_LEDGER_ENTRIES = "hand_ledger_entries"
    ROOM_SNAPSHOTS = "room_snapshots"
    ROOM_SNAPSHOT_PLAYERS = "room_snapshot_players"
    ROOM_SNAPSHOT_BLIND_LEVELS = "room_snapshot_blind_levels"

class ErrorMessage(StrEnum):
    GAME_NOT_FOUND = "Game not found"
    ROOM_NOT_FOUND = "Room not found"
    ROOM_SNAPSHOT_NOT_FOUND = "Room snapshot not found for game {game_id}"
    ROUND_NOT_FOUND = "Round not found"
    GAME_NOT_ACTIVE = "Game is not in ACTIVE status"
    GAME_NOT_PAUSED = "Game is not paused"
    ROUND_NOT_ACTIVE = "Round is not in ACTIVE status"
    NO_ACTIVE_ROUND = "No active round found"
    GAME_ALREADY_EXISTS = "An active game already exists for this room"
    NO_BLIND_LEVELS = "No blind levels configured for this room"
    ACTIVE_PLAYERS_REQUIRED = "At least 2 active players are required"
    MAX_BLIND_LEVEL_REACHED = "Already at the maximum blind level"
    PAYOUT_TOTAL_EXCEEDS_POT = "Total payouts exceed pot amount"
    PAYOUT_EMPTY = "At least one pot payout is required"
    ALREADY_AT_SHOWDOWN = "Cannot advance street: round is already at showdown"
    LEDGER_ENTRY_NOT_FOUND = "Ledger entry not found"
    ENTRY_ALREADY_REVERSED = "This ledger entry has already been reversed"
    CANNOT_REVERSE_CORRECTION = "Cannot reverse a correction entry"
    ROUND_NOT_COMPLETED = "Round must be completed before applying this correction"
    ROUND_ALREADY_ACTIVE = "Round is already active"
    BET_NOT_FOUND = "Bet not found"
    INVALID_ACTION = "Invalid bet action"
    PLAYER_ALREADY_FOLDED = "Player has already folded this round"
    RAISE_AMOUNT_TOO_LOW = "Raise amount must be greater than 0"
    ACTION_CLOSED = "Betting action is closed for this street"
    NOT_YOUR_TURN = "It is not your turn to act"
    PLAYER_NOT_IN_HAND = "Player is not in this hand"
    PLAYER_ALL_IN = "Player is already all-in"
    CHECK_NOT_ALLOWED = "Cannot check when there is a bet to call"
    CALL_NOT_ALLOWED = "Nothing to call - use check instead"
    BET_NOT_ALLOWED = "Cannot bet - there is already a bet on this street; use raise"
    RAISE_NOT_ALLOWED = "Cannot raise - no previous bet to raise; use bet"
    RAISE_BELOW_MINIMUM = "Raise amount is below the minimum raise"
    AMOUNT_EXCEEDS_STACK = "Bet amount exceeds remaining stack"
    BET_AMOUNT_TOO_LOW = "Bet amount must be greater than 0"
    BET_BELOW_MINIMUM = "Bet amount is below the minimum"
    RAISE_EXCEEDS_STACK = "Raise amount exceeds remaining stack"
    NOT_ENOUGH_ACTIVE_PLAYERS = "Need at least 2 active players"
    SESSION_NOT_PAUSED = "Can only resume a paused session"
    SEAT_NOT_ACTIVE = "Seat {seat_number} is not active"
    SEAT_NOT_SITTING_OUT = "Seat {seat_number} is not sitting out"
    SEAT_NOT_FOUND = "Seat {seat_number} not found"

class ResponseMessage(StrEnum):
    DELETED = "deleted"
