import pytest
from app.models.game import GameState
from app.models.board import ResourceType, Tile
from app.models.hex_lib import Hex, Vertex

class TestHarvestMechanics:
    
    def test_distribute_resources_simple(self):
        """
        Scenario:
        1. Create game.
        2. Find a tile with known resource (e.g., WOOD) and known number (e.g., 6).
        3. Place a settlement on that tile's vertex.
        4. Trigger distribute_resources(6).
        5. Assert player got 1 WOOD.
        """
        game = GameState.create_new_game(["Alice", "Bob"])
        alice = game.players[0]

        # 1. Hack the board to ensure we have a deterministic test case
        # Let's pick the center tile (0,0,0) and force it to be WOOD with number 6
        center_hex = Hex(0,0,0)
        game.board.tiles[center_hex] = Tile(center_hex, ResourceType.WOOD, 6)

        # 2. Alice builds a settlement on one corner of the center tile
        vertex = Vertex(center_hex, 0)
        game.place_settlement(alice, vertex, free=True)
        
        # Verify Alice has 0 Wood initially
        assert alice.resources[ResourceType.WOOD] == 0

        # 3. Trigger resource distribution for '6'
        game.distribute_resources(6)

        # 4. Verify Alice got the resource
        assert alice.resources[ResourceType.WOOD] == 1

    def test_distribute_resources_multiple_players(self):
        """
        Scenario: Two players have settlements on the SAME tile. Both should get resources.
        """
        game = GameState.create_new_game(["Alice", "Bob"])
        alice = game.players[0]
        bob = game.players[1]

        center_hex = Hex(0,0,0)
        game.board.tiles[center_hex] = Tile(center_hex, ResourceType.WHEAT, 8)

        # Alice on corner 0
        game.place_settlement(alice, Vertex(center_hex, 0), free=True)
        # Bob on corner 3 (opposite side)
        game.place_settlement(bob, Vertex(center_hex, 3), free=True)

        game.distribute_resources(8)

        assert alice.resources[ResourceType.WHEAT] == 1
        assert bob.resources[ResourceType.WHEAT] == 1

    def test_no_resources_on_wrong_roll(self):
        game = GameState.create_new_game(["Alice", "Bob"])
        alice = game.players[0]
        
        center_hex = Hex(0,0,0)
        game.board.tiles[center_hex] = Tile(center_hex, ResourceType.ORE, 5)
        
        game.place_settlement(alice, Vertex(center_hex, 0), free=True)
        
        # Roll is 10, tile is 5
        game.distribute_resources(10)
        
        assert alice.resources[ResourceType.ORE] == 0