"""
Game records: one JSON document per game, holding everything needed to replay
it move by move and to know what each player could see. The format is
described in docs/game-record.md.

    record = new_record(game, source="platform")   # right after the game is created
    record["events"] += game.take_events()          # after every action
    close_record(record, game)                       # when the game is over
    replayed = replay(record)                        # rebuilds the same game

Run as a module to record a game between random players, or to check a file:

    python -m app.services.game_record simulate --seed 7 --out game.json
    python -m app.services.game_record check game.json
    python -m app.services.game_record check records/1a2b3c4d.json.gz
"""
import argparse
import copy
import gzip
import json
import random
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.models.board import Board
from app.models.game import GameState
from app.models.player import DevCard, PlayerColor
from app.models.settings import GameSettings
from app.services.actions import apply_action
from app.services.serializer import GameSerializer

FORMAT = "catan-game-record"
VERSION = 1
SOURCES = ("platform", "tournament", "simulation")


class RecordError(ValueError):
    """The record is malformed, or replaying it breaks a rule."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_record(
    game: GameState, source: str, players: Optional[List[Dict[str, Any]]] = None, game_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Describes the game as it starts. Call it before the first action: the deck
    is read from the game, and it shrinks with every card bought. `players`
    may add per seat facts such as {"kind": "bot", "bot_level": "hard"}.
    """
    if source not in SOURCES:
        raise ValueError(f"Unknown source {source!r}.")
    if game.events or game.turn_number or game.settlements:
        raise ValueError("The record must start before the first action.")
    extra = players or [{} for _ in game.players]
    return {
        "format": FORMAT,
        "version": VERSION,
        "source": source,
        "game_id": game_id,
        "started_at": _now(),
        "finished_at": None,
        "settings": game.settings.to_dict(),
        "players": [
            {"seat": seat, "name": p.name, "color": p.color.value, "kind": "human", "bot_level": None, **extra[seat]}
            for seat, p in enumerate(game.players)
        ],
        "board": {
            "tiles": GameSerializer._tiles_to_list(game.board.tiles),
            "ports": GameSerializer._ports_to_list(game.board.ports),
            "robber": GameSerializer._hex_to_dict(game.robber_hex),
        },
        # The game draws from the end of its list; the record keeps draw order.
        # Nobody sees the deck: each card shows up in the event that draws it.
        "dev_deck": {"cards": [card.value for card in reversed(game.dev_deck)], "visible_to": []},
        "events": [],
        "result": None,
    }


def close_record(record: Dict[str, Any], game: GameState) -> Dict[str, Any]:
    """Adds the result. Points include hidden cards, as at the end of a real game."""
    record["finished_at"] = _now()
    record["result"] = {
        "winner_seat": game.seat_of(game.winner) if game.winner else None,
        "victory_points": [p.victory_points + p.hidden_points() for p in game.players],
        "turns": game.turn_number,
    }
    return record


class _RecordedChance:
    """Stands in for the game's random source during a replay, giving back the recorded outcome."""

    def __init__(self, index: int, outcome: Dict[str, Any]):
        self.index = index
        self.dice = list(outcome.get("dice", []))
        self.resource = outcome.get("resource")

    def randint(self, low: int, high: int) -> int:
        if not self.dice:
            raise RecordError(f"Event {self.index} rolls dice but records no dice.")
        value = self.dice.pop(0)
        if not low <= value <= high:
            raise RecordError(f"Event {self.index} records an impossible die {value}.")
        return value

    def choice(self, options):
        for option in options:
            if getattr(option, "value", option) == self.resource:
                return option
        raise RecordError(f"Event {self.index} steals {self.resource!r}, which the victim did not have.")


def _start(record: Dict[str, Any]) -> GameState:
    if record.get("format") != FORMAT:
        raise RecordError("Not a game record.")
    if record.get("version") != VERSION:
        raise RecordError(f"Unsupported record version {record.get('version')!r}; this code reads {VERSION}.")
    try:
        board = Board()
        board.tiles = GameSerializer._list_to_tiles(record["board"]["tiles"])
        board.ports = GameSerializer._list_to_ports(record["board"]["ports"])
        deck = [DevCard(card) for card in reversed(record["dev_deck"]["cards"])]
        players = sorted(record["players"], key=lambda p: p["seat"])
        game = GameState.create_new_game(
            [p["name"] for p in players], GameSettings.from_dict(record["settings"]), board=board, dev_deck=deck
        )
    except (KeyError, TypeError, ValueError) as error:
        raise RecordError(f"Broken header: {error}") from None
    if [p.color for p in game.players] != [PlayerColor(p["color"]) for p in players]:
        raise RecordError("Seat colors differ from the order the game assigns.")
    if GameSerializer._hex_to_dict(game.robber_hex) != record["board"]["robber"]:
        raise RecordError("The robber does not start on the desert.")
    return game


def replay(record: Dict[str, Any], upto: Optional[int] = None) -> GameState:
    """
    Plays the recorded events, or the first `upto` of them, through the same
    checks as live actions. Raises RecordError at the first event that does
    not fit, so a successful replay proves the record is complete.
    """
    game = _start(record)
    for index, event in enumerate(record["events"][:upto]):
        game.rng = _RecordedChance(index, event.get("outcome", {}))
        try:
            apply_action(game, event["seat"], event["action"], event["payload"])
        except (KeyError, TypeError, IndexError) as error:
            raise RecordError(f"Event {index} is malformed: {error}") from None
        except ValueError as error:
            raise RecordError(f"Event {index} ({event['action']}) was refused: {error}") from None
        if game.rng.dice:
            raise RecordError(f"Event {index} records dice that were never rolled.")
    game.rng = random
    return game


def fingerprint(game: GameState) -> Dict[str, Any]:
    """
    The whole state, minus what a replay legitimately changes: player ids and
    the text log. Two games with equal fingerprints are the same game.
    """
    # A copy, because the serializer hands out the game's own lists
    data = copy.deepcopy(GameSerializer.game_to_dict(game))
    del data["log"]
    for player in data["players"]:
        del player["id"]
    return data


def simulate(seed: int, players: int = 4, max_actions: int = 40_000) -> Dict[str, Any]:
    """Records a whole game between random players."""
    from app.services.random_player import play_step

    random.seed(seed)
    rng = random.Random(seed)
    game = GameState.create_new_game(["Alice", "Bob", "Charlie", "Dana"][:players])
    record = new_record(game, source="simulation", players=[{"kind": "bot", "bot_level": "random"}] * players)
    for _ in range(max_actions):
        if game.is_game_over:
            break
        play_step(game, rng)
        record["events"] += game.take_events()
    return close_record(record, game)


def _main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    sim = commands.add_parser("simulate", help="record a game between random players")
    sim.add_argument("--seed", type=int, default=1)
    sim.add_argument("--players", type=int, default=4, choices=(2, 3, 4))
    sim.add_argument("--out", required=True)
    check = commands.add_parser("check", help="replay a record and print a summary")
    check.add_argument("path")
    args = parser.parse_args(argv)

    if args.command == "simulate":
        record = simulate(args.seed, args.players)
        with open(args.out, "w", encoding="utf-8") as file:
            json.dump(record, file, indent=1)
        print(f"wrote {args.out}: {len(record['events'])} events, winner seat {record['result']['winner_seat']}")
        return 0

    # Saved games are gzipped (app/services/record_store.py), downloaded ones are not
    opener = gzip.open if args.path.endswith(".gz") else open
    with opener(args.path, "rt", encoding="utf-8") as file:
        record = json.load(file)
    try:
        game = replay(record)
    except RecordError as error:
        print(f"invalid: {error}")
        return 1
    hidden = sum(1 for e in record["events"] if "visible_to" in e)
    print(f"ok: {len(record['events'])} events ({hidden} with hidden outcomes), {game.turn_number} turns")
    for seat, player in enumerate(game.players):
        points = player.victory_points + player.hidden_points()
        mark = "  <- winner" if game.winner and game.seat_of(game.winner) == seat else ""
        print(f"  seat {seat} {player.name:8} {player.color.value:7} {points:2} points{mark}")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
