import pytest
from app.models.hex_lib import Hex, Vertex, Edge

class TestHexCore:
    def test_hex_creation_valid(self):
        h = Hex(0, -1, 1)
        assert h.q == 0

    def test_hex_neighbors(self):
        center = Hex(0, 0, 0)
        neighbor = center.neighbor(0)
        assert neighbor == Hex(1, 0, -1)

class TestVertexCanonicalization:
    def test_canonical_vertex_equality(self):
        """
        Test that the same physical vertex accessed from 3 different hexes
        resolves to the same canonical Vertex object.
        """
        # Center hex (0,0,0)
        h_center = Hex(0, 0, 0)
        
        # Neighbor at direction 0 (1, 0, -1)
        h_neighbor_0 = h_center.neighbor(0)
        
        # Neighbor at direction 5 (0, 1, -1)
        h_neighbor_5 = h_center.neighbor(5)

        # The vertex '0' of Center is shared by Neighbor 0 and Neighbor 5.
        # Perspective 1: Center, Vertex 0
        v1 = Vertex(h_center, 0).get_canonical()
        
        # Perspective 2: Neighbor 0. 
        # Looking back at Center (dir 3) and Neighbor 5 (dir 4). 
        # The vertex between 3 and 4 is Vertex 4.
        v2 = Vertex(h_neighbor_0, 4).get_canonical()
        
        # Perspective 3: Neighbor 5.
        # Looking back at Neighbor 0 (dir 1) and Center (dir 2).
        # The vertex between 1 and 2 is Vertex 2.
        v3 = Vertex(h_neighbor_5, 2).get_canonical()

        # They MUST be identical
        assert v1 == v2
        assert v2 == v3
        assert v1 == v3

    def test_vertex_set_usage(self):
        """Verify that canonical vertices work correctly in sets (hashing)."""
        h_center = Hex(0, 0, 0)
        h_neighbor = h_center.neighbor(0)
        
        # Same geometric point (Vertex 0 of Center == Vertex 4 of Neighbor 0)
        v1 = Vertex(h_center, 0).get_canonical()
        v2 = Vertex(h_neighbor, 4).get_canonical()
        
        vertex_set = set()
        vertex_set.add(v1)
        vertex_set.add(v2)
        
        # Should only have 1 element because v1 and v2 represent the same point
        assert len(vertex_set) == 1

class TestEdgeCanonicalization:
    def test_canonical_edge_equality(self):
        """
        Test that the same physical edge accessed from 2 adjacent hexes
        resolves to the same canonical Edge object.
        """
        h1 = Hex(0, 0, 0)
        h2 = h1.neighbor(0) # Neighbor to the right/top-right

        # Edge 0 of h1 is shared with Edge 3 (opposite) of h2
        e1 = Edge(h1, 0).get_canonical()
        e2 = Edge(h2, 3).get_canonical()

        assert e1 == e2

    def test_edge_set_usage(self):
        h1 = Hex(0, 0, 0)
        h2 = h1.neighbor(1)
        
        # Edge 1 of h1 touches Edge 4 of h2
        e1 = Edge(h1, 1).get_canonical()
        e2 = Edge(h2, 4).get_canonical()
        
        edge_set = {e1, e2}
        assert len(edge_set) == 1