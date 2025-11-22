import socketio
from fastapi import FastAPI
from app.services.redis_service import RedisService
from app.services.serializer import GameSerializer
from app.models.game import GameState
from contextlib import asynccontextmanager

# 1. Setup Socket.IO Server
# cors_allowed_origins='*' allows frontend to connect from localhost:3000 or any other port
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')

# 2. Setup FastAPI
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.redis = RedisService()
    yield
    # Shutdown
    await app.state.redis.close()

app = FastAPI(lifespan=lifespan)

# 3. Mount Socket.IO app
socket_app = socketio.ASGIApp(sio, app)
app.mount("/", socket_app) # Mount at root, socket.io handles /socket.io/ path

# --- Event Handlers (Placeholder for now) ---

@sio.event
async def connect(sid, environ):
    print(f"Client connected: {sid}")

@sio.event
async def disconnect(sid):
    print(f"Client disconnected: {sid}")

@sio.event
async def create_test_game(sid):
    """
    Temporary event to test Redis serialization.
    Creates a game, saves it to Redis, reads it back, and confirms logic works.
    """
    print(f"Creating test game for {sid}...")
    
    # 1. Logic
    game = GameState.create_new_game(["Player1", "Player2"])
    room_id = "room_test_1"
    
    # 2. Serialization
    game_dict = GameSerializer.game_to_dict(game)
    
    # 3. Save to Redis
    redis: RedisService = app.state.redis
    await redis.save_game_state(room_id, game_dict)
    print("Game saved to Redis.")
    
    # 4. Load from Redis
    loaded_dict = await redis.get_game_state(room_id)
    if loaded_dict:
        loaded_game = GameSerializer.dict_to_game(loaded_dict)
        print("Game loaded from Redis successfully!")
        print(f"Current player from loaded game: {loaded_game.get_current_player().name}")
        
        await sio.emit('test_response', {'status': 'success', 'player': loaded_game.get_current_player().name}, room=sid)
    else:
        await sio.emit('test_response', {'status': 'error'}, room=sid)

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "catan-backend"}