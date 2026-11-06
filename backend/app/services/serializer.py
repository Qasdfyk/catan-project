from typing import Dict, Any, List
from app.models.game import DICE_TOTALS, GameState, Building, TradeOffer, TurnPhase, BuildingType
from app.models.board import Board, Tile, ResourceType, Port, PortType
from app.models.player import DevCard, Player, PlayerColor
from app.models.hex_lib import Hex, Vertex, Edge
from app.models.settings import GameSettings

class GameSerializer:

    @staticmethod
    def game_to_dict(game: GameState) -> Dict[str, Any]:
        return {
            "players": [GameSerializer._player_to_dict(p) for p in game.players],
            "settings": game.settings.to_dict(),
            "current_turn_index": game.current_turn_index,
            "turn_number": game.turn_number,
            "turn_phase": game.turn_phase.value,
            "dice_roll": game.dice_roll,
            "dice": game.dice,
            "roll_counts": game.roll_counts,

            "setup_queue": game.setup_queue,
            "setup_waiting_for_road": game.setup_waiting_for_road,
            "setup_last_vertex": GameSerializer._vertex_to_dict(game.setup_last_vertex) if game.setup_last_vertex else None,

            "pending_discards": {c.value: n for c, n in game.pending_discards.items()},
            "longest_road_holder": game.longest_road_holder.value if game.longest_road_holder else None,
            "road_lengths": {c.value: n for c, n in game.road_lengths.items()},
            "log": game.log,

            "trade_offer": GameSerializer._offer_to_dict(game.trade_offer) if game.trade_offer else None,
            "return_phase": game.return_phase.value,
            "free_roads_left": game.free_roads_left,
            "dev_deck": [c.value for c in game.dev_deck],
            "dev_card_played": game.dev_card_played,
            "largest_army_holder": game.largest_army_holder.value if game.largest_army_holder else None,

            "robber_hex": GameSerializer._hex_to_dict(game.robber_hex) if game.robber_hex else None,
            "is_game_over": game.is_game_over,
            "winner_name": game.winner.name if game.winner else None,

            "board_tiles": GameSerializer._tiles_to_list(game.board.tiles),
            "ports": GameSerializer._ports_to_list(game.board.ports),
            "roads": GameSerializer._roads_to_list(game.roads),
            "settlements": GameSerializer._settlements_to_list(game.settlements)
        }

    @staticmethod
    def dict_to_game(data: Dict[str, Any]) -> GameState:
        board = Board()
        board.tiles = GameSerializer._list_to_tiles(data["board_tiles"])
        board.ports = GameSerializer._list_to_ports(data["ports"])

        players = [GameSerializer._dict_to_player(p) for p in data["players"]]

        game = GameState(
            board=board,
            players=players,
            # Games saved before settings existed were played by the standard rules
            settings=GameSettings.from_dict(data.get("settings")),
            current_turn_index=data["current_turn_index"],
            turn_number=data.get("turn_number", 0),
            dice_roll=data["dice_roll"],
            dice=data.get("dice", []),
            # Games saved before the counts existed start them from nothing
            roll_counts=data.get("roll_counts") or [0] * len(DICE_TOTALS),
            turn_phase=TurnPhase(data["turn_phase"]),
            robber_hex=GameSerializer._dict_to_hex(data["robber_hex"]) if data["robber_hex"] else None,
            is_game_over=data["is_game_over"],

            setup_queue=data.get("setup_queue", []),
            setup_waiting_for_road=data.get("setup_waiting_for_road", False),
            setup_last_vertex=GameSerializer._dict_to_vertex(data["setup_last_vertex"]) if data.get("setup_last_vertex") else None,

            pending_discards={PlayerColor(c): n for c, n in data.get("pending_discards", {}).items()},
            longest_road_holder=PlayerColor(data["longest_road_holder"]) if data.get("longest_road_holder") else None,
            road_lengths={PlayerColor(c): n for c, n in data.get("road_lengths", {}).items()},
            log=data.get("log", []),

            trade_offer=GameSerializer._dict_to_offer(data["trade_offer"]) if data.get("trade_offer") else None,
            return_phase=TurnPhase(data.get("return_phase", TurnPhase.MAIN_PHASE)),
            free_roads_left=data.get("free_roads_left", 0),
            dev_deck=[DevCard(c) for c in data.get("dev_deck", [])],
            dev_card_played=data.get("dev_card_played", False),
            largest_army_holder=PlayerColor(data["largest_army_holder"]) if data.get("largest_army_holder") else None
        )

        game.roads = GameSerializer._list_to_roads(data["roads"])
        game.settlements = GameSerializer._list_to_settlements(data["settlements"])

        if data["winner_name"]:
            game.winner = next((p for p in players if p.name == data["winner_name"]), None)

        return game

    @staticmethod
    def _offer_to_dict(offer: TradeOffer) -> Dict[str, Any]:
        return {
            "proposer": offer.proposer.value,
            "give": {r.value: n for r, n in offer.give.items()},
            "get": {r.value: n for r, n in offer.get.items()},
            "accepted": [c.value for c in offer.accepted],
            "declined": [c.value for c in offer.declined],
        }

    @staticmethod
    def _dict_to_offer(d: Dict[str, Any]) -> TradeOffer:
        return TradeOffer(
            proposer=PlayerColor(d["proposer"]),
            give={ResourceType(r): n for r, n in d["give"].items()},
            get={ResourceType(r): n for r, n in d["get"].items()},
            accepted=[PlayerColor(c) for c in d["accepted"]],
            declined=[PlayerColor(c) for c in d["declined"]],
        )

    @staticmethod
    def _hex_to_dict(h: Hex) -> Dict[str, int]:
        return {"q": h.q, "r": h.r, "s": h.s}

    @staticmethod
    def _dict_to_hex(d: Dict[str, int]) -> Hex:
        return Hex(q=d['q'], r=d['r'], s=d['s'])

    @staticmethod
    def _vertex_to_dict(v: Vertex) -> Dict[str, Any]:
        return {"hex": GameSerializer._hex_to_dict(v.owner), "direction": v.direction}

    @staticmethod
    def _dict_to_vertex(d: Dict[str, Any]) -> Vertex:
        return Vertex(GameSerializer._dict_to_hex(d["hex"]), d["direction"]).get_canonical()

    @staticmethod
    def _player_to_dict(p: Player) -> Dict[str, Any]:
        return {
            "id": p.id,
            "name": p.name,
            "color": p.color.value,
            "resources": dict(p.resources),
            "victory_points": p.victory_points,
            "dev_cards": [c.value for c in p.dev_cards],
            "new_dev_cards": [c.value for c in p.new_dev_cards],
            "knights_played": p.knights_played
        }

    @staticmethod
    def _dict_to_player(d: Dict[str, Any]) -> Player:
        p = Player(name=d["name"], color=PlayerColor(d["color"]), id=d.get("id", ""))
        p.victory_points = d["victory_points"]
        p.dev_cards = [DevCard(c) for c in d.get("dev_cards", [])]
        p.new_dev_cards = [DevCard(c) for c in d.get("new_dev_cards", [])]
        p.knights_played = d.get("knights_played", 0)
        for res_str, amount in d["resources"].items():
            p.resources[ResourceType(res_str)] = amount
        return p

    @staticmethod
    def _tiles_to_list(tiles: Dict[Hex, Tile]) -> List[Dict]:
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
    def _ports_to_list(ports: List[Port]) -> List[Dict]:
        return [
            {
                "type": port.type.value,
                "vertices": [GameSerializer._vertex_to_dict(v) for v in port.valid_vertices]
            }
            for port in ports
        ]

    @staticmethod
    def _list_to_ports(data: List[Dict]) -> List[Port]:
        return [
            Port(
                type=PortType(item["type"]),
                valid_vertices=[GameSerializer._dict_to_vertex(v) for v in item["vertices"]]
            )
            for item in data
        ]

    @staticmethod
    def _roads_to_list(roads: Dict[Edge, PlayerColor]) -> List[Dict]:
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
