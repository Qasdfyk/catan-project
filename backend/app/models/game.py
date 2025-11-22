from typing import List, Optional, Dict
import random
from dataclasses import dataclass, field

from app.models.board import Board, ResourceType
from app.models.player import Player, PlayerColor
from app.models.hex_lib import Edge, Vertex, Hex

@dataclass
class GameState:
    """
    The root entity for the game logic.
    """
    board: Board
    players: List[Player] = field(default_factory=list)
    current_turn_index: int = 0
    dice_roll: Optional[int] = None
    is_game_over: bool = False
    
    # State of the board (buildings)
    # We use canonical Edges/Vertices as keys
    roads: Dict[Edge, PlayerColor] = field(default_factory=dict)
    settlements: Dict[Vertex, PlayerColor] = field(default_factory=dict)

    @staticmethod
    def create_new_game(player_names: List[str]) -> 'GameState':
        if len(player_names) < 2 or len(player_names) > 4:
            raise ValueError("Game requires 2 to 4 players.")

        board = Board.create_standard_game()
        players = []
        colors = list(PlayerColor)
        
        for i, name in enumerate(player_names):
            players.append(Player(name=name, color=colors[i]))

        return GameState(board=board, players=players)

    def get_current_player(self) -> Player:
        return self.players[self.current_turn_index]

    def next_turn(self):
        self.current_turn_index = (self.current_turn_index + 1) % len(self.players)
        self.dice_roll = None

    def roll_dice(self) -> int:
        """
        Rolls dice and triggers resource distribution.
        """
        d1 = random.randint(1, 6)
        d2 = random.randint(1, 6)
        self.dice_roll = d1 + d2
        
        # Trigger harvest logic immediately after roll
        self.distribute_resources(self.dice_roll)
        
        return self.dice_roll

    def distribute_resources(self, roll_number: int):
        """
        Gives resources to players based on the dice roll.
        """
        if roll_number == 7:
            # TODO: Implement Robber logic later
            return

        # 1. Find all tiles matching the dice roll
        matching_tiles = [t for t in self.board.tiles.values() if t.number == roll_number]

        for tile in matching_tiles:
            if tile.resource == ResourceType.DESERT:
                continue

            # 2. Check all 6 corners (vertices) of this tile
            # We must construct vertices and get their canonical form to match the keys in self.settlements
            for direction in range(6):
                # Create a temporary vertex object for this corner
                raw_vertex = Vertex(tile.hex_coords, direction)
                canonical_vertex = raw_vertex.get_canonical()

                # 3. Check if anyone built here
                if canonical_vertex in self.settlements:
                    owner_color = self.settlements[canonical_vertex]
                    
                    # Find the player object
                    # (In a real DB scenario we'd use a map, but list search is fine for 4 players)
                    player = next((p for p in self.players if p.color == owner_color), None)
                    
                    if player:
                        # 4. Give resource
                        # (Future: Check if it's a City to give 2)
                        amount = 1 
                        player.add_resource(tile.resource, amount)
                        print(f"Harvest: {player.name} got {amount} {tile.resource} from roll {roll_number}")

    # --- Building Logic ---

    def place_road(self, player: Player, edge: Edge, free: bool = False):
        """
        Attempts to build a road on the given edge.
        :param free: If True, ignores resource cost (for setup phase).
        """
        canonical_edge = edge.get_canonical()

        # 1. Check availability
        if canonical_edge in self.roads:
            raise ValueError("This edge is already occupied.")

        # 2. Check cost (if not free)
        road_cost = {ResourceType.WOOD: 1, ResourceType.BRICK: 1}
        if not free and not player.has_resources(road_cost):
            raise ValueError("Insufficient resources for a road.")

        # 3. Check connectivity
        if not self._has_road_connectivity(player, canonical_edge):
             raise ValueError("Road must be connected to your existing network.")

        # Execute
        if not free:
            player.deduct_resources(road_cost)
        
        self.roads[canonical_edge] = player.color

    def place_settlement(self, player: Player, vertex: Vertex, free: bool = False):
        """
        Attempts to build a settlement on the given vertex.
        """
        canonical_vertex = vertex.get_canonical()

        # 1. Check availability
        if canonical_vertex in self.settlements:
            raise ValueError("This intersection is already occupied.")

        # 2. Check Distance Rule (No neighbor settlements)
        neighbors = canonical_vertex.get_adjacent_vertices()
        for n in neighbors:
            if n in self.settlements:
                raise ValueError("Distance Rule: Cannot build next to another settlement.")

        # 3. Check connectivity
        if not free:
            if not self._has_settlement_connectivity(player, canonical_vertex):
                 raise ValueError("Settlement must be connected to your road.")

        # 4. Check cost
        settlement_cost = {
            ResourceType.WOOD: 1, ResourceType.BRICK: 1,
            ResourceType.WHEAT: 1, ResourceType.SHEEP: 1
        }
        if not free and not player.has_resources(settlement_cost):
            raise ValueError("Insufficient resources for a settlement.")

        # Execute
        if not free:
            player.deduct_resources(settlement_cost)
        
        self.settlements[canonical_vertex] = player.color
        player.victory_points += 1

    # --- Helper Private Methods ---

    def _has_road_connectivity(self, player: Player, edge: Edge) -> bool:
        """
        Checks if a new road connects to player's existing network.
        """
        connected_edges = edge.get_connected_edges()
        for e in connected_edges:
            if self.roads.get(e) == player.color:
                return True
        
        vertices = edge.get_vertices()
        for v in vertices:
            if self.settlements.get(v) == player.color:
                return True
                
        return False

    def _has_settlement_connectivity(self, player: Player, vertex: Vertex) -> bool:
        """
        Checks if a vertex is reached by player's road.
        """
        touching_edges = vertex.get_touching_edges()
        for e in touching_edges:
            if self.roads.get(e) == player.color:
                return True
        return False