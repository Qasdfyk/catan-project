# ============================================================
# FILE: app/models/game.py
# ============================================================
from typing import List, Optional, Dict
import random
from dataclasses import dataclass, field
from enum import Enum

from app.models.board import Board, ResourceType, Tile
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
            players.append(Player(name=name, color=colors[i]))

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
        if player.resources[give] < 4:
            raise ValueError(f"Not enough {give} to trade. Need 4.")
        
        player.remove_resource(give, 4)
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
        # Placeholder for Phase 1 logic
        # In future phases, this will run BFS/DFS to calculate road length
        pass

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