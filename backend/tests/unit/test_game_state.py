# ============================================================
# FILE: tests/unit/test_game_state.py
# ============================================================
import pytest
from unittest.mock import patch 
from app.models.game import GameState, TurnPhase
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
        assert game.board is not None
        assert game.current_turn_index == 0
        assert game.turn_phase == TurnPhase.ROLL_DICE

    def test_invalid_player_count(self):
        with pytest.raises(ValueError):
            GameState.create_new_game(["Solo"]) 

    def test_turn_cycle(self):
        names = ["Alice", "Bob"]
        game = GameState.create_new_game(names)
        
        assert game.get_current_player().name == "Alice"
        
        game.next_turn()
        assert game.get_current_player().name == "Bob"
        assert game.turn_phase == TurnPhase.ROLL_DICE
        
        game.next_turn()
        assert game.get_current_player().name == "Alice"

    def test_dice_roll_mocked(self):
        """
        Use a mock to ensure deterministic dice roll.
        random.randint is called twice (for d1 and d2).
        """
        game = GameState.create_new_game(["A", "B"])
        
        # side_effect=[3, 4] means: first call returns 3, second call returns 4.
        # Total sum should be 7.
        with patch('random.randint', side_effect=[3, 4]):
            roll = game.roll_dice()
            
            assert roll == 7
            assert game.dice_roll == 7
            assert game.turn_phase == TurnPhase.MAIN_PHASE