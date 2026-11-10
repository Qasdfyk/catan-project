from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from app.schemas.game_schemas import PlayerNameRequest, RoomSession, SessionRequest
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


@router.post("/rooms/{room_id}/rematch", response_model=RoomSession)
async def join_rematch(room_id: str, body: SessionRequest, rooms: RoomService = Depends(get_rooms)):
    """Takes the token of the finished game, so a player keeps their seat in the next one."""
    return await rooms.join_rematch(room_id, body.token)


@router.get("/rooms/{room_id}")
async def get_room(room_id: str, rooms: RoomService = Depends(get_rooms)):
    """Public summary for the join screen. Holds no tokens and no game state."""
    return await rooms.get_summary(room_id)


@router.get("/rooms/{room_id}/record")
async def download_record(room_id: str, rooms: RoomService = Depends(get_rooms)):
    """
    The whole game, hidden cards included, as described in docs/game-record.md.
    Only once the game is over: during it, the record would reveal every hand.
    """
    record = await rooms.get_record(room_id)
    # get_record has checked the ID, so it is safe inside the header
    return JSONResponse(record, headers={"Content-Disposition": f'attachment; filename="catan-{room_id}.json"'})
