from unittest.mock import patch

import pytest

from app.models.game import GameState, TurnPhase
from app.services.serializer import GameSerializer
from app.services.views import public_view


def rolling_game():
    game = GameState.create_new_game(["Alice", "Bob"])
    game.turn_phase = TurnPhase.ROLL_DICE
    game.setup_queue = []
    return game


def roll(game, d1, d2):
    game.turn_phase = TurnPhase.ROLL_DICE
    with patch('random.randint', side_effect=[d1, d2]):
        game.roll_dice()


def room():
    return {"room_id": "r", "version": 1, "status": "playing", "host_seat": 0,
            "seats": [{"name": "Alice"}, {"name": "Bob"}]}


class TestRollCounts:
    def test_new_game_has_no_rolls(self):
        assert rolling_game().roll_counts == [0] * 11

    def test_each_total_is_counted(self):
        game = rolling_game()

        roll(game, 1, 1)
        roll(game, 3, 5)
        roll(game, 4, 4)
        roll(game, 6, 6)

        # Index 0 counts the 2s, index 10 the 12s
        assert game.roll_counts == [1, 0, 0, 0, 0, 0, 2, 0, 0, 0, 1]

    def test_a_seven_counts_too(self):
        game = rolling_game()

        roll(game, 3, 4)

        assert game.roll_counts[5] == 1
        assert sum(game.roll_counts) == 1

    def test_refused_roll_counts_nothing(self):
        game = rolling_game()
        game.turn_phase = TurnPhase.MAIN_PHASE

        with pytest.raises(ValueError):
            game.roll_dice()

        assert sum(game.roll_counts) == 0

    def test_survives_serialization(self):
        game = rolling_game()
        roll(game, 2, 3)

        loaded = GameSerializer.dict_to_game(GameSerializer.game_to_dict(game))

        assert loaded.roll_counts == game.roll_counts
        assert loaded.roll_counts[3] == 1

    def test_old_saves_start_from_zero(self):
        data = GameSerializer.game_to_dict(rolling_game())
        del data["roll_counts"]

        assert GameSerializer.dict_to_game(data).roll_counts == [0] * 11

    def test_everyone_sees_the_counts(self):
        game = rolling_game()
        roll(game, 5, 5)

        view = public_view(room(), game)

        assert view["game"]["roll_counts"][8] == 1
