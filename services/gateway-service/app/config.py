from __future__ import annotations

import os

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8000")
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://user-service:8000")
ROOM_SERVICE_URL = os.getenv("ROOM_SERVICE_URL", "http://room-service:8000")
GAME_SERVICE_URL = os.getenv("GAME_SERVICE_URL", "http://game-service:8000")
BETTING_SERVICE_URL = os.getenv("BETTING_SERVICE_URL", "http://betting-service:8000")

SERVICE_NAME = "gateway-service"
SERVICE_LOG_PREFIX = f"[{SERVICE_NAME}]"