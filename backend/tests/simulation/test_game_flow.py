from unittest.mock import patch
from app.models.game import GameState, TurnPhase
from app.models.board import ResourceType
from app.models.hex_lib import Hex, Vertex

def test_short_game_simulation():
    # 1. INIT
    game = GameState.create_new_game(["Alice", "Bob"])
    alice = game.players[0]
    bob = game.players[1]

    # --- SETUP SIMULATION (snake draft: Alice, Bob, Bob, Alice) ---

    v1 = Vertex(Hex(0,0,0), 0)
    game.place_settlement(alice, v1)
    game.place_road(alice, v1.get_touching_edges()[0])
    assert game.get_current_player() == bob

    v2 = Vertex(Hex(-1,0,1), 3)
    game.place_settlement(bob, v2)
    game.place_road(bob, v2.get_touching_edges()[0])
    assert game.get_current_player() == bob

    v3 = Vertex(Hex(0,2,-2), 1)
    game.place_settlement(bob, v3)
    game.place_road(bob, v3.get_touching_edges()[0])
    assert game.get_current_player() == alice

    v4 = Vertex(Hex(0,-2,2), 4)
    game.place_settlement(alice, v4)
    game.place_road(alice, v4.get_touching_edges()[0])

    # --- GAMEPLAY START ---
    assert game.current_turn_index == 0 # Alice
    assert game.turn_phase == TurnPhase.ROLL_DICE

    # 2. ROLL DICE
    with patch('random.randint', side_effect=[3, 3]): # Roll = 6
        roll = game.roll_dice(alice)

    assert roll == 6
    assert game.turn_phase == TurnPhase.MAIN_PHASE

    # The board is random, so the hand is set only after the roll has paid out
    alice.resources.clear()
    alice.add_resource(ResourceType.WOOD, 1)
    alice.add_resource(ResourceType.BRICK, 1)

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
    game.end_turn(alice)
    assert game.get_current_player() == bob
    assert game.turn_phase == TurnPhase.ROLL_DICE
