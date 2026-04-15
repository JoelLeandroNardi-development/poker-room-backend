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
- **Unified action pipeline** – single `apply_action()` entry point validates, mutates player/round state, and advances turns atomically
- **Domain exceptions** – pure domain error hierarchy; HTTP status codes mapped only at the API boundary
- **Ledger mirroring** – every state mutation (blinds, bets, payouts) writes an immutable `HandLedgerEntry`
- **DB invariants** – ForeignKey, UniqueConstraint, and CheckConstraint on all game-service models

### Poker engine (game-service)

The game-service owns the complete Texas Hold'em lifecycle:

- **Round management** – create rounds, track street progression (preflop → flop → turn → river → showdown)
- **Dealer & blinds** – automatic dealer button rotation, small/big blind + ante posting
- **Turn engine** – per-action turn advancement with fold/check/call/raise/all-in validation
- **Bet validator** – enforces min-raise, pot-limit, and no-limit rules
- **Side-pot calculator** – splits pots correctly when players are all-in at different stack levels
- **Settlement** – atomic multi-winner settlement with chip distribution and hand ledger recording
- **Payout validation** – submitted payouts validated against computed side-pot structure (eligible winners + amounts)
- **Dealer corrections** – projection-safe: reverse action, adjust stack, reopen hand, correct payout (all mirror to ledger + mutable state)

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

**310 unit tests** covering:

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
│   ├── unit/                # 310 unit tests
│   └── integration/         # Integration tests (placeholder)
├── docker-compose.yml
├── Makefile
└── .github/workflows/tests.yml
```

## Changelog

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

- [ ] Integration tests – the `tests/integration/` directory is a placeholder; needs real cross-service tests with PostgreSQL
- [ ] Hand evaluation – no poker hand ranking engine yet (e.g. determining flush vs. straight)
- [ ] WebSocket support – real-time game state push to connected players
- [ ] Password reset flow – `PasswordResetToken` model exists in auth-service but the flow is not implemented
- [ ] Rate limiting – no request throttling on the gateway
- [ ] Observability – structured logging, metrics, distributed tracing
- [ ] Frontend client – no UI exists yet; backend is API-only
