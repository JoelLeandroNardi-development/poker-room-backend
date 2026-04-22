from __future__ import annotations

import os

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8000")
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://user-service:8000")
ROOM_SERVICE_URL = os.getenv("ROOM_SERVICE_URL", "http://room-service:8000")
GAME_SERVICE_URL = os.getenv("GAME_SERVICE_URL", "http://game-service:8000")

RABBIT_URL = os.getenv("RABBIT_URL")
EXCHANGE_NAME = os.getenv("EXCHANGE_NAME", "domain_events").strip() or "domain_events"

TABLE_STATE_EVENT_ROUTING_KEYS = [
    key.strip()
    for key in os.getenv(
        "TABLE_STATE_EVENT_ROUTING_KEYS",
        ",".join([
            "bet.placed",
            "game.round_started",
            "game.round_completed",
            "game.street_advanced",
            "game.correction_applied",
        ]),
    ).split(",")
    if key.strip()
]

TABLE_STATE_RECONCILE_INTERVAL_SECONDS = float(
    os.getenv("TABLE_STATE_RECONCILE_INTERVAL_SECONDS", "30")
)
TABLE_STATE_EVENT_CONSUMER_QUEUE = os.getenv(
    "TABLE_STATE_EVENT_CONSUMER_QUEUE",
    "gateway.table_state.events",
)
TABLE_STATE_EVENT_RETRY_DELAY_MS = int(
    os.getenv("TABLE_STATE_EVENT_RETRY_DELAY_MS", "5000")
)
TABLE_STATE_EVENT_MAX_RETRIES = int(
    os.getenv("TABLE_STATE_EVENT_MAX_RETRIES", "3")
)

SERVICE_NAME = "gateway-service"
SERVICE_LOG_PREFIX = f"[{SERVICE_NAME}]"