"""Domain exceptions for the poker hand engine.

These exceptions carry structured error information without coupling
to any HTTP framework.  The API layer maps them to HTTP responses.
"""
from __future__ import annotations


class DomainError(Exception):
    """Base for all domain-layer errors."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


# ── Hand / round guards ─────────────────────────────────────────────

class RoundNotActive(DomainError):
    """The round is not in ACTIVE status."""


class ActionClosed(DomainError):
    """Betting action is closed for this street."""


class RoundNotCompleted(DomainError):
    """Round must be completed before this operation."""


class RoundAlreadyActive(DomainError):
    """Round is already active."""


class AlreadyAtShowdown(DomainError):
    """Cannot advance street: round is already at showdown."""


# ── Player guards ────────────────────────────────────────────────────

class PlayerNotInHand(DomainError):
    """Player is not participating in this hand."""


class PlayerAlreadyFolded(DomainError):
    """Player has already folded this round."""


class PlayerAlreadyAllIn(DomainError):
    """Player is already all-in."""


class NotYourTurn(DomainError):
    """It is not this player's turn to act."""


# ── Bet validation ───────────────────────────────────────────────────

class IllegalAction(DomainError):
    """Generic illegal betting action."""


class CheckNotAllowed(DomainError):
    """Cannot check when there is a bet to call."""


class CallNotAllowed(DomainError):
    """Nothing to call — use check instead."""


class BetNotAllowed(DomainError):
    """Cannot open a bet when there is already a bet on this street."""


class RaiseNotAllowed(DomainError):
    """Cannot raise when there is no previous bet to raise."""


class RaiseBelowMinimum(DomainError):
    """Raise amount is below the minimum raise."""


class AmountExceedsStack(DomainError):
    """Bet/raise amount exceeds remaining stack."""


class InvalidAmount(DomainError):
    """Amount must be greater than zero."""


# ── Game-level guards ────────────────────────────────────────────────

class GameNotActive(DomainError):
    """Game is not in ACTIVE status."""


class GameAlreadyExists(DomainError):
    """An active game already exists for this room."""


# ── Resource not found ───────────────────────────────────────────────

class NotFound(DomainError):
    """A requested resource was not found."""


# ── Ledger / correction guards ───────────────────────────────────────

class LedgerEntryNotFound(DomainError):
    """Ledger entry not found."""


class EntryAlreadyReversed(DomainError):
    """This ledger entry has already been reversed."""


class CannotReverseCorrection(DomainError):
    """Cannot reverse a correction entry."""


# ── Settlement guards ────────────────────────────────────────────────

class PayoutExceedsPot(DomainError):
    """Total payouts exceed pot amount."""


class PayoutEmpty(DomainError):
    """At least one pot payout is required."""


class PayoutMismatch(DomainError):
    """Pot winners total does not match pot amount."""
