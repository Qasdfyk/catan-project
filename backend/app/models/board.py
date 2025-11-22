from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional
import random

from app.models.hex_lib import Hex

class ResourceType(str, Enum):
    """Available resource types in the game."""
    WOOD = "wood"
    BRICK = "brick"
    SHEEP = "sheep"
    WHEAT = "wheat"
    ORE = "ore"
    DESERT = "desert"

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

    def get_tile(self, hex_coords: Hex) -> Optional[Tile]:
        """Retrieve a tile by its coordinates."""
        return self.tiles.get(hex_coords)

    @staticmethod
    def create_standard_game() -> 'Board':
        """
        Factory method to create a standard Catan board (Radius 2).
        - 19 Tiles total.
        - Randomly assigns resources and number tokens.
        """
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

        # 4. Shuffle resources and numbers
        random.shuffle(resources)
        random.shuffle(numbers)

        # 5. Assign to tiles
        # Note: In a real game, there are rules preventing 6s and 8s from touching.
        # For this iteration, we use pure random assignment.
        number_idx = 0
        
        for i, h in enumerate(hexes):
            res = resources[i]
            num = None
            
            if res != ResourceType.DESERT:
                num = numbers[number_idx]
                number_idx += 1
            
            board.tiles[h] = Tile(hex_coords=h, resource=res, number=num)

        return board

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