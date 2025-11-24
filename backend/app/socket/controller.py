import socketio
from app.models.game import GameState
from app.services.serializer import GameSerializer
from app.services.redis_service import RedisService

class SocketController:
    """
    Handles Socket.IO events. 
    Initialized with dependencies to avoid global state issues.
    """
    def __init__(self, sio: socketio.AsyncServer, redis_service: RedisService):
        self.sio = sio
        self.redis = redis_service

    async def on_connect(self, sid, environ):
        print(f"Client connected: {sid}")
        # Here we could validate tokens in the future

    async def on_disconnect(self, sid):
        print(f"Client disconnected: {sid}")

    async def on_create_test_game(self, sid):
        """
        Refactored handler for creating a test game.
        """
        print(f"Processing create_test_game for {sid}...")
        
        # 1. Game Logic
        game = GameState.create_new_game(["Player1", "Player2"])
        room_id = "room_test_1"
        
        # 2. Serialization
        game_dict = GameSerializer.game_to_dict(game)
        
        # 3. Save to Redis (Using injected service)
        await self.redis.save_game_state(room_id, game_dict)
        
        # 4. Load back to verify
        loaded_dict = await self.redis.get_game_state(room_id)
        
        if loaded_dict:
            loaded_game = GameSerializer.dict_to_game(loaded_dict)
            current_player = loaded_game.get_current_player()
            
            # Emit back to the specific client
            await self.sio.emit('test_response', {
                'status': 'success', 
                'room_id': room_id,
                'player_name': current_player.name,
                'player_id': current_player.id # Send ID back to frontend
            }, room=sid)
        else:
            await self.sio.emit('test_response', {'status': 'error'}, room=sid)