import pytest
import uuid
from app.models.game import GameState, TurnPhase
from app.services.serializer import GameSerializer
from app.services.redis_service import RedisService

@pytest.mark.asyncio
async def test_full_game_persistence_cycle():
    """
    Integration Test:
    1. Creates a real GameState with Players having IDs.
    2. Serializes it.
    3. Saves it to a REAL Redis instance.
    4. Loads it back.
    5. Deserializes it.
    6. Verifies data integrity, specifically Player IDs.
    """
    
    # 1. Setup
    service = RedisService()
    room_id = f"integration_test_{uuid.uuid4()}" # Unique room for this test run
    
    # Create a game
    original_game = GameState.create_new_game(["Alice", "Bob"])
    
    # FIX: Force phase to ROLL_DICE to allow rolling
    original_game.turn_phase = TurnPhase.ROLL_DICE
    original_game.roll_dice() 
    
    # Capture original data for comparison
    original_p1_id = original_game.players[0].id
    original_p2_id = original_game.players[1].id
    original_turn_idx = original_game.current_turn_index
    
    # Verify IDs were actually generated
    assert len(original_p1_id) > 0, "Player 1 ID should not be empty"
    assert len(original_p2_id) > 0, "Player 2 ID should not be empty"
    assert original_p1_id != original_p2_id, "Players must have unique IDs"

    # 2. Serialize & Save
    game_dict = GameSerializer.game_to_dict(original_game)
    await service.save_game_state(room_id, game_dict)

    # 3. Load from Redis
    loaded_dict = await service.get_game_state(room_id)
    assert loaded_dict is not None, "Redis returned None, save failed."

    # 4. Deserialize
    loaded_game = GameSerializer.dict_to_game(loaded_dict)

    # 5. Verify Data Integrity
    # CRITICAL: Check if IDs persisted properly
    assert loaded_game.players[0].id == original_p1_id
    assert loaded_game.players[1].id == original_p2_id
    
    # Check if other fields persisted
    assert loaded_game.players[0].name == "Alice"
    assert loaded_game.current_turn_index == original_turn_idx
    assert len(loaded_game.board.tiles) == 19

    # Cleanup
    await service.redis.delete(f"game:{room_id}")
    await service.close()