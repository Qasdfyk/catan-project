from fastapi import APIRouter, Depends, Request
from app.schemas.game_schemas import PlayerNameRequest, RoomSession
from app.services.room_service import RoomService

router = APIRouter()


def get_rooms(request: Request) -> RoomService:
    return request.app.state.rooms


@router.post("/rooms", response_model=RoomSession)
async def create_room(body: PlayerNameRequest, rooms: RoomService = Depends(get_rooms)):
    return await rooms.create_room(body.name)


@router.post("/rooms/{room_id}/join", response_model=RoomSession)
async def join_room(room_id: str, body: PlayerNameRequest, rooms: RoomService = Depends(get_rooms)):
    return await rooms.join_room(room_id, body.name)


@router.get("/rooms/{room_id}")
async def get_room(room_id: str, rooms: RoomService = Depends(get_rooms)):
    """Public summary for the join screen. Holds no tokens and no game state."""
    return await rooms.get_summary(room_id)
