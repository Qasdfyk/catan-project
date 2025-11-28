import pytest
from unittest.mock import patch
from app.models.game import GameState, TurnPhase
from app.models.board import ResourceType
from app.models.hex_lib import Hex, Vertex, Edge

def test_short_game_simulation():
    # 1. INIT
    game = GameState.create_new_game(["Alice", "Bob"])
    alice = game.players[0]
    bob = game.players[1]

    # --- SETUP SIMULATION ---
    
    # Alice places first settlement at Center, Vertex 0 (Top-Right)
    h1 = Hex(0,0,0)
    v1 = Vertex(h1, 0)
    game.place_settlement(alice, v1, free=True)
    game.place_road(alice, v1.get_touching_edges()[0], free=True)
    
    # Pass turn to Bob
    game.next_turn() 
    assert game.get_current_player() == bob

    # Bob places his settlement.
    # FIX: Pick a location clearly far away.
    # Old logic used Hex(1,0,-1) Vertex 2, which collided with Alice in new math.
    # Let's pick Bottom-Left Hex (-1, 0, 1) Vertex 3 (Left).
    h2 = Hex(-1,0,1) 
    v2 = Vertex(h2, 3)
    
    game.place_settlement(bob, v2, free=True)
    game.place_road(bob, v2.get_touching_edges()[0], free=True)
    
    # Pass turn back to Alice
    game.next_turn()
    assert game.get_current_player() == alice

    # --- GAMEPLAY START ---
    assert game.current_turn_index == 0 # Alice
    assert game.turn_phase == TurnPhase.ROLL_DICE
    
    # 2. ROLL DICE
    alice.add_resource(ResourceType.WOOD, 1)
    alice.add_resource(ResourceType.BRICK, 1)
    
    game.turn_phase = TurnPhase.ROLL_DICE # Reset for retry
    with patch('random.randint', side_effect=[3, 3]): # Roll = 6
        roll = game.roll_dice()
    
    assert roll == 6
    assert game.turn_phase == TurnPhase.MAIN_PHASE
    
    # 3. BUILD ROAD
    # Find a valid edge connected to Alice's existing network.
    existing_road_edge = v1.get_touching_edges()[0].get_canonical()
    
    # Get any edge connected to the existing road that isn't the road itself
    next_edge = None
    for e in existing_road_edge.get_connected_edges():
        if e.get_canonical() not in game.roads:
            next_edge = e
            break
            
    assert next_edge is not None, "Should have a free edge to build on"
    
    # Execute build
    game.place_road(alice, next_edge)
    
    # Verify State
    assert game.roads[next_edge.get_canonical()] == alice.color
    assert alice.resources[ResourceType.WOOD] == 0 # Spent
    assert alice.resources[ResourceType.BRICK] == 0 # Spent
    
    # Verify Longest Road calculation (should be at least 2 segments now)
    assert game._check_longest_road(alice) >= 2

    # 4. END TURN
    game.next_turn()
    assert game.get_current_player() == bob
    assert game.turn_phase == TurnPhase.ROLL_DICE