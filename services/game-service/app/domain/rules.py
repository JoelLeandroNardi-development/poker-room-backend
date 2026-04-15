"""Formal rules profile for poker variants.

A ``RulesProfile`` encodes the structural rules of a poker variant
(betting structure, forced bets, street sequence, raise caps, etc.)
so that the hand engine can be parameterized rather than hard-coded.

Currently only No-Limit Texas Hold'em is defined.  Adding new variants
(Pot-Limit Omaha, Fixed-Limit, etc.) is a matter of creating a new
profile — the engine reads from the profile instead of literals.

Usage::

    from .rules import NO_LIMIT_HOLDEM
    profile = NO_LIMIT_HOLDEM
    if profile.betting_structure == "no_limit":
        ...
"""

from __future__ import annotations

from dataclasses import dataclass

from .constants import Street


@dataclass(frozen=True, slots=True)
class RulesProfile:
    """Immutable specification of a poker variant's rules."""

    name: str
    betting_structure: str  # "no_limit" | "pot_limit" | "fixed_limit"
    forced_bets: str  # "blinds" | "antes" | "blinds_and_antes"
    min_players: int
    max_players: int
    streets: tuple[str, ...]
    min_raise_equals_last_raise: bool  # True = standard NLHE rule
    unlimited_raises: bool  # True = no cap on raises
    max_raises_per_street: int | None  # None = unlimited
    all_in_reopens_action: bool  # whether incomplete all-in reopens
    dead_button_rule: bool  # whether dead button can occur
    engine_version: str  # semver for the engine rules version


# ── Pre-built profiles ───────────────────────────────────────────────

NO_LIMIT_HOLDEM = RulesProfile(
    name="No-Limit Texas Hold'em",
    betting_structure="no_limit",
    forced_bets="blinds",
    min_players=2,
    max_players=10,
    streets=(
        Street.PRE_FLOP,
        Street.FLOP,
        Street.TURN,
        Street.RIVER,
        Street.SHOWDOWN,
    ),
    min_raise_equals_last_raise=True,
    unlimited_raises=True,
    max_raises_per_street=None,
    all_in_reopens_action=False,
    dead_button_rule=False,
    engine_version="0.15.0",
)
