import pytest
from app.models.game import GameState, TurnPhase
from app.models.hex_lib import Hex, Vertex, Edge
from app.models.board import ResourceType, Tile

class TestSetupPhase:

    def test_snake_draft_order_2_players(self):
        game = GameState.create_new_game(["Alice", "Bob"])
        alice = game.players[0]
        bob = game.players[1]
        
        assert game.get_current_player() == alice
        assert game.turn_phase == TurnPhase.SETUP
        assert game.setup_waiting_for_road is False
        
        v1 = Vertex(Hex(0,0,0), 0)
        game.place_settlement(alice, v1)
        
        assert game.setup_waiting_for_road is True
        
        e1 = v1.get_touching_edges()[0]
        game.place_road(alice, e1) 

        assert game.get_current_player() == bob
        assert game.setup_waiting_for_road is False
        
        v2 = Vertex(Hex(1,0,-1), 0)
        game.place_settlement(bob, v2)
        e2 = v2.get_touching_edges()[0]
        game.place_road(bob, e2)

        assert game.get_current_player() == bob
        
        v3 = Vertex(Hex(2,0,-2), 0)
        game.place_settlement(bob, v3)
        e3 = v3.get_touching_edges()[0]
        game.place_road(bob, e3)

        assert game.get_current_player() == alice
        
        v4 = Vertex(Hex(-1,0,1), 0)
        game.place_settlement(alice, v4)
        e4 = v4.get_touching_edges()[0]
        game.place_road(alice, e4)
        
        assert game.turn_phase == TurnPhase.ROLL_DICE
        assert game.current_turn_index == 0

    def test_enforce_settlement_before_road(self):
        game = GameState.create_new_game(["Alice", "Bob"])
        alice = game.players[0]
        
        e1 = Edge(Hex(0,0,0), 0)
        
        with pytest.raises(ValueError, match="place a settlement first"):
            game.place_road(alice, e1)

    def test_enforce_road_after_settlement(self):
        game = GameState.create_new_game(["Alice", "Bob"])
        alice = game.players[0]
        
        v1 = Vertex(Hex(0,0,0), 0)
        game.place_settlement(alice, v1)
        
        v2 = Vertex(Hex(1,0,-1), 0)
        with pytest.raises(ValueError, match="place a road"):
            game.place_settlement(alice, v2)

    def test_initial_resources_on_second_settlement(self):
        game = GameState.create_new_game(["Alice", "Bob"])
        alice = game.players[0]
        
        game.board.tiles.clear()
        
        h1 = Hex(0,0,0)
        # Neighbor 0 is now EAST
        h2 = h1.neighbor(0) 
        
        game.board.tiles[h1] = Tile(h1, ResourceType.WOOD, 6)
        game.board.tiles[h2] = Tile(h2, ResourceType.BRICK, 8)
        
        game.turn_phase = TurnPhase.SETUP
        
        v1 = Vertex(Hex(10,10,-20), 0)
        game.place_settlement(alice, v1)
        assert sum(alice.resources.values()) == 0
        
        game.setup_waiting_for_road = False
        
        # Vertex 0 on Center touches Neighbor 0 (East) and Neighbor 5 (NE).
        # Since h2 is Neighbor 0, this vertex touches Wood(h1) and Brick(h2).
        v2 = Vertex(h1, 0)
        
        game.place_settlement(alice, v2)
        
        assert alice.resources[ResourceType.WOOD] == 1
        assert alice.resources[ResourceType.BRICK] == 1
        assert sum(alice.resources.values()) == 2