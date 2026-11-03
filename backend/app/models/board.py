from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Set
from app.models.hex_lib import Edge, Hex, Vertex
from app.models.settings import DESERT_CENTER, DESERT_RANDOM
import random

RED_NUMBERS = (6, 8)
CENTER = Hex(0, 0, 0)

class ResourceType(str, Enum):
    """Available resource types in the game."""
    WOOD = "wood"
    BRICK = "brick"
    SHEEP = "sheep"
    WHEAT = "wheat"
    ORE = "ore"
    DESERT = "desert"

class PortType(str, Enum):
    GENERIC_3_1 = "3:1"
    WOOD_2_1 = "wood_2:1"
    BRICK_2_1 = "brick_2:1"
    SHEEP_2_1 = "sheep_2:1"
    WHEAT_2_1 = "wheat_2:1"
    ORE_2_1 = "ore_2:1"

@dataclass
class Port:
    type: PortType
    valid_vertices: List['Vertex']

@dataclass
class Tile:
    """Represents a single tile on the board with a resource and a dice number."""
    hex_coords: Hex
    resource: ResourceType
    number: Optional[int] = None  # None for Desert

class Board:
    """
    Manages the game board state.
    Stores tiles in a dictionary for O(1) access using Hex coordinates.
    """
    def __init__(self):
        self.tiles: Dict[Hex, Tile] = {}
        self.ports: List[Port] = []

    def get_tile(self, hex_coords: Hex) -> Optional[Tile]:
        """Retrieve a tile by its coordinates."""
        return self.tiles.get(hex_coords)

    @staticmethod
    def create_standard_game(desert: str = DESERT_RANDOM) -> 'Board':
        """
        Factory method to create a standard Catan board (Radius 2).
        - 19 Tiles total.
        - Randomly assigns resources and number tokens.
        - The desert lands anywhere, or in the center with desert="center".
        """
        if desert not in (DESERT_RANDOM, DESERT_CENTER):
            raise ValueError(f"Unknown desert placement: {desert}.")
        board = Board()

        # 1. Generate Coordinates for Radius 2 (Standard map)
        hexes = Board._generate_hex_grid(radius=2)

        # 2. Define Standard Resource Distribution
        # 4 Wood, 4 Sheep, 4 Wheat, 3 Brick, 3 Ore, 1 Desert
        resources = (
            [ResourceType.WOOD] * 4 +
            [ResourceType.SHEEP] * 4 +
            [ResourceType.WHEAT] * 4 +
            [ResourceType.BRICK] * 3 +
            [ResourceType.ORE] * 3 +
            [ResourceType.DESERT] * 1
        )

        # 3. Define Standard Number Tokens (probabilities)
        # 2-12 (skipping 7). Distribution tailored for 19 tiles minus 1 desert = 18 tokens.
        # 1x2, 2x3, 2x4, 2x5, 2x6, 2x8, 2x9, 2x10, 2x11, 1x12
        numbers = [2, 3, 3, 4, 4, 5, 5, 6, 6, 8, 8, 9, 9, 10, 10, 11, 11, 12]

        # 4. Shuffle until the most productive numbers are spread over the island
        while True:
            random.shuffle(resources)
            if desert == DESERT_CENTER:
                resources.remove(ResourceType.DESERT)
                resources.insert(hexes.index(CENTER), ResourceType.DESERT)
            random.shuffle(numbers)
            board.tiles = Board._assign_tiles(hexes, resources, numbers)
            if not Board._red_numbers_touch(board):
                break

        board.ports = Board._create_ports(board)
        return board

    @staticmethod
    def _assign_tiles(hexes: List[Hex], resources: List[ResourceType], numbers: List[int]) -> Dict[Hex, Tile]:
        tiles = {}
        remaining_numbers = iter(numbers)
        for h, res in zip(hexes, resources, strict=True):
            num = None if res == ResourceType.DESERT else next(remaining_numbers)
            tiles[h] = Tile(hex_coords=h, resource=res, number=num)
        return tiles

    @staticmethod
    def _red_numbers_touch(board: 'Board') -> bool:
        """6s and 8s are the most likely rolls, so they must not be neighbors."""
        for h, tile in board.tiles.items():
            if tile.number not in RED_NUMBERS:
                continue
            for direction in range(6):
                neighbor = board.tiles.get(h.neighbor(direction))
                if neighbor and neighbor.number in RED_NUMBERS:
                    return True
        return False

    def is_on_board(self, position: Vertex | Edge) -> bool:
        """A vertex or edge exists only if it touches at least one tile."""
        return any(h in self.tiles for h in position.get_touching_hexes())

    def vertices(self) -> Set[Vertex]:
        return {Vertex(h, d).get_canonical() for h in self.tiles for d in range(6)}

    def edges(self) -> Set[Edge]:
        return {Edge(h, d).get_canonical() for h in self.tiles for d in range(6)}

    @staticmethod
    def _create_ports(board: 'Board') -> List[Port]:
        """
        Places the 9 standard ports (4x 3:1, one 2:1 per resource) on the coast.
        Walking around the 30 coastal edges, ports repeat every 3, 3 and 4 edges,
        which leaves the same gaps as the printed frame of the board.
        """
        port_types = [PortType.GENERIC_3_1] * 4 + [
            PortType.WOOD_2_1, PortType.BRICK_2_1, PortType.SHEEP_2_1,
            PortType.WHEAT_2_1, PortType.ORE_2_1,
        ]
        random.shuffle(port_types)

        coast = Board._coastal_edges_in_order(board)
        ports = []
        index = 0
        for i, port_type in enumerate(port_types):
            ports.append(Port(port_type, coast[index].get_vertices()))
            index += 4 if i % 3 == 2 else 3
        return ports

    @staticmethod
    def _coastal_edges_in_order(board: 'Board') -> List[Edge]:
        """Returns the edges touching exactly one tile, as a closed walk along the coast."""
        remaining = {
            e for e in board.edges()
            if sum(h in board.tiles for h in e.get_touching_hexes()) == 1
        }
        current = min(remaining, key=lambda e: (e.owner.q, e.owner.r, e.direction))
        remaining.discard(current)
        vertex = current.get_vertices()[1]
        walk = [current]
        while remaining:
            current = next(e for e in vertex.get_touching_edges() if e in remaining)
            remaining.discard(current)
            walk.append(current)
            first, second = current.get_vertices()
            vertex = second if first == vertex else first
        return walk

    @staticmethod
    def _generate_hex_grid(radius: int) -> List[Hex]:
        """
        Generates a list of Hex coordinates forming a spiral/circle of given radius.
        Radius 2 means center + 2 rings.
        """
        hexes = []
        for q in range(-radius, radius + 1):
            r1 = max(-radius, -q - radius)
            r2 = min(radius, -q + radius)
            for r in range(r1, r2 + 1):
                s = -q - r
                hexes.append(Hex(q, r, s))
        return hexes
