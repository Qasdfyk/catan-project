from unittest.mock import patch

import pytest

from app.models.board import Board, ResourceType, Tile
from app.models.game import Building, BuildingType, GameState, TurnPhase
from app.models.hex_lib import Hex, Vertex
from app.models.player import DevCard
from app.models.settings import GameSettings
from app.schemas.game_schemas import SettingsUpdate
from app.services.serializer import GameSerializer
from app.services.views import public_view

CENTER = Hex(0, 0, 0)
NEAR = Hex(1, -1, 0)
FAR = Hex(-2, 2, 0)
FRIENDLY = GameSettings(desert="center", friendly_robber=True)


def game_with(settings, *names):
    game = GameState.create_new_game(list(names or ("Alice", "Bob")), settings)
    game.turn_phase = TurnPhase.MAIN_PHASE
    game.setup_queue = []
    return game


def robber_turn(settings=FRIENDLY):
    """Alice moves the robber; Bob has a settlement on NEAR and 2 visible points."""
    game = game_with(settings, "Alice", "Bob", "Charlie")
    bob = game.players[1]
    game.settlements[Vertex(NEAR, 0).get_canonical()] = Building(bob.color, BuildingType.SETTLEMENT)
    bob.victory_points = 2
    bob.add_resource(ResourceType.WOOD, 3)
    game.robber_hex = FAR
    game.turn_phase = TurnPhase.MOVE_ROBBER
    return game


def room(**extra):
    return {"room_id": "r", "version": 1, "status": "lobby", "host_seat": 0,
            "seats": [{"name": "Alice"}], **extra}


class TestDefaults:
    def test_defaults_are_the_standard_rules(self):
        assert GameSettings().to_dict() == {
            "victory_points": 10, "discard_limit": 7, "desert": "random",
            "friendly_robber": False, "turn_seconds": None,
        }

    def test_missing_and_unknown_keys_are_ignored(self):
        assert GameSettings.from_dict(None) == GameSettings()
        assert GameSettings.from_dict({"victory_points": 8, "old": 1}) == GameSettings(victory_points=8)

    def test_new_game_uses_the_defaults(self):
        assert GameState.create_new_game(["Alice", "Bob"]).settings == GameSettings()


class TestVictoryPoints:
    def test_lower_target_wins_earlier(self):
        game = game_with(GameSettings(victory_points=6))
        alice = game.players[0]
        alice.victory_points = 5
        alice.dev_cards = [DevCard.VICTORY_POINT]

        game._check_victory()

        assert game.winner is alice

    def test_higher_target_is_not_reached_at_ten(self):
        game = game_with(GameSettings(victory_points=12))
        game.players[0].victory_points = 11

        game._check_victory()

        assert not game.is_game_over


class TestDiscardLimit:
    def roll_seven(self, game, cards):
        game.turn_phase = TurnPhase.ROLL_DICE
        game.players[1].add_resource(ResourceType.WOOD, cards)
        with patch('random.randint', side_effect=[3, 4]):
            game.roll_dice(game.players[0])

    def test_hand_at_the_limit_is_kept(self):
        game = game_with(GameSettings(discard_limit=9))

        self.roll_seven(game, 9)

        assert game.pending_discards == {}
        assert game.turn_phase == TurnPhase.MOVE_ROBBER

    def test_hand_over_the_limit_loses_half(self):
        game = game_with(GameSettings(discard_limit=5))

        self.roll_seven(game, 7)

        assert game.pending_discards == {game.players[1].color: 3}


class TestDesert:
    def test_center_desert_is_always_in_the_middle(self):
        for _ in range(30):
            board = Board.create_standard_game(desert="center")
            assert board.tiles[CENTER].resource == ResourceType.DESERT
            assert board.tiles[CENTER].number is None
            assert not Board._red_numbers_touch(board)

    def test_random_desert_moves_around(self):
        positions = {
            next(h for h, t in Board.create_standard_game().tiles.items() if t.resource == ResourceType.DESERT)
            for _ in range(50)
        }
        assert len(positions) > 1

    def test_robber_starts_on_the_center_desert(self):
        game = GameState.create_new_game(["Alice", "Bob"], GameSettings(desert="center"))

        assert game.robber_hex == CENTER

    def test_unknown_placement_is_refused(self):
        with pytest.raises(ValueError, match="desert"):
            Board.create_standard_game(desert="edge")


class TestFriendlyRobber:
    def test_hexes_of_players_with_two_points_are_skipped(self):
        game = robber_turn()

        hexes = game.legal_robber_hexes(game.players[0])

        # A settlement touches three tiles, and all of them are spared
        touched = set(Vertex(NEAR, 0).get_touching_hexes()) - {CENTER}
        assert NEAR in touched
        assert set(hexes) == set(game.board.tiles) - touched - {FAR}

    def test_hexes_are_open_again_at_three_points(self):
        game = robber_turn()
        game.players[1].victory_points = 3

        assert NEAR in game.legal_robber_hexes(game.players[0])

    def test_hidden_points_do_not_lift_the_protection(self):
        game = robber_turn()
        game.players[1].dev_cards = [DevCard.VICTORY_POINT] * 3

        assert NEAR not in game.legal_robber_hexes(game.players[0])

    def test_own_buildings_do_not_protect_a_hex(self):
        game = robber_turn()
        game.settlements[Vertex(FAR, 3).get_canonical()] = Building(game.players[0].color, BuildingType.SETTLEMENT)
        game.robber_hex = CENTER

        assert FAR in game.legal_robber_hexes(game.players[0])

    def test_desert_is_always_allowed(self):
        game = robber_turn()
        game.settlements[Vertex(CENTER, 3).get_canonical()] = Building(game.players[1].color, BuildingType.SETTLEMENT)

        assert CENTER in game.legal_robber_hexes(game.players[0])

    def test_falls_back_to_every_hex_when_all_are_protected(self):
        game = robber_turn()
        game.board.tiles = {
            FAR: Tile(FAR, ResourceType.DESERT),
            NEAR: Tile(NEAR, ResourceType.WOOD, 5),
        }

        assert game.legal_robber_hexes(game.players[0]) == [NEAR]

    def test_off_by_default(self):
        game = robber_turn(GameSettings(desert="center"))

        assert NEAR in game.legal_robber_hexes(game.players[0])

    def test_moving_onto_a_protected_hex_is_refused(self):
        game = robber_turn()

        with pytest.raises(ValueError, match="friendly robber"):
            game.move_robber(game.players[0], NEAR)
        game.move_robber(game.players[0], CENTER)
        assert game.robber_hex == CENTER

    def test_knight_follows_the_same_rule(self):
        game = robber_turn()
        game.turn_phase = TurnPhase.MAIN_PHASE
        game.players[0].dev_cards = [DevCard.KNIGHT]

        game.play_knight(game.players[0])

        with pytest.raises(ValueError, match="friendly robber"):
            game.move_robber(game.players[0], NEAR)

    def test_protected_players_cannot_be_robbed(self):
        game = robber_turn()
        alice, bob = game.players[0], game.players[1]
        # Only reachable through the fallback, when every hex is protected
        game.robber_hex = NEAR
        game.turn_phase = TurnPhase.STEAL

        assert game.steal_victims(alice) == []
        with pytest.raises(ValueError, match="friendly robber"):
            game.steal_resource(alice, bob)

    def test_players_with_more_points_are_still_robbed(self):
        game = robber_turn()
        game.players[1].victory_points = 3
        game.robber_hex = NEAR

        assert game.steal_victims(game.players[0]) == [game.players[1]]


class TestSerialization:
    def test_settings_survive_a_round_trip(self):
        settings = GameSettings(victory_points=12, discard_limit=9, desert="center",
                                friendly_robber=True, turn_seconds=90)
        game = GameState.create_new_game(["Alice", "Bob"], settings)

        loaded = GameSerializer.dict_to_game(GameSerializer.game_to_dict(game))

        assert loaded.settings == settings

    def test_games_saved_without_settings_use_the_defaults(self):
        data = GameSerializer.game_to_dict(GameState.create_new_game(["Alice", "Bob"]))
        del data["settings"]

        assert GameSerializer.dict_to_game(data).settings == GameSettings()


class TestPublicView:
    def test_lobby_shows_the_room_settings(self):
        view = public_view(room(settings={**GameSettings().to_dict(), "victory_points": 8}), None)

        assert view["settings"]["victory_points"] == 8

    def test_old_rooms_show_the_defaults(self):
        assert public_view(room(), None)["settings"] == GameSettings().to_dict()

    def test_game_shows_its_own_settings(self):
        game = GameState.create_new_game(["Alice", "Bob"], GameSettings(turn_seconds=60))

        view = public_view(room(status="playing", seats=[{"name": "Alice"}, {"name": "Bob"}]), game)

        assert view["settings"]["turn_seconds"] == 60


class TestSettingsUpdate:
    def test_only_the_keys_sent_are_returned(self):
        assert SettingsUpdate.changes({"desert": "center", "turn_seconds": None}) == {
            "desert": "center", "turn_seconds": None,
        }

    @pytest.mark.parametrize("payload, message", [
        ({"victory_points": 5}, "6 to 15"),
        ({"victory_points": 16}, "6 to 15"),
        ({"victory_points": True}, "6 to 15"),
        ({"victory_points": None}, "6 to 15"),
        ({"discard_limit": "7"}, "5 to 12"),
        ({"discard_limit": 13}, "5 to 12"),
        ({"desert": "edge"}, "desert"),
        ({"friendly_robber": 1}, "on or off"),
        ({"turn_seconds": 45}, "turn time"),
        ({"speed": "fast"}, "Unknown setting: speed"),
    ])
    def test_invalid_values_get_a_readable_message(self, payload, message):
        with pytest.raises(ValueError, match=message):
            SettingsUpdate.changes(payload)
