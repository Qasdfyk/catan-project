import pytest
import pytest_asyncio
from app.models.game import GameState
from app.services.serializer import GameSerializer
from app.services.redis_service import RedisService

@pytest.mark.asyncio
async def test_full_game_persistence_cycle():
    """
    Integration Test:
    1. Creates a real GameState.
    2. Serializes it.
    3. Saves it to a REAL Redis instance.
    4. Loads it back.
    5. Deserializes it.
    6. Verifies data integrity.
    """
    
    # 1. Setup
    service = RedisService()
    room_id = "integration_test_room_123"
    
    # Create a game and modify it slightly (roll dice) to ensure state is captured
    original_game = GameState.create_new_game(["Alice", "Bob"])
    original_game.roll_dice() 
    original_turn_idx = original_game.current_turn_index
    original_dice = original_game.dice_roll

    # 2. Serialize & Save
    game_dict = GameSerializer.game_to_dict(original_game)
    await service.save_game_state(room_id, game_dict)

    # 3. Load from Redis
    loaded_dict = await service.get_game_state(room_id)
    
    # Assert Redis actually returned data
    assert loaded_dict is not None, "Redis returned None, save failed."

    # 4. Deserialize
    loaded_game = GameSerializer.dict_to_game(loaded_dict)

    # 5. Verify Data Integrity
    assert len(loaded_game.players) == 2
    assert loaded_game.players[0].name == "Alice"
    assert loaded_game.players[1].name == "Bob"
    
    # Verify State Persistence
    assert loaded_game.dice_roll == original_dice
    assert loaded_game.current_turn_index == original_turn_idx
    
    # Verify Board Integrity (Check just one tile to be sure)
    # We check if the count of tiles is preserved
    assert len(loaded_game.board.tiles) == 19

    # Cleanup
    await service.redis.delete(f"game:{room_id}")
    await service.close()