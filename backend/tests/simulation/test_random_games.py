import random

import pytest

from app.models.game import TRADABLE_RESOURCES, GameState, TurnPhase
from app.models.settings import GameSettings
from app.services.random_player import play_step
from app.services.serializer import GameSerializer

MAX_ACTIONS = 40_000


def assert_invariants(game: GameState):
    if game.turn_phase == TurnPhase.DISCARD:
        assert all(
            game.get_player_by_color(c).card_count() > game.settings.discard_limit
            for c in game.pending_discards
        )

    for player in game.players:
        assert all(n >= 0 for n in player.resources.values())
        assert player.knights_played + len(player.dev_cards) <= 25
        assert game._count_roads(player) <= 15

        buildings = [b for b in game.settlements.values() if b.owner == player.color]
        points = sum(2 if b.type == "city" else 1 for b in buildings)
        if game.longest_road_holder == player.color:
            points += 2
        if game.largest_army_holder == player.color:
            points += 2
        assert player.victory_points == points

    for resource in TRADABLE_RESOURCES:
        assert sum(p.resources[resource] for p in game.players) <= 19

    for vertex in game.settlements:
        assert game.board.is_on_board(vertex)
        assert not any(n in game.settlements for n in vertex.get_adjacent_vertices())


HOUSE_RULES = [
    GameSettings(victory_points=6, discard_limit=5, desert="center", friendly_robber=True, turn_seconds=60),
    GameSettings(victory_points=15, discard_limit=12, friendly_robber=True),
    GameSettings(victory_points=8, discard_limit=9, desert="center"),
]


@pytest.mark.parametrize("seed", range(12))
def test_random_game_reaches_a_winner_through_serialization(seed):
    play_to_the_end(seed, GameSettings())


@pytest.mark.parametrize("seed", range(6))
def test_random_game_with_house_rules(seed):
    play_to_the_end(seed, HOUSE_RULES[seed % len(HOUSE_RULES)])


def play_to_the_end(seed: int, settings: GameSettings):
    rng = random.Random(seed)
    random.seed(seed)
    names = ["Alice", "Bob", "Charlie", "Dana"][: 2 + seed % 3]
    game = GameState.create_new_game(names, settings)

    for _ in range(MAX_ACTIONS):
        if game.is_game_over:
            break
        play_step(game, rng)
        assert_invariants(game)
        # Every action on the server starts from the persisted state
        game = GameSerializer.dict_to_game(GameSerializer.game_to_dict(game))

    assert game.is_game_over
    assert game.winner is not None
    assert game.winner.victory_points + game.winner.hidden_points() >= settings.victory_points
    assert game.settings == settings

    with pytest.raises(ValueError, match="game is over"):
        game.end_turn(game.get_current_player())


TIMED_OUT_TURNS = 300


@pytest.mark.parametrize("seed", range(6))
def test_games_where_every_turn_times_out(seed):
    """Nobody builds after the setup, so these games cannot end: they run a fixed number of turns."""
    settings = [GameSettings(), *HOUSE_RULES][seed % 4]
    rng = random.Random(seed)
    random.seed(seed)
    names = ["Alice", "Bob", "Charlie", "Dana"][: 2 + seed % 3]
    game = GameState.create_new_game(names, settings)

    for turn in range(TIMED_OUT_TURNS):
        seat = game.current_turn_index
        game.auto_finish_turn(rng)
        assert_invariants(game)
        assert game.turn_number == turn + 1
        if turn >= 2 * len(names):
            assert game.current_turn_index == (seat + 1) % len(names)
        game = GameSerializer.dict_to_game(GameSerializer.game_to_dict(game))

    assert not game.is_game_over
    assert game.turn_phase == TurnPhase.ROLL_DICE
    assert all(game._count_roads(p) == 2 for p in game.players)


@pytest.mark.parametrize("seed", range(9))
def test_random_games_with_players_running_out_of_time(seed):
    """Timeouts strike at any moment of a normal game, so they meet every phase it reaches."""
    settings = [GameSettings(), *HOUSE_RULES][seed % 4]
    rng = random.Random(seed)
    random.seed(seed)
    names = ["Alice", "Bob", "Charlie", "Dana"][: 2 + seed % 3]
    game = GameState.create_new_game(names, settings)
    phases = set()

    for _ in range(MAX_ACTIONS):
        if game.is_game_over:
            break
        if rng.random() < 0.05:
            phases.add(game.turn_phase)
            turn = game.turn_number
            game.auto_finish_turn(rng)
            assert game.is_game_over or game.turn_number == turn + 1
        else:
            play_step(game, rng)
        assert_invariants(game)
        game = GameSerializer.dict_to_game(GameSerializer.game_to_dict(game))

    assert game.is_game_over
    assert {TurnPhase.ROLL_DICE, TurnPhase.MAIN_PHASE} <= phases
