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
    Tworzy nową grę, zapisuje ją w Redis i zwraca room_id.
    """
    # 1. Generujemy unikalny ID pokoju
    room_id = str(uuid.uuid4())[:8] # np. "a1b2c3d4"
    
    # 2. Tworzymy logikę gry (Python Core)
    try:
        game = GameState.create_new_game(body.player_names)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # 3. Serializacja
    game_dict = GameSerializer.game_to_dict(game)
    
    # 4. Zapis do Redis (używamy serwisu z app.state)
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
    Zwraca aktualny stan gry z Redisa (np. dla debugowania lub reconnectu).
    """
    redis: RedisService = request.app.state.redis
    game_data = await redis.get_game_state(room_id)
    
    if not game_data:
        raise HTTPException(status_code=404, detail="Game not found")
        
    return game_data