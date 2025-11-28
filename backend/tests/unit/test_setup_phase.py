import pytest
from app.models.game import GameState, TurnPhase
from app.models.hex_lib import Hex, Vertex, Edge
from app.models.board import ResourceType, Tile

class TestSetupPhase:

    def test_snake_draft_order_2_players(self):
        """
        Verify A -> B -> B -> A order.
        """
        game = GameState.create_new_game(["Alice", "Bob"])
        alice = game.players[0]
        bob = game.players[1]
        
        # 1. Alice turn (Setup queue: [0, 1, 1, 0])
        assert game.get_current_player() == alice
        assert game.turn_phase == TurnPhase.SETUP
        assert game.setup_waiting_for_road is False
        
        # Alice places Settlement
        v1 = Vertex(Hex(0,0,0), 0)
        game.place_settlement(alice, v1)
        
        assert game.setup_waiting_for_road is True
        
        # Alice places Road
        e1 = v1.get_touching_edges()[0]
        game.place_road(alice, e1) 
        # place_road auto-calls next_turn() in Setup

        # 2. Bob Turn
        assert game.get_current_player() == bob
        assert game.setup_waiting_for_road is False
        
        v2 = Vertex(Hex(1,0,-1), 0)
        game.place_settlement(bob, v2)
        e2 = v2.get_touching_edges()[0]
        game.place_road(bob, e2)

        # 3. Bob Turn AGAIN (Snake: B->B)
        assert game.get_current_player() == bob
        
        v3 = Vertex(Hex(2,0,-2), 0)
        game.place_settlement(bob, v3)
        e3 = v3.get_touching_edges()[0]
        game.place_road(bob, e3)

        # 4. Alice Turn AGAIN (Snake: ... -> A)
        assert game.get_current_player() == alice
        
        v4 = Vertex(Hex(-1,0,1), 0)
        game.place_settlement(alice, v4)
        e4 = v4.get_touching_edges()[0]
        game.place_road(alice, e4)
        
        # 5. End of Setup -> Roll Dice Phase
        assert game.turn_phase == TurnPhase.ROLL_DICE
        assert game.current_turn_index == 0 # Back to Alice

    def test_enforce_settlement_before_road(self):
        game = GameState.create_new_game(["Alice", "Bob"])
        alice = game.players[0]
        
        e1 = Edge(Hex(0,0,0), 0)
        
        # Try to place road immediately
        with pytest.raises(ValueError, match="place a settlement first"):
            game.place_road(alice, e1)

    def test_enforce_road_after_settlement(self):
        game = GameState.create_new_game(["Alice", "Bob"])
        alice = game.players[0]
        
        v1 = Vertex(Hex(0,0,0), 0)
        game.place_settlement(alice, v1)
        
        # Try to place another settlement instead of a road
        v2 = Vertex(Hex(1,0,-1), 0)
        with pytest.raises(ValueError, match="place a road"):
            game.place_settlement(alice, v2)

    def test_initial_resources_on_second_settlement(self):
        game = GameState.create_new_game(["Alice", "Bob"])
        alice = game.players[0]
        
        # Clear board to control resources
        game.board.tiles.clear()
        
        h1 = Hex(0,0,0)
        h2 = Hex(1,0,-1) # Neighbor
        
        # Setup specific resources
        game.board.tiles[h1] = Tile(h1, ResourceType.WOOD, 6)
        game.board.tiles[h2] = Tile(h2, ResourceType.BRICK, 8)
        
        # 1st Settlement (Alice) - No resources
        game.turn_phase = TurnPhase.SETUP
        # Mocking queue for simplicity or just placing carefully
        
        v1 = Vertex(Hex(10,10,-20), 0) # Far away
        game.place_settlement(alice, v1)
        assert sum(alice.resources.values()) == 0
        
        # 2nd Settlement (Alice) - Should get resources
        # We manually simulate that she has 1 building already (done above)
        # We reset the 'setup_waiting_for_road' to allow placement for test
        game.setup_waiting_for_road = False
        
        # Place at vertex shared by h1 and h2 (and a 3rd missing one)
        # Vertex(h1, 0) touches h1 and neighbor(0) -> h2
        v2 = Vertex(h1, 0)
        
        game.place_settlement(alice, v2)
        
        # Alice should get 1 Wood and 1 Brick
        assert alice.resources[ResourceType.WOOD] == 1
        assert alice.resources[ResourceType.BRICK] == 1
        assert sum(alice.resources.values()) == 2