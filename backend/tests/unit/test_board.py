import pytest
from collections import Counter
from app.models.board import Board, ResourceType, Tile
from app.models.hex_lib import Hex

class TestBoardGenerator:
    
    def test_standard_board_size(self):
        """Standard board (radius 2) should have 19 tiles."""
        board = Board.create_standard_game()
        assert len(board.tiles) == 19

    def test_resource_distribution(self):
        """Check if the exact count of resources is present."""
        board = Board.create_standard_game()
        resources = [t.resource for t in board.tiles.values()]
        counts = Counter(resources)

        assert counts[ResourceType.WOOD] == 4
        assert counts[ResourceType.SHEEP] == 4
        assert counts[ResourceType.WHEAT] == 4
        assert counts[ResourceType.BRICK] == 3
        assert counts[ResourceType.ORE] == 3
        assert counts[ResourceType.DESERT] == 1

    def test_number_distribution(self):
        """Check if numbers are correct (no 7, specific counts)."""
        board = Board.create_standard_game()
        # Filter out None (Desert)
        numbers = [t.number for t in board.tiles.values() if t.number is not None]
        counts = Counter(numbers)

        # Total numbered tiles should be 18
        assert len(numbers) == 18
        
        # 7 should not exist
        assert 7 not in counts
        
        # Check specific frequencies (examples)
        assert counts[2] == 1
        assert counts[12] == 1
        assert counts[6] == 2
        assert counts[8] == 2

    def test_desert_has_no_number(self):
        """Desert tile must verify number is None."""
        board = Board.create_standard_game()
        desert_tiles = [t for t in board.tiles.values() if t.resource == ResourceType.DESERT]
        
        assert len(desert_tiles) == 1
        assert desert_tiles[0].number is None

    def test_coordinate_lookup(self):
        """Test verifying we can retrieve a tile by coordinate."""
        board = Board.create_standard_game()
        center = Hex(0, 0, 0)
        
        tile = board.get_tile(center)
        assert tile is not None
        assert isinstance(tile, Tile)
        assert tile.hex_coords == center

    def test_out_of_bounds_lookup(self):
        """Test lookup for a hex that doesn't exist."""
        board = Board.create_standard_game()
        far_away = Hex(10, -10, 0)
        
        assert board.get_tile(far_away) is None