"""Translates untrusted client actions into calls on the rules engine."""
from typing import Any, Callable, Dict

from app.models.board import ResourceType
from app.models.game import GameState
from app.models.hex_lib import Edge, Hex, Vertex
from app.models.player import Player

MAX_CARDS_IN_ONE_DISCARD = 200


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _parse_hex(data: Any) -> Hex:
    if not isinstance(data, dict) or not all(_is_int(data.get(k)) for k in ("q", "r", "s")):
        raise ValueError("Invalid position.")
    if data["q"] + data["r"] + data["s"] != 0:
        raise ValueError("Invalid position.")
    return Hex(data["q"], data["r"], data["s"])


def _parse_direction(data: Any) -> int:
    if not _is_int(data) or not 0 <= data <= 5:
        raise ValueError("Invalid position.")
    return data


def _parse_vertex(payload: Dict[str, Any]) -> Vertex:
    return Vertex(_parse_hex(payload.get("hex")), _parse_direction(payload.get("direction")))


def _parse_edge(payload: Dict[str, Any]) -> Edge:
    return Edge(_parse_hex(payload.get("hex")), _parse_direction(payload.get("direction")))


def _parse_resource(data: Any) -> ResourceType:
    try:
        return ResourceType(data)
    except ValueError:
        raise ValueError("Unknown resource.") from None


def _parse_cards(data: Any) -> Dict[ResourceType, int]:
    if not isinstance(data, dict):
        raise ValueError("Invalid cards.")
    cards = {}
    for name, amount in data.items():
        if not _is_int(amount) or abs(amount) > MAX_CARDS_IN_ONE_DISCARD:
            raise ValueError("Invalid cards.")
        if amount != 0:
            cards[_parse_resource(name)] = amount
    return cards


def _parse_victim(game: GameState, data: Any) -> Player:
    if not _is_int(data) or not 0 <= data < len(game.players):
        raise ValueError("Unknown player.")
    return game.players[data]


ACTIONS: Dict[str, Callable[[GameState, Player, Dict[str, Any]], Any]] = {
    "roll_dice": lambda g, p, _: g.roll_dice(p),
    "end_turn": lambda g, p, _: g.end_turn(p),
    "build_settlement": lambda g, p, data: g.place_settlement(p, _parse_vertex(data)),
    "build_road": lambda g, p, data: g.place_road(p, _parse_edge(data)),
    "upgrade_city": lambda g, p, data: g.upgrade_to_city(p, _parse_vertex(data)),
    "discard": lambda g, p, data: g.discard(p, _parse_cards(data.get("cards"))),
    "move_robber": lambda g, p, data: g.move_robber(p, _parse_hex(data.get("hex"))),
    "steal": lambda g, p, data: g.steal_resource(p, _parse_victim(g, data.get("victim_seat"))),
    "buy_dev_card": lambda g, p, _: g.buy_dev_card(p),
    "play_knight": lambda g, p, _: g.play_knight(p),
    "play_road_building": lambda g, p, _: g.play_road_building(p),
    "play_year_of_plenty": lambda g, p, data: g.play_year_of_plenty(
        p, _parse_resource(data.get("first")), _parse_resource(data.get("second"))
    ),
    "play_monopoly": lambda g, p, data: g.play_monopoly(p, _parse_resource(data.get("resource"))),
    "trade_with_bank": lambda g, p, data: g.trade_with_bank(
        p, _parse_resource(data.get("give")), _parse_resource(data.get("get"))
    ),
}


def apply_action(game: GameState, seat: int, action_type: str, payload: Dict[str, Any]):
    action = ACTIONS.get(action_type)
    if action is None:
        raise ValueError("Unknown action.")
    action(game, game.players[seat], payload)
