.PHONY: up down build logs migrate-auth migrate-user migrate-room migrate-game migrate-all restart ps

up:
	docker compose up -d --build

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

migrate-auth:
	docker compose exec auth-service alembic upgrade head

migrate-user:
	docker compose exec user-service alembic upgrade head

migrate-room:
	docker compose exec room-service alembic upgrade head

migrate-game:
	docker compose exec game-service alembic upgrade head

migrate-all: migrate-auth migrate-user migrate-room migrate-game

restart:
	docker compose restart

ps:
	docker compose ps
