import pytest
from unittest.mock import patch 
from app.models.game import GameState, TurnPhase
from app.models.player import Player, PlayerColor
from app.models.board import ResourceType

# ... (TestPlayerResources class remains unchanged) ...

class TestGameState:
    def test_game_initialization(self):
        names = ["Alice", "Bob", "Charlie"]
        game = GameState.create_new_game(names)
        
        assert len(game.players) == 3
        assert game.players[0].color == PlayerColor.RED
        assert game.board is not None
        assert game.current_turn_index == 0
        
        # FIX: New games start in SETUP phase
        assert game.turn_phase == TurnPhase.SETUP
        
        assert game.players[0].id != ""
        assert game.players[1].id != ""
        assert game.players[0].id != game.players[1].id

    def test_turn_cycle_main_phase(self):
        """Test the standard turn cycling in MAIN_PHASE."""
        names = ["Alice", "Bob"]
        game = GameState.create_new_game(names)
        
        # FIX: Fast forward to MAIN_PHASE
        game.turn_phase = TurnPhase.MAIN_PHASE
        
        assert game.get_current_player().name == "Alice"
        
        game.next_turn()
        assert game.get_current_player().name == "Bob"
        # In main phase, next_turn resets to ROLL_DICE
        assert game.turn_phase == TurnPhase.ROLL_DICE
        
        game.next_turn()
        assert game.get_current_player().name == "Alice"

    def test_dice_roll_mocked(self):
        game = GameState.create_new_game(["A", "B"])
        
        # FIX: Must be in ROLL_DICE phase
        game.turn_phase = TurnPhase.ROLL_DICE
        
        with patch('random.randint', side_effect=[3, 4]):
            roll = game.roll_dice()
            
            assert roll == 7
            assert game.dice_roll == 7
            assert game.turn_phase == TurnPhase.MAIN_PHASE