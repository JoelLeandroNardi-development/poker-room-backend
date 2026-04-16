
from __future__ import annotations

import os

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.exceptions import NotFound
from ..domain.models import RoomSnapshot, RoomSnapshotBlindLevel, RoomSnapshotPlayer
from ..domain.room_adapter import BlindLevelConfig, PlayerConfig, RoomConfig, RoomConfigProvider

ROOM_SERVICE_URL = os.getenv("ROOM_SERVICE_URL", "http://room-service:8000")


async def fetch_room_config_http(room_id: str) -> RoomConfig:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{ROOM_SERVICE_URL}/rooms/{room_id}")
        if resp.status_code == 404:
            raise NotFound("Room not found")
        resp.raise_for_status()

    data = resp.json()
    return RoomConfig(
        room_id=room_id,
        starting_dealer_seat=data.get("starting_dealer_seat", 1),
        players=[
            PlayerConfig(
                player_id=p["player_id"],
                seat_number=p["seat_number"],
                chip_count=p.get("chip_count", 0),
                is_active=p.get("is_active", True),
                is_eliminated=p.get("is_eliminated", False),
            )
            for p in data.get("players", [])
        ],
        blind_levels=[
            BlindLevelConfig(
                level=bl["level"],
                small_blind=bl["small_blind"],
                big_blind=bl["big_blind"],
                ante=bl.get("ante", 0),
                duration_minutes=bl.get("duration_minutes"),
            )
            for bl in data.get("blind_levels", [])
        ],
    )


async def save_room_snapshot(db: AsyncSession, game_id: str, config: RoomConfig) -> None:
    db.add(RoomSnapshot(
        game_id=game_id,
        room_id=config.room_id,
        starting_dealer_seat=config.starting_dealer_seat,
    ))
    for p in config.players:
        db.add(RoomSnapshotPlayer(
            game_id=game_id,
            player_id=p.player_id,
            seat_number=p.seat_number,
            chip_count=p.chip_count,
            is_active=p.is_active,
            is_eliminated=p.is_eliminated,
        ))
    for bl in config.blind_levels:
        db.add(RoomSnapshotBlindLevel(
            game_id=game_id,
            level=bl.level,
            small_blind=bl.small_blind,
            big_blind=bl.big_blind,
            ante=bl.ante,
            duration_minutes=bl.duration_minutes,
        ))


async def load_room_snapshot(db: AsyncSession, game_id: str) -> RoomConfig:
    res = await db.execute(
        select(RoomSnapshot).where(RoomSnapshot.game_id == game_id)
    )
    snap = res.scalar_one_or_none()
    if snap is None:
        raise NotFound(f"Room snapshot not found for game {game_id}")

    players_res = await db.execute(
        select(RoomSnapshotPlayer)
        .where(RoomSnapshotPlayer.game_id == game_id)
        .order_by(RoomSnapshotPlayer.seat_number.asc())
    )
    players = [
        PlayerConfig(
            player_id=p.player_id,
            seat_number=p.seat_number,
            chip_count=p.chip_count,
            is_active=p.is_active,
            is_eliminated=p.is_eliminated,
        )
        for p in players_res.scalars().all()
    ]

    levels_res = await db.execute(
        select(RoomSnapshotBlindLevel)
        .where(RoomSnapshotBlindLevel.game_id == game_id)
        .order_by(RoomSnapshotBlindLevel.level.asc())
    )
    blind_levels = [
        BlindLevelConfig(
            level=bl.level,
            small_blind=bl.small_blind,
            big_blind=bl.big_blind,
            ante=bl.ante,
            duration_minutes=bl.duration_minutes,
        )
        for bl in levels_res.scalars().all()
    ]

    return RoomConfig(
        room_id=snap.room_id,
        starting_dealer_seat=snap.starting_dealer_seat,
        players=players,
        blind_levels=blind_levels,
    )


class HttpRoomConfigProvider:

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def fetch_live(self, room_id: str) -> RoomConfig:
        return await fetch_room_config_http(room_id)

    async def save_snapshot(self, game_id: str, config: RoomConfig) -> None:
        await save_room_snapshot(self._db, game_id, config)

    async def load_snapshot(self, game_id: str) -> RoomConfig:
        return await load_room_snapshot(self._db, game_id)
