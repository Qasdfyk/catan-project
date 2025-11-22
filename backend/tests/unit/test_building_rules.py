import pytest
from app.models.game import GameState
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
        
        # Should succeed without resources or roads
        game.place_settlement(alice, v, free=True)
        
        assert game.settlements[v.get_canonical()] == PlayerColor.RED
        assert alice.victory_points == 1

    def test_distance_rule(self, game):
        """Settlements cannot be placed on adjacent vertices."""
        alice = game.players[0]
        v1 = Vertex(Hex(0,0,0), 0)
        v_neighbor = v1.get_adjacent_vertices()[0]
        
        game.place_settlement(alice, v1, free=True)
        
        # Bob tries to build next door
        bob = game.players[1]
        with pytest.raises(ValueError, match="Distance Rule"):
            game.place_settlement(bob, v_neighbor, free=True)

    def test_road_connectivity_required(self, game):
        """Normal settlement placement requires a connecting road."""
        alice = game.players[0]
        # Give resources
        alice.add_resource(ResourceType.WOOD)
        alice.add_resource(ResourceType.BRICK)
        alice.add_resource(ResourceType.WHEAT)
        alice.add_resource(ResourceType.SHEEP)
        
        v = Vertex(Hex(0,0,0), 0)
        
        # Should fail because no road leads there
        with pytest.raises(ValueError, match="connected to your road"):
            game.place_settlement(alice, v, free=False)

    def test_road_placement_logic(self, game):
        alice = game.players[0]
        v_start = Vertex(Hex(0,0,0), 0)
        
        # 1. Place initial settlement
        game.place_settlement(alice, v_start, free=True)
        
        # 2. Place road connected to settlement (Free setup road)
        e_connected = v_start.get_touching_edges()[0]
        game.place_road(alice, e_connected, free=True)
        
        assert game.roads[e_connected.get_canonical()] == PlayerColor.RED

        # 3. Try placing disconnected road (should fail)
        e_far = Edge(Hex(5, -5, 0), 0)
        with pytest.raises(ValueError, match="must be connected"):
            game.place_road(alice, e_far, free=True)

    def test_resource_deduction(self, game):
        alice = game.players[0]
        alice.add_resource(ResourceType.WOOD, 1)
        alice.add_resource(ResourceType.BRICK, 1)
        
        # Setup connectivity first
        v = Vertex(Hex(0,0,0), 0)
        game.place_settlement(alice, v, free=True)
        e = v.get_touching_edges()[0]
        
        # Build road with cost
        game.place_road(alice, e, free=False)
        
        assert alice.resources[ResourceType.WOOD] == 0
        assert alice.resources[ResourceType.BRICK] == 0
        assert game.roads[e.get_canonical()] == PlayerColor.RED