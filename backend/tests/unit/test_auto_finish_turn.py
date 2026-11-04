import random
from unittest.mock import patch

import pytest

from app.models.board import ResourceType
from app.models.game import Building, BuildingType, GameState, TurnPhase
from app.models.hex_lib import Hex, Vertex
from app.models.player import DevCard
from app.models.settings import GameSettings
from app.services.serializer import GameSerializer

NEAR = Hex(1, -1, 0)
FAR = Hex(-2, 2, 0)


def played_game(*names, settings=None, seed=0):
    """A game past the setup, with the first player about to roll."""
    game = GameState.create_new_game(list(names or ("Alice", "Bob")), settings)
    rng = random.Random(seed)
    while game.turn_phase == TurnPhase.SETUP:
        game.auto_finish_turn(rng)
    return game


def main_phase(game):
    game.turn_phase = TurnPhase.MAIN_PHASE
    game.dice_roll = 8
    return game


class TestTurnNumber:
    def test_every_setup_turn_counts(self):
        game = GameState.create_new_game(["Alice", "Bob"])
        seats = []

        while game.turn_phase == TurnPhase.SETUP:
            seats.append(game.current_turn_index)
            game.auto_finish_turn(random.Random(1))
            assert game.turn_number == len(seats)

        # The snake order gives Bob two turns in a row, and each has its own number
        assert seats == [0, 1, 1, 0]
        assert game.current_turn_index == 0
        assert game.turn_phase == TurnPhase.ROLL_DICE

    def test_ending_a_turn_counts(self):
        game = main_phase(played_game())
        before = game.turn_number

        game.end_turn(game.players[0])

        assert game.turn_number == before + 1

    def test_winning_move_does_not_count(self):
        game = main_phase(played_game())
        game.players[0].victory_points = 10
        before = game.turn_number

        game.next_turn()

        assert game.is_game_over
        assert game.turn_number == before

    def test_survives_serialization(self):
        game = played_game()

        loaded = GameSerializer.dict_to_game(GameSerializer.game_to_dict(game))

        assert loaded.turn_number == game.turn_number == 4

    def test_old_saves_start_at_zero(self):
        data = GameSerializer.game_to_dict(played_game())
        del data["turn_number"]

        assert GameSerializer.dict_to_game(data).turn_number == 0


class TestAutoFinishTurn:
    def test_setup_places_a_settlement_and_a_road(self):
        game = GameState.create_new_game(["Alice", "Bob"])
        alice = game.players[0]

        game.auto_finish_turn(random.Random(0))

        assert sum(1 for b in game.settlements.values() if b.owner == alice.color) == 1
        assert game._count_roads(alice) == 1
        assert game.current_turn_index == 1
        assert game.log[0] == "Alice ran out of time."

    def test_setup_after_the_settlement_only_places_the_road(self):
        game = GameState.create_new_game(["Alice", "Bob"])
        alice = game.players[0]
        game.place_settlement(alice, game.legal_settlements(alice)[0])

        game.auto_finish_turn(random.Random(0))

        assert sum(1 for b in game.settlements.values() if b.owner == alice.color) == 1
        assert game._count_roads(alice) == 1
        assert game.current_turn_index == 1

    def test_last_setup_turn_leads_to_the_first_roll(self):
        game = played_game("Alice", "Bob", "Charlie")

        assert game.turn_phase == TurnPhase.ROLL_DICE
        assert game.current_turn_index == 0
        assert all(game._count_roads(p) == 2 for p in game.players)

    def test_roll_then_end_the_turn(self):
        game = played_game()

        with patch("random.randint", side_effect=[3, 5]):
            game.auto_finish_turn(random.Random(0))

        assert game.current_turn_index == 1
        assert game.turn_phase == TurnPhase.ROLL_DICE
        assert "Alice rolled 8." in game.log

    def test_main_phase_cancels_the_open_offer(self):
        game = main_phase(played_game())
        alice, bob = game.players
        alice.add_resource(ResourceType.WOOD, 1)
        game.offer_trade(alice, {ResourceType.WOOD: 1}, {ResourceType.ORE: 1})

        with patch.object(game, "cancel_trade", wraps=game.cancel_trade) as cancel:
            game.auto_finish_turn(random.Random(0))

        cancel.assert_called_once_with(alice)
        assert game.trade_offer is None
        assert game.current_turn_index == 1

    def test_seven_makes_every_player_over_the_limit_discard(self):
        game = played_game("Alice", "Bob", "Charlie")
        alice, bob, charlie = game.players
        for player in game.players:
            player.resources.clear()
        alice.add_resource(ResourceType.WOOD, 8)
        bob.add_resource(ResourceType.ORE, 5)
        bob.add_resource(ResourceType.SHEEP, 5)
        charlie.add_resource(ResourceType.WHEAT, 3)

        with patch("random.randint", side_effect=[3, 4]):
            game.auto_finish_turn(random.Random(0))

        # Alice may have stolen one card back after discarding half
        assert alice.card_count() <= 5
        assert bob.card_count() <= 5
        assert game.current_turn_index == 1
        assert game.pending_discards == {}

    def test_discard_finishes_for_all_waiting_players(self):
        game = played_game("Alice", "Bob", "Charlie")
        alice, bob, charlie = game.players
        for player in game.players:
            player.resources.clear()
        bob.add_resource(ResourceType.ORE, 8)
        charlie.add_resource(ResourceType.WOOD, 4)
        charlie.add_resource(ResourceType.BRICK, 6)
        game.turn_phase = TurnPhase.DISCARD
        game.dice_roll = 7
        game.pending_discards = {bob.color: 4, charlie.color: 5}
        game.log = []

        game.auto_finish_turn(random.Random(0))

        assert bob.card_count() == 4
        assert charlie.card_count() == 5
        assert "Bob ran out of time." in game.log
        assert "Charlie ran out of time." in game.log
        assert "Alice ran out of time." not in game.log
        assert game.current_turn_index == 1

    def test_moves_the_robber_and_steals(self):
        game = main_phase(played_game("Alice", "Bob"))
        alice, bob = game.players
        game.settlements = {Vertex(NEAR, 0).get_canonical(): Building(bob.color, BuildingType.SETTLEMENT)}
        game.robber_hex = FAR
        bob.resources.clear()
        bob.add_resource(ResourceType.ORE, 1)
        alice.resources.clear()
        game.turn_phase = TurnPhase.MOVE_ROBBER

        with patch.object(game, "legal_robber_hexes", return_value=[NEAR]):
            game.auto_finish_turn(random.Random(0))

        assert game.robber_hex == NEAR
        assert alice.resources[ResourceType.ORE] == 1
        assert bob.card_count() == 0
        assert game.current_turn_index == 1

    def test_friendly_robber_spares_the_players_behind(self):
        settings = GameSettings(friendly_robber=True)
        game = main_phase(played_game("Alice", "Bob", settings=settings))
        alice, bob = game.players
        game.turn_phase = TurnPhase.MOVE_ROBBER
        legal = game.legal_robber_hexes(alice)

        for seed in range(20):
            trial = GameSerializer.dict_to_game(GameSerializer.game_to_dict(game))
            trial.auto_finish_turn(random.Random(seed))
            assert trial.robber_hex in legal

        # Bob has only his 2 setup points, so the robber keeps away from him
        assert bob.victory_points == 2
        assert len(legal) < len(game.board.tiles) - 1

    def test_knight_before_rolling_goes_on_to_the_roll(self):
        game = played_game()
        alice = game.players[0]
        alice.dev_cards = [DevCard.KNIGHT]
        game.play_knight(alice)

        with patch("random.randint", side_effect=[2, 2]):
            game.auto_finish_turn(random.Random(0))

        assert "Alice rolled 4." in game.log
        assert game.current_turn_index == 1

    def test_steal_phase_takes_a_card(self):
        game = main_phase(played_game())
        alice, bob = game.players
        game.robber_hex = NEAR
        game.settlements[Vertex(NEAR, 0).get_canonical()] = Building(bob.color, BuildingType.SETTLEMENT)
        bob.add_resource(ResourceType.SHEEP, 1)
        before = alice.card_count()
        game.turn_phase = TurnPhase.STEAL

        game.auto_finish_turn(random.Random(0))

        assert alice.card_count() == before + 1
        assert game.current_turn_index == 1

    def test_steal_phase_without_victims_moves_on(self):
        game = main_phase(played_game())
        game.robber_hex = FAR
        game.settlements = {}
        game.turn_phase = TurnPhase.STEAL

        game.auto_finish_turn(random.Random(0))

        assert game.current_turn_index == 1

    def test_places_the_free_roads(self):
        game = main_phase(played_game())
        alice = game.players[0]
        alice.dev_cards = [DevCard.ROAD_BUILDING]
        game.play_road_building(alice)
        before = game._count_roads(alice)

        game.auto_finish_turn(random.Random(0))

        assert game._count_roads(alice) == before + 2
        assert game.free_roads_left == 0
        assert game.current_turn_index == 1

    def test_road_building_with_no_edge_left_moves_on(self):
        game = main_phase(played_game())
        game.turn_phase = TurnPhase.ROAD_BUILDING
        game.free_roads_left = 2

        with patch.object(game, "legal_roads", return_value=[]):
            game.auto_finish_turn(random.Random(0))

        assert game.free_roads_left == 0
        assert game.current_turn_index == 1

    def test_stops_when_the_game_is_won(self):
        game = main_phase(played_game())
        alice = game.players[0]
        alice.dev_cards = [DevCard.VICTORY_POINT] * 5
        alice.victory_points = 5
        before = game.turn_number

        game.auto_finish_turn(random.Random(0))

        assert game.is_game_over
        assert game.winner is alice
        assert game.turn_number == before

    def test_refused_after_the_game_is_over(self):
        game = played_game()
        game.is_game_over = True

        with pytest.raises(ValueError, match="game is over"):
            game.auto_finish_turn()

    def test_uses_the_module_random_by_default(self):
        game = GameState.create_new_game(["Alice", "Bob"])

        game.auto_finish_turn()

        assert game.current_turn_index == 1
