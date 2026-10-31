"""Endpoints for the Go gateway only."""
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.core.config import settings
from app.api.routes import get_rooms
from app.schemas.game_schemas import ActionRequest, SessionRequest
from app.services.room_service import RoomService


async def verify_internal_key(x_internal_key: str = Header(default="")):
    if not secrets.compare_digest(x_internal_key, settings.INTERNAL_API_KEY):
        raise HTTPException(status_code=403, detail="Forbidden")


router = APIRouter(dependencies=[Depends(verify_internal_key)])


@router.post("/rooms/{room_id}/session")
async def get_session(room_id: str, body: SessionRequest, rooms: RoomService = Depends(get_rooms)):
    return await rooms.get_session_state(room_id, body.token)


@router.post("/rooms/{room_id}/actions")
async def perform_action(room_id: str, body: ActionRequest, rooms: RoomService = Depends(get_rooms)):
    await rooms.perform_action(room_id, body.token, body.type, body.payload)
    return {"ok": True}
