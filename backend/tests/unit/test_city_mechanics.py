import pytest
from app.models.game import GameState, TurnPhase, BuildingType
from app.models.board import ResourceType
from app.models.hex_lib import Hex, Vertex

class TestCityMechanics:
    
    def test_upgrade_settlement_to_city(self):
        game = GameState.create_new_game(["Alice", "Bob"])
        alice = game.players[0]
        game.turn_phase = TurnPhase.MAIN_PHASE
        
        v = Vertex(Hex(0,0,0), 0)
        game.place_settlement(alice, v, free=True)
        
        assert game.settlements[v.get_canonical()].type == BuildingType.SETTLEMENT
        
        alice.add_resource(ResourceType.ORE, 3)
        alice.add_resource(ResourceType.WHEAT, 2)
        
        game.upgrade_to_city(alice, v)
        
        bldg = game.settlements[v.get_canonical()]
        assert bldg.type == BuildingType.CITY
        
        assert alice.resources[ResourceType.ORE] == 0

    def test_city_produces_double_resources(self):
        game = GameState.create_new_game(["Alice", "Bob"])
        alice = game.players[0]
        game.turn_phase = TurnPhase.MAIN_PHASE
        
        # Move robber to avoid interference
        game.robber_hex = Hex(100, 100, -200)
        
        h = Hex(0,0,0)
        from app.models.board import Tile
        game.board.tiles.clear()
        game.board.tiles[h] = Tile(h, ResourceType.WOOD, 6)
        
        # BUILD ON VERTEX 0.
        # NOTE: Vertex 0 is shared by Hex 0 and Neighbor 0 and Neighbor 5.
        # Distribute resources iterates all dirs 0-5 of Hex 0.
        # It calculates Canonical(Vertex(0,0)).
        # It WILL find the building.
        v = Vertex(h, 0)
        game.place_settlement(alice, v, free=True)
        
        alice.add_resource(ResourceType.ORE, 3)
        alice.add_resource(ResourceType.WHEAT, 2)
        game.upgrade_to_city(alice, v)
        
        alice.resources.clear()
        
        game.turn_phase = TurnPhase.ROLL_DICE
        game.distribute_resources(6)
        
        assert alice.resources[ResourceType.WOOD] == 2