from dataclasses import dataclass
from typing import List

@dataclass(frozen=True, order=True)
class Hex:
    q: int
    r: int
    s: int

    def __add__(self, other: 'Hex') -> 'Hex':
        return Hex(self.q + other.q, self.r + other.r, self.s + other.s)

    def neighbor(self, direction: int) -> 'Hex':
        # STANDARD POINTY TOP VECTORS (Clockwise starting from East/Right)
        # 0: East
        # 1: South-East
        # 2: South-West
        # 3: West
        # 4: North-West
        # 5: North-East
        vectors = [
            Hex(1, 0, -1),  # 0
            Hex(0, 1, -1),  # 1
            Hex(-1, 1, 0),  # 2
            Hex(-1, 0, 1),  # 3
            Hex(0, -1, 1),  # 4
            Hex(1, -1, 0)   # 5
        ]
        return self + vectors[direction % 6]

@dataclass(frozen=True)
class Vertex:
    owner: Hex
    direction: int

    def get_canonical(self) -> 'Vertex':
        """
        Returns the unique identifier for a vertex.
        In Pointy Top, Vertex 0 is at -30 deg (Top Right).
        """
        h = self.owner
        d = self.direction % 6
        
        # LOOKUP TABLE FOR VERTEX EQUIVALENCE
        # Key: My Vertex Direction (0-5)
        # Value: List of (Neighbor Direction, Vertex Index on that Neighbor)
        lookup = {
            0: [(5, 2), (0, 4)],
            1: [(0, 3), (1, 5)],
            2: [(1, 4), (2, 0)],
            3: [(2, 5), (3, 1)],
            4: [(3, 0), (4, 2)],
            5: [(4, 1), (5, 3)]
        }
        
        # 1. Candidate: Self
        candidates = [(h, d)]
        
        # 2. Candidates: Neighbors
        mappings = lookup[d]
        for neigh_dir, neigh_vert_idx in mappings:
            n_hex = h.neighbor(neigh_dir)
            candidates.append((n_hex, neigh_vert_idx))
            
        # Sort: Smallest (q, r, s) becomes the canonical representation
        candidates.sort(key=lambda x: (x[0].q, x[0].r, x[0].s))
        
        return Vertex(candidates[0][0], candidates[0][1])

    def get_touching_edges(self) -> List['Edge']:
        """
        Returns the 3 edges meeting at this vertex.
        """
        # 1. Edge d (Forward on Self)
        e1 = Edge(self.owner, self.direction).get_canonical()
        
        # 2. Edge d-1 (Backward on Self)
        e2 = Edge(self.owner, (self.direction - 1) % 6).get_canonical()
        
        # 3. Spoke Edge (Radiating outward)
        # Lookup table for the 3rd edge based on geometry
        lookup_spoke = {
            0: (5, 2), # For V0, take Neighbor 5's Edge 2
            1: (0, 3),
            2: (1, 4),
            3: (2, 5),
            4: (3, 0),
            5: (4, 1)
        }
        
        neigh_dir, neigh_edge_idx = lookup_spoke[self.direction % 6]
        n_hex = self.owner.neighbor(neigh_dir)
        e3 = Edge(n_hex, neigh_edge_idx).get_canonical()
        
        return [e1, e2, e3]

    def get_adjacent_vertices(self) -> List['Vertex']:
        canon_self = self.get_canonical()
        edges = self.get_touching_edges()
        neighbors = set()
        for e in edges:
            for v in e.get_vertices():
                if v.get_canonical() != canon_self:
                    neighbors.add(v.get_canonical())
        return list(neighbors)

    def __repr__(self):
        return f"Vertex({self.owner.q},{self.owner.r},{self.owner.s}|{self.direction})"
    def __eq__(self, other):
        if not isinstance(other, Vertex): return False
        c1 = self.get_canonical()
        c2 = other.get_canonical()
        return (c1.owner == c2.owner) and (c1.direction == c2.direction)
    def __hash__(self):
        c = self.get_canonical()
        return hash((c.owner.q, c.owner.r, c.owner.s, c.direction))

@dataclass(frozen=True)
class Edge:
    owner: Hex
    direction: int

    def get_canonical(self) -> 'Edge':
        """
        Edge N is shared with Neighbor N.
        On Neighbor N, it corresponds to Edge (N+3)%6.
        """
        h1 = self.owner
        d1 = self.direction % 6
        
        n = h1.neighbor(d1)
        d2 = (d1 + 3) % 6
        
        c1 = (h1, d1)
        c2 = (n, d2)
        
        if (c1[0].q, c1[0].r, c1[0].s) < (c2[0].q, c2[0].r, c2[0].s):
            return Edge(c1[0], c1[1])
        else:
            return Edge(c2[0], c2[1])

    def get_vertices(self) -> List[Vertex]:
        v1 = Vertex(self.owner, self.direction).get_canonical()
        v2 = Vertex(self.owner, (self.direction + 1) % 6).get_canonical()
        return [v1, v2]

    def get_connected_edges(self) -> List['Edge']:
        v1, v2 = self.get_vertices()
        result = set()
        for v in [v1, v2]:
            for e in v.get_touching_edges():
                if e.get_canonical() != self.get_canonical():
                    result.add(e.get_canonical())
        return list(result)
        
    def __repr__(self):
        return f"Edge({self.owner.q},{self.owner.r},{self.owner.s}|{self.direction})"
    def __eq__(self, other):
        if not isinstance(other, Edge): return False
        c1 = self.get_canonical()
        c2 = other.get_canonical()
        return (c1.owner == c2.owner) and (c1.direction == c2.direction)
    def __hash__(self):
        c = self.get_canonical()
        return hash((c.owner.q, c.owner.r, c.owner.s, c.direction))