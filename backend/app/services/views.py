"""
What each player may see. Hands and session tokens stay private: the public
view goes to the whole room, the private one only to its seat.
"""
from typing import Any, Dict, List, Optional

from app.models.game import TRADABLE_RESOURCES, GameState, TurnPhase
from app.models.hex_lib import Edge, Hex, Vertex
from app.services.serializer import GameSerializer

PUBLIC_GAME_FIELDS = (
    "turn_phase", "dice_roll", "setup_waiting_for_road", "robber_hex", "is_game_over",
    "board_tiles", "ports", "roads", "settlements", "longest_road_holder", "log",
)


def _vertex(vertex: Vertex) -> Dict[str, Any]:
    return GameSerializer._vertex_to_dict(vertex)


def _edge(edge: Edge) -> Dict[str, Any]:
    return {"hex": GameSerializer._hex_to_dict(edge.owner), "direction": edge.direction}


def _hex(h: Hex) -> Dict[str, int]:
    return GameSerializer._hex_to_dict(h)


def public_view(room: Dict[str, Any], game: Optional[GameState]) -> Dict[str, Any]:
    view: Dict[str, Any] = {
        "room_id": room["room_id"],
        "version": room["version"],
        "status": room["status"],
        "host_seat": room["host_seat"],
    }

    if game is None:
        view["players"] = [
            {"seat": seat, "name": entry["name"]}
            for seat, entry in enumerate(room["seats"])
        ]
        view["game"] = None
        return view

    data = GameSerializer.game_to_dict(game)
    view["players"] = [
        {
            "seat": seat,
            "name": player.name,
            "color": player.color.value,
            "victory_points": player.victory_points,
            "card_count": player.card_count(),
            "road_length": game.road_lengths.get(player.color, 0),
            "pending_discard": game.pending_discards.get(player.color, 0),
        }
        for seat, player in enumerate(game.players)
    ]
    view["game"] = {
        **{key: data[key] for key in PUBLIC_GAME_FIELDS},
        "current_seat": game.current_turn_index,
        "winner_seat": game.players.index(game.winner) if game.winner else None,
    }
    return view


def private_view(game: Optional[GameState], seat: int) -> Dict[str, Any]:
    if game is None:
        return {"seat": seat, "resources": {}, "legal": None}

    player = game.players[seat]
    is_current = game.current_turn_index == seat and not game.is_game_over
    return {
        "seat": seat,
        "resources": {r.value: player.resources[r] for r in TRADABLE_RESOURCES},
        "trade_rates": {r.value: game.trade_rate(player, r) for r in TRADABLE_RESOURCES},
        "legal": {
            "settlements": [_vertex(v) for v in game.legal_settlements(player)],
            "roads": [_edge(e) for e in game.legal_roads(player)],
            "cities": [_vertex(v) for v in game.legal_cities(player)],
            "robber_hexes": [_hex(h) for h in game.legal_robber_hexes(player)],
            "steal_targets": _steal_targets(game, seat) if is_current else [],
            "must_discard": game.pending_discards.get(player.color, 0),
        },
    }


def _steal_targets(game: GameState, seat: int) -> List[int]:
    if game.turn_phase != TurnPhase.STEAL:
        return []
    return [game.players.index(p) for p in game.steal_victims(game.players[seat])]
