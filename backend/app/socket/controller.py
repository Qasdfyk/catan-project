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

    async def on_action(self, sid, data):
        """
        Generic handler for player actions.
        Expected data: { 'room_id': str, 'type': str, 'payload': dict }
        """
        room_id = data.get('room_id')
        action_type = data.get('type')
        
        print(f"Action {action_type} from {sid} in room {room_id}")

        # 1. Load Game State
        game_dict = await self.redis.get_game_state(room_id)
        if not game_dict:
            return
        
        # 2. Deserialize to Python Object
        game = GameSerializer.dict_to_game(game_dict)

        # 3. Execute Logic based on Action Type
        try:
            if action_type == 'roll_dice':
                roll = game.roll_dice()
                print(f"Dice rolled: {roll}")
            
            elif action_type == 'end_turn':
                game.next_turn()
                print(f"Turn ended. Now playing: {game.get_current_player().name}")
            
            # TODO: Add 'end_turn', 'build_road' etc. later

            # 4. Save updated state back to Redis
            new_game_dict = GameSerializer.game_to_dict(game)
            await self.redis.save_game_state(room_id, new_game_dict)

            # 5. Broadcast new state to EVERYONE in the room
            await self.sio.emit('game_state_update', new_game_dict, room=room_id)

        except ValueError as e:
            await self.sio.emit('game_error', {'message': str(e)}, room=sid)
