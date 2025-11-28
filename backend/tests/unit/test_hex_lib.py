import pytest
from app.models.hex_lib import Hex, Vertex, Edge

class TestHexCore:
    def test_hex_neighbors(self):
        center = Hex(0, 0, 0)
        # MATCH IMPLEMENTATION: Direction 0 is (1, 0, -1)
        assert center.neighbor(0) == Hex(1, 0, -1)

    def test_neighbor_cycle(self):
        center = Hex(0,0,0)
        # 0: (1, 0, -1)
        # 3: (-1, 0, 1) [Opposite]
        right = center.neighbor(0)
        left = center.neighbor(3)
        assert right.q == 1
        assert left.q == -1

class TestVertexCanonicalization:
    def test_canonical_vertex_equality(self):
        h_center = Hex(0, 0, 0)
        
        # V0 (Top-Right/East corner) touches:
        # Neighbor 5 (NE) and Neighbor 0 (E)
        h_ne = h_center.neighbor(5)
        h_e = h_center.neighbor(0)

        # 1. Center V0
        v1 = Vertex(h_center, 0).get_canonical()
        
        # 2. Neighbor NE (V2 - Bottom)
        # Let's verify via lookup table in hex_lib logic:
        # V0 -> (5, 2) and (0, 4)
        v2 = Vertex(h_ne, 2).get_canonical()
        
        # 3. Neighbor E (V4 - Top-Left)
        v3 = Vertex(h_e, 4).get_canonical()

        assert v1 == v2
        assert v2 == v3
        assert v1 == v3

    def test_vertex_set_usage(self):
        h_center = Hex(0, 0, 0)
        h_right = h_center.neighbor(0)
        
        # V0 touches Neighbor 0 at V4
        v1 = Vertex(h_center, 0).get_canonical()
        v2 = Vertex(h_right, 4).get_canonical()
        
        vertex_set = set()
        vertex_set.add(v1)
        vertex_set.add(v2)
        
        assert len(vertex_set) == 1

class TestEdgeCanonicalization:
    def test_canonical_edge_equality(self):
        h1 = Hex(0, 0, 0)
        h2 = h1.neighbor(0) 

        # Edge 0 of h1 touches Edge 3 of h2
        e1 = Edge(h1, 0).get_canonical()
        e2 = Edge(h2, 3).get_canonical()

        assert e1 == e2