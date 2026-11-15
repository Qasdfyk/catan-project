import gzip
import json
import math

import pytest

from app.services import record_stats
from app.services.game_record import simulate
from app.services.record_stats import (
    entropy,
    eta_squared,
    game_stats,
    head_to_head,
    label,
    point_sources,
    summarize,
    win_type,
)


@pytest.fixture(scope="module")
def records():
    games = [simulate(seed) for seed in (3, 4, 5)]
    # Two zoo bots, so the labels differ and personalities show up
    for record in games:
        record["players"][0]["bot_level"] = "zoo"
        record["players"][0]["bot_style"] = {"archetype": "port", "personality": "wary"}
        record["players"][1]["bot_level"] = "zoo"
        record["players"][1]["bot_style"] = {"archetype": "ore-wheat", "personality": "friendly"}
    return games


@pytest.fixture(scope="module")
def stats(records):
    return [game_stats(record) for record in records]


def test_point_sources_add_up_to_the_recorded_points(records, stats):
    for record, game in zip(records, stats, strict=True):
        for seat in game["seats"]:
            assert sum(point_sources(seat).values()) == record["result"]["victory_points"][seat["seat"]]


def test_seat_facts_agree_with_the_events(records, stats):
    for record, game in zip(records, stats, strict=True):
        confirmed = sum(1 for e in record["events"] if e["action"] == "confirm_trade")
        # Every trade between players has two sides
        assert sum(s["trades"] for s in game["seats"]) == 2 * confirmed
        bought = sum(1 for e in record["events"] if e["action"] == "buy_dev_card")
        assert sum(s["dev_cards"] for s in game["seats"]) == bought
        assert [s["won"] for s in game["seats"]].count(True) == 1
        for seat in game["seats"]:
            assert math.isclose(sum(seat["setup"].values()), 1)
            assert 2 <= seat["settlements"] + seat["cities"] <= 9


def test_labels():
    assert label({"bot_level": "zoo", "bot_style": {"archetype": "port"}}) == "port"
    assert label({"kind": "bot", "bot_level": "hard"}) == "hard"
    assert label({"kind": "human", "bot_level": None}) == "human"
    assert label({}) == "human"


def test_win_type():
    seat = {"longest_road": True, "largest_army": False}
    assert win_type(seat) == "road"
    assert win_type({**seat, "largest_army": True}) == "road and army"
    assert win_type({"longest_road": False, "largest_army": True}) == "army"
    assert win_type({"longest_road": False, "largest_army": False}) == "neither"


def test_entropy():
    assert entropy([5, 5, 5, 5]) == 2
    assert entropy([7, 0]) == 0
    assert entropy([]) == 0
    assert math.isclose(entropy([1, 1]), 1)


def test_eta_squared():
    assert eta_squared({"a": [1, 2, 3], "b": [1, 2, 3]}) == 0
    assert eta_squared({"a": [1, 1], "b": [5, 5]}) == 1
    assert eta_squared({"a": [4]}) == 0
    assert eta_squared({"a": [2, 2], "b": [2]}) == 0
    assert 0 < eta_squared({"a": [1, 2], "b": [3, 5]}) < 1


def seat(name, points, won=False):
    return {"label": name, "points": points, "won": won}


def test_head_to_head_counts_places_between_labels():
    games = [
        {"seats": [seat("a", 10, True), seat("b", 7), seat("b", 4)]},
        {"seats": [seat("a", 6), seat("b", 6), seat("c", 10, True)]},
    ]
    table = head_to_head(games)
    # a above both b in game 1, level with b in game 2
    assert table["a"]["b"] == pytest.approx(2.5 / 3)
    assert table["b"]["a"] == pytest.approx(0.5 / 3)
    assert table["c"] == {"a": 1, "b": 1}
    assert "a" not in table["a"]
    for a, row in table.items():
        for b, share in row.items():
            assert share + table[b][a] == pytest.approx(1)


def test_summary(stats):
    s = summarize(stats)
    assert s["games"] == 3
    assert set(s["labels"]) == {"port", "ore-wheat", "random"}
    assert s["labels"]["random"]["seats"] == 6
    assert set(s["personalities"]) == {"wary", "friendly"}
    assert sum(s["win_types"].values()) == 3
    assert sum(s["winner_points"].values()) == pytest.approx(1)
    assert all(0 <= v <= 1 for v in s["style_spread"].values())
    assert all(v >= 0 for v in s["spread"].values())
    assert summarize([])["spread"]["roads"] == 0


def test_command_line(records, tmp_path, capsys):
    with gzip.open(tmp_path / "a.json.gz", "wt", encoding="utf-8") as file:
        json.dump(records[0], file)
    (tmp_path / "b.json").write_text(json.dumps(records[1]), encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not a record", encoding="utf-8")

    assert record_stats._main([str(tmp_path), "--jobs", "1"]) == 0
    report = capsys.readouterr().out
    assert report.startswith("2 games")
    assert "head to head" in report and "ore-wheat" in report

    assert record_stats._main([str(tmp_path / "b.json"), str(tmp_path / "a.json.gz"), "--json", "--jobs", "2"]) == 0
    assert json.loads(capsys.readouterr().out)["games"] == 2

    empty = tmp_path / "empty"
    empty.mkdir()
    assert record_stats._main([str(empty)]) == 1
