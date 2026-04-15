from ..domain.models import Room, RoomPlayer, BlindLevel
from ..domain.schemas import RoomResponse, RoomPlayerResponse, BlindLevelResponse

def room_to_response(room: Room) -> RoomResponse:
    return RoomResponse(
        room_id=room.room_id,
        code=room.code,
        name=room.name,
        status=room.status,
        max_players=room.max_players,
        starting_chips=room.starting_chips,
        antes_enabled=room.antes_enabled,
        created_by=room.created_by,
        created_at=room.created_at,
    )

def player_to_response(player: RoomPlayer) -> RoomPlayerResponse:
    return RoomPlayerResponse(
        player_id=player.player_id,
        room_id=player.room_id,
        player_name=player.player_name,
        seat_number=player.seat_number,
        chip_count=player.chip_count,
        is_active=bool(player.is_active),
        is_eliminated=bool(player.is_eliminated),
        joined_at=player.joined_at,
    )

def blind_level_to_response(bl: BlindLevel) -> BlindLevelResponse:
    return BlindLevelResponse(
        level=bl.level,
        small_blind=bl.small_blind,
        big_blind=bl.big_blind,
        ante=bl.ante,
        duration_minutes=bl.duration_minutes,
    )