from collections import Counter

from app.models.board import Board, PortType
from app.services.serializer import GameSerializer
from app.models.game import GameState


def test_board_has_nine_standard_ports():
    board = Board.create_standard_game()
    counts = Counter(port.type for port in board.ports)

    assert len(board.ports) == 9
    assert counts[PortType.GENERIC_3_1] == 4
    for port_type in PortType:
        if port_type != PortType.GENERIC_3_1:
            assert counts[port_type] == 1


def test_ports_sit_on_distinct_coastal_vertices():
    board = Board.create_standard_game()
    vertices = [v for port in board.ports for v in port.valid_vertices]

    assert len(set(vertices)) == 18
    for vertex in vertices:
        on_board = [h for h in vertex.get_touching_hexes() if h in board.tiles]
        assert len(on_board) < 3, vertex


def test_coast_is_a_closed_walk_of_thirty_edges():
    board = Board.create_standard_game()
    coast = Board._coastal_edges_in_order(board)

    assert len(coast) == 30
    for first, second in zip(coast, coast[1:] + coast[:1]):
        assert set(first.get_vertices()) & set(second.get_vertices())


def test_ports_survive_serialization():
    """Regression: ports were dropped on the first read from Redis."""
    game = GameState.create_new_game(["Alice", "Bob"])

    loaded = GameSerializer.dict_to_game(GameSerializer.game_to_dict(game))

    assert [(p.type, p.valid_vertices) for p in loaded.board.ports] == [
        (p.type, p.valid_vertices) for p in game.board.ports
    ]
