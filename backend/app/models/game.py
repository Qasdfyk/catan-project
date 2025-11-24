from typing import List, Optional, Dict, Set
import random
import uuid  # Added UUID import
from dataclasses import dataclass, field
from enum import Enum

from app.models.board import Board, ResourceType, Tile, PortType
from app.models.player import Player, PlayerColor
from app.models.hex_lib import Edge, Vertex, Hex

class TurnPhase(str, Enum):
    ROLL_DICE = "roll_dice"
    MAIN_PHASE = "main_phase"

class BuildingType(str, Enum):
    SETTLEMENT = "settlement"
    CITY = "city"

@dataclass
class Building:
    owner: PlayerColor
    type: BuildingType

@dataclass
class GameState:
    """
    The root entity for the game logic.
    """
    board: Board
    players: List[Player] = field(default_factory=list)
    current_turn_index: int = 0
    dice_roll: Optional[int] = None
    turn_phase: TurnPhase = TurnPhase.ROLL_DICE
    
    # Robber position (initially should be on Desert)
    robber_hex: Optional[Hex] = None 

    is_game_over: bool = False
    winner: Optional[Player] = None
    
    # State of the board
    roads: Dict[Edge, PlayerColor] = field(default_factory=dict)
    # Now maps Vertex -> Building object
    settlements: Dict[Vertex, Building] = field(default_factory=dict)

    @staticmethod
    def create_new_game(player_names: List[str]) -> 'GameState':
        if len(player_names) < 2 or len(player_names) > 4:
            raise ValueError("Game requires 2 to 4 players.")

        board = Board.create_standard_game()
        players = []
        colors = list(PlayerColor)
        
        for i, name in enumerate(player_names):
            # FIX: Generate UUID for players
            new_player = Player(name=name, color=colors[i], id=str(uuid.uuid4()))
            players.append(new_player)

        # Find Desert to place Robber initially
        desert_hex = next((t.hex_coords for t in board.tiles.values() if t.resource == ResourceType.DESERT), Hex(0,0,0))

        return GameState(
            board=board, 
            players=players,
            robber_hex=desert_hex
        )

    def get_current_player(self) -> Player:
        return self.players[self.current_turn_index]

    def next_turn(self):
        self._check_victory()
        if self.is_game_over:
            return

        self.current_turn_index = (self.current_turn_index + 1) % len(self.players)
        self.dice_roll = None
        self.turn_phase = TurnPhase.ROLL_DICE

    def roll_dice(self) -> int:
        if self.turn_phase != TurnPhase.ROLL_DICE:
            raise ValueError("Cannot roll dice in MAIN_PHASE.")

        d1 = random.randint(1, 6)
        d2 = random.randint(1, 6)
        self.dice_roll = d1 + d2
        
        self.turn_phase = TurnPhase.MAIN_PHASE

        if self.dice_roll == 7:
            # Phase 1: Just wait for move_robber
            pass
        else:
            self.distribute_resources(self.dice_roll)
        
        return self.dice_roll

    def distribute_resources(self, roll_number: int):
        matching_tiles = [t for t in self.board.tiles.values() if t.number == roll_number]

        for tile in matching_tiles:
            # ROBBER LOGIC
            if tile.hex_coords == self.robber_hex:
                continue
            
            if tile.resource == ResourceType.DESERT:
                continue

            for direction in range(6):
                raw_vertex = Vertex(tile.hex_coords, direction)
                canonical_vertex = raw_vertex.get_canonical()

                if canonical_vertex in self.settlements:
                    building = self.settlements[canonical_vertex]
                    player = next((p for p in self.players if p.color == building.owner), None)
                    
                    if player:
                        amount = 2 if building.type == BuildingType.CITY else 1
                        player.add_resource(tile.resource, amount)

    def move_robber(self, player: Player, target_hex: Hex):
        self._verify_turn(player)
        if target_hex == self.robber_hex:
             raise ValueError("Robber must be moved to a new location.")
        if target_hex not in self.board.tiles:
            raise ValueError("Invalid hex coordinates.")
        
        self.robber_hex = target_hex

    def steal_resource(self, thief: Player, victim: Player):
        """
        Steals 1 random resource from victim to thief.
        Required: Robber must be on a hex adjacent to victim's settlement.
        """
        self._verify_turn(thief)
        
        if self.robber_hex is None:
            raise ValueError("Robber is not placed on the board.")
        
        if thief == victim:
            raise ValueError("Cannot steal from yourself.")

        # 1. Validate geometric proximity to Robber
        robber_vertices = [Vertex(self.robber_hex, d).get_canonical() for d in range(6)]
        
        has_building = False
        for v in robber_vertices:
            if v in self.settlements and self.settlements[v].owner == victim.color:
                has_building = True
                break
        
        if not has_building:
            raise ValueError("Victim has no building on the robber hex.")

        # 2. Execute Steal
        total_res_count = sum(victim.resources.values())
        if total_res_count == 0:
            raise ValueError("Victim has no resources to steal.")

        pool = []
        for res, count in victim.resources.items():
            pool.extend([res] * count)
        
        stolen_res = random.choice(pool)
        
        victim.remove_resource(stolen_res, 1)
        thief.add_resource(stolen_res, 1)
        
        return stolen_res

    # --- Building Logic ---

    def place_road(self, player: Player, edge: Edge, free: bool = False):
        if not free:
            self._verify_turn(player)

        canonical_edge = edge.get_canonical()

        if canonical_edge in self.roads:
            raise ValueError("This edge is already occupied.")

        road_cost = {ResourceType.WOOD: 1, ResourceType.BRICK: 1}
        if not free and not player.has_resources(road_cost):
            raise ValueError("Insufficient resources for a road.")

        if not self._has_road_connectivity(player, canonical_edge):
             raise ValueError("Road must be connected to your existing network.")

        if not free:
            player.deduct_resources(road_cost)
        
        self.roads[canonical_edge] = player.color
        self._check_longest_road(player)

    def place_settlement(self, player: Player, vertex: Vertex, free: bool = False):
        if not free:
            self._verify_turn(player)

        canonical_vertex = vertex.get_canonical()

        if canonical_vertex in self.settlements:
            raise ValueError("This intersection is already occupied.")

        neighbors = canonical_vertex.get_adjacent_vertices()
        for n in neighbors:
            if n in self.settlements:
                raise ValueError("Distance Rule: Cannot build next to another settlement.")

        if not free:
            if not self._has_settlement_connectivity(player, canonical_vertex):
                 raise ValueError("Settlement must be connected to your road.")

        settlement_cost = {
            ResourceType.WOOD: 1, ResourceType.BRICK: 1,
            ResourceType.WHEAT: 1, ResourceType.SHEEP: 1
        }
        if not free and not player.has_resources(settlement_cost):
            raise ValueError("Insufficient resources for a settlement.")

        if not free:
            player.deduct_resources(settlement_cost)
        
        self.settlements[canonical_vertex] = Building(player.color, BuildingType.SETTLEMENT)
        player.victory_points += 1
        self._check_victory()

    def upgrade_to_city(self, player: Player, vertex: Vertex):
        self._verify_turn(player)
        canonical_vertex = vertex.get_canonical()

        building = self.settlements.get(canonical_vertex)
        if not building:
            raise ValueError("No settlement at this location.")
        if building.owner != player.color:
            raise ValueError("You can only upgrade your own settlements.")
        if building.type == BuildingType.CITY:
            raise ValueError("This is already a city.")

        city_cost = {ResourceType.ORE: 3, ResourceType.WHEAT: 2}
        if not player.has_resources(city_cost):
             raise ValueError("Insufficient resources for a city.")

        player.deduct_resources(city_cost)
        building.type = BuildingType.CITY
        player.victory_points += 1 
        self._check_victory()

    def trade_with_bank(self, player: Player, give: ResourceType, get: ResourceType):
        self._verify_turn(player)
        
        cost = 4
        
        player_ports = self._get_player_ports(player)
        
        if PortType.GENERIC_3_1 in player_ports:
            cost = 3
            
        special_port_map = {
            ResourceType.WOOD: PortType.WOOD_2_1,
            ResourceType.BRICK: PortType.BRICK_2_1,
            ResourceType.SHEEP: PortType.SHEEP_2_1,
            ResourceType.WHEAT: PortType.WHEAT_2_1,
            ResourceType.ORE: PortType.ORE_2_1
        }
        
        if special_port_map.get(give) in player_ports:
            cost = 2
            
        if player.resources[give] < cost:
            raise ValueError(f"Not enough {give}. Need {cost} (Rate {cost}:1).")
        
        player.remove_resource(give, cost)
        player.add_resource(get, 1)

    # --- Helpers ---

    def _verify_turn(self, player: Player):
        if player != self.get_current_player():
            raise ValueError("It is not your turn.")
        if self.turn_phase == TurnPhase.ROLL_DICE:
             raise ValueError("You must roll the dice first.")

    def _check_victory(self):
        p = self.get_current_player()
        if p.victory_points >= 10:
            self.is_game_over = True
            self.winner = p

    def _check_longest_road(self, player: Player):
        """
        Calculates the longest continuous road for the player.
        Updates special victory points (placeholder for 2 VP logic).
        """
        player_edges = [e for e, color in self.roads.items() if color == player.color]
        
        if not player_edges:
            return 0

        max_length = 0
        
        for start_edge in player_edges:
            # FIX: Count the starting edge itself (1) + the max depth found from it
            length = 1 + self._dfs_longest_road(start_edge, player.color, set([start_edge]))
            if length > max_length:
                max_length = length
                
        return max_length

    def _dfs_longest_road(self, current_edge: Edge, color: PlayerColor, visited: Set[Edge]) -> int:
        """
        Recursive DFS to find longest path.
        Nodes are Edges. Adjacency is defined by shared vertices.
        """
        max_depth = 0
        
        vertices = current_edge.get_vertices()
        
        for v in vertices:
            building = self.settlements.get(v)
            if building and building.owner != color:
                continue
            
            connected_edges = v.get_touching_edges()
            
            for next_edge in connected_edges:
                canon_next = next_edge.get_canonical()
                
                if canon_next == current_edge:
                    continue
                    
                if self.roads.get(canon_next) == color and canon_next not in visited:
                    new_visited = visited.copy()
                    new_visited.add(canon_next)
                    
                    depth = 1 + self._dfs_longest_road(canon_next, color, new_visited)
                    if depth > max_depth:
                        max_depth = depth
                        
        return max_depth

    def _has_road_connectivity(self, player: Player, edge: Edge) -> bool:
        connected_edges = edge.get_connected_edges()
        for e in connected_edges:
            if self.roads.get(e) == player.color:
                return True
        
        vertices = edge.get_vertices()
        for v in vertices:
            building = self.settlements.get(v)
            if building and building.owner == player.color:
                return True
        return False

    def _has_settlement_connectivity(self, player: Player, vertex: Vertex) -> bool:
        touching_edges = vertex.get_touching_edges()
        for e in touching_edges:
            if self.roads.get(e) == player.color:
                return True
        return False

    def _get_player_ports(self, player: Player) -> Set[PortType]:
        """Returns a set of port types the player has access to."""
        owned_ports = set()
        for port in self.board.ports:
            for v in port.valid_vertices:
                canon_v = v.get_canonical()
                if canon_v in self.settlements:
                    if self.settlements[canon_v].owner == player.color:
                        owned_ports.add(port.type)
                        break
        return owned_ports