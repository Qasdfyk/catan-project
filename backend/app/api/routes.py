import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from app.schemas.game_schemas import GameCreateRequest, GameResponse
from app.models.game import GameState
from app.services.serializer import GameSerializer
from app.services.redis_service import RedisService

router = APIRouter()

@router.post("/games", response_model=GameResponse)
async def create_game(request: Request, body: GameCreateRequest):
    """
    Creates new game, saves it in Redis, return room_id.
    """
    room_id = str(uuid.uuid4())[:8]
    
    try:
        game = GameState.create_new_game(body.player_names)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    game_dict = GameSerializer.game_to_dict(game)
    
    redis: RedisService = request.app.state.redis
    await redis.save_game_state(room_id, game_dict)
    
    return GameResponse(
        room_id=room_id,
        status="created",
        created_at=datetime.now().isoformat(),
        players=[p.name for p in game.players]
    )

@router.get("/games/{room_id}")
async def get_game_state(request: Request, room_id: str):
    """
    Return current game state from Redis.
    """
    redis: RedisService = request.app.state.redis
    game_data = await redis.get_game_state(room_id)
    
    if not game_data:
        raise HTTPException(status_code=404, detail="Game not found")
        
    return game_data