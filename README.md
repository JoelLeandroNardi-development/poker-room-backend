# poker-room-backend

[![Tests](https://github.com/JoelLeandroNardi-development/poker-room-backend/actions/workflows/tests.yml/badge.svg)](https://github.com/JoelLeandroNardi-development/poker-room-backend/actions/workflows/tests.yml)

Backend written in Python and mounted on top of Docker to manage a poker game room with rules, turns, bets — a mathematical engine for Texas Hold'em. Designed to connect to a frontend app.

---

## Architecture

| Service | Port | Description |
|---|---|---|
| **gateway-service** | 8000 | Public HTTP façade – proxies all requests via persistent connection-pooled clients |
| **auth-service** | 8004 | Registration, login, JWT tokens, session management |
| **user-service** | 8005 | User profiles (display name, personal info) |
| **room-service** | 8001 | Room creation, join codes, player management, blind structures |
| **game-service** | 8002 | Full poker engine – game lifecycle, rounds, betting, side pots, settlement, hand ledger |

**Infrastructure:** PostgreSQL 15 · RabbitMQ 3 (topic exchange) · Docker Compose

### Key patterns

- **CQRS** – command / query separation per service
- **Outbox pattern** – reliable event publishing to RabbitMQ
- **Shared package** – cross-cutting DB, messaging, and schema helpers in `shared/`
- **Atomic transactions** – round settlement wrapped in DB transactions with outbox writes
- **Side-pot calculator** – handles all-in scenarios with multiple pots and multi-winner splitting
- **Room snapshot adapter** – room config captured at game start; mid-hand operations use local snapshot (no live HTTP calls)
- **Unified action pipeline** – `transition_hand_state()` is a **pure** domain function that returns a structured `HandTransition`; `apply_action()` is a thin ORM adapter that writes the diff
- **Domain exceptions** – pure domain error hierarchy; HTTP status codes mapped only at the API boundary
- **Ledger mirroring** – every state mutation (blinds, bets, payouts) writes an immutable `HandLedgerEntry`
- **DB invariants** – ForeignKey, UniqueConstraint, CheckConstraint (including enum value constraints), and Index on all game-service models
- **Anti-corruption layer** – `RoomConfigProvider` protocol + `HttpRoomConfigProvider` implementation; room-service data translated into game-native DTOs

---

## Poker engine (game-service)

The game-service owns the complete Texas Hold'em lifecycle. Every module is a pure domain function — no ORM, no HTTP, no side effects — except for the thin infrastructure layer that persists state.

### Data model roles

Every table in game-service has a clearly defined role. This prevents drift when adding features:

| Table | Role | Description |
|---|---|---|
| **Game** | Authoritative | Current game lifecycle state (status, blind level, dealer positions) |
| **Round** + **RoundPlayer** | Authoritative projection | Mutable snapshot of the current hand. Updated in-place by each action via `apply_action()`. Single source of truth for "where is the hand right now?" |
| **HandLedgerEntry** | Immutable audit trail | Append-only log of every state change (blinds, bets, payouts, corrections). Never updated or deleted. Can rebuild hand state from scratch via `rebuild_hand_state()` |
| **Bet** | Action read model | Denormalized record of each betting action for query convenience. Redundant with the ledger — kept for backward compatibility and fast per-round action history queries |
| **RoundPayout** | Settlement record | Records chip distribution at hand resolution. Authoritative for "who won what" alongside the ledger |
| **RoomSnapshot** / **RoomSnapshotPlayer** / **RoomSnapshotBlindLevel** | Anti-corruption snapshot | Local copy of room-service data captured at game start. Insulates the hand engine from external service availability |

> **Rule:** `Round` + `RoundPlayer` is what the engine reads during play.
> `HandLedgerEntry` is what you replay for audits and corrections.
> `Bet` may eventually be removed if the ledger fully covers query needs.

### Engine capabilities

- **Round management** – create rounds, track street progression (preflop → flop → turn → river → showdown)
- **Dealer & blinds** – automatic dealer button rotation, small/big blind + ante posting
- **Turn engine** – per-action turn advancement with fold/check/call/raise/all-in validation
- **Bet validator** – enforces min-raise, pot-limit, and no-limit rules
- **Side-pot calculator** – splits pots correctly when players are all-in at different stack levels
- **Settlement** – atomic multi-winner settlement with chip distribution and hand ledger recording
- **Payout validation** – submitted payouts validated against computed side-pot structure (eligible winners + amounts)
- **Dealer corrections** – projection-safe: reverse action, adjust stack, reopen hand, correct payout (all mirror to ledger + mutable state)
- **Hand replay engine** – pure `replay_hand()` rebuilds step-by-step hand state from ledger entries using O(n) incremental replay; `verify_consistency()` compares replayed vs live state for determinism proof
- **Settlement explainer** – `explain_settlement()` produces structured pot breakdown with contributor/eligibility/winner details and human-readable narrative
- **Hand history timeline** – `build_hand_timeline()` reconstructs per-street action timeline with running pot totals, payouts, and corrections
- **Scenario runner** – declarative DSL for scripting full hand scenarios using real blind posting engine (setup → blinds → actions → expectations) with automatic verification
- **Rules profile** – `RulesProfile` dataclass encodes poker variant rules; `NO_LIMIT_HOLDEM` pre-built profile parameterizes validator, action pipeline, and round creation
- **Engine versioning** – `engine_version` + `state_version` columns on Round for version tracking and optimistic concurrency
- **Optimistic concurrency** – `state_version` compare-and-swap guard in `apply_action()` with `StaleStateError`; prevents stale-read race conditions
- **Idempotency** – optional `idempotency_key` on bet commands; duplicate submissions return the original response instead of double-applying
- **Table runtime** – pure state machine for multi-hand session lifecycle: seat management, sit-out/sit-in, blind clock, pause/resume
- **Frontend table-state contract** – `GET /rounds/{id}/table-state` returns authoritative state with legal actions, pot, acting player, and `state_version`

---

## Module reference

### Domain layer (`game-service/app/domain/`)

#### `action_pipeline.py` — Unified hand state transitions

The central pipeline for processing any player action. Contains both pure state-transition logic and the ORM adapter that persists the diff.

**Dataclasses:**

| Class | Description |
|---|---|
| `PlayerMutation` | Per-player state diff: stack delta, street/hand commit deltas, fold/all-in flags |
| `RoundMutation` | Round-level state diff: pot delta, new highest bet, new min raise, next acting player, aggressor seat, action-closed flag |
| `HandTransition` | Complete result of a hand action: the resolved action + amount, whether the round closed, next player, player mutation, round mutation |
| `ApplyActionResult` | Simplified return value from `apply_action()` for the API layer |

**Functions:**

| Function | Signature | Description |
|---|---|---|
| `transition_hand_state` | `(ctx: HandContext, player_id, action, amount, last_aggressor_seat, rules) → HandTransition` | **Pure function.** Takes an immutable `HandContext` and action parameters, validates via `validate_bet()`, computes all state mutations (stack deltas, pot changes, next-to-act via `next_to_act()`), and returns a structured `HandTransition`. No side effects — no DB, no ORM |
| `apply_action` | `(round, players, player_id, action, amount) → ApplyActionResult` | Thin ORM adapter. Builds a `HandContext` from live `Round`/`RoundPlayer` models, calls `transition_hand_state()`, then writes the resulting `PlayerMutation` and `RoundMutation` back onto the ORM objects. Increments `state_version` |

---

#### `validator.py` — Bet validation engine

Enforces all betting rules for Texas Hold'em. Every action passes through `validate_bet()` before any state mutation.

**Dataclasses:**

| Class | Description |
|---|---|
| `PlayerState` | Frozen snapshot of one player's state: stack, commitments (street + hand), fold/all-in/active flags, seat number |
| `HandContext` | Frozen snapshot of the hand state: round ID, status, street, acting player, highest bet, minimum raise, action-closed flag, player list. Has `get_player(player_id)` helper |
| `ValidatedAction` | Result: the resolved action string and effective amount |

**Function:** `validate_bet(ctx, player_id, action, amount, rules) → ValidatedAction`

Validation logic flow:
1. Round must be `ACTIVE` status
2. Betting must not be closed for this street
3. Player must be in the hand, not folded, not all-in
4. Must be the player's turn (if `acting_player_id` is set)
5. Action-specific rules:
   - **FOLD** → always allowed, returns amount 0
   - **CHECK** → only when `call_amount == 0` (no outstanding bet)
   - **CALL** → only when there is something to call; auto-promotes to ALL_IN if call exceeds stack
   - **BET** → only when no prior bet on this street; enforces minimum bet amount; auto-promotes to ALL_IN if bet equals full stack
   - **RAISE** → only when prior bet exists; validates raise increment against minimum raise; the `amount` parameter is the total commitment (not just the increment); auto-promotes to ALL_IN if raise consumes full stack
   - **ALL_IN** → commits entire remaining stack

---

#### `turn_engine.py` — Turn rotation logic

Determines who acts next after each action, and whether the betting round is closed.

**Dataclasses:**

| Class | Description |
|---|---|
| `ActionSeat` | Frozen snapshot of a player's seat state: player ID, seat number, folded/all-in/active flags, street commitment |
| `NextActorResult` | Result: next player ID and seat (or `None`), and whether the round is closed |

**Function:** `next_to_act(players, current_actor_seat, last_aggressor_seat, current_highest_bet) → NextActorResult`

Algorithm:
1. Filter to eligible players (active, not folded, not all-in)
2. If fewer than 2 eligible → round is closed
3. Sort by seat number, find the first seat after the current actor (wrapping around)
4. Scan clockwise. If the candidate is the last aggressor → round is closed (everyone has acted since the last raise)
5. If the candidate has committed less than the highest bet → that player acts next
6. If no one needs action → round is closed

---

#### `street_progression.py` — Street advancement logic

Evaluates what happens when a betting round closes: advance to the next street, go to showdown, or settle the hand.

**Constants:** `STREET_ORDER = (PRE_FLOP, FLOP, TURN, RIVER, SHOWDOWN)`

**Dataclasses:**

| Class | Description |
|---|---|
| `PlayerSeat` | Frozen snapshot: player ID, seat, folded/all-in/active flags |
| `StreetAdvanceResult` | Result: action (NEXT_STREET / SETTLE_HAND / SHOWDOWN), optional next street, optional first-to-act player, optional winner |

**Functions:**

| Function | Description |
|---|---|
| `next_street(current)` | Returns the next street in sequence, or `None` if at the end |
| `find_first_to_act(eligible, reference_seat)` | Finds the first eligible player clockwise from the reference seat (used to set the first actor on a new street) |
| `evaluate_street_end(current_street, dealer_seat, big_blind_seat, players)` | Main decision function: if ≤1 player remains → `SETTLE_HAND` with winner; if at river/showdown → `SHOWDOWN`; if ≤1 can act (rest all-in) → `SHOWDOWN`; otherwise → `NEXT_STREET` with the computed first-to-act |

---

#### `blind_posting.py` — Forced bet engine

Posts small blind, big blind, and antes for all players at the start of a round.

**Dataclasses:**

| Class | Description |
|---|---|
| `SeatPlayer` | Input: player ID, seat number, starting stack |
| `PostedPlayer` | Output per player: remaining stack, street/hand commitments, all-in flag |
| `BlindPostingResult` | Complete result: list of posted players, pot total, current highest bet |

**Function:** `post_blinds_and_antes(players, small_blind_seat, big_blind_seat, small_blind_amount, big_blind_amount, ante_amount) → BlindPostingResult`

For each player: deducts ante first (capped at remaining stack), then deducts SB or BB (capped at remaining stack). Sets `is_all_in = True` if remaining stack reaches 0 after posting. Returns the aggregate pot and highest bet.

---

#### `side_pots.py` — Side-pot calculator

Computes the correct pot structure when players are all-in at different stack levels.

**Dataclasses:**

| Class | Description |
|---|---|
| `PlayerContribution` | Input per player: player ID, total committed this hand, folded flag, reached-showdown flag |
| `Pot` | Output per pot: index, amount, contributor IDs, eligible winner IDs |

**Function:** `calculate_side_pots(players) → list[Pot]`

Algorithm:
1. Sort players by committed amount (ascending)
2. For each commitment level, compute a pot slice: `(current_level - previous_level) × number_of_contributors`
3. Mark contributors and eligible winners (not folded, reached showdown)
4. Merge "dead pots" (pots with no eligible winners) into the next pot with eligible winners via `_merge_dead_pots()`
5. Return indexed pots

---

#### `hand_ledger.py` — Immutable event log and state rebuilder

Append-only ledger that records every state change in a hand. Can rebuild the complete hand state from scratch.

**Dataclasses:**

| Class | Description |
|---|---|
| `LedgerRow` | Frozen input: entry ID, entry type, player ID, amount, detail dict, original entry ID (for reversals) |
| `PlayerSnapshot` | Mutable per-player state: stack adjustment, total committed, total won, action-reversed flag |
| `HandState` | Mutable aggregate state: player snapshots dict, pot total, completion/reopened flags, reversed entry IDs set, payout corrections list, entry count |

**Functions:**

| Function | Description |
|---|---|
| `apply_entry(state, entry)` | Applies a single ledger entry to a `HandState`. Handles: `BLIND_POSTED`/`ANTE_POSTED`/`BET_PLACED` (add to pot + player committed), `PAYOUT_AWARDED` (add to player won), `ROUND_COMPLETED` (mark completed), `ACTION_REVERSED` (subtract from pot + committed, track reversed ID), `STACK_ADJUSTED` (adjust player stack), `HAND_REOPENED` (mark uncompleted + reopened), `PAYOUT_CORRECTED` (swap winner amounts) |
| `rebuild_hand_state(entries)` | Creates a fresh `HandState` and applies all entries in order — full state reconstruction from the ledger |

---

#### `hand_replay.py` — Step-by-step hand replay

Replays a hand from ledger entries, producing intermediate states at each step for debugging and auditing.

**Dataclasses:**

| Class | Description |
|---|---|
| `HandStep` | One step in the replay: step number, entry ID/type, player, amount, state snapshot after this step |
| `ReplayResult` | Complete replay: list of steps, final state, entry count, consistency flag |

**Functions:**

| Function | Description |
|---|---|
| `replay_hand(entries)` | Iterates through ledger entries, calling `apply_entry()` for each and capturing a deep-copied `HandState` snapshot after each step. Returns the full step-by-step replay |
| `verify_consistency(entries, live_pot_total, live_player_committed)` | Rebuilds state from entries and compares against live values. Returns a list of discrepancy strings (pot mismatch, player committed mismatch, missing players). Empty list = consistent |

---

#### `settlement_explainer.py` — Human-readable pot breakdown

Produces a structured explanation of settlement with auto-generated narrative text.

**Dataclasses:**

| Class | Description |
|---|---|
| `WinnerDetail` | Player ID + amount won |
| `PotExplanation` | Per-pot breakdown: index, label ("Main Pot" / "Side Pot N"), amount, contributor IDs, eligible IDs, ineligibility reasons (folded, didn't reach showdown), winner details, awarded total, unclaimed remainder |
| `SettlementExplanation` | Aggregate: total pot, total awarded, total unclaimed, list of pot explanations, narrative lines |

**Function:** `explain_settlement(contributions, submitted_payouts) → SettlementExplanation`

1. Computes side pots via `calculate_side_pots()`
2. Maps submitted payouts by pot index
3. For each pot: identifies contributors, eligible/ineligible players (with reasons), winners, unclaimed amounts
4. Generates human-readable narrative lines (e.g. "Main Pot: 300 chips from 3 contributors", "→ player_a wins 300 chips")

---

#### `hand_history.py` — Per-street action timeline

Reconstructs a complete hand timeline organized by street with running pot totals.

**Dataclasses:**

| Class | Description |
|---|---|
| `ActionEntry` | Single action: entry ID, player, action type, amount, running pot total |
| `StreetSummary` | One street: name, list of actions, pot at start and end |
| `PayoutEntry` | Payout record: entry ID, player, amount |
| `CorrectionEntry` | Correction record: entry ID, type, player, amount, original entry ID, detail |
| `HandTimeline` | Full timeline: round ID, streets list, payouts list, corrections list, completed/reopened flags, total entries |

**Function:** `build_hand_timeline(round_id, entries) → HandTimeline`

Processes entries in order. Tracks current street (starting at PRE_FLOP). On `STREET_DEALT` → finalize current street, start new one. Blind/bet entries → accumulate in current street with running pot. Payouts, completions, and corrections tracked separately. Action reversals subtract from the running pot.

---

#### `payout_validation.py` — Side-pot payout verification

Validates dealer-submitted payouts against the mathematically computed pot structure.

**Function:** `validate_payouts_against_side_pots(round_players, submitted_payouts, total_pot) → list[Pot]`

1. Builds `PlayerContribution` list from `RoundPlayer` data
2. Computes expected side pots via `calculate_side_pots()`
3. For each submitted payout: verifies the pot index exists, total doesn't exceed the computed pot amount, and every winner is in the eligible set
4. Raises `PayoutMismatch` or `PayoutExceedsPot` on violations

---

#### `scenario_runner.py` — Declarative hand scripting DSL

Framework for scripting complete hand scenarios for testing. Uses the real blind posting engine.

**Dataclasses:**

| Class | Description |
|---|---|
| `PlayerSetup` | Player definition: ID, seat, starting stack |
| `BlindSetup` | Blind structure: small, big, ante |
| `ScriptedAction` | One action: player ID, action string, amount |
| `Expectation` | Verification check: type (pot / action_closed / player_stack / player_folded / error) + args |
| `ExpectationResult` | Check result: passed flag, expectation, failure message |
| `HandScenario` | Full scenario: name, players, blinds, dealer seat, actions, expectations. Helper methods: `add_action()`, `expect_pot()`, `expect_action_closed()`, `expect_player_stack()`, `expect_player_folded()`, `expect_error()` |
| `ScenarioResult` | Run result: scenario name, passed flag, actions applied count, expectation results list, error. `failures` property filters to failed expectations |

**Function:** `run_scenario(scenario, apply_action_fn, Round, RoundPlayer) → ScenarioResult`

1. Creates in-memory `Round` and `RoundPlayer` objects from the scenario definition
2. Posts blinds using the real `post_blinds_and_antes()` engine (determines correct SB/BB seats clockwise from dealer)
3. Executes each scripted action via the provided `apply_action_fn`, catching any exceptions
4. Evaluates all expectations against the final state

---

#### `rules.py` — Poker variant configuration

Frozen `RulesProfile` dataclass encoding the rules for a poker variant. The validator, action pipeline, and round creation are all parameterized by this profile.

**Fields:** `name`, `betting_structure` (no_limit), `forced_bets` (blinds), `min_players`, `max_players`, `streets` (tuple of street names), `min_raise_equals_last_raise`, `unlimited_raises`, `max_raises_per_street`, `all_in_reopens_action`, `dead_button_rule`, `engine_version`

**Pre-built profile:** `NO_LIMIT_HOLDEM` — standard No-Limit Texas Hold'em with 2–10 players, 5 streets, unlimited raises, min raise = last raise, engine version `0.15.0`

---

#### `table_runtime.py` — Multi-hand session state machine

Pure domain state machine managing the lifecycle of a multi-hand poker session at a table.

**Enums:** `SeatStatus` (ACTIVE / SITTING_OUT / EMPTY), `TableStatus` (WAITING / RUNNING / PAUSED / FINISHED)

**Dataclasses:**

| Class | Description |
|---|---|
| `TableSeat` | One seat: seat number, player ID, status, chip count, hands sat out counter |
| `BlindClock` | Blind level tracker: current level, level start time, hands at current level. Methods: `should_advance(hands_per_level, seconds_per_level)` checks both hand-based and time-based advancement; `advance()` increments level + resets counters; `record_hand()` increments hand counter |
| `TableRuntime` | Table state: game ID, status, seats list, blind clock, hands played, dealer seat. Properties: `active_seats` (ACTIVE with a player), `seated_count`. Methods: `can_start_hand()` (running + ≥2 active), `start_session()`, `pause_session()`, `resume_session()`, `finish_session()`, `sit_out(seat)`, `sit_in(seat)`, `record_hand_completed()` (increments counters, tracks sat-out hands), `next_hand_number()` |

---

#### `room_adapter.py` — Anti-corruption layer protocol

Defines the domain-side contract for room configuration, keeping the engine isolated from room-service details.

**Dataclasses:** `PlayerConfig` (player ID, seat, chip count, active/eliminated flags), `BlindLevelConfig` (level, small/big blind, ante, duration), `RoomConfig` (room ID, starting dealer seat, players list, blind levels list, with `active_seats`, `active_players`, `blind_level(n)` helpers)

**Protocol:** `RoomConfigProvider` — defines `fetch_live(room_id)`, `save_snapshot(game_id, config)`, `load_snapshot(game_id)` as the three operations the engine needs

---

#### `constants.py` — Enumerations and sentinel values

All string enumerations used across the game-service domain:

| Enum | Values |
|---|---|
| `GameStatus` | WAITING, ACTIVE, PAUSED, FINISHED |
| `RoundStatus` | ACTIVE, COMPLETED |
| `Street` | PRE_FLOP, FLOP, TURN, RIVER, SHOWDOWN |
| `StreetAdvanceAction` | NEXT_STREET, SETTLE_HAND, SHOWDOWN |
| `LedgerEntryType` | BLIND_POSTED, ANTE_POSTED, BET_PLACED, STREET_DEALT, PAYOUT_AWARDED, ROUND_COMPLETED, ACTION_REVERSED, STACK_ADJUSTED, HAND_REOPENED, PAYOUT_CORRECTED |
| `BetAction` | FOLD, CHECK, CALL, BET, RAISE, ALL_IN |
| `GameEventType` | game.started, game.round_started, game.round_completed, game.street_advanced, game.blinds_increased, game.correction_applied, bet.placed, game.finished |
| `ErrorMessage` | All user-facing error strings (GAME_NOT_FOUND, ROUND_NOT_ACTIVE, NOT_YOUR_TURN, etc.) |
| `EventKey` / `DataKey` / `TableName` | JSON payload keys, table name constants |

---

#### `exceptions.py` — Domain error hierarchy

Pure exception hierarchy rooted at `DomainError(message)`. HTTP status codes are mapped only at the API boundary via `@exception_handler`.

Exceptions: `RoundNotActive`, `ActionClosed`, `RoundNotCompleted`, `RoundAlreadyActive`, `AlreadyAtShowdown`, `PlayerNotInHand`, `PlayerAlreadyFolded`, `PlayerAlreadyAllIn`, `NotYourTurn`, `IllegalAction`, `CheckNotAllowed`, `CallNotAllowed`, `BetNotAllowed`, `RaiseNotAllowed`, `RaiseBelowMinimum`, `AmountExceedsStack`, `InvalidAmount`, `GameNotActive`, `GameAlreadyExists`, `NotFound`, `LedgerEntryNotFound`, `EntryAlreadyReversed`, `CannotReverseCorrection`, `PayoutExceedsPot`, `PayoutEmpty`, `PayoutMismatch`, `StaleStateError`, `DuplicateActionError`, `IdempotencyConflict`

---

### Application layer (`game-service/app/application/`)

#### Command services

| Service | Responsibilities |
|---|---|
| `GameCommandService` | `start_game` (creates game + room snapshot + outbox event), `start_round` (posts blinds via blind engine, creates Round/RoundPlayer/ledger entries, assigns first-to-act), `resolve_hand` (validates payouts against side-pot structure, distributes chips, records ledger), `advance_street` (evaluates street end, progresses or settles), `declare_winner` (single-winner shortcut), `advance_blinds` (increments blind level from room snapshot), `end_game` (sets FINISHED status) |
| `BetCommandService` | `place_bet` (finds active round, loads players, calls `apply_action()`, records bet + ledger + outbox via `record_bet_action()`, uses CAS update for optimistic concurrency, supports idempotency keys) |
| `CorrectionCommandService` | `reverse_action` (reverses a ledger entry, projects reversal onto Round/RoundPlayer state), `adjust_stack` (delta stack adjustment for a player), `reopen_hand` (reopens a completed round), `correct_payout` (swaps a payout from one player to another). All corrections write a ledger entry and update the mutable projection |
| `TableRuntimeCommandService` | `pause_table`, `resume_table`, `record_hand_completed`, `get_session_status` — manages table runtime state machine, persists to Game model |

#### Action helpers (`action_helpers.py`)

| Helper | Description |
|---|---|
| `record_bet_action(db, round_id, player_id, action, amount, game_id, room_id)` | Creates a `Bet` row + `HandLedgerEntry` + outbox event in one call |
| `append_ledger_entry(db, round_id, entry_type, player_id, amount, detail, original_entry_id)` | Creates a single `HandLedgerEntry` with a generated UUID |

---

### Infrastructure layer (`game-service/app/infrastructure/`)

#### `repository.py` — Database access functions

Pure async repository functions (no class, just functions accepting `AsyncSession`):

| Function | Description |
|---|---|
| `fetch_or_raise(db, model, filter_column, filter_value, detail)` | Generic single-row fetch with `NotFound` exception |
| `get_active_game_for_room(db, room_id)` | Find the ACTIVE game for a room |
| `get_latest_round(db, game_id)` | Latest round by round_number DESC |
| `get_active_round(db, game_id)` | Find the ACTIVE round for a game |
| `count_rounds(db, game_id)` | Count of rounds in a game |
| `get_rounds_for_game(db, game_id)` | All rounds ordered by round_number |
| `get_round_players(db, round_id)` | All players in a round ordered by seat |
| `get_round_payouts(db, round_id)` | Payouts ordered by pot_index |
| `get_ledger_entries(db, round_id)` | All ledger entries ordered by ID |
| `get_ledger_entry_by_id(db, entry_id)` | Single ledger entry by entry_id |
| `get_bets_for_round(db, round_id)` | All bets ordered by created_at |
| `get_pot_total(db, round_id)` | Sum of bet amounts for a round |
| `cas_update_round(db, round, expected_version)` | Compare-and-swap update on Round using `state_version`. Disables autoflush, issues a `WHERE state_version = expected` UPDATE, raises `StaleStateError` on conflict (0 rows affected). This is the optimistic concurrency guard |

#### `room_config.py` — Room snapshot adapter

Implements the `RoomConfigProvider` protocol from the domain layer:

| Function / Class | Description |
|---|---|
| `fetch_room_config_http(room_id)` | HTTP GET to room-service, translates response into a `RoomConfig` domain DTO |
| `save_room_snapshot(db, game_id, config)` | Persists `RoomSnapshot` + `RoomSnapshotPlayer` + `RoomSnapshotBlindLevel` rows |
| `load_room_snapshot(db, game_id)` | Loads the snapshot back into a `RoomConfig` DTO from the database |
| `HttpRoomConfigProvider` | Class implementing the protocol: `fetch_live()`, `save_snapshot()`, `load_snapshot()` — delegates to the functions above |

#### `logging.py` — Structured logging with correlation IDs

| Component | Description |
|---|---|
| `correlation_id_ctx` | `ContextVar` holding the current correlation ID (set by middleware, propagated through async calls) |
| `StructuredLogger` | Wrapper around `logging.Logger` that auto-attaches the correlation ID to every log message via an `extra.structured` dict. Methods: `info()`, `warning()`, `error()`, `debug()` — all accept arbitrary `**fields` keyword arguments |
| `StructuredFormatter` | Custom `logging.Formatter` that appends structured fields as `key=value` pairs to the log line |
| `configure_logging(level)` | Sets up the root logger with the structured formatter |

#### `middleware.py` — HTTP middleware

| Component | Description |
|---|---|
| `CorrelationIdMiddleware` | Starlette middleware that extracts `X-Correlation-ID` from the request header (or generates a UUID), sets it in the context var, measures request duration, logs the method/path/status/duration, and returns the correlation ID in the response header |

---

### API layer (`game-service/app/api/routes.py`)

All endpoints use FastAPI dependency injection for the async DB session.

#### Game lifecycle

| Method | Path | Description |
|---|---|---|
| POST | `/games` | Start a new game for a room |
| GET | `/games/{game_id}` | Get game details |
| GET | `/games/room/{room_id}` | Get active game for a room |
| POST | `/games/{game_id}/rounds` | Start a new round |
| GET | `/games/{game_id}/rounds` | List all rounds for a game |
| GET | `/games/{game_id}/rounds/active` | Get the active round |
| GET | `/rounds/{round_id}` | Get round details |
| POST | `/rounds/{round_id}/resolve` | Resolve hand with payouts |
| POST | `/rounds/{round_id}/advance-street` | Advance to next street |
| POST | `/rounds/{round_id}/winner` | Declare a single winner |
| POST | `/games/{game_id}/advance-blinds` | Increment blind level |
| POST | `/games/{game_id}/end` | End the game |

#### Betting

| Method | Path | Description |
|---|---|---|
| POST | `/bets` | Place a bet (fold/check/call/bet/raise/all-in) |
| GET | `/bets/round/{round_id}` | Get all bets for a round |
| GET | `/bets/round/{round_id}/pot` | Get current pot total |
| GET | `/bets/round/{round_id}/players` | Get per-player bet summaries |

#### Corrections

| Method | Path | Description |
|---|---|---|
| POST | `/rounds/{round_id}/corrections/reverse-action` | Reverse a ledger entry |
| POST | `/rounds/{round_id}/corrections/adjust-stack` | Adjust a player's stack |
| POST | `/rounds/{round_id}/corrections/reopen-hand` | Reopen a completed hand |
| POST | `/rounds/{round_id}/corrections/correct-payout` | Correct a payout |

#### Queries & analysis

| Method | Path | Description |
|---|---|---|
| GET | `/rounds/{round_id}/ledger` | Get all ledger entries |
| GET | `/rounds/{round_id}/hand-state` | Get rebuilt hand state from ledger |
| GET | `/rounds/{round_id}/replay` | Step-by-step hand replay |
| GET | `/rounds/{round_id}/timeline` | Per-street action timeline |
| GET | `/rounds/{round_id}/settlement-explanation` | Structured pot breakdown + narrative |
| GET | `/rounds/{round_id}/consistency-check` | Compare replayed vs live state |
| GET | `/rounds/{round_id}/table-state` | Frontend contract: legal actions, pot, acting player, state_version |

#### Table runtime

| Method | Path | Description |
|---|---|---|
| POST | `/games/{game_id}/pause` | Pause the table session |
| POST | `/games/{game_id}/resume` | Resume a paused session |
| POST | `/games/{game_id}/record-hand-completed` | Record hand completion for blind clock |
| GET | `/games/{game_id}/session-status` | Get table runtime state |

---

### Shared library (`shared/`)

#### `core/db/session.py` — Async session management

| Component | Description |
|---|---|
| `make_get_db(SessionLocal)` | Factory that returns a FastAPI dependency generator yielding an `AsyncSession` |
| `atomic(session)` | Async context manager wrapping a block in `session.begin_nested()` (SAVEPOINT). On success, the savepoint is committed; on exception, it is rolled back. Used to group multiple DB writes (e.g. round + players + ledger + outbox) into a single atomic unit |

#### `core/messaging/consumer.py` — RabbitMQ consumer

Declares a durable topic exchange, per-service queue, dead-letter exchange (DLX) with retry topology. Binds routing keys, dispatches messages to handler callables. Supports automatic nack → DLQ routing on handler failure.

#### `core/outbox/worker.py` — Outbox publisher

Background worker that polls the outbox table for unsent events, publishes them to RabbitMQ, and marks them as sent. Provides reliable at-least-once delivery.

#### `core/outbox/helpers.py` — Outbox write helper

`add_outbox_event(db, OutboxModel, event_dict)` — creates an outbox row from an event dict in a single call.

#### `schemas/` — Shared Pydantic schemas

Cross-service request/response schemas: `auth.py` (tokens, login), `bets.py` (PlaceBet, BetResponse, PotResponse, PlayerBetSummary), `games.py` (game/round schemas), `rooms.py` (room/player schemas), `users.py` (user profile schemas).

---

## Quick start

```bash
# bring everything up (builds images, starts infra + services)
make up

# run Alembic migrations
make migrate-all

# tail logs
make logs
```

### Individual commands

```bash
make build          # rebuild images
make down           # stop all containers
make ps             # show running services
make restart        # restart all containers
make migrate-auth   # migrate auth-service DB
make migrate-user   # migrate user-service DB
make migrate-room   # migrate room-service DB
make migrate-game   # migrate game-service DB
```

## Running tests

```bash
# install test dependencies
pip install -r requirements-test.txt
cd shared && pip install -e ".[test]" && cd ..
for service in services/*/; do pip install -r "$service/requirements.txt"; done

# run all tests
python -m pytest tests/ -v

# run with coverage
python -m pytest tests/unit/ -v --cov=shared --cov=services --cov-report=term-missing
```

**421 unit tests** (413 passing, 8 PostgreSQL-only skipped in SQLite mode):

| Area | Tests | Description |
|---|---|---|
| Auth service | 12 | Token generation, password hashing, JWT operations |
| Bet validator | 39 | Min-raise, pot-limit, no-limit, all-in edge cases |
| Blind posting | 23 | SB/BB/ante posting, heads-up, missing stacks |
| Hand ledger | 24 | Ledger recording, multi-winner entries, chip tracking |
| Holdem scenarios | 37 | End-to-end Texas Hold'em scenarios (full hands) |
| Positions | 12 | Dealer button rotation, seat assignment |
| Settlement | 8 | Atomic settlement transactions, multi-winner splits |
| Side pots | 25 | All-in side-pot calculation, complex multi-pot scenarios |
| Street progression | 47 | Street advancement, skip logic, showdown triggers |
| Turn engine | 47 | Turn rotation, fold/check/call/raise/all-in flow |
| Action pipeline | 13 | Unified apply_action: mutation, turn progression, validation |
| Payout validation | 7 | Side-pot eligibility, overpay rejection, split pots |
| Integration flows | 13 | Full betting rounds, street transitions, settlement, ledger rebuild, pure transitions |
| Engine modules | 25 | Hand replay, settlement explainer, hand timeline, rules profile |
| Scenario runner | 9 | Declarative hand scenarios: heads-up, 3-way, all-in, reraise, expectations |
| New features | 34 | Incremental replay, optimistic concurrency, RulesProfile wiring, table runtime, blind clock, idempotency |
| Room repository | 11 | Room CRUD, player management queries |
| User CRUD | 5 | User creation, listing, lookup |

### CI

Tests run automatically on push/PR to `main` and `develop` via GitHub Actions. The workflow includes:

- Unit tests with SQLite in-memory databases
- Coverage reporting via Codecov
- Test collection verification (markers-check job)

## Tech stack

- Python 3.13 · FastAPI · SQLAlchemy 2 (async) · Pydantic 2
- bcrypt · python-jose (JWT) · aio-pika · asyncpg · httpx · Alembic
- Docker & Docker Compose · GitHub Actions

## Project structure

```
├── shared/                  # Cross-cutting library (installed as editable package)
│   ├── core/
│   │   ├── auth/            # Role definitions
│   │   ├── db/              # Session management (atomic()), CRUD helpers
│   │   ├── messaging/       # RabbitMQ publisher, consumer (DLX + retry), events
│   │   └── outbox/          # Outbox pattern (model, helpers, worker)
│   └── schemas/             # Pydantic schemas shared across services
├── services/
│   ├── auth-service/        # JWT auth, registration, login
│   ├── user-service/        # User profiles
│   ├── room-service/        # Room + player management
│   ├── game-service/        # Full poker engine (rounds, betting, settlement)
│   │   └── app/
│   │       ├── api/         # FastAPI routes (30+ endpoints)
│   │       ├── application/ # Command + query services, action helpers, mappers
│   │       ├── domain/      # Pure domain logic (15 modules documented above)
│   │       └── infrastructure/ # Repository, room config adapter, logging, middleware
│   └── gateway-service/     # HTTP gateway with connection-pooled clients
├── tests/
│   ├── unit/                # 421 unit tests
│   └── integration/         # Integration tests (Postgres-backed)
├── docker-compose.yml
├── Makefile
└── .github/workflows/tests.yml
```

## Changelog

### Comment cleanup (task 17)

- **Stripped all comments and docstrings** from 102 source files (203 inline comments, 162 docstring blocks removed)
- **Comprehensive README documentation** — all module documentation consolidated into the Module Reference section above
- **Empty class bodies fixed** — exception classes that lost their docstring bodies received `pass` statements
- **Tests verified** — 421 collected, 413 passed, 0 failed, 8 PG-skipped

### Hardening — DB CAS, idempotency, table runtime, observability (task 16)

- **DB-level CAS** — `cas_update_round()` uses `WHERE state_version = expected` UPDATE; `StaleStateError` on conflict; autoflush disabled during CAS
- **Scoped idempotency** — `idempotency_key` on bet commands; duplicate submissions return original response via `DuplicateActionError` / `IdempotencyConflict`
- **Table runtime persistence** — `TableRuntimeCommandService` wires domain state machine to Game model; `pause_table`, `resume_table`, `record_hand_completed`, `get_session_status` endpoints
- **Expanded frontend contract** — `TableStateResponse` with legal actions, pot, acting player, `state_version`; `SessionStatusResponse` read model
- **Structured logging** — `StructuredLogger` with correlation ID context var, `StructuredFormatter`, `CorrelationIdMiddleware`
- **Integration tests** — Postgres-backed tests with real async sessions

### Engine evolution — replay, explainer, scenarios (task 15)

- **Hand replay engine** – `replay_hand()` rebuilds every intermediate `HandState` from ledger entries; `verify_consistency()` compares replayed state against live projection
- **Settlement explanation engine** – `explain_settlement()` produces structured `SettlementExplanation` with per-pot breakdown and auto-generated narrative
- **Hand history timeline** – `build_hand_timeline()` reconstructs a `HandTimeline` organized by street with running pot totals
- **Scenario runner framework** – declarative `HandScenario` DSL with `run_scenario()` that drives `apply_action` and verifies expectations
- **Rules profile** – frozen `RulesProfile` dataclass; `NO_LIMIT_HOLDEM` pre-built profile
- **Engine versioning** – `engine_version` + `state_version` columns on Round
- **34 new tests** – `test_engine_modules.py` (25) + `test_scenarios.py` (9)

### Hand engine refinement (task 14)

- **Explicit `last_aggressor_seat`** – new column on Round; eliminates fragile `acting_player_id` proxy
- **Pure state-transition core** – `transition_hand_state()` as pure function; `apply_action()` as thin ORM adapter
- **Command-service boilerplate reduction** – `record_bet_action()` + `append_ledger_entry()` helpers
- **Enum CheckConstraints** – DB-level enum validation on status/street/action/entry_type columns
- **Anti-corruption layer formalized** – `RoomConfigProvider` protocol + `HttpRoomConfigProvider`
- **13 new integration tests** – `test_integration_flows.py`

### Architecture overhaul (task 13)

- **Domain exceptions** – pure hierarchy; HTTP mapping at API boundary only
- **DB invariants** – ForeignKey, UniqueConstraint, CheckConstraint, Index on all game-service models
- **Room snapshot adapter** – room config captured at game start; no live HTTP during play
- **Unified action pipeline** – single `apply_action()` entry point
- **Ledger mirroring** – every mutation writes an immutable `HandLedgerEntry`
- **Side-pot validation** – `payout_validation.py` validates against `calculate_side_pots()`
- **20 new tests** – `test_action_pipeline.py` (13) + `test_payout_validation.py` (7)

### Service consolidation & cleanup (task 12)

- **Removed betting-service** – consolidated into game-service
- **Gateway connection pooling** – persistent `AsyncClient` with lazy init
- **Dead consumer + dead code removed** across all services
- **Tests reorganized** + **CI workflow added**

## Pending / future work

- [ ] **Bet table evaluation** – The `Bet` table is now redundant with `HandLedgerEntry`. Kept as a read model for fast per-round action queries. May be removed when ledger coverage is sufficient
- [ ] Hand evaluation – no poker hand ranking engine yet (e.g. determining flush vs. straight)
- [ ] WebSocket support – real-time game state push to connected players
- [ ] Password reset flow – `PasswordResetToken` model exists but the flow is not implemented
- [ ] Rate limiting – no request throttling on the gateway
- [ ] Metrics & distributed tracing – structured logging is in place; metrics (Prometheus) and tracing (OpenTelemetry) not yet added
- [ ] Frontend client – no UI exists yet; backend is API-only
