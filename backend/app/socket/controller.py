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
        #TODO validate tokens

    async def on_disconnect(self, sid):
        print(f"Client disconnected: {sid}")
    
    async def on_join_game(self, sid, data):
        """
        Handler for 'join_game' event.
        Expects data: {'room_id': '...'}
        """
        room_id = data.get('room_id')
        if not room_id:
            print(f"Error: join_game called without room_id by {sid}")
            return

        print(f"Socket {sid} joining room {room_id}")

        # 1. Join the Socket.IO room so this user receives future broadcasts
        await self.sio.enter_room(sid, room_id)

        # 2. Fetch current game state from Redis
        game_state = await self.redis.get_game_state(room_id)

        if game_state:
            # 3. Emit the state ONLY to the user who just joined (for initial sync)
            # We use 'game_state_update' which matches the frontend listener
            await self.sio.emit('game_state_update', game_state, room=sid)
            print(f"Sent initial game state to {sid}")
        else:
            print(f"Game {room_id} not found in Redis")
            await self.sio.emit('error', {'message': 'Game not found'}, room=sid)
