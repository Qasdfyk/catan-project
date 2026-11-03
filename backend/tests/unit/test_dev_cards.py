import pytest
from unittest.mock import patch
from collections import Counter

from app.models.board import ResourceType
from app.models.game import Building, BuildingType, GameState, TurnPhase
from app.models.hex_lib import Hex, Vertex
from app.models.player import DevCard
from app.services.serializer import GameSerializer


def main_phase_game():
    game = GameState.create_new_game(["Alice", "Bob"])
    game.turn_phase = TurnPhase.MAIN_PHASE
    game.setup_queue = []
    return game


def add_network(game, player):
    vertex = Vertex(Hex(0, 0, 0), 0).get_canonical()
    game.settlements[vertex] = Building(player.color, BuildingType.SETTLEMENT)
    return vertex


class TestBuying:
    def test_deck_has_the_standard_cards(self):
        game = GameState.create_new_game(["Alice", "Bob"])

        assert Counter(game.dev_deck) == {
            DevCard.KNIGHT: 14, DevCard.VICTORY_POINT: 5, DevCard.ROAD_BUILDING: 2,
            DevCard.YEAR_OF_PLENTY: 2, DevCard.MONOPOLY: 2,
        }

    def test_buying_costs_ore_wheat_sheep(self):
        game = main_phase_game()
        alice = game.players[0]
        for resource in (ResourceType.ORE, ResourceType.WHEAT, ResourceType.SHEEP):
            alice.add_resource(resource)

        game.buy_dev_card(alice)

        assert alice.card_count() == 0
        assert len(alice.new_dev_cards) == 1
        assert len(game.dev_deck) == 24

    def test_cannot_buy_without_resources_or_from_empty_deck(self):
        game = main_phase_game()
        alice = game.players[0]

        with pytest.raises(ValueError, match="Insufficient"):
            game.buy_dev_card(alice)

        game.dev_deck = []
        with pytest.raises(ValueError, match="no development cards"):
            game.buy_dev_card(alice)

    def test_card_is_playable_from_the_next_turn(self):
        game = main_phase_game()
        alice, bob = game.players
        alice.new_dev_cards = [DevCard.KNIGHT]

        with pytest.raises(ValueError, match="turn you bought"):
            game.play_knight(alice)

        game.end_turn(alice)
        game.turn_phase = TurnPhase.MAIN_PHASE
        game.end_turn(bob)

        assert alice.dev_cards == [DevCard.KNIGHT]
        game.play_knight(alice)


class TestPlaying:
    def test_only_one_card_per_turn(self):
        game = main_phase_game()
        alice = game.players[0]
        alice.dev_cards = [DevCard.MONOPOLY, DevCard.YEAR_OF_PLENTY]

        game.play_monopoly(alice, ResourceType.ORE)

        with pytest.raises(ValueError, match="already played"):
            game.play_year_of_plenty(alice, ResourceType.ORE, ResourceType.ORE)
        assert game.playable_dev_cards(alice) == []

    def test_cannot_play_a_card_you_do_not_have(self):
        game = main_phase_game()

        with pytest.raises(ValueError, match="do not have"):
            game.play_knight(game.players[0])

    def test_cannot_play_on_another_players_turn(self):
        game = main_phase_game()
        bob = game.players[1]
        bob.dev_cards = [DevCard.KNIGHT]

        with pytest.raises(ValueError, match="not your turn"):
            game.play_knight(bob)

    def test_victory_point_card_is_never_playable(self):
        game = main_phase_game()
        alice = game.players[0]
        alice.dev_cards = [DevCard.VICTORY_POINT]

        assert game.playable_dev_cards(alice) == []

    def test_knight_after_rolling_returns_to_main_phase(self):
        game = main_phase_game()
        alice = game.players[0]
        alice.dev_cards = [DevCard.KNIGHT]

        game.play_knight(alice)
        assert game.turn_phase == TurnPhase.MOVE_ROBBER

        game.move_robber(alice, next(h for h in game.board.tiles if h != game.robber_hex))

        assert game.turn_phase == TurnPhase.MAIN_PHASE
        assert alice.knights_played == 1

    def test_knight_before_rolling_returns_to_the_roll(self):
        game = main_phase_game()
        game.turn_phase = TurnPhase.ROLL_DICE
        alice, bob = game.players
        alice.dev_cards = [DevCard.KNIGHT]
        target = Hex(2, -2, 0)
        game.robber_hex = Hex(0, 0, 0)
        game.settlements[Vertex(target, 0).get_canonical()] = Building(bob.color, BuildingType.SETTLEMENT)
        bob.add_resource(ResourceType.ORE)

        game.play_knight(alice)
        game.move_robber(alice, target)
        game.steal_resource(alice, bob)

        assert game.turn_phase == TurnPhase.ROLL_DICE

    def test_seven_after_a_knight_ends_in_main_phase(self):
        game = main_phase_game()
        game.turn_phase = TurnPhase.ROLL_DICE
        alice = game.players[0]
        alice.dev_cards = [DevCard.KNIGHT]

        game.play_knight(alice)
        game.move_robber(alice, next(h for h in game.board.tiles if h != game.robber_hex))
        game.return_phase = TurnPhase.ROLL_DICE
        with patch('random.randint', side_effect=[3, 4]):
            game.roll_dice(alice)
        game.move_robber(alice, next(h for h in game.board.tiles if h != game.robber_hex))

        assert game.turn_phase == TurnPhase.MAIN_PHASE

    def test_road_building_gives_two_free_roads(self):
        game = main_phase_game()
        alice = game.players[0]
        vertex = add_network(game, alice)
        alice.dev_cards = [DevCard.ROAD_BUILDING]

        game.play_road_building(alice)
        assert game.turn_phase == TurnPhase.ROAD_BUILDING
        with pytest.raises(ValueError, match="free roads"):
            game.end_turn(alice)

        game.place_road(alice, vertex.get_touching_edges()[0])
        assert game.free_roads_left == 1
        game.place_road(alice, game.legal_roads(alice)[0])

        assert game.turn_phase == TurnPhase.MAIN_PHASE
        assert game._count_roads(alice) == 2
        assert alice.card_count() == 0

    def test_road_building_needs_a_place_for_a_road(self):
        game = main_phase_game()
        alice = game.players[0]
        alice.dev_cards = [DevCard.ROAD_BUILDING]

        with pytest.raises(ValueError, match="nowhere"):
            game.play_road_building(alice)

        assert alice.dev_cards == [DevCard.ROAD_BUILDING]
        assert game.playable_dev_cards(alice) == []

    def test_year_of_plenty_takes_two_cards_from_the_bank(self):
        game = main_phase_game()
        alice = game.players[0]
        alice.dev_cards = [DevCard.YEAR_OF_PLENTY]

        game.play_year_of_plenty(alice, ResourceType.ORE, ResourceType.WHEAT)

        assert alice.resources[ResourceType.ORE] == 1
        assert alice.resources[ResourceType.WHEAT] == 1

    def test_year_of_plenty_is_limited_by_the_bank(self):
        game = main_phase_game()
        alice, bob = game.players
        alice.dev_cards = [DevCard.YEAR_OF_PLENTY]
        bob.add_resource(ResourceType.ORE, 18)

        with pytest.raises(ValueError, match="bank does not have"):
            game.play_year_of_plenty(alice, ResourceType.ORE, ResourceType.ORE)

        assert alice.dev_cards == [DevCard.YEAR_OF_PLENTY]

    def test_monopoly_takes_every_card_of_a_resource(self):
        game = GameState.create_new_game(["Alice", "Bob", "Charlie"])
        game.turn_phase = TurnPhase.MAIN_PHASE
        alice, bob, charlie = game.players
        alice.dev_cards = [DevCard.MONOPOLY]
        bob.add_resource(ResourceType.ORE, 3)
        charlie.add_resource(ResourceType.ORE, 2)
        charlie.add_resource(ResourceType.WOOD, 1)

        game.play_monopoly(alice, ResourceType.ORE)

        assert alice.resources[ResourceType.ORE] == 5
        assert bob.card_count() == 0
        assert charlie.card_count() == 1


class TestLargestArmy:
    def play_knights(self, game, player, count):
        for _ in range(count):
            player.dev_cards = [DevCard.KNIGHT]
            game.dev_card_played = False
            game.turn_phase = TurnPhase.MAIN_PHASE
            game.current_turn_index = game.players.index(player)
            game.play_knight(player)

    def test_three_knights_give_two_points(self):
        game = main_phase_game()
        alice = game.players[0]

        self.play_knights(game, alice, 2)
        assert game.largest_army_holder is None

        self.play_knights(game, alice, 1)

        assert game.largest_army_holder == alice.color
        assert alice.victory_points == 2

    def test_challenger_needs_more_knights(self):
        game = main_phase_game()
        alice, bob = game.players
        self.play_knights(game, alice, 3)

        self.play_knights(game, bob, 3)
        assert game.largest_army_holder == alice.color

        self.play_knights(game, bob, 1)

        assert game.largest_army_holder == bob.color
        assert alice.victory_points == 0
        assert bob.victory_points == 2


class TestVictoryPointCards:
    def test_hidden_points_win_on_own_turn(self):
        game = main_phase_game()
        alice = game.players[0]
        alice.victory_points = 9
        for resource in (ResourceType.ORE, ResourceType.WHEAT, ResourceType.SHEEP):
            alice.add_resource(resource)
        game.dev_deck = [DevCard.VICTORY_POINT]

        game.buy_dev_card(alice)

        assert game.is_game_over
        assert game.winner == alice

    def test_hidden_points_do_not_show_in_public_points(self):
        game = main_phase_game()
        alice = game.players[0]
        alice.dev_cards = [DevCard.VICTORY_POINT]

        assert alice.victory_points == 0
        assert alice.hidden_points() == 1


def test_dev_card_state_survives_serialization():
    game = main_phase_game()
    alice = game.players[0]
    alice.dev_cards = [DevCard.KNIGHT, DevCard.MONOPOLY]
    alice.new_dev_cards = [DevCard.VICTORY_POINT]
    alice.knights_played = 2
    game.dev_card_played = True
    game.return_phase = TurnPhase.ROLL_DICE
    game.free_roads_left = 1

    loaded = GameSerializer.dict_to_game(GameSerializer.game_to_dict(game))

    player = loaded.players[0]
    assert player.dev_cards == alice.dev_cards
    assert player.new_dev_cards == alice.new_dev_cards
    assert player.knights_played == 2
    assert loaded.dev_deck == game.dev_deck
    assert loaded.dev_card_played is True
    assert loaded.return_phase == TurnPhase.ROLL_DICE
    assert loaded.free_roads_left == 1
