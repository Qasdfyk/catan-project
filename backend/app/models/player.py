from dataclasses import dataclass, field
from enum import Enum
from typing import Dict
from collections import Counter

from app.models.board import ResourceType

class PlayerColor(str, Enum):
    RED = "red"
    BLUE = "blue"
    WHITE = "white"
    ORANGE = "orange"

@dataclass
class Player:
    """
    Represents a player in the game.
    Tracks resources, victory points, and identifiers.
    """
    name: str
    color: PlayerColor
    # Resources are stored in a Counter for easy addition/subtraction
    resources: Counter = field(default_factory=Counter)
    victory_points: int = 0
    
    # Will be used later for authentication
    id: str = field(default="") 

    def add_resource(self, resource: ResourceType, amount: int = 1):
        """Adds resources to the player's hand."""
        self.resources[resource] += amount

    def remove_resource(self, resource: ResourceType, amount: int = 1):
        """
        Removes resources. 
        Raises ValueError if player doesn't have enough.
        """
        if self.resources[resource] < amount:
            raise ValueError(f"Not enough {resource}. Has {self.resources[resource]}, needs {amount}.")
        self.resources[resource] -= amount

    def has_resources(self, cost: Dict[ResourceType, int]) -> bool:
        """
        Checks if player can afford a specific cost.
        Example cost: {ResourceType.WOOD: 1, ResourceType.BRICK: 1}
        """
        for res, amount in cost.items():
            if self.resources[res] < amount:
                return False
        return True

    def deduct_resources(self, cost: Dict[ResourceType, int]):
        """
        Deducts resources for a cost. 
        Raises ValueError if not affordable (atomic operation check needed in caller or here).
        """
        if not self.has_resources(cost):
            raise ValueError("Insufficient resources to pay cost.")
        
        for res, amount in cost.items():
            self.remove_resource(res, amount)