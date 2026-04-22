# poker-room-backend

[![Tests](https://github.com/JoelLeandroNardi-development/poker-room-backend/actions/workflows/tests.yml/badge.svg)](https://github.com/JoelLeandroNardi-development/poker-room-backend/actions/workflows/tests.yml)

Backend for a poker room tracker. The project is a Python/FastAPI microservice system for creating poker rooms, registering players, configuring blind levels and antes, starting games, running Texas Hold'em betting rounds, rotating dealer/SB/BB positions, tracking player actions, calculating pots, settling hands, and exposing state for a future frontend.

The backend is API-only. It is designed to sit behind the gateway service and connect to a frontend that lets each player join a room and submit their own actions.

---

## Current State

The codebase currently supports:

- Auth registration/login/refresh/logout with JWTs and refresh-token persistence.
- Auth-user administration: list, fetch by id/email, update password/roles, delete.
- User profile CRUD by email.
- Room creation with join code, max players, starting chips, ante setting, and creator id.
- Player joining by room code with optional explicit seat selection.
- Seat reordering for waiting rooms.
- Blind structure setup: level number, small blind, big blind, ante, duration minutes, starting dealer seat.
- Player chip updates and elimination.
- Game start from a room snapshot.
- Automatic dealer, small blind, and big blind assignment and rotation.
- Round creation with blind and ante posting.
- Betting actions: fold, check, call, bet, raise, all-in.
- Optimistic concurrency through `expected_version` and `state_version`.
- Optional idempotency keys for bet submission.
- Side-pot calculation and payout validation.
- Hand resolution, single-winner shortcut, payout recording, and immutable hand ledger.
- Dealer corrections: reverse action, adjust stack, reopen hand, correct payout.
- Hand replay, hand-state rebuilding, consistency checks, settlement explanation, and action timeline.
- Table runtime state: pause/resume, duration-based blind clock, session status.
- Password reset token request, email delivery, and reset flow.
- Gateway WebSocket endpoint for event-driven table-state snapshots from RabbitMQ/outbox events, with periodic reconciliation fallback.
- Gateway proxy over all main public routes.
- Docker Compose environment with PostgreSQL and RabbitMQ.

Remaining limitations:

- There is no poker hand evaluator yet. The backend tracks betting/settlement but does not decide that a flush beats a straight.

---

## Architecture

| Service | External port | Internal port | Responsibility |
|---|---:|---:|---|
| `gateway-service` | 8000 | 8000 | Public HTTP facade. Proxies requests to service clients and adds `X-Correlation-ID`. |
| `room-service` | 8001 | 8000 | Room lifecycle, join codes, players, chips, blind structures. |
| `game-service` | 8002 | 8000 | Poker engine, games, rounds, betting, settlement, table runtime, analysis. |
| `auth-service` | 8004 | 8000 | Registration, login, JWT access/refresh tokens, auth-user management. |
| `user-service` | 8005 | 8000 | User profile CRUD. |
| `postgres` | 5432 | 5432 | PostgreSQL 15, one database per service via `init-databases.sql`. |
| `rabbitmq` | 5672, 15672 | 5672, 15672 | RabbitMQ 3 management image for domain events and outbox publishing. |

### Main Patterns

- CQRS-style application layer: separate command and query services.
- Shared package for schemas, DB helpers, messaging, outbox helpers, and auth roles.
- Outbox pattern for service events.
- Async SQLAlchemy 2 sessions and Alembic migrations per service.
- Domain-heavy game engine: core poker rules are implemented as pure functions where possible.
- Immutable hand ledger plus mutable round projection.
- Room snapshot anti-corruption layer: game-service snapshots room-service data at game start.
- Gateway routes use shared Pydantic schemas and service clients instead of reimplementing business logic.

---

## Typical Poker Room Flow

1. Create a room:

```http
POST /rooms
```

Payload:

```json
{
  "name": "Friday poker",
  "max_players": 6,
  "starting_chips": 1000,
  "antes_enabled": true,
  "created_by": "joel"
}
```

2. Players join by code:

```http
POST /rooms/join/{code}
```

Payload:

```json
{ "player_name": "Joel", "seat_number": 1 }
```

`seat_number` is optional. If omitted, the room assigns the next available seat number. Waiting rooms can also be reordered with `PUT /rooms/{room_id}/seats`.

3. Set blind structure and starting dealer:

```http
PUT /rooms/{room_id}/blinds
```

Payload:

```json
{
  "starting_dealer_seat": 1,
  "levels": [
    { "level": 1, "small_blind": 5, "big_blind": 10, "ante": 0, "duration_minutes": 15 },
    { "level": 2, "small_blind": 10, "big_blind": 20, "ante": 2, "duration_minutes": 15 }
  ]
}
```

4. Start game:

```http
POST /games
```

Payload:

```json
{ "room_id": "..." }
```

Game-service fetches the room details from room-service and stores a local snapshot.

5. Start a round:

```http
POST /games/{game_id}/rounds
```

The round is created from the room snapshot. Blinds and antes are posted automatically, the first actor is set, and ledger entries are written.

6. Each player submits actions:

```http
POST /bets
```

Payload:

```json
{
  "round_id": "...",
  "player_id": "...",
  "action": "CALL",
  "amount": 0,
  "expected_version": 1,
  "idempotency_key": "client-generated-key-001"
}
```

Supported actions: `FOLD`, `CHECK`, `CALL`, `BET`, `RAISE`, `ALL_IN`.

7. Frontend reads current table state:

```http
GET /rounds/{round_id}/table-state
```

This returns acting player, legal actions, call amount, pot, street, dealer/SB/BB seats, players, and `state_version`.

8. Resolve the hand:

```http
POST /rounds/{round_id}/resolve
```

Payload:

```json
{
  "payouts": [
    {
      "pot_index": 0,
      "pot_type": "main",
      "amount": 120,
      "winners": [{ "player_id": "...", "amount": 120 }]
    }
  ]
}
```

Submitted payouts are validated against the computed side-pot structure.

---

## Service Details

### Auth Service

Location: `services/auth-service`

Owns credentials, password hashing, JWT access/refresh tokens, token rotation, logout, and auth-user administration.

Main modules:

| Path | Purpose |
|---|---|
| `app/api/commands/auth_authentication_command_routes.py` | Register, login, refresh, and logout routes. |
| `app/api/commands/auth_password_command_routes.py` | Forgot-password and reset-password routes. |
| `app/api/commands/auth_user_command_routes.py` | Auth-user mutation routes. |
| `app/api/queries/auth_user_query_routes.py` | Auth-user read routes. |
| `app/application/commands/auth_authentication_command_service.py` | Register, login, refresh, logout, token rotation, and session revocation. |
| `app/application/commands/auth_password_command_service.py` | Password reset token creation, reset email dispatch, password replacement, and session revocation after reset. |
| `app/application/commands/auth_user_command_service.py` | Update/delete auth users. |
| `app/application/helpers.py` | Shared auth lookups and refresh-token revocation helpers. |
| `app/application/queries/auth_user_query_service.py` | List and fetch auth users. |
| `app/infrastructure/password_hasher.py` | bcrypt hashing and verification. |
| `app/infrastructure/password_reset_email.py` | Password reset link creation plus console/SMTP delivery. |
| `app/infrastructure/token_service.py` | JWT and opaque refresh-token utilities. |
| `app/domain/models.py` | Auth users, refresh tokens, password reset token model. |
| `app/application/mappers.py` | Auth ORM model to response schema mapping. |

Auth endpoints:

| Method | Gateway path | Internal path | Description |
|---|---|---|---|
| POST | `/register` | `/register` | Register an auth user. |
| POST | `/login` | `/login` | Login and receive access/refresh tokens. |
| POST | `/refresh` | `/refresh` | Rotate refresh token and issue fresh pair. |
| POST | `/logout` | `/logout` | Revoke a refresh token. |
| POST | `/forgot-password` | `/forgot-password` | Create a password reset token and deliver a reset link by the configured email backend. |
| POST | `/reset-password` | `/reset-password` | Use a reset token to set a new password and revoke active sessions. |
| GET | `/auth-users` | `/auth-users` | List auth users. |
| GET | `/auth-users/{user_id}` | `/auth-users/{user_id}` | Fetch auth user by id. |
| GET | `/auth-users/by-email/{email}` | `/auth-users/by-email/{email}` | Fetch auth user by email. |
| PUT | `/auth-users/{user_id}` | `/auth-users/{user_id}` | Update password and/or roles. |
| DELETE | `/auth-users/{user_id}` | `/auth-users/{user_id}` | Delete auth user. |

Shared auth schemas:

| Schema | Fields / purpose |
|---|---|
| `Register` | `email`, `password`, `roles`; roles are normalized with default `user`. |
| `RegisterResponse` | `message`, `roles`. |
| `Login` | `email`, `password`. |
| `TokenPairResponse` | `access_token`, `refresh_token`, optional `expires_in`. |
| `RefreshRequest` | `refresh_token`. |
| `LogoutRequest` | `refresh_token`. |
| `ForgotPasswordRequest` | `email`. |
| `ResetPasswordRequest` | `token`, `new_password`. |
| `AuthActionResponse` | `ok`, optional `debug_token` only when explicitly enabled for local/test use. |
| `AuthUserResponse` | `id`, `email`, `roles`, `last_login_at`. |
| `UpdateAuthUser` | Optional `password`, optional normalized `roles`. |
| `DeleteAuthUserResponse` | `message`, `user_id`. |

Password reset email behavior:

- `POST /forgot-password` always returns `{ "ok": true }` for unknown emails so the endpoint does not reveal whether an account exists.
- For existing users, auth-service stores a hashed reset token, builds a reset link from `PASSWORD_RESET_BASE_URL`, and sends it through `PASSWORD_RESET_EMAIL_BACKEND`.
- Supported reset email backends are `console`, `smtp`, and `disabled`. `console` prints the reset link to service logs for local development. `smtp` sends a plain-text email through the configured SMTP server. `disabled` skips delivery and is intended for tests or explicitly controlled local scenarios.
- Reset tokens expire after `PASSWORD_RESET_TOKEN_TTL_MIN` minutes and are single-use. Successful reset revokes active refresh sessions.
- `debug_token` is not returned by default. Set `PASSWORD_RESET_INCLUDE_DEBUG_TOKEN=true` only for local development or automated tests.

### User Service

Location: `services/user-service`

Owns public user profile information separate from credentials.

Main modules:

| Path | Purpose |
|---|---|
| `app/api/commands/user_command_routes.py` | User profile create, update, and delete routes. |
| `app/api/queries/user_query_routes.py` | User profile list and fetch routes. |
| `app/application/commands/user_command_service.py` | Create, update, delete users. |
| `app/application/queries/user_query_service.py` | List and fetch users. |
| `app/domain/models.py` | User profile persistence model. |
| `app/application/mappers.py` | ORM model to `UserResponse`. |

User endpoints:

| Method | Gateway path | Internal path | Description |
|---|---|---|---|
| GET | `/users` | `/users` | List users with `limit` and `offset`. |
| GET | `/users/{email}` | `/users/{email}` | Fetch a user by email. |
| POST | `/users` | `/users` | Create a user profile. |
| PUT | `/users/{email}` | `/users/{email}` | Partial profile update. |
| DELETE | `/users/{email}` | `/users/{email}` | Delete a profile. |

Shared user schemas:

| Schema | Fields / purpose |
|---|---|
| `CreateUser` | `email`, optional `display_name`, `first_name`, `last_name`. |
| `UpdateUser` | Optional `display_name`, `first_name`, `last_name`. |
| `UserResponse` | `email`, display/personal fields, `created_at`. |
| `DeleteUserResponse` | `message`, `email`. |

### Room Service

Location: `services/room-service`

Owns room setup and player seating/chip metadata before the game-service snapshots it.

Main modules:

| Path | Purpose |
|---|---|
| `app/api/commands/room_command_routes.py` | Room creation, blind setup, seat reorder, and room deletion routes. |
| `app/api/commands/room_player_command_routes.py` | Join room, chip update, and player elimination routes. |
| `app/api/queries/room_query_routes.py` | Room detail, join-code lookup, and room list routes. |
| `app/api/queries/room_player_query_routes.py` | Player detail routes. |
| `app/application/commands/room_command_service.py` | Create room, set blinds, reorder seats, delete room. |
| `app/application/commands/room_player_command_service.py` | Join room, update chips, eliminate player. |
| `app/application/queries/room_query_service.py` | Room reads. |
| `app/application/queries/room_player_query_service.py` | Player reads. |
| `app/application/room_details.py` | Shared room detail response assembly. |
| `app/application/seat_helpers.py` | Join-seat resolution and seat-reorder validation. |
| `app/application/mappers.py` | Response mappers, including `room_detail_to_response`. |
| `app/infrastructure/repositories/room_repository.py` | Room code generation, join-code lookup, blind-level queries. |
| `app/infrastructure/repositories/room_player_repository.py` | Room-player list, count, seat, and name lookup queries. |
| `app/domain/models.py` | `Room`, `RoomPlayer`, `BlindLevel`. |
| `app/domain/events.py` | Room event builder. |
| `app/infrastructure/outbox_worker.py` | Outbox publishing loop. |

Room endpoints:

| Method | Gateway path | Internal path | Description |
|---|---|---|---|
| POST | `/rooms` | `/rooms` | Create a room. |
| GET | `/rooms` | `/rooms` | List rooms with `limit`, `offset`, optional `status`. |
| GET | `/rooms/{room_id}` | `/rooms/{room_id}` | Get room detail: room, players, blind levels. |
| GET | `/rooms/code/{code}` | `/rooms/code/{code}` | Get room detail by join code. |
| POST | `/rooms/join/{code}` | `/rooms/join/{code}` | Join a waiting room by code. |
| PUT | `/rooms/{room_id}/blinds` | `/rooms/{room_id}/blinds` | Replace blind structure and starting dealer seat. |
| PUT | `/rooms/{room_id}/seats` | `/rooms/{room_id}/seats` | Reassign player seats while room is waiting. |
| DELETE | `/rooms/{room_id}` | `/rooms/{room_id}` | Delete room plus room players/blinds. |
| GET | `/players/{player_id}` | `/players/{player_id}` | Fetch room player. |
| PUT | `/players/{player_id}/chips` | `/players/{player_id}/chips` | Update player chip count. |
| POST | `/players/{player_id}/eliminate` | `/players/{player_id}/eliminate` | Mark player eliminated and set chips to zero. |

Room schemas:

| Schema | Fields / purpose |
|---|---|
| `CreateRoom` | Optional `name`, `max_players` 2-10, `starting_chips`, `antes_enabled`, `created_by`. |
| `JoinRoom` | `player_name`, optional `seat_number`. |
| `SeatAssignment` | `player_id`, `seat_number`. |
| `ReorderSeats` | List of `SeatAssignment` entries. |
| `BlindLevelInput` | `level`, `small_blind`, `big_blind`, `ante`, `duration_minutes`. |
| `SetBlindStructure` | `levels`, `starting_dealer_seat`. |
| `RoomResponse` | Room identity, code, name, status, max players, starting chips, ante flag, creator, created time. |
| `RoomPlayerResponse` | Player id, room id, name, seat number, chip count, active/eliminated flags, joined time. |
| `BlindLevelResponse` | Blind level fields. |
| `RoomDetailResponse` | Room response plus ordered players, blind levels, starting dealer seat. |
| `UpdateChips` | `chip_count`. |
| `DeleteRoomResponse` | `message`, `room_id`. |

Room behavior notes:

- New rooms start in `WAITING` status.
- Join codes are uppercase alphanumeric codes generated with `secrets.choice`.
- Players can join only while the room is waiting.
- Duplicate player names in the same room are rejected.
- If no requested seat is supplied, seats use `max(seat_number) + 1`.
- Requested seats and reordered seats must be within room capacity and unique.
- Blind structures can be replaced only while the room is waiting.

### Game Service

Location: `services/game-service`

Owns the poker engine, game lifecycle, round state, betting, settlement, ledger, replay, and table runtime.

Main application modules:

| Path | Purpose |
|---|---|
| `app/api/routes.py` | Game, round, bet, correction, analysis, table runtime endpoints. |
| `app/application/commands/game_command_service.py` | Start game/round, resolve hand, advance street/blinds, declare winner, end game. |
| `app/application/commands/bet_command_service.py` | Place a bet through validation, action pipeline, CAS, idempotency. |
| `app/application/commands/correction_command_service.py` | Reverse action, adjust stack, reopen hand, correct payout. |
| `app/application/commands/table_runtime_command_service.py` | Pause/resume, record hand completion, session status. |
| `app/application/queries/game_query_service.py` | Game/round reads, replay, timeline, settlement explanation, consistency, table state. |
| `app/application/queries/bet_query_service.py` | Bet list, pot, player bet summaries. |
| `app/application/action_helpers.py` | Helpers to write `Bet`, `HandLedgerEntry`, and outbox events. |
| `app/application/mappers.py` | ORM/domain objects to shared response schemas. |

Game endpoints:

| Method | Gateway path | Internal path | Description |
|---|---|---|---|
| POST | `/games` | `/games` | Start a game for a room. |
| GET | `/games/{game_id}` | `/games/{game_id}` | Fetch game details. |
| GET | `/games/room/{room_id}` | `/games/room/{room_id}` | Fetch active game for a room. |
| POST | `/games/{game_id}/rounds` | `/games/{game_id}/rounds` | Start a new round/hand. |
| GET | `/games/{game_id}/rounds` | `/games/{game_id}/rounds` | List game rounds. |
| GET | `/games/{game_id}/rounds/active` | `/games/{game_id}/rounds/active` | Fetch active round. |
| POST | `/games/{game_id}/advance-blinds` | `/games/{game_id}/advance-blinds` | Move to next configured blind level. |
| POST | `/games/{game_id}/end` | `/games/{game_id}/end` | Mark game as finished. |
| POST | `/games/{game_id}/pause` | `/games/{game_id}/pause` | Pause table runtime. Internal route only currently; not exposed by gateway route file. |
| POST | `/games/{game_id}/resume` | `/games/{game_id}/resume` | Resume table runtime. Internal route only currently; not exposed by gateway route file. |
| POST | `/games/{game_id}/record-hand-completed` | `/games/{game_id}/record-hand-completed` | Increment hand/blind-clock counters. Internal route only currently; not exposed by gateway route file. |
| GET | `/games/{game_id}/session-status` | `/games/{game_id}/session-status` | Read table runtime status. Internal route only currently; not exposed by gateway route file. |

Round endpoints:

| Method | Gateway path | Internal path | Description |
|---|---|---|---|
| GET | `/rounds/{round_id}` | `/rounds/{round_id}` | Fetch round details. |
| POST | `/rounds/{round_id}/resolve` | `/rounds/{round_id}/resolve` | Resolve hand with pot payouts. |
| POST | `/rounds/{round_id}/advance-street` | `/rounds/{round_id}/advance-street` | Move from preflop/flop/turn/river or mark showdown/settle. |
| POST | `/rounds/{round_id}/winner` | `/rounds/{round_id}/winner` | Shortcut to award full pot to one winner. |
| GET | `/rounds/{round_id}/ledger` | `/rounds/{round_id}/ledger` | Return immutable ledger entries. |
| GET | `/rounds/{round_id}/hand-state` | `/rounds/{round_id}/hand-state` | Rebuild hand state from ledger. |
| GET | `/rounds/{round_id}/replay` | `/rounds/{round_id}/replay` | Step-by-step replay snapshots. |
| GET | `/rounds/{round_id}/timeline` | `/rounds/{round_id}/timeline` | Per-street action timeline. |
| GET | `/rounds/{round_id}/settlement-explanation` | `/rounds/{round_id}/settlement-explanation` | Pot breakdown and narrative. |
| GET | `/rounds/{round_id}/consistency-check` | `/rounds/{round_id}/consistency-check` | Compare live projection against ledger replay. |
| GET | `/rounds/{round_id}/table-state` | `/rounds/{round_id}/table-state` | Frontend-oriented authoritative state. |
| WS | `/rounds/{round_id}/table-state/ws` | N/A | Gateway WebSocket that sends an initial table-state snapshot, pushes updates on RabbitMQ/outbox events, and sends reconciliation snapshots. Optional `reconcile_interval` query parameter, clamped to 1-300 seconds. Legacy `interval` is also accepted. |

Bet endpoints:

| Method | Gateway path | Internal path | Description |
|---|---|---|---|
| POST | `/bets` | `/bets` | Submit a betting action. |
| GET | `/bets/round/{round_id}` | `/bets/round/{round_id}` | List bets for a round. |
| GET | `/bets/round/{round_id}/pot` | `/bets/round/{round_id}/pot` | Read pot total and bets. |
| GET | `/bets/round/{round_id}/players` | `/bets/round/{round_id}/players` | Per-player bet summary. |

Correction endpoints:

| Method | Gateway path | Internal path | Description |
|---|---|---|---|
| POST | `/rounds/{round_id}/corrections/reverse-action` | Same | Reverse a ledger entry and project it into live state. |
| POST | `/rounds/{round_id}/corrections/adjust-stack` | Same | Adjust a player's stack by delta. |
| POST | `/rounds/{round_id}/corrections/reopen-hand` | Same | Reopen a completed hand. |
| POST | `/rounds/{round_id}/corrections/correct-payout` | Same | Move payout amount from old winner to new winner. |

Game schemas:

| Schema | Fields / purpose |
|---|---|
| `StartGame` | `room_id`. |
| `GameResponse` | Game id, room id, status, blind level, level start, dealer/SB/BB seats, hand counters, created time. |
| `RoundResponse` | Round id, game id, number, dealer/SB/BB, blind amounts, ante, status, pot, street, actor, highest bet, min raise, action closed, players, payouts, timestamps. |
| `RoundPlayerResponse` | Player id, seat, remaining stack, street/hand commitments, folded/all-in/active flags. |
| `PlaceBet` | `round_id`, `player_id`, `action`, `amount`, optional `idempotency_key`, optional `expected_version`. |
| `BetResponse` | Bet id, round id, player id, action, amount, created time. |
| `ResolveHandRequest` | List of pot payouts. |
| `PotPayout` | `pot_index`, `pot_type`, `amount`, list of winner shares. |
| `WinnerShare` | `player_id`, `amount`. |
| `ResolveHandResponse` | Round id, status, pot amount, payout list. |
| `DeclareWinner` | `winner_player_id`. |
| `AdvanceStreetResponse` | Street advance action, round/game ids, street, acting player, bet state, winner if settled, players. |
| `LedgerEntryResponse` | Entry id, round id, type, player, amount, detail, original entry, dealer, created time. |
| `HandStateResponse` | Ledger-rebuilt state: pot, completion flags, reversed ids, payout corrections, player snapshots. |
| `ReplayResponse` | Replay steps and consistency flag. |
| `TimelineResponse` | Streets, payouts, corrections. |
| `SettlementExplanationResponse` | Pot explanations and narrative lines. |
| `ConsistencyCheckResponse` | Boolean and discrepancy list. |
| `TableStateResponse` | Frontend table state with legal actions and `state_version`. |
| `SessionStatusResponse` | Table runtime counters, current blind information, and optional `seconds_until_blind_advance`. |

---

## Game Engine Reference

### Data Model Roles

| Table | Role | Description |
|---|---|---|
| `Game` | Authoritative game lifecycle | Active/paused/finished state, current blind level, level start, current dealer/SB/BB seats, hand counters. |
| `Round` | Mutable hand projection | Current street, pot, acting player, highest bet, min raise, completion flags, version fields. |
| `RoundPlayer` | Mutable player hand projection | Stack remaining, committed chips, fold/all-in/active status. |
| `HandLedgerEntry` | Immutable audit trail | Append-only record for blinds, antes, bets, payouts, corrections, and completion. |
| `Bet` | Read model | Denormalized action history for query convenience and backward compatibility. |
| `RoundPayout` | Settlement record | Records who received chips from each pot. |
| `RoomSnapshot` | Anti-corruption snapshot | Room metadata copied at game start. |
| `RoomSnapshotPlayer` | Snapshot player rows | Player id, name, seat, chips, active/eliminated flags. |
| `RoomSnapshotBlindLevel` | Snapshot blind rows | Level, SB, BB, ante, duration. |

Rule of thumb:

- `Round` + `RoundPlayer` answer "what is happening right now?"
- `HandLedgerEntry` answers "what happened, exactly, in order?"
- `Bet` supports quick action-history queries but overlaps with ledger data.
- `RoomSnapshot*` isolates game play from room-service availability after game start.

### Domain Modules

#### `domain/engine/positions.py`

Pure dealer/SB/BB placement logic:

| Function | Description |
|---|---|
| `assign_positions(active_seats, starting_dealer)` | Assigns dealer, small blind, and big blind from active seats at game start. Heads-up dealer is also SB. |
| `rotate_positions(active_seats, current_dealer)` | Moves dealer clockwise and derives SB/BB for the next hand. |

`GameCommandService` keeps `_assign_positions` and `_rotate_positions` wrappers for compatibility with existing tests/callers, but the logic lives in the domain engine.

#### `domain/engine/blind_posting.py`

Posts forced bets at round start.

| Dataclass | Description |
|---|---|
| `SeatPlayer` | Input player id, seat, starting stack. |
| `PostedPlayer` | Output stack and commitments after forced bets. |
| `BlindPostingResult` | Posted players, pot total, current highest bet. |

Function:

| Function | Description |
|---|---|
| `post_blinds_and_antes(...)` | Deducts antes first, then SB/BB, capped by stack; sets all-in when stack reaches zero. |

#### `domain/engine/validator.py`

Validates a single action before state mutation.

| Dataclass | Description |
|---|---|
| `PlayerState` | Frozen player state snapshot. |
| `HandContext` | Frozen hand context, including players and acting player. |
| `ValidatedAction` | Resolved action and effective amount. |

Main function:

| Function | Description |
|---|---|
| `validate_bet(ctx, player_id, action, amount, rules)` | Enforces round status, action closure, turn order, fold/check/call/bet/raise/all-in semantics, stack limits, and min raise rules. |

Validation behavior:

- `FOLD`: always allowed for an active actor, amount becomes 0.
- `CHECK`: allowed only when call amount is 0.
- `CALL`: allowed only when there is an outstanding amount; short calls become all-in.
- `BET`: allowed only when no bet exists on the street.
- `RAISE`: allowed only when a bet exists; `amount` is total street commitment, not just extra chips.
- `ALL_IN`: commits full remaining stack.

#### `domain/engine/turn_engine.py`

Determines who acts next.

| Dataclass | Description |
|---|---|
| `ActionSeat` | Player id, seat, fold/all-in/active flags, street commitment. |
| `NextActorResult` | Next player id/seat or round-closed result. |

Function:

| Function | Description |
|---|---|
| `next_to_act(players, current_actor_seat, last_aggressor_seat, current_highest_bet)` | Scans clockwise, skips folded/all-in/inactive seats, closes action when everyone has matched or action returns to aggressor. |

#### `domain/engine/action_pipeline.py`

Central transition pipeline.

| Dataclass | Description |
|---|---|
| `PlayerMutation` | Stack/commit/fold/all-in changes for one player. |
| `RoundMutation` | Pot, highest bet, min raise, next actor, aggressor, closure changes. |
| `HandTransition` | Full pure transition result. |
| `ApplyActionResult` | Simplified adapter result for application code. |

Functions:

| Function | Description |
|---|---|
| `transition_hand_state(...)` | Pure function that validates and computes state changes. |
| `apply_action(round, players, player_id, action, amount, expected_version)` | ORM adapter that builds context, applies mutation to models, and increments `state_version`. |

#### `domain/engine/street_progression.py`

Moves a closed betting street forward.

| Function | Description |
|---|---|
| `next_street(current)` | Returns preflop -> flop -> turn -> river -> showdown. |
| `find_first_to_act(eligible, reference_seat)` | Finds first eligible seat clockwise. |
| `evaluate_street_end(...)` | Returns next street, showdown, or settle-hand action. |

#### `domain/engine/side_pots.py`

Calculates main and side pots.

| Dataclass | Description |
|---|---|
| `PlayerContribution` | Player id, committed amount, folded flag, showdown flag. |
| `Pot` | Pot index, amount, contributor ids, eligible winner ids. |

Function:

| Function | Description |
|---|---|
| `calculate_side_pots(players)` | Slices commitment levels into pots and merges dead pots forward. |

#### `domain/engine/payout_validation.py`

Validates submitted settlement against computed side pots.

| Function | Description |
|---|---|
| `validate_payouts_against_side_pots(round_players, submitted_payouts, total_pot)` | Verifies pot indices, amounts, total pot, and winner eligibility. |

#### `domain/engine/table_runtime.py`

Pure table/session state machine.

| Component | Description |
|---|---|
| `SeatStatus` | `ACTIVE`, `SITTING_OUT`, `EMPTY`. |
| `TableStatus` | `WAITING`, `RUNNING`, `PAUSED`, `FINISHED`. |
| `TableSeat` | Seat/player/chip/sit-out information. |
| `BlindClock` | Blind level, level start time, hands at current level. |
| `TableRuntime` | Session lifecycle, active seats, sit-in/out, hand completion. |

#### `domain/ledger/hand_ledger.py`

Immutable hand event application and state rebuilding.

| Dataclass | Description |
|---|---|
| `LedgerRow` | Input row for replay/rebuild. |
| `PlayerSnapshot` | Rebuilt player-level state. |
| `HandState` | Rebuilt aggregate state. |

Functions:

| Function | Description |
|---|---|
| `apply_entry(state, entry)` | Applies blind/ante/bet/payout/completion/correction entries. |
| `rebuild_hand_state(entries)` | Replays all ledger rows into a fresh `HandState`. |

#### `domain/ledger/hand_replay.py`

| Function | Description |
|---|---|
| `replay_hand(entries)` | Captures a state snapshot after each ledger entry. |
| `verify_consistency(entries, live_pot_total, live_player_committed)` | Compares ledger-rebuilt state to live projection values. |

#### `domain/ledger/hand_history.py`

| Function | Description |
|---|---|
| `build_hand_timeline(round_id, entries)` | Builds per-street actions, running pot totals, payouts, and corrections. |

#### `domain/reporting/settlement_explainer.py`

| Function | Description |
|---|---|
| `explain_settlement(contributions, submitted_payouts)` | Produces structured pot explanations and narrative text. |

#### `domain/scenario_runner.py`

Declarative test DSL for full hand scenarios.

| Component | Description |
|---|---|
| `HandScenario` | Players, blinds, dealer seat, scripted actions, expectations. |
| `run_scenario(...)` | Runs actions through the real engine and evaluates expectations. |

#### `domain/integration/room_adapter.py`

Anti-corruption DTOs/protocol between room-service and game-service.

| Component | Description |
|---|---|
| `BlindLevelConfig` | Blind level DTO. |
| `PlayerConfig` | Player DTO. |
| `RoomConfig` | Room snapshot DTO with `active_players`, `active_seats`, and `blind_level()`. |
| `RoomConfigProvider` | Protocol for live fetch, snapshot save, snapshot load. |

#### `domain/rules.py`

| Component | Description |
|---|---|
| `RulesProfile` | Frozen config for a poker rules profile. |
| `NO_LIMIT_HOLDEM` | Current rules profile used by the engine. |

#### `domain/exceptions.py`

Pure domain error hierarchy rooted at `DomainError`. HTTP handling is kept outside domain logic.

Notable exceptions include:

`RoundNotActive`, `ActionClosed`, `AlreadyAtShowdown`, `PlayerNotInHand`, `PlayerAlreadyFolded`, `PlayerAlreadyAllIn`, `NotYourTurn`, `IllegalAction`, `CheckNotAllowed`, `CallNotAllowed`, `BetNotAllowed`, `RaiseNotAllowed`, `RaiseBelowMinimum`, `AmountExceedsStack`, `InvalidAmount`, `GameNotActive`, `GameAlreadyExists`, `NotFound`, `LedgerEntryNotFound`, `EntryAlreadyReversed`, `CannotReverseCorrection`, `PayoutExceedsPot`, `PayoutEmpty`, `PayoutMismatch`, `StaleStateError`, `DuplicateActionError`, `IdempotencyConflict`.

---

## Shared Library

Location: `shared`

| Path | Purpose |
|---|---|
| `shared/core/auth/roles.py` | Role normalization helpers. |
| `shared/core/db/session.py` | Async DB factory, FastAPI dependency factory, `atomic()` savepoint helper. |
| `shared/core/db/crud.py` | Generic `fetch_or_404()` and `apply_partial_update()`. |
| `shared/core/messaging/mq.py` | RabbitMQ publisher and config. |
| `shared/core/messaging/events.py` | Domain-event builder helpers. |
| `shared/core/messaging/consumer.py` | RabbitMQ consumer with retry/DLQ topology. |
| `shared/core/outbox/model.py` | Outbox model factory. |
| `shared/core/outbox/helpers.py` | `add_outbox_event()`. |
| `shared/core/outbox/worker.py` | Polling publisher loop and stats. |
| `shared/schemas/*.py` | Cross-service request/response Pydantic schemas. |

---

## Gateway Service

Location: `services/gateway-service`

The gateway is the intended public API surface.

Main modules:

| Path | Purpose |
|---|---|
| `app/main.py` | FastAPI app, route registration, correlation middleware, client shutdown. |
| `app/clients/service_client.py` | Persistent service clients for auth/user/room/game. |
| `app/infrastructure/table_state_ws.py` | In-memory WebSocket subscription manager keyed by `round_id`. |
| `app/infrastructure/table_state_fanout.py` | Fetches authoritative game-service table state and broadcasts to subscribers. |
| `app/infrastructure/table_state_events.py` | RabbitMQ consumer for table-state-relevant outbox events. |
| `app/utils/proxy.py` | Response forwarding and error propagation. |
| `app/routes/auth_routes.py` | Auth and auth-user proxy routes. |
| `app/routes/user_routes.py` | User profile proxy routes. |
| `app/routes/room_routes.py` | Room proxy routes. |
| `app/routes/player_routes.py` | Player proxy routes. |
| `app/routes/game_routes.py` | Game proxy routes. |
| `app/routes/round_routes.py` | Round/correction/analysis proxy routes. |
| `app/routes/bet_routes.py` | Bet proxy routes. |

The gateway adds or propagates `X-Correlation-ID` for each request.

Table-state WebSocket behavior:

- Clients connect to `WS /rounds/{round_id}/table-state/ws`.
- The gateway subscribes that socket to the `round_id` and immediately sends the current table-state snapshot from game-service.
- The gateway consumes RabbitMQ events from the shared domain-event exchange. By default it reacts to `bet.placed`, `game.round_started`, `game.round_completed`, `game.street_advanced`, and `game.correction_applied`.
- On each event with a `round_id`, the gateway fetches `GET /rounds/{round_id}/table-state` from game-service and broadcasts that authoritative snapshot to connected clients for that round.
- The socket also sends a slower reconciliation snapshot every `TABLE_STATE_RECONCILE_INTERVAL_SECONDS` seconds so clients recover if an event is missed.

---

## Quick Start

Prerequisites:

- Docker and Docker Compose.
- Python 3.13 for local tests.

Start infrastructure and services:

```bash
make up
```

Run migrations:

```bash
make migrate-all
```

View logs:

```bash
make logs
```

Useful commands:

```bash
make build
make down
make ps
make restart
make migrate-auth
make migrate-user
make migrate-room
make migrate-game
make openapi
```

Service URLs:

| Service | URL |
|---|---|
| Gateway | `http://localhost:8000` |
| Room service | `http://localhost:8001` |
| Game service | `http://localhost:8002` |
| Auth service | `http://localhost:8004` |
| User service | `http://localhost:8005` |
| RabbitMQ management | `http://localhost:15672` |

---

## Running Tests

Install dependencies:

```bash
pip install -r requirements-test.txt
cd shared
pip install -e ".[test]"
cd ..
```

Install service requirements as needed:

```bash
pip install -r services/auth-service/requirements.txt
pip install -r services/user-service/requirements.txt
pip install -r services/room-service/requirements.txt
pip install -r services/game-service/requirements.txt
pip install -r services/gateway-service/requirements.txt
```

Run unit tests:

```bash
python -m pytest tests/unit
```

Run all tests:

```bash
python -m pytest tests
```

Run compile check:

```bash
python -m compileall services shared tests
```

Current local verification:

```text
python -m compileall services shared tests
python -m pytest tests/unit
404 passed
```

Integration tests live under `tests/integration` and are intended for database-backed behavior such as PostgreSQL concurrency.

---

## Test Coverage Map

Current unit suite size: 404 tests.

| Area | What it covers |
|---|---|
| Auth infrastructure | Password hashing, JWTs, refresh token helpers, password reset email flow. |
| Gateway table-state fanout | WebSocket subscription manager and RabbitMQ event-triggered table-state broadcasts. |
| User CRUD | Create/list/fetch user profile behavior. |
| Room repository | Room codes, room lookup, players ordered by seat, counts, duplicate names. |
| Bet validator | Turn rules, fold/check/call/bet/raise/all-in validation, stack and min-raise rules. |
| Blind posting | Antes, SB/BB, heads-up, short stacks, mixed stacks. |
| Position rotation | Dealer/SB/BB assignment and rotation including heads-up and wraparound. |
| Turn engine | Clockwise action, skipped folded/all-in players, closure at aggressor, all-in cases. |
| Street progression | Next street, showdown triggers, settle-hand triggers, first actor per street. |
| Action pipeline | State mutation and action progression through the unified transition path. |
| Side pots | Main/side pots, folded players, dead-pot merging, chip conservation. |
| Payout validation | Payout amount, pot index, eligibility checks. |
| Hand ledger | Rebuilds, reversals, stack adjustments, reopen/correct payout workflows. |
| Hand replay/timeline/explainer | Replay snapshots, consistency, timeline, settlement explanation. |
| Scenario runner | Declarative full-hand scenarios. |
| Table runtime | Seat state, pause/resume, blind clock, hand counters. |
| Settlement transactions | Atomic savepoints and rollback behavior. |
| Integration-style unit flows | Full betting rounds, street transitions, settlement and ledger rebuilds. |

---

## Project Structure

```text
.
|-- shared/
|   |-- core/
|   |   |-- auth/
|   |   |-- db/
|   |   |-- messaging/
|   |   `-- outbox/
|   `-- schemas/
|-- services/
|   |-- auth-service/
|   |-- user-service/
|   |-- room-service/
|   |-- game-service/
|   |   `-- app/
|   |       |-- api/
|   |       |-- application/
|   |       |   |-- commands/
|   |       |   `-- queries/
|   |       |-- domain/
|   |       |   |-- engine/
|   |       |   |-- integration/
|   |       |   |-- ledger/
|   |       |   `-- reporting/
|   |       `-- infrastructure/
|   `-- gateway-service/
|-- tests/
|   |-- unit/
|   `-- integration/
|-- docker-compose.yml
|-- Makefile
|-- init-databases.sql
|-- requirements-test.txt
`-- README.md
```

---

## Docker Compose Environment

`docker-compose.yml` starts:

- PostgreSQL 15 with the `poker` user.
- RabbitMQ 3 with the management UI.
- `auth-service`, `user-service`, `room-service`, `game-service`, and `gateway-service`.

Key environment variables:

| Variable | Used by | Purpose |
|---|---|---|
| `AUTH_DB` | auth-service | Async SQLAlchemy URL for auth database. |
| `USER_DB` | user-service | Async SQLAlchemy URL for user database. |
| `ROOM_DB` | room-service | Async SQLAlchemy URL for room database. |
| `GAME_DB` | game-service | Async SQLAlchemy URL for game database. |
| `JWT_SECRET` | auth-service | JWT signing secret. |
| `PASSWORD_RESET_BASE_URL` | auth-service | Frontend reset-password URL used to build email links. Defaults to `http://localhost:3000/reset-password`. |
| `PASSWORD_RESET_TOKEN_TTL_MIN` | auth-service | Reset token lifetime in minutes. Defaults to `60`. |
| `PASSWORD_RESET_EMAIL_BACKEND` | auth-service | Reset email backend: `console`, `smtp`, or `disabled`. Defaults to `console`. |
| `PASSWORD_RESET_INCLUDE_DEBUG_TOKEN` | auth-service | When true, includes `debug_token` in `/forgot-password` responses. Defaults to false. |
| `SMTP_HOST` | auth-service | SMTP host required when `PASSWORD_RESET_EMAIL_BACKEND=smtp`. |
| `SMTP_PORT` | auth-service | SMTP port. Defaults to `587`. |
| `SMTP_USERNAME` | auth-service | Optional SMTP username. |
| `SMTP_PASSWORD` | auth-service | Optional SMTP password. |
| `SMTP_FROM_EMAIL` | auth-service | Sender address for password reset email. Defaults to `no-reply@localhost`. |
| `SMTP_USE_TLS` | auth-service | Enables SMTP STARTTLS. Defaults to true. |
| `SMTP_TIMEOUT_SECONDS` | auth-service | SMTP connection timeout. Defaults to `10`. |
| `RABBIT_URL` | room/game/user/gateway services | RabbitMQ connection URL. |
| `EXCHANGE_NAME` | room/game/user/gateway services | Topic exchange name. |
| `ROOM_SERVICE_URL` | game-service/gateway | Room service base URL. |
| `GAME_SERVICE_URL` | gateway | Game service base URL. |
| `AUTH_SERVICE_URL` | gateway | Auth service base URL. |
| `USER_SERVICE_URL` | gateway | User service base URL. |
| `TABLE_STATE_EVENT_ROUTING_KEYS` | gateway | Comma-separated event routing keys that trigger WebSocket table-state pushes. Defaults to bet/round/correction events. |
| `TABLE_STATE_RECONCILE_INTERVAL_SECONDS` | gateway | WebSocket reconciliation snapshot interval. Defaults to `30`. |
| `TABLE_STATE_EVENT_CONSUMER_QUEUE` | gateway | RabbitMQ queue name for table-state event fanout. Defaults to `gateway.table_state.events`. |
| `TABLE_STATE_EVENT_RETRY_DELAY_MS` | gateway | Retry delay for failed table-state event handling. Defaults to `5000`. |
| `TABLE_STATE_EVENT_MAX_RETRIES` | gateway | Max retries before a table-state event goes to DLQ. Defaults to `3`. |

---

## Tech Stack

- Python 3.13
- FastAPI
- SQLAlchemy 2 async
- Alembic
- Pydantic 2
- PostgreSQL / asyncpg
- RabbitMQ / aio-pika
- httpx
- bcrypt
- python-jose
- Docker Compose
- pytest

---

## Recent Cleanup Notes

The latest code state includes these cleanup changes:

- Room detail response assembly is centralized in `build_room_detail_response()`.
- Gateway table-state WebSockets are event-driven from RabbitMQ/outbox events, with reconciliation snapshots as a fallback.
- Dealer/SB/BB assignment and rotation are centralized in `domain/engine/positions.py`.
- Room code generation uses `secrets.choice`.
- The unused `get_latest_round()` helper was removed from game repository documentation/code.
- The empty `EliminatePlayer` schema was removed; eliminate player endpoint does not require a request body.
- Mojibake log strings were normalized to ASCII.

---

## Future Work

- Add a poker hand evaluator for showdown hand ranking.
- Expose table runtime routes through the gateway if they should be public.
- Add rate limiting to the gateway.
- Add metrics and distributed tracing.
- Consider replacing `Bet` read model with ledger-backed queries once frontend needs are clear.
