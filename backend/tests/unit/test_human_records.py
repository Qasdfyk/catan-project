import json

import pytest

from app.services.human_records import anonymize, eligible, new_dataset_id


def room(*seats):
    return {"seats": list(seats)}


AGREED = {"name": "Alice", "share_for_research": True}
REFUSED = {"name": "Bob", "share_for_research": False}
SILENT = {"name": "Carol"}
BOT = {"name": "Ada", "bot": True, "level": "hard"}


@pytest.mark.parametrize("seats, expected", [
    ((AGREED,), True),
    ((AGREED, BOT, BOT), True),
    ((AGREED, REFUSED), False),
    # Not answering is not agreeing
    ((AGREED, SILENT), False),
    # A bot finishing the game of somebody who left does not answer for them
    ((AGREED, {**REFUSED, "bot": True, "replaced": True}), False),
    ((AGREED, {**AGREED, "name": "Bob", "bot": True, "replaced": True}), True),
    # Bots alone are not a human game
    ((BOT, BOT), False),
])
def test_every_person_must_agree(seats, expected):
    assert eligible(room(*seats)) is expected


def test_truthy_values_are_not_consent():
    assert not eligible(room({"name": "Alice", "share_for_research": "yes"}))


def closed_record():
    return {
        "format": "catan-game-record",
        "game_id": "ab12cd34",
        "started_at": "2026-11-27T19:56:02+00:00",
        "finished_at": "2026-11-27T20:41:17+00:00",
        "players": [
            {"seat": 0, "name": "Alice Kowalska", "color": "red", "kind": "human", "bot_level": None},
            {"seat": 1, "name": "Ada", "color": "blue", "kind": "bot", "bot_level": "hard"},
            {"seat": 2, "name": "Bob", "color": "white", "kind": "human", "bot_level": None},
        ],
        "events": [{"turn": 0, "seat": 0, "action": "roll_dice", "payload": {}}],
        "result": {"winner_seat": 2, "victory_points": [4, 6, 10], "turns": 51},
    }


def test_anonymous_copy_hides_who_played_and_when():
    record = closed_record()

    anonymous = anonymize(record, "0123456789abcdef")

    assert [p["name"] for p in anonymous["players"]] == ["Player 1", "Bot 2", "Player 3"]
    assert anonymous["game_id"] == "0123456789abcdef"
    assert (anonymous["started_at"], anonymous["finished_at"]) == ("2026-11-27", "2026-11-27")
    text = json.dumps(anonymous)
    for secret in ("Alice", "Kowalska", "Bob", "ab12cd34", "19:56", "20:41"):
        assert secret not in text


def test_anonymous_copy_keeps_the_game():
    record = closed_record()

    anonymous = anonymize(record, new_dataset_id())

    for key in ("events", "result", "format"):
        assert anonymous[key] == record[key]
    assert [(p["kind"], p["bot_level"], p["color"]) for p in anonymous["players"]] == [
        (p["kind"], p["bot_level"], p["color"]) for p in record["players"]
    ]
    # The platform record itself stays as it was
    assert record["players"][0]["name"] == "Alice Kowalska"


def test_unfinished_games_are_refused():
    with pytest.raises(ValueError):
        anonymize({**closed_record(), "finished_at": None}, new_dataset_id())


def test_dataset_ids_are_random_and_safe_as_file_names():
    ids = {new_dataset_id() for _ in range(100)}
    assert len(ids) == 100
    assert all(len(i) == 16 and i.isalnum() for i in ids)
