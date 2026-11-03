"""
What each player may see. Hands and session tokens stay private: the public
view goes to the whole room, the private one only to its seat.
"""
from typing import Any, Dict, List, Optional

from app.models.game import TRADABLE_RESOURCES, GameState, TurnPhase
from app.models.hex_lib import Edge, Hex, Vertex
from app.models.settings import GameSettings
from app.services.serializer import GameSerializer

PUBLIC_GAME_FIELDS = (
    "turn_phase", "dice_roll", "dice", "setup_waiting_for_road", "robber_hex", "is_game_over",
    "board_tiles", "ports", "roads", "settlements", "longest_road_holder", "largest_army_holder",
    "free_roads_left", "log",
)


def _vertex(vertex: Vertex) -> Dict[str, Any]:
    return GameSerializer._vertex_to_dict(vertex)


def _edge(edge: Edge) -> Dict[str, Any]:
    return {"hex": GameSerializer._hex_to_dict(edge.owner), "direction": edge.direction}


def _hex(h: Hex) -> Dict[str, int]:
    return GameSerializer._hex_to_dict(h)


def _offer(game: GameState) -> Optional[Dict[str, Any]]:
    offer = game.trade_offer
    if offer is None:
        return None
    seat_of = {player.color: seat for seat, player in enumerate(game.players)}
    return {
        "proposer_seat": seat_of[offer.proposer],
        "give": {r.value: n for r, n in offer.give.items()},
        "get": {r.value: n for r, n in offer.get.items()},
        "accepted_seats": [seat_of[c] for c in offer.accepted],
        "declined_seats": [seat_of[c] for c in offer.declined],
    }


def public_view(room: Dict[str, Any], game: Optional[GameState]) -> Dict[str, Any]:
    view: Dict[str, Any] = {
        "room_id": room["room_id"],
        "version": room["version"],
        "status": room["status"],
        "host_seat": room["host_seat"],
        # Chosen in the lobby; the game keeps its own copy once it starts
        "settings": (game.settings if game else GameSettings.from_dict(room.get("settings"))).to_dict(),
    }

    if game is None:
        view["players"] = [
            {"seat": seat, "name": entry["name"], "is_bot": entry.get("bot", False)}
            for seat, entry in enumerate(room["seats"])
        ]
        view["game"] = None
        return view

    data = GameSerializer.game_to_dict(game)
    view["players"] = [
        {
            "seat": seat,
            "name": player.name,
            "is_bot": room["seats"][seat].get("bot", False),
            "color": player.color.value,
            # Hidden cards are revealed when they can no longer be used against the owner
            "victory_points": player.victory_points + (player.hidden_points() if game.is_game_over else 0),
            "card_count": player.card_count(),
            "road_length": game.road_lengths.get(player.color, 0),
            "pending_discard": game.pending_discards.get(player.color, 0),
            "dev_card_count": len(player.dev_cards) + len(player.new_dev_cards),
            "knights_played": player.knights_played,
        }
        for seat, player in enumerate(game.players)
    ]
    view["game"] = {
        **{key: data[key] for key in PUBLIC_GAME_FIELDS},
        "current_seat": game.current_turn_index,
        "winner_seat": game.players.index(game.winner) if game.winner else None,
        "bank": {r.value: game.bank_count(r) for r in TRADABLE_RESOURCES},
        "dev_deck_count": len(game.dev_deck),
        "trade_offer": _offer(game),
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
        "dev_cards": [c.value for c in player.dev_cards + player.new_dev_cards],
        "hidden_points": player.hidden_points(),
        "legal": {
            "settlements": [_vertex(v) for v in game.legal_settlements(player)],
            "roads": [_edge(e) for e in game.legal_roads(player)],
            "cities": [_vertex(v) for v in game.legal_cities(player)],
            "robber_hexes": [_hex(h) for h in game.legal_robber_hexes(player)],
            "steal_targets": _steal_targets(game, seat) if is_current else [],
            "must_discard": game.pending_discards.get(player.color, 0),
            "can_buy_dev_card": game.can_buy_dev_card(player),
            "playable_dev_cards": [c.value for c in game.playable_dev_cards(player)],
        },
    }


def _steal_targets(game: GameState, seat: int) -> List[int]:
    if game.turn_phase != TurnPhase.STEAL:
        return []
    return [game.players.index(p) for p in game.steal_victims(game.players[seat])]
