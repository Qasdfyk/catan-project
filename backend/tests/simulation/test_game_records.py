"""
A record is complete when replaying it rebuilds the game exactly. These tests
record random games the way the server would, with the state saved and loaded
between actions, and replay them from JSON.
"""
import copy
import json
import random

import pytest

from app.models.game import GameState
from app.models.settings import GameSettings
from app.services.game_record import close_record, new_record, replay
from app.services.random_player import play_step
from app.services.serializer import GameSerializer

MAX_ACTIONS = 40_000
SETTINGS = [
    GameSettings(),
    GameSettings(victory_points=6, discard_limit=5, desert="center", friendly_robber=True, turn_seconds=60),
    GameSettings(victory_points=12, discard_limit=9),
]


def fingerprint(game: GameState) -> dict:
    """The whole state, minus what a replay legitimately changes: player ids and the text log."""
    # A copy, because the serializer hands out the game's own lists
    data = copy.deepcopy(GameSerializer.game_to_dict(game))
    del data["log"]
    for player in data["players"]:
        del player["id"]
    return data


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
