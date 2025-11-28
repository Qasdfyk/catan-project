import pytest
import uuid
from app.models.game import GameState, TurnPhase
from app.models.hex_lib import Hex, Vertex
from app.services.serializer import GameSerializer
from app.services.redis_service import RedisService

@pytest.mark.asyncio
async def test_setup_state_persistence():
    service = RedisService()
    room_id = f"setup_test_{uuid.uuid4()}"

    # 1. Initialize Game
    game = GameState.create_new_game(["Alice", "Bob"])
    alice = game.players[0]
    
    assert game.turn_phase == TurnPhase.SETUP
    assert game.setup_waiting_for_road is False
    assert len(game.setup_queue) > 0

    # 2. Alice places FIRST Settlement
    v1 = Vertex(Hex(0,0,0), 0)
    game.place_settlement(alice, v1)
    
    assert game.setup_waiting_for_road is True
    assert len(game.settlements) == 1

    # 3. SAVE to Redis
    game_dict = GameSerializer.game_to_dict(game)
    await service.save_game_state(room_id, game_dict)

    # 4. LOAD from Redis
    loaded_data = await service.get_game_state(room_id)
    
    # FIX: Explicit assertion tells Pylance "loaded_data" is definitely a dict, not None
    assert loaded_data is not None, "Failed to retrieve game state from Redis"

    loaded_game = GameSerializer.dict_to_game(loaded_data)

    # 5. VERIFY State
    assert loaded_game.setup_waiting_for_road is True, "Backend forgot we are waiting for a road!"
    assert loaded_game.turn_phase == TurnPhase.SETUP
    assert loaded_game.setup_queue == game.setup_queue
    
    # 6. Verify cheating prevention
    v2 = Vertex(Hex(10, 0, -10), 0)
    
    with pytest.raises(ValueError, match="must place a road"):
        loaded_game.place_settlement(alice, v2)

    # Cleanup
    await service.redis.delete(f"game:{room_id}")
    await service.close()