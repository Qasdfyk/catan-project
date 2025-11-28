import pytest
from app.models.game import GameState, TurnPhase
from app.models.board import ResourceType, Tile
from app.models.hex_lib import Hex, Vertex

class TestHarvestMechanics:
    
    def test_distribute_resources_simple(self):
        game = GameState.create_new_game(["Alice", "Bob"])
        alice = game.players[0]

        # FIX: Bypass Setup Phase constraints
        game.turn_phase = TurnPhase.MAIN_PHASE

        center_hex = Hex(0,0,0)
        
        game.board.tiles.clear()
        
        game.robber_hex = Hex(100, -100, 0)

        # Setup Logic
        game.board.tiles[center_hex] = Tile(center_hex, ResourceType.WOOD, 6)
        vertex = Vertex(center_hex, 0)
        game.place_settlement(alice, vertex, free=True)
        
        assert alice.resources[ResourceType.WOOD] == 0

        # Trigger
        game.turn_phase = TurnPhase.ROLL_DICE
        game.distribute_resources(6)

        assert alice.resources[ResourceType.WOOD] == 1

    def test_distribute_resources_multiple_players(self):
        game = GameState.create_new_game(["Alice", "Bob"])
        alice = game.players[0]
        bob = game.players[1]
        
        # FIX: Bypass Setup Phase constraints
        game.turn_phase = TurnPhase.MAIN_PHASE

        center_hex = Hex(0,0,0)
        
        game.board.tiles.clear()

        game.robber_hex = Hex(100, -100, 0)
        
        game.board.tiles[center_hex] = Tile(center_hex, ResourceType.WHEAT, 8)

        game.place_settlement(alice, Vertex(center_hex, 0), free=True)
        game.place_settlement(bob, Vertex(center_hex, 3), free=True)

        game.turn_phase = TurnPhase.ROLL_DICE
        game.distribute_resources(8)

        assert alice.resources[ResourceType.WHEAT] == 1
        assert bob.resources[ResourceType.WHEAT] == 1

    def test_no_resources_on_wrong_roll(self):
        game = GameState.create_new_game(["Alice", "Bob"])
        alice = game.players[0]
        
        # FIX: Bypass Setup Phase constraints
        game.turn_phase = TurnPhase.MAIN_PHASE

        center_hex = Hex(0,0,0)
        
        game.board.tiles.clear()

        game.robber_hex = Hex(100, -100, 0)
        
        game.board.tiles[center_hex] = Tile(center_hex, ResourceType.ORE, 5)
        
        game.place_settlement(alice, Vertex(center_hex, 0), free=True)
        
        game.turn_phase = TurnPhase.ROLL_DICE
        game.distribute_resources(10)
        
        assert alice.resources[ResourceType.ORE] == 0