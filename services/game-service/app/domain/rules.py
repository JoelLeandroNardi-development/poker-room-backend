
from __future__ import annotations

from dataclasses import dataclass

from .constants import Street

@dataclass(frozen=True, slots=True)
class RulesProfile:

    name: str
    betting_structure: str
    forced_bets: str
    min_players: int
    max_players: int
    streets: tuple[str, ...]
    min_raise_equals_last_raise: bool
    unlimited_raises: bool
    max_raises_per_street: int | None
    all_in_reopens_action: bool
    dead_button_rule: bool
    engine_version: str

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