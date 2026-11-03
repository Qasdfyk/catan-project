import pytest

from app.models.board import ResourceType
from app.models.game import GameState, TurnPhase
from app.services.actions import apply_action
from app.services.serializer import GameSerializer

WOOD = ResourceType.WOOD
ORE = ResourceType.ORE


@pytest.fixture
def game():
    g = GameState.create_new_game(["Alice", "Bob", "Charlie"])
    g.turn_phase = TurnPhase.MAIN_PHASE
    g.players[0].add_resource(WOOD, 2)
    g.players[1].add_resource(ORE, 1)
    return g


def test_accepted_offer_swaps_the_cards(game):
    alice, bob, _ = game.players

    game.offer_trade(alice, {WOOD: 2}, {ORE: 1})
    game.respond_to_trade(bob, True)
    game.confirm_trade(alice, bob)

    assert alice.resources[ORE] == 1
    assert alice.resources[WOOD] == 0
    assert bob.resources[WOOD] == 2
    assert game.trade_offer is None


def test_only_the_current_player_can_offer(game):
    with pytest.raises(ValueError, match="not your turn"):
        game.offer_trade(game.players[1], {ORE: 1}, {WOOD: 1})


def test_offer_needs_the_main_phase(game):
    game.turn_phase = TurnPhase.ROLL_DICE

    with pytest.raises(ValueError, match="roll the dice"):
        game.offer_trade(game.players[0], {WOOD: 1}, {ORE: 1})


@pytest.mark.parametrize("give, get, message", [
    ({}, {ORE: 1}, "both sides"),
    ({WOOD: 1}, {}, "both sides"),
    ({WOOD: 1}, {WOOD: 1}, "are giving"),
    ({WOOD: 3}, {ORE: 1}, "do not have"),
    ({WOOD: -1}, {ORE: 1}, "negative"),
    ({WOOD: 1}, {ResourceType.DESERT: 1}, "cannot be traded"),
])
def test_invalid_offers(game, give, get, message):
    with pytest.raises(ValueError, match=message):
        game.offer_trade(game.players[0], give, get)


def test_cannot_accept_without_the_cards(game):
    alice, _, charlie = game.players
    game.offer_trade(alice, {WOOD: 1}, {ORE: 1})

    with pytest.raises(ValueError, match="do not have the cards"):
        game.respond_to_trade(charlie, True)


def test_proposer_cannot_answer_own_offer(game):
    alice = game.players[0]
    game.offer_trade(alice, {WOOD: 1}, {ORE: 1})

    with pytest.raises(ValueError, match="your own offer"):
        game.respond_to_trade(alice, True)


def test_cannot_confirm_with_a_player_who_declined(game):
    alice, bob, _ = game.players
    game.offer_trade(alice, {WOOD: 1}, {ORE: 1})
    game.respond_to_trade(bob, False)

    with pytest.raises(ValueError, match="has not accepted"):
        game.confirm_trade(alice, bob)


def test_changing_the_answer_replaces_it(game):
    alice, bob, _ = game.players
    game.offer_trade(alice, {WOOD: 1}, {ORE: 1})

    game.respond_to_trade(bob, False)
    game.respond_to_trade(bob, True)

    assert game.trade_offer.accepted == [bob.color]
    assert game.trade_offer.declined == []


def test_confirm_rechecks_hands(game):
    alice, bob, _ = game.players
    game.offer_trade(alice, {WOOD: 2}, {ORE: 1})
    game.respond_to_trade(bob, True)
    alice.resources[WOOD] = 1

    with pytest.raises(ValueError, match="no longer available"):
        game.confirm_trade(alice, bob)

    assert bob.resources[ORE] == 1


def test_only_proposer_can_cancel(game):
    alice, bob, _ = game.players
    game.offer_trade(alice, {WOOD: 1}, {ORE: 1})

    with pytest.raises(ValueError, match="no open offer"):
        game.cancel_trade(bob)

    game.cancel_trade(alice)
    assert game.trade_offer is None


def test_offer_ends_with_the_turn(game):
    alice = game.players[0]
    game.offer_trade(alice, {WOOD: 1}, {ORE: 1})

    game.end_turn(alice)

    assert game.trade_offer is None


def test_offer_survives_serialization(game):
    alice, bob, _ = game.players
    game.offer_trade(alice, {WOOD: 2}, {ORE: 1})
    game.respond_to_trade(bob, True)

    loaded = GameSerializer.dict_to_game(GameSerializer.game_to_dict(game))

    assert loaded.trade_offer == game.trade_offer


def test_actions_parse_trade_payloads(game):
    apply_action(game, 0, "offer_trade", {"give": {"wood": 2}, "get": {"ore": 1}})
    apply_action(game, 1, "respond_trade", {"accept": True})
    apply_action(game, 0, "confirm_trade", {"partner_seat": 1})

    assert game.players[0].resources[ORE] == 1


@pytest.mark.parametrize("payload", [{"give": "x", "get": {}}, {"give": {"gold": 1}, "get": {"ore": 1}}])
def test_malformed_trade_payload(game, payload):
    with pytest.raises(ValueError):
        apply_action(game, 0, "offer_trade", payload)
