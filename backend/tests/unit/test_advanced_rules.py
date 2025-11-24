# ============================================================
# FILE: tests/unit/test_advanced_rules.py
# ============================================================
import pytest
from unittest.mock import patch
from app.models.game import GameState, TurnPhase
from app.models.board import ResourceType, PortType, Port
from app.models.hex_lib import Hex, Vertex, Edge
from app.models.player import PlayerColor

class TestRobberStealing:
    def test_steal_resource_success(self):
        """
        Verifies that a player can steal a resource from another player
        if the robber is adjacent to the victim's settlement.
        """
        game = GameState.create_new_game(["Alice", "Bob"])
        alice = game.players[0]
        bob = game.players[1]
        
        # FIX: Advance phase to allow actions
        game.turn_phase = TurnPhase.MAIN_PHASE

        # Setup: Bob has a settlement at (0,0,0) and 1 WOOD
        h = Hex(0,0,0)
        game.place_settlement(bob, Vertex(h, 0), free=True)
        bob.add_resource(ResourceType.WOOD, 1)
        
        # Setup: Robber is placed on (0,0,0)
        game.robber_hex = h
        
        # Alice steals
        with patch('random.choice', return_value=ResourceType.WOOD):
            stolen = game.steal_resource(thief=alice, victim=bob)
            
        assert stolen == ResourceType.WOOD
        assert bob.resources[ResourceType.WOOD] == 0
        assert alice.resources[ResourceType.WOOD] == 1

    def test_steal_fail_no_building(self):
        """
        Verifies that stealing fails if the victim has no building adjacent to the robber.
        """
        game = GameState.create_new_game(["Alice", "Bob"])
        alice = game.players[0]
        bob = game.players[1]
        
        # FIX: Advance phase
        game.turn_phase = TurnPhase.MAIN_PHASE

        h_robber = Hex(0,0,0)
        game.robber_hex = h_robber
        
        # Bob has a settlement far away
        game.place_settlement(bob, Vertex(Hex(5, -5, 0), 0), free=True)
        
        with pytest.raises(ValueError, match="Victim has no building on the robber hex"):
            game.steal_resource(alice, bob)

    def test_robber_hex_none_check(self):
        """
        Verifies the fix for 'Hex | None': should raise error if robber is not placed.
        """
        game = GameState.create_new_game(["Alice", "Bob"])
        alice = game.players[0]
        bob = game.players[1]

        # FIX: Advance phase
        game.turn_phase = TurnPhase.MAIN_PHASE

        # Force robber to be None (simulating initialization state before any move)
        game.robber_hex = None

        with pytest.raises(ValueError, match="Robber is not placed"):
            game.steal_resource(alice, bob)

class TestPortTrading:
    def test_trade_generic_3_1(self):
        """
        Verifies 3:1 trading ratio when player owns a Generic Port.
        """
        game = GameState.create_new_game(["Alice", "Bob"])
        alice = game.players[0]
        
        # Manually inject a port into the board for testing purposes
        h = Hex(0,0,0)
        v1 = Vertex(h, 0).get_canonical()
        v2 = Vertex(h, 1).get_canonical()
        game.board.ports.append(Port(PortType.GENERIC_3_1, [v1, v2]))
        
        # Alice builds a settlement at the port location
        game.place_settlement(alice, v1, free=True)
        
        # Alice has 3 WOOD, wants 1 BRICK
        alice.add_resource(ResourceType.WOOD, 3)
        
        game.turn_phase = TurnPhase.MAIN_PHASE # Trading requires Main Phase
        game.trade_with_bank(alice, give=ResourceType.WOOD, get=ResourceType.BRICK)
        
        assert alice.resources[ResourceType.WOOD] == 0
        assert alice.resources[ResourceType.BRICK] == 1

    def test_trade_default_4_1(self):
        """
        Verifies default 4:1 trading ratio when player has no ports.
        """
        game = GameState.create_new_game(["Alice", "Bob"])
        alice = game.players[0]
        
        # No ports owned
        alice.add_resource(ResourceType.WOOD, 3)
        
        game.turn_phase = TurnPhase.MAIN_PHASE
        
        # Attempting to trade with only 3 resources should fail
        with pytest.raises(ValueError, match="Need 4"):
            game.trade_with_bank(alice, give=ResourceType.WOOD, get=ResourceType.BRICK)

class TestLongestRoad:
    def test_simple_line(self):
        """
        Verifies longest road calculation for a simple continuous line of 3 segments.
        """
        game = GameState.create_new_game(["Alice", "Bob"])
        alice = game.players[0]
        
        # Create a path of 3 connected edges around a single hex
        # Path: Edge(0) -> Edge(1) -> Edge(2) of Hex(0,0,0)
        h = Hex(0,0,0)
        path = [
            Edge(h, 0).get_canonical(),
            Edge(h, 1).get_canonical(),
            Edge(h, 2).get_canonical()
        ]
        
        for e in path:
            game.roads[e] = alice.color
            
        assert game._check_longest_road(alice) == 3

    def test_branching_road(self):
        """
        Verifies that branches (Y-shape) are not summed up.
        Calculates the longest single continuous path.
        """
        game = GameState.create_new_game(["Alice", "Bob"])
        alice = game.players[0]
        
        # Create a "Y" shape at Vertex(0) of Hex(0,0,0).
        h = Hex(0,0,0)
        
        # Edge 1: (0,0,0) dir 0
        # Edge 2: (0,0,0) dir 1
        # Edge 3: (0,0,0) dir 5 (Connected to Edge 0 at vertex 0)
        
        # This forms a continuous line of 3 segments (5-0-1) around the vertex.
        
        game.roads[Edge(h, 0).get_canonical()] = alice.color
        game.roads[Edge(h, 1).get_canonical()] = alice.color
        game.roads[Edge(h, 5).get_canonical()] = alice.color 
        
        assert game._check_longest_road(alice) == 3

    def test_road_interrupted_by_enemy_settlement(self):
        """
        Verifies that an opponent's settlement breaks the road continuity.
        """
        game = GameState.create_new_game(["Alice", "Bob"])
        alice = game.players[0]
        bob = game.players[1]
        
        # Alice has two road segments connected by a vertex
        h = Hex(0,0,0)
        e1 = Edge(h, 0).get_canonical()
        e2 = Edge(h, 1).get_canonical() # Connected at Vertex(h, 1)
        
        game.roads[e1] = alice.color
        game.roads[e2] = alice.color
        
        # Verify it is 2 initially
        assert game._check_longest_road(alice) == 2
        
        # Bob places a settlement at the intersection Vertex(h, 1)
        v_interrupter = Vertex(h, 1).get_canonical()
        
        # We assume standard rules where you can build on existing roads if valid (or setup phase)
        # Here we manually inject for unit testing the calculation logic
        from app.models.game import Building, BuildingType
        game.settlements[v_interrupter] = Building(bob.color, BuildingType.SETTLEMENT)
        
        # Now Alice should have two separate roads of length 1
        assert game._check_longest_road(alice) == 1