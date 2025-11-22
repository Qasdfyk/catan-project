from dataclasses import dataclass
from typing import List, Tuple, Set

@dataclass(frozen=True, order=True)
class Hex:
    """
    Representation of a single hexagonal tile using Cube Coordinates system.
    Constraint: q + r + s = 0
    """
    q: int
    r: int
    s: int

    def __post_init__(self):
        if self.q + self.r + self.s != 0:
            raise ValueError("Sum of coordinates q + r + s must be 0!")

    def __add__(self, other: 'Hex') -> 'Hex':
        return Hex(self.q + other.q, self.r + other.r, self.s + other.s)

    def __sub__(self, other: 'Hex') -> 'Hex':
        return Hex(self.q - other.q, self.r - other.r, self.s - other.s)

    def neighbor(self, direction: int) -> 'Hex':
        directions = [
            Hex(1, 0, -1), Hex(1, -1, 0), Hex(0, -1, 1),
            Hex(-1, 0, 1), Hex(-1, 1, 0), Hex(0, 1, -1)
        ]
        return self + directions[direction % 6]
    
    def length(self) -> int:
        return (abs(self.q) + abs(self.r) + abs(self.s)) // 2

    def distance(self, other: 'Hex') -> int:
        return (self - other).length()

@dataclass(frozen=True)
class Vertex:
    """
    Represents a corner of a hex.
    """
    owner: Hex
    direction: int

    def get_canonical(self) -> 'Vertex':
        """Returns the unique, canonical representation of this vertex."""
        h1 = self.owner
        d1 = self.direction % 6
        
        h2 = h1.neighbor(d1)
        d2 = (d1 + 4) % 6
        
        h3 = h1.neighbor((d1 - 1) % 6)
        d3 = (d1 + 2) % 6

        candidates = [(h1, d1), (h2, d2), (h3, d3)]
        best_hex, best_dir = min(candidates, key=lambda x: (x[0].q, x[0].r, x[0].s))
        return Vertex(best_hex, best_dir)

    def get_adjacent_vertices(self) -> List['Vertex']:
        """
        Returns the 3 vertices connected to this vertex via edges.
        Used for the 'Distance Rule' (settlements cannot be adjacent).
        """
        edges = self.get_touching_edges()
        result = set()
        for edge in edges:
            # Each edge has 2 vertices. One is 'self', the other is the neighbor.
            vs = edge.get_vertices()
            for v in vs:
                # We only want the OTHER vertex, not ourselves
                if v.get_canonical() != self.get_canonical():
                    result.add(v.get_canonical())
        return list(result)

    def get_touching_edges(self) -> List['Edge']:
        """
        Returns the 3 edges that meet at this vertex.
        """
        # The 3 edges meeting at Vertex(H, d) are:
        # 1. Edge(H, d)   -> The edge "forward" clockwise
        # 2. Edge(H, d-1) -> The edge "backward" counter-clockwise
        # 3. The "spine" edge between the two neighbors.
        #    Neighbor(d) is the hex at direction d.
        #    The shared edge between Neighbor(d) and Neighbor(d-1) is at index 4 relative to Neighbor(d).
        
        edges = [
            Edge(self.owner, self.direction).get_canonical(),
            Edge(self.owner, (self.direction - 1) % 6).get_canonical(),
            # FIX: Changed offset from +2 to +4 to correctly identify the shared edge between neighbors
            Edge(self.owner.neighbor(self.direction), (self.direction + 4) % 6).get_canonical()
        ]
        return edges

    def __repr__(self):
        return f"Vertex({self.owner}, dir={self.direction})"

@dataclass(frozen=True)
class Edge:
    """
    Represents a side of a hex.
    """
    owner: Hex
    direction: int

    def get_canonical(self) -> 'Edge':
        h1 = self.owner
        d1 = self.direction % 6
        h2 = h1.neighbor(d1)
        d2 = (d1 + 3) % 6 
        candidates = [(h1, d1), (h2, d2)]
        best_hex, best_dir = min(candidates, key=lambda x: (x[0].q, x[0].r, x[0].s))
        return Edge(best_hex, best_dir)
    
    def get_vertices(self) -> List[Vertex]:
        """Returns the 2 vertices at the ends of this edge."""
        # Edge 'd' sits between Vertex 'd' and Vertex 'd+1'
        v1 = Vertex(self.owner, self.direction).get_canonical()
        v2 = Vertex(self.owner, (self.direction + 1) % 6).get_canonical()
        return [v1, v2]

    def get_connected_edges(self) -> List['Edge']:
        """
        Returns the 4 edges connected to this edge (2 at each end).
        Used for finding 'Longest Road'.
        """
        v1, v2 = self.get_vertices()
        connected = set()
        
        for e in v1.get_touching_edges():
            if e.get_canonical() != self.get_canonical():
                connected.add(e.get_canonical())
                
        for e in v2.get_touching_edges():
            if e.get_canonical() != self.get_canonical():
                connected.add(e.get_canonical())
                
        return list(connected)

    def __repr__(self):
        return f"Edge({self.owner}, dir={self.direction})"