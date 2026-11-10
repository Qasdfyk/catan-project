"""
A record is complete when replaying it rebuilds the game exactly. These tests
record random games the way the server would, with the state saved and loaded
between actions, and replay them from JSON.
"""
import json
import random

import pytest

from app.models.game import GameState
from app.models.settings import GameSettings
from app.services.game_record import close_record, fingerprint, new_record, replay, simulate
from app.services.random_player import play_step
from app.services.serializer import GameSerializer

MAX_ACTIONS = 40_000
SETTINGS = [
    GameSettings(),
    GameSettings(victory_points=6, discard_limit=5, desert="center", friendly_robber=True, turn_seconds=60),
    GameSettings(victory_points=12, discard_limit=9),
]


def record_game(seed: int, timeout_every: int = 0):
    """Plays a random game; with timeout_every > 0, some turns are finished by the timer instead."""
    rng = random.Random(seed)
    random.seed(seed)
    names = ["Alice", "Bob", "Charlie", "Dana"][: 2 + seed % 3]
    game = GameState.create_new_game(names, SETTINGS[seed % len(SETTINGS)])
    record = new_record(game, source="simulation")
    snapshots = []

    for step in range(MAX_ACTIONS):
        if game.is_game_over:
            break
        if timeout_every and step % timeout_every == timeout_every - 1:
            game.auto_finish_turn(rng)
        else:
            play_step(game, rng)
        record["events"] += game.take_events()
        snapshots.append((len(record["events"]), fingerprint(game)))
        # The server saves the state after every action, and the events must survive that
        game = GameSerializer.dict_to_game(GameSerializer.game_to_dict(game))

    assert game.is_game_over
    return close_record(record, game), game, snapshots


@pytest.mark.parametrize("seed", range(9))
def test_replaying_a_record_rebuilds_the_game(seed):
    record, game, _ = record_game(seed)
    record = json.loads(json.dumps(record))

    replayed = replay(record)

    assert fingerprint(replayed) == fingerprint(game)
    # Replaying records the same events again, outcomes and visibility included
    assert replayed.take_events() == record["events"]
    assert record["result"]["winner_seat"] == game.seat_of(game.winner)


@pytest.mark.parametrize("seed", range(6))
def test_records_keep_moves_made_by_the_turn_timer(seed):
    record, game, _ = record_game(seed, timeout_every=7)

    assert any(event.get("auto") for event in record["events"])
    assert fingerprint(replay(record)) == fingerprint(game)


def test_a_partial_replay_matches_the_game_at_that_point():
    record, _, snapshots = record_game(3)

    for count, expected in snapshots[:: max(1, len(snapshots) // 25)]:
        assert fingerprint(replay(record, upto=count)) == expected


def test_random_player_never_asks_the_bank_for_what_it_lacks():
    # Found by the A3 playtest: in this game the bank runs out of ore, and the
    # random player used to ask for it anyway
    record = simulate(51, 4)
    assert replay(json.loads(json.dumps(record))).is_game_over
