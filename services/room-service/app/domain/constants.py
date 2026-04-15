from __future__ import annotations

from enum import StrEnum

class RoomStatus(StrEnum):
    WAITING = "WAITING"
    ACTIVE = "ACTIVE"
    FINISHED = "FINISHED"

class RoomEventType(StrEnum):
    CREATED = "room.created"
    PLAYER_JOINED = "room.player_joined"
    PLAYER_ELIMINATED = "room.player_eliminated"
    CHIPS_UPDATED = "room.chips_updated"

class EventKey(StrEnum):
    EVENT_ID = "event_id"
    EVENT_TYPE = "event_type"
    DATA = "data"

class DataKey(StrEnum):
    ROOM_ID = "room_id"
    CODE = "code"
    PLAYER_ID = "player_id"
    PLAYER_NAME = "player_name"
    SEAT_NUMBER = "seat_number"
    CHIP_COUNT = "chip_count"
    MAX_PLAYERS = "max_players"
    CREATED_BY = "created_by"

class TableName(StrEnum):
    ROOMS = "rooms"
    ROOM_PLAYERS = "room_players"
    BLIND_LEVELS = "blind_levels"

class ErrorMessage(StrEnum):
    ROOM_NOT_FOUND = "Room not found"
    PLAYER_NOT_FOUND = "Player not found"
    ROOM_FULL = "Room is full"
    ROOM_NOT_WAITING = "Room is not in WAITING status"
    INVALID_CODE = "Invalid room code"
    DUPLICATE_NAME = "A player with that name is already in the room"

class ResponseMessage(StrEnum):
    DELETED = "deleted"

CODE_LENGTH = 4