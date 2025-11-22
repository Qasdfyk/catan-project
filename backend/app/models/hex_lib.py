from dataclasses import dataclass
from typing import List

@dataclass(frozen=True)
class Hex:
    """
    Representation of a single hexagonal tile using Cube Coordinates system.
    Constraint: q + r + s = 0
    
    Used frozen=True to make instances immutable and hashable
    (so they can be used as dictionary keys, e.g., {Hex(0,0,0): Resource.WOOD}).
    """
    q: int
    r: int
    s: int

    def __post_init__(self):
        """Validate cube coordinate consistency."""
        if self.q + self.r + self.s != 0:
            raise ValueError("Sum of coordinates q + r + s must be 0!")

    def __add__(self, other: 'Hex') -> 'Hex':
        """Vector addition for hex coordinates."""
        return Hex(self.q + other.q, self.r + other.r, self.s + other.s)

    def __sub__(self, other: 'Hex') -> 'Hex':
        """Vector subtraction for hex coordinates."""
        return Hex(self.q - other.q, self.r - other.r, self.s - other.s)

    def scale(self, factor: int) -> 'Hex':
        """Scale the hex vector by a factor."""
        return Hex(self.q * factor, self.r * factor, self.s * factor)

    def length(self) -> int:
        """
        Calculate the length of the vector from the center (0,0,0).
        Formula: (abs(q) + abs(r) + abs(s)) / 2
        """
        return (abs(self.q) + abs(self.r) + abs(self.s)) // 2

    def distance(self, other: 'Hex') -> int:
        """
        Calculate Manhattan distance on a hex grid between two tiles.
        """
        return (self - other).length()

    def neighbor(self, direction: int) -> 'Hex':
        """
        Returns the neighbor in a specific direction (0-5).
        Directions are counter-clockwise, starting from East-ish.
        """
        # Direction vectors in Cube Coordinates
        directions = [
            Hex(1, 0, -1), Hex(1, -1, 0), Hex(0, -1, 1),
            Hex(-1, 0, 1), Hex(-1, 1, 0), Hex(0, 1, -1)
        ]
        return self + directions[direction % 6]
    
    def get_all_neighbors(self) -> List['Hex']:
        """Returns a list of all 6 neighboring hexes."""
        return [self.neighbor(i) for i in range(6)]

    def __repr__(self):
        return f"Hex({self.q}, {self.r}, {self.s})"