import socketio
from app.models.game import GameState
from app.services.serializer import GameSerializer
from app.services.redis_service import RedisService

def register_socket_events(sio: socketio.AsyncServer, app_state):
    """
    Registers all Socket.IO event handlers.
    """

    @sio.event
    async def connect(sid, environ):
        print(f"Client connected: {sid}")

    @sio.event
    async def disconnect(sid):
        print(f"Client disconnected: {sid}")

    @sio.event
    async def create_test_game(sid):
        """
        Handler for creating a test game.
        """
        print(f"Processing create_test_game for {sid}...")
        
        # 1. Game Logic
        game = GameState.create_new_game(["Player1", "Player2"])
        room_id = "room_test_1"
        
        # 2. Serialization
        game_dict = GameSerializer.game_to_dict(game)
        
        # 3. Save to Redis (Accessing RedisService from app state)
        # Note: In FastAPI+SocketIO, passing app state is tricky, 
        # so often we instantiate services or use dependency injection.
        # Here we assume app_state has the redis instance.
        redis: RedisService = app_state.redis
        await redis.save_game_state(room_id, game_dict)
        
        # 4. Load back to verify
        loaded_dict = await redis.get_game_state(room_id)
        
        if loaded_dict:
            loaded_game = GameSerializer.dict_to_game(loaded_dict)
            await sio.emit('test_response', {
                'status': 'success', 
                'player': loaded_game.get_current_player().name
            }, room=sid)
        else:
            await sio.emit('test_response', {'status': 'error'}, room=sid)