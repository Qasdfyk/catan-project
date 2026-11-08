import copy
import random

import pytest

from app.models.board import ResourceType
from app.models.game import GameState, TurnPhase
from app.models.player import DevCard
from app.services.game_record import FORMAT, RecordError, close_record, new_record, replay, simulate


def setup_game(seed=1, names=("Alice", "Bob", "Charlie")) -> GameState:
    """A game past the setup, with the setup recorded."""
    random.seed(seed)
    game = GameState.create_new_game(list(names))
    rng = random.Random(seed)
    while game.turn_phase == TurnPhase.SETUP:
        game.auto_finish_turn(rng)
    return game


@pytest.fixture(scope="module")
def sample():
    return simulate(seed=5, players=3)


def test_every_action_is_recorded_once_with_its_seat_and_payload():
    game = setup_game()
    game.events.clear()
    player = game.get_current_player()

    game.roll_dice(player)
    events = game.take_events()

    assert len(events) == 1
    event = events[0]
    assert event["seat"] == game.seat_of(player)
    assert event["action"] == "roll_dice"
    assert event["payload"] == {}
    assert event["outcome"] == {"dice": game.dice}
    assert "visible_to" not in event, "everyone sees the dice"
    assert game.take_events() == [], "taking the events empties the list"


def test_a_refused_action_leaves_no_event():
    game = setup_game()
    game.events.clear()
    not_current = game.players[(game.current_turn_index + 1) % len(game.players)]

    with pytest.raises(ValueError):
        game.roll_dice(not_current)

    assert game.events == []


def test_a_stolen_card_is_seen_only_by_the_thief_and_the_victim(sample):
    steals = [e for e in sample["events"] if e["action"] == "steal"]

    assert steals
    for event in steals:
        assert event["visible_to"] == sorted([event["seat"], event["payload"]["victim_seat"]])
        assert event["outcome"]["resource"] in {r.value for r in ResourceType}


def test_a_bought_card_is_seen_only_by_the_buyer(sample):
    buys = [e for e in sample["events"] if e["action"] == "buy_dev_card"]

    assert buys
    assert all(e["visible_to"] == [e["seat"]] for e in buys)
    assert [e["outcome"]["card"] for e in buys] == sample["dev_deck"]["cards"][: len(buys)]


def test_only_steals_and_purchases_hide_anything(sample):
    hidden = {e["action"] for e in sample["events"] if "visible_to" in e}

    assert hidden == {"steal", "buy_dev_card"}
    assert sample["dev_deck"]["visible_to"] == []


def test_timer_moves_are_marked_auto():
    game = GameState.create_new_game(["Alice", "Bob"])
    record = new_record(game, source="simulation")

    game.auto_finish_turn(random.Random(1))
    record["events"] += game.take_events()

    assert [e["action"] for e in record["events"]] == ["build_settlement", "build_road"]
    assert all(e["auto"] for e in record["events"])


def test_the_header_describes_the_start_of_the_game():
    random.seed(2)
    game = GameState.create_new_game(["Alice", "Bob"])
    record = new_record(game, source="platform", players=[{}, {"kind": "bot", "bot_level": "hard"}])

    assert record["format"] == FORMAT and record["version"] == 1
    assert len(record["board"]["tiles"]) == 19
    assert sorted(record["dev_deck"]["cards"]) == sorted(c.value for c in game.dev_deck)
    assert record["dev_deck"]["cards"][0] == game.dev_deck[-1].value, "the first card listed is drawn first"
    assert record["players"][1] == {
        "seat": 1, "name": "Bob", "color": "blue", "kind": "bot", "bot_level": "hard",
    }


def test_a_record_cannot_start_after_the_first_action():
    game = setup_game()

    with pytest.raises(ValueError, match="before the first action"):
        new_record(game, source="platform")


def test_the_result_counts_hidden_points(sample):
    replayed = replay(sample)
    winner = replayed.winner

    assert sample["result"]["winner_seat"] == replayed.seat_of(winner)
    assert sample["result"]["victory_points"][replayed.seat_of(winner)] == (
        winner.victory_points + winner.hidden_points()
    )
    assert close_record(copy.deepcopy(sample), replayed)["result"] == sample["result"]


def broken(sample, change):
    record = copy.deepcopy(sample)
    change(record)
    return record


def first(record, action):
    return next(e for e in record["events"] if e["action"] == action)


@pytest.mark.parametrize("change, message", [
    (lambda r: r.update(format="something-else"), "Not a game record"),
    (lambda r: r.update(version=99), "Unsupported record version 99"),
    (lambda r: first(r, "roll_dice")["outcome"].update(dice=[]), "records no dice"),
    (lambda r: first(r, "roll_dice")["outcome"].update(dice=[7, 1]), "impossible die 7"),
    (lambda r: first(r, "end_turn").update(outcome={"dice": [1, 2]}), "never rolled"),
    (lambda r: first(r, "steal")["outcome"].update(resource="desert"), "did not have"),
    (lambda r: first(r, "roll_dice").update(seat=(first(r, "roll_dice")["seat"] + 1) % 3), "was refused"),
    (lambda r: first(r, "build_road").pop("payload"), "malformed"),
    (lambda r: r["players"][0].update(color="orange"), "colors"),
])
def test_a_broken_record_fails_at_the_first_bad_event(sample, change, message):
    with pytest.raises(RecordError, match=message):
        replay(broken(sample, change))


def test_the_recorded_deck_decides_the_cards_drawn(sample):
    record = broken(sample, lambda r: r["dev_deck"]["cards"].reverse())
    if record["dev_deck"]["cards"] == sample["dev_deck"]["cards"]:
        pytest.skip("a symmetric deck")

    replayed = replay(record, upto=sample["events"].index(first(sample, "buy_dev_card")) + 1)
    buyer = replayed.players[first(sample, "buy_dev_card")["seat"]]

    assert buyer.new_dev_cards == [DevCard(record["dev_deck"]["cards"][0])]
