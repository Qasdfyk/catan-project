"""
Statistics of finished games, read from game records (docs/game-record.md).

Everything is worked out from the record alone, by replaying it, so the same
numbers describe bot tournaments, games played on the site and any game
converted to the record format later. It answers two questions about a set of
games: how differently the players played, and who beats whom.

    python -m app.services.record_stats ../.logs/zoo-data/zoo
    python -m app.services.record_stats DIR [DIR ...] --json > stats.json

Seats are grouped by their label: the archetype of a zoo bot, otherwise the
bot level, otherwise "human".
"""
import argparse
import gzip
import json
import math
import os
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.models.game import LARGEST_ARMY_POINTS, LONGEST_ROAD_POINTS, BuildingType
from app.models.hex_lib import Hex, Vertex
from app.services.game_record import replay

RESOURCES = ("wood", "brick", "sheep", "wheat", "ore")
# What the winner held besides buildings and cards
WIN_TYPES = ("road and army", "road", "army", "neither")
# Where points come from
SOURCES = ("settlements", "cities", "vp_cards", "longest_road", "largest_army")
# Seat facts whose spread between labels says how distinct the styles are
STYLE_FACTS = ("setup_ore_wheat", "setup_wood_brick", "cities", "settlements", "roads", "dev_cards", "trades", "port")


def pips(number: Optional[int]) -> int:
    """How many of the 36 rolls of two dice make this number."""
    return 0 if number is None else 6 - abs(7 - number)


def label(player: Dict[str, Any]) -> str:
    style = player.get("bot_style")
    if style:
        return style["archetype"]
    return player.get("bot_level") or player.get("kind") or "human"


def personality(player: Dict[str, Any]) -> Optional[str]:
    style = player.get("bot_style")
    return style["personality"] if style else None


def _setup_pips(record: Dict[str, Any], players: int) -> List[Counter]:
    """The pips of each resource around each seat's two setup settlements."""
    tiles = {(t["hex"]["q"], t["hex"]["r"], t["hex"]["s"]): t for t in record["board"]["tiles"]}
    found = [Counter() for _ in range(players)]
    for event in record["events"]:
        if event["turn"] >= 2 * players:
            break
        if event["action"] != "build_settlement":
            continue
        at = event["payload"]
        vertex = Vertex(Hex(**at["hex"]), at["direction"])
        for hex_ in vertex.get_touching_hexes():
            tile = tiles.get((hex_.q, hex_.r, hex_.s))
            if tile and tile["number"] is not None:
                found[event["seat"]][tile["resource"]] += pips(tile["number"])
    return found


def win_type(seat: Dict[str, Any]) -> str:
    """Which of the two bonus cards a winner held."""
    road, army = seat["longest_road"], seat["largest_army"]
    return WIN_TYPES[0] if road and army else "road" if road else "army" if army else "neither"


def point_sources(seat: Dict[str, Any]) -> Dict[str, int]:
    """A player's points by where they came from. They add up to the final points."""
    return {
        "settlements": seat["settlements"],
        "cities": 2 * seat["cities"],
        "vp_cards": seat["vp_cards"],
        "longest_road": LONGEST_ROAD_POINTS * seat["longest_road"],
        "largest_army": LARGEST_ARMY_POINTS * seat["largest_army"],
    }


def game_stats(record: Dict[str, Any]) -> Dict[str, Any]:
    """Replays one record and describes the game and every seat in it."""
    game = replay(record)
    players = sorted(record["players"], key=lambda p: p["seat"])
    result = record["result"]
    setup = _setup_pips(record, len(players))
    counts: Dict[str, Counter] = defaultdict(Counter)
    for event in record["events"]:
        counts[event["action"]][event["seat"]] += 1
        if event["action"] == "confirm_trade":
            counts["trades"][event["payload"]["partner_seat"]] += 1
    counts["trades"].update(counts["confirm_trade"])

    seats = []
    for entry, player in zip(players, game.players, strict=True):
        seat = entry["seat"]
        buildings = Counter(b.type for b in game.settlements.values() if b.owner == player.color)
        total = sum(setup[seat].values()) or 1
        facts = {
            "seat": seat,
            "label": label(entry),
            "personality": personality(entry),
            "won": seat == result["winner_seat"],
            "points": result["victory_points"][seat],
            "settlements": buildings[BuildingType.SETTLEMENT],
            "cities": buildings[BuildingType.CITY],
            "vp_cards": player.hidden_points(),
            "longest_road": game.longest_road_holder == player.color,
            "largest_army": game.largest_army_holder == player.color,
            "roads": sum(1 for owner in game.roads.values() if owner == player.color),
            "dev_cards": counts["buy_dev_card"][seat],
            "knights": counts["play_knight"][seat],
            "offers": counts["offer_trade"][seat],
            "trades": counts["trades"][seat],
            "bank_trades": counts["trade_with_bank"][seat],
            "port": bool(game._get_player_ports(player)),
            "setup": {r: setup[seat][r] / total for r in RESOURCES},
        }
        facts["setup_ore_wheat"] = facts["setup"]["ore"] + facts["setup"]["wheat"]
        facts["setup_wood_brick"] = facts["setup"]["wood"] + facts["setup"]["brick"]
        seats.append(facts)
    winner = seats[result["winner_seat"]]
    return {"turns": result["turns"], "winner": winner["label"], "win_type": win_type(winner), "seats": seats}


def entropy(counts: Iterable[int]) -> float:
    """Shannon entropy in bits: 0 when every case is the same, log2(n) when n cases are equally common."""
    counts = [c for c in counts if c > 0]
    total = sum(counts)
    return sum(-c / total * math.log2(c / total) for c in counts) if total else 0.0


def eta_squared(groups: Dict[str, List[float]]) -> float:
    """
    The share of the variance of a value explained by the group: 0 when every
    group looks the same, 1 when the group alone fixes the value.
    """
    values = [v for group in groups.values() for v in group]
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    total = sum((v - mean) ** 2 for v in values)
    between = sum(len(g) * (sum(g) / len(g) - mean) ** 2 for g in groups.values() if g)
    return between / total if total else 0.0


def _stdev(values: List[float]) -> float:
    """Population standard deviation: how far a typical seat is from the mean."""
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))


def head_to_head(games: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """
    For every two labels A and B, how often a seat of A finished above a seat
    of B in the games where both played: points decide, a tie counts half and
    the winner is above everyone. Seats of the same label are not compared.
    """
    score: Dict[str, Counter] = defaultdict(Counter)
    meetings: Dict[str, Counter] = defaultdict(Counter)
    for game in games:
        for a in game["seats"]:
            for b in game["seats"]:
                if a["label"] == b["label"]:
                    continue
                meetings[a["label"]][b["label"]] += 1
                if (a["won"], a["points"]) > (b["won"], b["points"]):
                    score[a["label"]][b["label"]] += 1
                elif (a["won"], a["points"]) == (b["won"], b["points"]):
                    score[a["label"]][b["label"]] += 0.5
    return {a: {b: score[a][b] / n for b, n in sorted(row.items())} for a, row in sorted(meetings.items())}


def summarize(games: List[Dict[str, Any]]) -> Dict[str, Any]:
    seats = [seat for game in games for seat in game["seats"]]
    by_label: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for seat in seats:
        by_label[seat["label"]].append(seat)

    def mean(group, key):
        return sum(float(s[key]) for s in group) / len(group)

    labels = {}
    for name, group in sorted(by_label.items()):
        labels[name] = {
            "seats": len(group),
            "wins": sum(s["won"] for s in group),
            "win_rate": mean(group, "won"),
            **{key: mean(group, key) for key in (
                "points", "settlements", "cities", "vp_cards", "roads", "dev_cards", "knights",
                "offers", "trades", "bank_trades", "port", "longest_road", "largest_army",
            )},
            "setup": {r: sum(s["setup"][r] for s in group) / len(group) for r in RESOURCES},
        }
    personalities: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for seat in seats:
        if seat["personality"]:
            personalities[seat["personality"]].append(seat)
    types = Counter(game["win_type"] for game in games)
    winners = [seat for game in games for seat in game["seats"] if seat["won"]]
    winner_points = sum(s["points"] for s in winners) or 1
    return {
        "games": len(games),
        "mean_turns": sum(g["turns"] for g in games) / len(games) if games else 0.0,
        "labels": labels,
        "personalities": {
            name: {key: mean(group, key) for key in ("won", "offers", "trades", "bank_trades")} | {"seats": len(group)}
            for name, group in sorted(personalities.items())
        },
        "head_to_head": head_to_head(games),
        "win_types": {kind: types[kind] for kind in WIN_TYPES},
        "win_type_entropy": entropy(types.values()),
        "winner_points": {
            source: sum(point_sources(s)[source] for s in winners) / winner_points for source in SOURCES
        },
        "spread": {fact: _stdev([float(s[fact]) for s in seats]) for fact in STYLE_FACTS},
        "style_spread": {
            fact: eta_squared({name: [float(s[fact]) for s in group] for name, group in by_label.items()})
            for fact in STYLE_FACTS
        },
    }


def load(path: Path) -> Dict[str, Any]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as file:
        return json.load(file)


def _stats_of(path: Path) -> Dict[str, Any]:
    return game_stats(load(path))


def record_paths(places: Iterable[str]) -> List[Path]:
    paths = []
    for place in map(Path, places):
        if place.is_dir():
            paths += sorted(p for p in place.iterdir() if p.name.endswith((".json", ".json.gz")))
        else:
            paths.append(place)
    return paths


def print_report(s: Dict[str, Any], out=None) -> None:
    out = out or sys.stdout
    def pct(x: float) -> str:
        return f"{100 * x:5.1f}%"

    print(f"{s['games']} games, {s['mean_turns']:.1f} turns on average\n", file=out)
    width = max([5] + [len(name) for name in s["labels"]])
    columns = ("win", "points", "setup ore+wheat", "wood+brick", "cities", "settl.", "roads", "dev", "trades", "port")
    print(f"{'label':{width}}  {'seats':>5}  " + "  ".join(f"{c:>6}" for c in columns), file=out)
    for name, row in s["labels"].items():
        cells = (
            pct(row["win_rate"]), f"{row['points']:.1f}",
            pct(row["setup"]["ore"] + row["setup"]["wheat"]), pct(row["setup"]["wood"] + row["setup"]["brick"]),
            f"{row['cities']:.2f}", f"{row['settlements']:.2f}", f"{row['roads']:.1f}",
            f"{row['dev_cards']:.1f}", f"{row['trades']:.1f}", pct(row["port"]),
        )
        print(f"{name:{width}}  {row['seats']:5}  " + "  ".join(f"{c:>{max(6, len(h))}}" for c, h in zip(cells, columns, strict=True)), file=out)

    if s["personalities"]:
        print(f"\n{'trading':10} {'seats':>5} {'win':>6} {'offers':>7} {'trades':>7} {'bank':>6}", file=out)
        for name, row in s["personalities"].items():
            print(f"{name:10} {row['seats']:5} {pct(row['won'])} {row['offers']:7.1f} {row['trades']:7.1f} {row['bank_trades']:6.1f}", file=out)

    names = list(s["head_to_head"])
    if len(names) > 1:
        print("\nhead to head: how often the row finished above the column", file=out)
        print(f"{'':{width}}  " + "  ".join(f"{n:>{max(6, len(n))}}" for n in names), file=out)
        for a in names:
            cells = [pct(s["head_to_head"][a][b]) if b in s["head_to_head"][a] else "—" for b in names]
            print(f"{a:{width}}  " + "  ".join(f"{c:>{max(6, len(n))}}" for c, n in zip(cells, names, strict=True)), file=out)

    sources = ", ".join(f"{source} {pct(share).strip()}" for source, share in s["winner_points"].items())
    print(f"\nwinners' points: {sources}", file=out)
    kinds = ", ".join(f"{kind} {n}" for kind, n in s["win_types"].items())
    print(f"winners holding the bonus cards: {kinds}", file=out)
    print(f"entropy of that mix: {s['win_type_entropy']:.2f} bits (0 = always the same, 2 = all four alike)", file=out)
    spread = ", ".join(f"{fact} {value:.2f}" for fact, value in s["spread"].items())
    print(f"spread between seats (standard deviation): {spread}", file=out)
    spread = ", ".join(f"{fact} {value:.2f}" for fact, value in s["style_spread"].items())
    print(f"share of variance explained by the label (eta²): {spread}", file=out)


def _main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("places", nargs="+", help="record files or directories of them")
    parser.add_argument("--json", action="store_true", help="print the summary as JSON")
    parser.add_argument("--jobs", type=int, default=os.cpu_count(), help="records replayed at once")
    args = parser.parse_args(argv)

    paths = record_paths(args.places)
    if not paths:
        print("no records found", file=sys.stderr)
        return 1
    if args.jobs > 1 and len(paths) > 1:
        with ProcessPoolExecutor(args.jobs) as pool:
            games = list(pool.map(_stats_of, paths, chunksize=8))
    else:
        games = [_stats_of(p) for p in paths]
    summary = summarize(games)
    if args.json:
        json.dump(summary, sys.stdout, indent=1)
        print()
    else:
        print_report(summary)
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
