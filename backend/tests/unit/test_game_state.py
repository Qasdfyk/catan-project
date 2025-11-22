import pytest
from app.models.game import GameState
from app.models.player import Player, PlayerColor
from app.models.board import ResourceType

class TestPlayerResources:
    def test_add_remove_resources(self):
        p = Player(name="Test", color=PlayerColor.RED)
        p.add_resource(ResourceType.WOOD, 1)
        assert p.resources[ResourceType.WOOD] == 1
        
        p.remove_resource(ResourceType.WOOD, 1)
        assert p.resources[ResourceType.WOOD] == 0

    def test_remove_insufficient_resources(self):
        p = Player(name="Test", color=PlayerColor.RED)
        with pytest.raises(ValueError):
            p.remove_resource(ResourceType.BRICK, 1)

    def test_affordability_check(self):
        p = Player(name="Test", color=PlayerColor.RED)
        p.add_resource(ResourceType.WOOD, 1)
        p.add_resource(ResourceType.BRICK, 1)
        
        road_cost = {ResourceType.WOOD: 1, ResourceType.BRICK: 1}
        city_cost = {ResourceType.ORE: 3, ResourceType.WHEAT: 2}
        
        assert p.has_resources(road_cost) is True
        assert p.has_resources(city_cost) is False

    def test_deduct_resources(self):
        p = Player(name="Test", color=PlayerColor.RED)
        p.add_resource(ResourceType.WOOD, 2)
        p.add_resource(ResourceType.BRICK, 1)
        
        road_cost = {ResourceType.WOOD: 1, ResourceType.BRICK: 1}
        p.deduct_resources(road_cost)
        
        assert p.resources[ResourceType.WOOD] == 1
        assert p.resources[ResourceType.BRICK] == 0

class TestGameState:
    def test_game_initialization(self):
        names = ["Alice", "Bob", "Charlie"]
        game = GameState.create_new_game(names)
        
        assert len(game.players) == 3
        assert game.players[0].color == PlayerColor.RED
        assert game.players[1].color == PlayerColor.BLUE
        assert game.board is not None
        assert game.current_turn_index == 0

    def test_invalid_player_count(self):
        with pytest.raises(ValueError):
            GameState.create_new_game(["Solo"]) # Need at least 2

    def test_turn_cycle(self):
        names = ["Alice", "Bob"]
        game = GameState.create_new_game(names)
        
        # Alice's turn
        assert game.get_current_player().name == "Alice"
        
        game.next_turn()
        # Bob's turn
        assert game.get_current_player().name == "Bob"
        
        game.next_turn()
        # Back to Alice
        assert game.get_current_player().name == "Alice"

    def test_dice_roll(self):
        game = GameState.create_new_game(["A", "B"])
        roll = game.roll_dice()
        assert 2 <= roll <= 12
        assert game.dice_roll == roll