# ============================================================
# FILE: tests/unit/test_building_rules.py
# ============================================================
import pytest
from app.models.game import GameState, TurnPhase
from app.models.player import PlayerColor
from app.models.hex_lib import Hex, Vertex, Edge
from app.models.board import ResourceType

class TestBuildingRules:
    
    @pytest.fixture
    def game(self):
        return GameState.create_new_game(["Alice", "Bob"])

    def test_place_initial_settlement_free(self, game):
        """Test placing a settlement during setup (free, no road required)."""
        alice = game.players[0]
        v = Vertex(Hex(0,0,0), 0)
        
        # Free setup bypasses phase check
        game.place_settlement(alice, v, free=True)
        
        # Check structure .owner
        assert game.settlements[v.get_canonical()].owner == PlayerColor.RED
        assert alice.victory_points == 1

    def test_distance_rule(self, game):
        alice = game.players[0]
        v1 = Vertex(Hex(0,0,0), 0)
        v_neighbor = v1.get_adjacent_vertices()[0]
        
        game.place_settlement(alice, v1, free=True)
        
        bob = game.players[1]
        with pytest.raises(ValueError, match="Distance Rule"):
            game.place_settlement(bob, v_neighbor, free=True)

    def test_road_connectivity_required(self, game):
        alice = game.players[0]
        alice.add_resource(ResourceType.WOOD)
        alice.add_resource(ResourceType.BRICK)
        alice.add_resource(ResourceType.WHEAT)
        alice.add_resource(ResourceType.SHEEP)
        
        v = Vertex(Hex(0,0,0), 0)
        
        # To build normally, we must be in MAIN_PHASE
        game.turn_phase = TurnPhase.MAIN_PHASE

        with pytest.raises(ValueError, match="connected to your road"):
            game.place_settlement(alice, v, free=False)

    def test_road_placement_logic(self, game):
        alice = game.players[0]
        v_start = Vertex(Hex(0,0,0), 0)
        
        game.place_settlement(alice, v_start, free=True)
        
        e_connected = v_start.get_touching_edges()[0]
        game.place_road(alice, e_connected, free=True)
        
        assert game.roads[e_connected.get_canonical()] == PlayerColor.RED

        e_far = Edge(Hex(5, -5, 0), 0)
        with pytest.raises(ValueError, match="must be connected"):
            game.place_road(alice, e_far, free=True)

    def test_resource_deduction(self, game):
        alice = game.players[0]
        alice.add_resource(ResourceType.WOOD, 1)
        alice.add_resource(ResourceType.BRICK, 1)
        
        v = Vertex(Hex(0,0,0), 0)
        game.place_settlement(alice, v, free=True)
        e = v.get_touching_edges()[0]
        
        # Switch to Main Phase for paid building
        game.turn_phase = TurnPhase.MAIN_PHASE

        game.place_road(alice, e, free=False)
        
        assert alice.resources[ResourceType.WOOD] == 0
        assert alice.resources[ResourceType.BRICK] == 0
        assert game.roads[e.get_canonical()] == PlayerColor.RED