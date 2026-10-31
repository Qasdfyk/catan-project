import random

import pytest

from app.models.game import TRADABLE_RESOURCES, GameState, TurnPhase
from app.services.serializer import GameSerializer

MAX_ACTIONS = 40_000


def play_step(game: GameState, rng: random.Random):
    """Performs one random legal action, preferring ones that score points."""
    if game.turn_phase == TurnPhase.DISCARD:
        color, required = next(iter(game.pending_discards.items()))
        player = game.get_player_by_color(color)
        pool = [r for r, n in player.resources.items() for _ in range(n)]
        cards = {}
        for res in rng.sample(pool, required):
            cards[res] = cards.get(res, 0) + 1
        game.discard(player, cards)
        return

    player = game.get_current_player()

    if game.turn_phase == TurnPhase.ROLL_DICE:
        game.roll_dice(player)
    elif game.turn_phase == TurnPhase.MOVE_ROBBER:
        game.move_robber(player, rng.choice(game.legal_robber_hexes(player)))
    elif game.turn_phase == TurnPhase.STEAL:
        game.steal_resource(player, rng.choice(game.steal_victims(player)))
    elif game.turn_phase == TurnPhase.SETUP:
        if game.setup_waiting_for_road:
            game.place_road(player, rng.choice(game.legal_roads(player)))
        else:
            game.place_settlement(player, rng.choice(game.legal_settlements(player)))
    else:
        if cities := game.legal_cities(player):
            game.upgrade_to_city(player, rng.choice(cities))
        elif settlements := game.legal_settlements(player):
            game.place_settlement(player, rng.choice(settlements))
        elif (roads := game.legal_roads(player)) and rng.random() < 0.7:
            game.place_road(player, rng.choice(roads))
        else:
            for give in TRADABLE_RESOURCES:
                if player.resources[give] >= game.trade_rate(player, give):
                    get = rng.choice([r for r in TRADABLE_RESOURCES if r != give])
                    game.trade_with_bank(player, give, get)
                    return
            game.end_turn(player)


def assert_invariants(game: GameState):
    for player in game.players:
        assert all(n >= 0 for n in player.resources.values())
        assert game._count_roads(player) <= 15

        buildings = [b for b in game.settlements.values() if b.owner == player.color]
        points = sum(2 if b.type == "city" else 1 for b in buildings)
        if game.longest_road_holder == player.color:
            points += 2
        assert player.victory_points == points

    for vertex in game.settlements:
        assert game.board.is_on_board(vertex)
        assert not any(n in game.settlements for n in vertex.get_adjacent_vertices())


@pytest.mark.parametrize("seed", range(12))
def test_random_game_reaches_a_winner_through_serialization(seed):
    rng = random.Random(seed)
    random.seed(seed)
    names = ["Alice", "Bob", "Charlie", "Dana"][: 2 + seed % 3]
    game = GameState.create_new_game(names)

    for _ in range(MAX_ACTIONS):
        if game.is_game_over:
            break
        play_step(game, rng)
        assert_invariants(game)
        # Every action on the server starts from the persisted state
        game = GameSerializer.dict_to_game(GameSerializer.game_to_dict(game))

    assert game.is_game_over
    assert game.winner is not None
    assert game.winner.victory_points >= 10

    with pytest.raises(ValueError, match="game is over"):
        game.end_turn(game.get_current_player())
