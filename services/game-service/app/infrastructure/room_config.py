
from __future__ import annotations

import os

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.constants import ErrorMessage
from ..domain.exceptions import NotFound
from ..domain.models import RoundPlayer, RoomSnapshot, RoomSnapshotBlindLevel, RoomSnapshotPlayer
from ..domain.integration.room_adapter import BlindLevelConfig, PlayerConfig, RoomConfig

ROOM_SERVICE_URL = os.getenv("ROOM_SERVICE_URL", "http://room-service:8000")


async def _post_room_status_update(room_id: str, action: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{ROOM_SERVICE_URL}/rooms/{room_id}/{action}")
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to {action} room in room-service",
        ) from exc

    if resp.status_code == 404:
        raise NotFound(ErrorMessage.ROOM_NOT_FOUND)

    if resp.status_code >= 500:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to {action} room in room-service",
        )

    if resp.status_code >= 400:
        try:
            payload = resp.json()
        except ValueError:
            payload = {}
        detail = payload.get("detail") or resp.text or f"Unable to {action} room"
        raise HTTPException(status_code=resp.status_code, detail=detail)

async def fetch_room_config_http(room_id: str) -> RoomConfig:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{ROOM_SERVICE_URL}/rooms/{room_id}")
        if resp.status_code == 404:
            raise NotFound(ErrorMessage.ROOM_NOT_FOUND)
        resp.raise_for_status()

    data = resp.json()
    room_data = data.get("room", {})
    return RoomConfig(
        room_id=room_id,
        starting_dealer_seat=data.get("starting_dealer_seat", 1),
        antes_enabled=bool(room_data.get("antes_enabled", False)),
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
        antes_enabled=config.antes_enabled,
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
        raise NotFound(ErrorMessage.ROOM_SNAPSHOT_NOT_FOUND.format(game_id=game_id))

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
        antes_enabled=bool(snap.antes_enabled),
        players=players,
        blind_levels=blind_levels,
    )


async def mark_room_active_http(room_id: str) -> None:
    await _post_room_status_update(room_id, "activate")


async def mark_room_finished_http(room_id: str) -> None:
    await _post_room_status_update(room_id, "finish")

async def sync_room_snapshot_players_from_round(
    db: AsyncSession,
    game_id: str,
    round_players: list[RoundPlayer],
) -> list[int]:
    players_res = await db.execute(
        select(RoomSnapshotPlayer)
        .where(RoomSnapshotPlayer.game_id == game_id)
        .order_by(RoomSnapshotPlayer.seat_number.asc())
    )
    snapshot_players = players_res.scalars().all()
    snapshot_by_player_id = {player.player_id: player for player in snapshot_players}

    for round_player in round_players:
        snapshot_player = snapshot_by_player_id.get(round_player.player_id)
        if snapshot_player is None:
            continue

        chip_count = max(round_player.stack_remaining, 0)
        snapshot_player.chip_count = chip_count
        snapshot_player.is_active = chip_count > 0
        snapshot_player.is_eliminated = chip_count <= 0

    return [
        player.seat_number
        for player in snapshot_players
        if player.is_active and not player.is_eliminated and player.chip_count > 0
    ]

class HttpRoomConfigProvider:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def fetch_live(self, room_id: str) -> RoomConfig:
        return await fetch_room_config_http(room_id)

    async def save_snapshot(self, game_id: str, config: RoomConfig) -> None:
        await save_room_snapshot(self._db, game_id, config)

    async def load_snapshot(self, game_id: str) -> RoomConfig:
        return await load_room_snapshot(self._db, game_id)