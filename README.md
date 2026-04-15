# poker-room-backend

[![Tests](https://github.com/JoelLeandroNardi-development/poker-room-backend/actions/workflows/tests.yml/badge.svg)](https://github.com/JoelLeandroNardi-development/poker-room-backend/actions/workflows/tests.yml)

Backend written in Python and mounted on top of Docker to manage a poker game room with rules, turns, bets — a mathematical engine for Texas Hold'em. Designed to connect to a frontend app.

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

### Poker engine (game-service)

#### Data model roles

Every table in game-service has a clearly defined role.  This prevents drift when adding features:

| Table | Role | Description |
|---|---|---|
| **Game** | Authoritative | Current game lifecycle state (status, blind level, dealer positions) |
| **Round** + **RoundPlayer** | Authoritative projection | Mutable snapshot of the current hand.  Updated in-place by each action via `apply_action()`.  This is the single source of truth for "where is the hand right now?" |
| **HandLedgerEntry** | Immutable audit trail | Append-only log of every state change (blinds, bets, payouts, corrections).  Never updated or deleted.  Can rebuild hand state from scratch via `rebuild_hand_state()` |
| **Bet** | Action read model | Denormalized record of each betting action for query convenience.  Redundant with the ledger — kept for backward compatibility and fast per-round action history queries |
| **RoundPayout** | Settlement record | Records chip distribution at hand resolution.  Authoritative for "who won what" alongside the ledger |
| **RoomSnapshot** / **RoomSnapshotPlayer** / **RoomSnapshotBlindLevel** | Anti-corruption snapshot | Local copy of room-service data captured at game start.  Insulates the hand engine from external service availability |

> **Rule:** `Round` + `RoundPlayer` is what the engine reads during play.
> `HandLedgerEntry` is what you replay for audits and corrections.
> `Bet` may eventually be removed if the ledger fully covers query needs.

The game-service owns the complete Texas Hold'em lifecycle:

- **Round management** – create rounds, track street progression (preflop → flop → turn → river → showdown)
- **Dealer & blinds** – automatic dealer button rotation, small/big blind + ante posting
- **Turn engine** – per-action turn advancement with fold/check/call/raise/all-in validation
- **Bet validator** – enforces min-raise, pot-limit, and no-limit rules
- **Side-pot calculator** – splits pots correctly when players are all-in at different stack levels
- **Settlement** – atomic multi-winner settlement with chip distribution and hand ledger recording
- **Payout validation** – submitted payouts validated against computed side-pot structure (eligible winners + amounts)
- **Dealer corrections** – projection-safe: reverse action, adjust stack, reopen hand, correct payout (all mirror to ledger + mutable state)
- **Hand replay engine** – pure `replay_hand()` rebuilds step-by-step hand state from ledger entries; `verify_consistency()` compares replayed vs live state for determinism proof
- **Settlement explainer** – `explain_settlement()` produces structured pot breakdown with contributor/eligibility/winner details and human-readable narrative
- **Hand history timeline** – `build_hand_timeline()` reconstructs per-street action timeline with running pot totals, payouts, and corrections
- **Scenario runner** – declarative DSL for scripting full hand scenarios (setup → blinds → actions → expectations) with automatic verification
- **Rules profile** – `RulesProfile` dataclass encodes poker variant rules; `NO_LIMIT_HOLDEM` pre-built profile parameterizes the engine
- **Engine versioning** – `engine_version` + `state_version` columns on Round for version tracking and optimistic concurrency

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

**357 unit tests** covering:

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
│   │   ├── db/              # Session management, CRUD helpers
│   │   ├── messaging/       # RabbitMQ publisher, consumer, events
│   │   └── outbox/          # Outbox pattern (model, helpers, worker)
│   └── schemas/             # Pydantic schemas shared across services
├── services/
│   ├── auth-service/        # JWT auth, registration, login
│   ├── user-service/        # User profiles
│   ├── room-service/        # Room + player management
│   ├── game-service/        # Full poker engine (rounds, betting, settlement)
│   └── gateway-service/     # HTTP gateway with connection-pooled clients
├── tests/
│   └── unit/                # 357 unit tests
│   └── integration/         # Integration tests (placeholder)
├── docker-compose.yml
├── Makefile
└── .github/workflows/tests.yml
```

## Changelog

### Engine evolution — replay, explainer, scenarios (task 15)

- **Hand replay engine** – new `domain/hand_replay.py`: pure `replay_hand()` rebuilds every intermediate `HandState` from ledger entries (step-by-step); `verify_consistency()` compares replayed state against live projection and returns discrepancy list
- **Settlement explanation engine** – new `domain/settlement_explainer.py`: `explain_settlement()` produces structured `SettlementExplanation` with per-pot breakdown (contributors, eligible/ineligible players with reasons, winners, unclaimed amounts) and auto-generated human-readable narrative
- **Hand history timeline** – new `domain/hand_history.py`: `build_hand_timeline()` reconstructs a `HandTimeline` organized by street with running pot totals, payouts, and corrections tracked separately
- **Scenario runner framework** – new `domain/scenario_runner.py`: declarative `HandScenario` DSL (player setup → blind config → scripted actions → expectations) with `run_scenario()` that drives `apply_action` and verifies pot amounts, fold states, stack values, and error conditions
- **Rules profile** – new `domain/rules.py`: frozen `RulesProfile` dataclass parameterizing the engine; `NO_LIMIT_HOLDEM` pre-built profile (betting structure, street sequence, raise rules, engine version)
- **Engine versioning** – `engine_version` (string) and `state_version` (integer, ≥ 1) columns added to `Round` model with `CheckConstraint`; foundation for optimistic concurrency and version-tracked replays
- **34 new tests** – `test_engine_modules.py` (25 tests: replay, consistency verification, settlement explainer, timeline, rules profile) + `test_scenarios.py` (9 tests: heads-up, 3-player, all-in, reraise, meta-tests)

### Hand engine refinement (task 14)

- **Explicit `last_aggressor_seat`** – new column on `Round`; `apply_action()` sets it on bet/raise/all-in, `advance_street` resets it to `None`; eliminates the fragile fallback that used `acting_player_id` as a proxy
- **Pure state-transition core** – extracted `transition_hand_state()` as a **pure function** that takes immutable `HandContext` + action parameters and returns a structured `HandTransition` (player mutation + round mutation); `apply_action()` is now a thin ORM adapter that writes the diff
- **Source-of-truth documentation** – README "Data model roles" table classifies every table as authoritative, projection, audit trail, read model, or anti-corruption snapshot
- **Command-service boilerplate reduction** – new `action_helpers.py` with `record_bet_action()` (Bet + ledger + outbox in one call) and `append_ledger_entry()` (single-entry helper); all 3 command services refactored to use them
- **Enum CheckConstraints** – `Game.status`, `Round.status`, `Round.street`, `Bet.action`, and `HandLedgerEntry.entry_type` now constrained to valid enum values at the DB level
- **Anti-corruption layer formalized** – `RoomConfigProvider` protocol in the domain layer; `HttpRoomConfigProvider` class in infrastructure implementing fetch_live / save_snapshot / load_snapshot
- **13 new integration tests** – `test_integration_flows.py`: full betting rounds, aggressor tracking, street transitions, side-pot settlement, folded-player rejection, pure `transition_hand_state` immutability, ledger rebuild with reversals and payout corrections
- **Bet table evaluation** – documented in Pending section: kept as read model, flagged for potential removal when ledger coverage is sufficient

### Architecture overhaul (task 13)

- **Domain exceptions** – pure exception hierarchy (`DomainError` → specific errors); replaced all `HTTPException` usage in domain/application layers; `@exception_handler` maps back to HTTP at API boundary
- **DB invariants** – added `ForeignKey`, `UniqueConstraint`, `CheckConstraint`, and composite `Index` across all game-service models (Round, RoundPlayer, RoundPayout, Bet, HandLedgerEntry)
- **Room snapshot adapter** – new `RoomSnapshot`, `RoomSnapshotPlayer`, `RoomSnapshotBlindLevel` models; room config captured at `start_game`; `start_round`, `resolve_hand`, `advance_blinds` read from local snapshot (no live HTTP calls to room-service)
- **Unified action pipeline** – `apply_action()` in `domain/action_pipeline.py`: single entry point that validates via `validate_bet`, mutates ORM models (stack, commitments, fold/all-in flags, pot, highest bet), and computes next-to-act via `turn_engine`
- **Ledger mirroring** – every forced bet (blind/ante), player action (bet/fold/check/call/raise/all-in), payout, and round completion writes an immutable `HandLedgerEntry`
- **Side-pot validation** – `payout_validation.py` validates dealer-submitted payouts against `calculate_side_pots()` (computed pot amounts + eligible winners)
- **Corrections projection-safe** – `reverse_action` now projects reversal onto mutable `Round`/`RoundPlayer` state (pot, stack, commitments) alongside the ledger entry
- **20 new tests** – `test_action_pipeline.py` (13 tests) and `test_payout_validation.py` (7 tests)
- **Fixed latent bug** – restored missing `ErrorMessage` imports in command services

### Latest cleanup (task 12)

- **Removed betting-service** – all betting logic was consolidated into game-service; the entire `services/betting-service/` directory and all references (docker-compose, Makefile, init-databases, gateway config) were deleted
- **Gateway connection pooling** – `ServiceClient` refactored from creating a new `httpx` client per request to using a persistent `AsyncClient` with lazy initialization and proper shutdown via lifespan
- **Dead consumer removed** – game-service was starting a RabbitMQ consumer that processed nothing (empty routing keys); entire consumer infrastructure and config constants removed
- **Dead code removed** – unused repository functions, schema imports, error messages, model re-exports, and inline imports cleaned up across all services
- **Shared module cleaned** – removed dead `rabbit_connect()` function from `shared/core/messaging/mq.py`
- **Tests reorganized** – moved `test_bet_validator.py` from `betting_service/` to `game_service/` test directory; fixed pre-existing `test_list_users` failure
- **CI workflow added** – GitHub Actions workflow for automated testing on push/PR

## Pending / future work

- [ ] **Bet table evaluation** – The `Bet` table is now redundant with `HandLedgerEntry` for recording actions.  It exists as a read model for fast per-round action queries (e.g. "show me all bets this round").  If the ledger + round projection fully covers query needs, `Bet` may be removed.  Currently kept for backward compat and explicit action history UI support.
- [ ] Integration tests – the `tests/integration/` directory is a placeholder; needs real cross-service tests with PostgreSQL
- [ ] Hand evaluation – no poker hand ranking engine yet (e.g. determining flush vs. straight)
- [ ] WebSocket support – real-time game state push to connected players
- [ ] Password reset flow – `PasswordResetToken` model exists in auth-service but the flow is not implemented
- [ ] Rate limiting – no request throttling on the gateway
- [ ] Observability – structured logging, metrics, distributed tracing
- [ ] Frontend client – no UI exists yet; backend is API-only
