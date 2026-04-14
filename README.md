# poker-room-backend

Backend written in Python and mounted on top of Docker to manage a poker game room with rules, turns, bets — a mathematical engine for following a match. Designed to connect to a frontend app.

## Architecture

| Service | Port | Description |
|---|---|---|
| **gateway-service** | 8000 | Public HTTP façade – proxies all requests |
| **auth-service** | 8004 | Registration, login, JWT tokens, session management |
| **user-service** | 8005 | User profiles (display name, personal info) |
| **room-service** | 8001 | Room creation, join codes, player management, blind structures |
| **game-service** | 8002 | Game lifecycle, rounds, dealer/blind positions, winner declaration |
| **betting-service** | 8003 | Bet placement (call/raise/fold/check/all-in), pot calculation |

**Infrastructure:** PostgreSQL 15 · RabbitMQ 3 (topic exchange) · Docker Compose

### Key patterns

- **CQRS** – command / query separation per service
- **Outbox pattern** – reliable event publishing to RabbitMQ
- **DLQ + retry** – consumer resilience with dead-letter queues
- **Shared package** – cross-cutting DB, messaging, and schema helpers

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
make migrate-auth    # migrate auth-service DB
make migrate-user    # migrate user-service DB
make migrate-room    # migrate room-service DB
make migrate-game    # migrate game-service DB
make migrate-betting # migrate betting-service DB
```

## Tech stack

- Python 3.13 · FastAPI · SQLAlchemy 2 (async) · Pydantic 2
- bcrypt · python-jose (JWT) · aio-pika · asyncpg · httpx · Alembic
- Docker & Docker Compose
