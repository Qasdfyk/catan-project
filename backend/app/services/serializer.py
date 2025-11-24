from typing import Dict, Any, List
import json
from app.models.game import GameState, Building, TurnPhase, BuildingType
from app.models.board import Board, Tile, ResourceType
from app.models.player import Player, PlayerColor
from app.models.hex_lib import Hex, Vertex, Edge

class GameSerializer:
    """
    Responsibility: Convert complex GameState objects to JSON-compatible dictionaries and back.
    Crucial for storing state in Redis.
    """

    @staticmethod
    def game_to_dict(game: GameState) -> Dict[str, Any]:
        return {
            "players": [GameSerializer._player_to_dict(p) for p in game.players],
            "current_turn_index": game.current_turn_index,
            "turn_phase": game.turn_phase.value,
            "dice_roll": game.dice_roll,
            "robber_hex": GameSerializer._hex_to_dict(game.robber_hex) if game.robber_hex else None,
            "is_game_over": game.is_game_over,
            "winner_name": game.winner.name if game.winner else None,
            "board_tiles": GameSerializer._tiles_to_list(game.board.tiles),
            "roads": GameSerializer._roads_to_list(game.roads),
            "settlements": GameSerializer._settlements_to_list(game.settlements)
        }

    @staticmethod
    def dict_to_game(data: Dict[str, Any]) -> GameState:
        # Reconstruct Board
        board = Board()
        # We assume the board structure (hexes) is static for a standard game, 
        # but here we reload the resources/numbers from state.
        board.tiles = GameSerializer._list_to_tiles(data["board_tiles"])

        # Reconstruct Players
        players = [GameSerializer._dict_to_player(p) for p in data["players"]]

        # Reconstruct GameState
        game = GameState(
            board=board,
            players=players,
            current_turn_index=data["current_turn_index"],
            dice_roll=data["dice_roll"],
            turn_phase=TurnPhase(data["turn_phase"]),
            robber_hex=GameSerializer._dict_to_hex(data["robber_hex"]) if data["robber_hex"] else None,
            is_game_over=data["is_game_over"]
        )
        
        # Restore complex dicts
        game.roads = GameSerializer._list_to_roads(data["roads"])
        game.settlements = GameSerializer._list_to_settlements(data["settlements"])
        
        if data["winner_name"]:
            game.winner = next((p for p in players if p.name == data["winner_name"]), None)

        return game

    # --- Helpers for Nested Objects ---

    @staticmethod
    def _hex_to_dict(h: Hex) -> Dict[str, int]:
        return {"q": h.q, "r": h.r, "s": h.s}

    @staticmethod
    def _dict_to_hex(d: Dict[str, int]) -> Hex:
        return Hex(q=d['q'], r=d['r'], s=d['s'])

    @staticmethod
    def _player_to_dict(p: Player) -> Dict[str, Any]:
        return {
            "id": p.id,
            "name": p.name,
            "color": p.color.value,
            "resources": dict(p.resources),
            "victory_points": p.victory_points
        }

    @staticmethod
    def _dict_to_player(d: Dict[str, Any]) -> Player:
        p = Player(name=d["name"], color=PlayerColor(d["color"]), id=d.get("id", ""))
        p.victory_points = d["victory_points"]
        for res_str, amount in d["resources"].items():
            p.resources[ResourceType(res_str)] = amount
        return p

    @staticmethod
    def _tiles_to_list(tiles: Dict[Hex, Tile]) -> List[Dict]:
        """Convert Map<Hex, Tile> to List of objects for JSON."""
        result = []
        for h, tile in tiles.items():
            result.append({
                "hex": GameSerializer._hex_to_dict(h),
                "resource": tile.resource.value,
                "number": tile.number
            })
        return result

    @staticmethod
    def _list_to_tiles(data: List[Dict]) -> Dict[Hex, Tile]:
        result = {}
        for item in data:
            h = GameSerializer._dict_to_hex(item["hex"])
            result[h] = Tile(
                hex_coords=h,
                resource=ResourceType(item["resource"]),
                number=item["number"]
            )
        return result

    @staticmethod
    def _roads_to_list(roads: Dict[Edge, PlayerColor]) -> List[Dict]:
        # Edge needs to be serialized. Edge = (Hex, direction)
        result = []
        for edge, color in roads.items():
            result.append({
                "hex": GameSerializer._hex_to_dict(edge.owner),
                "direction": edge.direction,
                "color": color.value
            })
        return result

    @staticmethod
    def _list_to_roads(data: List[Dict]) -> Dict[Edge, PlayerColor]:
        result = {}
        for item in data:
            h = GameSerializer._dict_to_hex(item["hex"])
            # Recreate canonical edge
            edge = Edge(h, item["direction"]).get_canonical()
            result[edge] = PlayerColor(item["color"])
        return result

    @staticmethod
    def _settlements_to_list(settlements: Dict[Vertex, Building]) -> List[Dict]:
        result = []
        for vertex, building in settlements.items():
            result.append({
                "hex": GameSerializer._hex_to_dict(vertex.owner),
                "direction": vertex.direction,
                "owner": building.owner.value,
                "type": building.type.value
            })
        return result

    @staticmethod
    def _list_to_settlements(data: List[Dict]) -> Dict[Vertex, Building]:
        result = {}
        for item in data:
            h = GameSerializer._dict_to_hex(item["hex"])
            vertex = Vertex(h, item["direction"]).get_canonical()
            result[vertex] = Building(
                owner=PlayerColor(item["owner"]),
                type=BuildingType(item["type"])
            )
        return result