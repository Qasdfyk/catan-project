from app.models.board import Board
from app.models.hex_lib import Hex, Vertex


def board_vertices():
    return Board.create_standard_game().vertices()


def test_every_vertex_touches_three_distinct_edges():
    """Regression: the spoke edge used to duplicate one of the other two edges."""
    for vertex in board_vertices():
        edges = vertex.get_touching_edges()
        assert len(set(edges)) == 3, vertex
        for edge in edges:
            assert vertex in edge.get_vertices(), (vertex, edge)


def test_every_vertex_has_three_neighbors():
    """Regression: the broken spoke hid the third neighbor from the distance rule."""
    for vertex in board_vertices():
        assert len(vertex.get_adjacent_vertices()) == 3, vertex


def test_vertices_on_a_shared_spoke_are_neighbors():
    center = Hex(0, 0, 0)
    vertex = Vertex(center, 0)
    # Going out along the spoke between the NE and E neighbors
    spoke_end = Vertex(center.neighbor(0), 5)

    assert spoke_end.get_canonical() in vertex.get_adjacent_vertices()
