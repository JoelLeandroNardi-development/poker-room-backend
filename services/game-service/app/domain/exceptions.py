from __future__ import annotations

class DomainError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)

class RoundNotActive(DomainError):
    pass

class ActionClosed(DomainError):
    pass

class RoundNotCompleted(DomainError):
    pass

class RoundAlreadyActive(DomainError):
    pass

class AlreadyAtShowdown(DomainError):
    pass

class PlayerNotInHand(DomainError):
    pass

class PlayerAlreadyFolded(DomainError):
    pass

class PlayerAlreadyAllIn(DomainError):
    pass

class NotYourTurn(DomainError):
    pass

class IllegalAction(DomainError):
    pass

class CheckNotAllowed(DomainError):
    pass

class CallNotAllowed(DomainError):
    pass

class BetNotAllowed(DomainError):
    pass

class RaiseNotAllowed(DomainError):
    pass

class RaiseBelowMinimum(DomainError):
    pass

class AmountExceedsStack(DomainError):
    pass

class InvalidAmount(DomainError):
    pass

class GameNotActive(DomainError):
    pass

class GameAlreadyExists(DomainError):
    pass

class NotFound(DomainError):
    pass

class LedgerEntryNotFound(DomainError):
    pass

class EntryAlreadyReversed(DomainError):
    pass

class CannotReverseCorrection(DomainError):
    pass

class PayoutExceedsPot(DomainError):
    pass

class PayoutEmpty(DomainError):
    pass

class PayoutMismatch(DomainError):
    pass

class StaleStateError(DomainError):
    pass

class DuplicateActionError(DomainError):
    pass

class IdempotencyConflict(DomainError):
    pass

class TableRuntimeError(DomainError):
    pass

class NotEnoughActivePlayers(TableRuntimeError):
    pass

class SessionNotPaused(TableRuntimeError):
    pass

class SeatNotActive(TableRuntimeError):
    pass

class SeatNotSittingOut(TableRuntimeError):
    pass

class SeatNotFound(TableRuntimeError):
    pass