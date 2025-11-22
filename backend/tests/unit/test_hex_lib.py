import pytest
from app.models.hex_lib import Hex

class TestHexCore:
    def test_hex_creation_valid(self):
        """Test creating a valid hex instance."""
        h = Hex(0, -1, 1)
        assert h.q == 0
        assert h.r == -1
        assert h.s == 1

    def test_hex_creation_invalid(self):
        """Test if ValueError is raised when q+r+s != 0."""
        with pytest.raises(ValueError):
            Hex(1, 1, 1)

    def test_hex_equality(self):
        """Test object equality (Value Object pattern)."""
        h1 = Hex(1, -2, 1)
        h2 = Hex(1, -2, 1)
        h3 = Hex(0, 0, 0)
        assert h1 == h2
        assert h1 != h3

    def test_hex_addition(self):
        """Test vector addition."""
        h1 = Hex(1, -2, 1)
        h2 = Hex(2, -1, -1)
        result = h1 + h2
        assert result == Hex(3, -3, 0)

    def test_hex_subtraction(self):
        """Test vector subtraction."""
        h1 = Hex(1, -2, 1)
        h2 = Hex(2, -1, -1)
        result = h1 - h2
        assert result == Hex(-1, -1, 2)

    def test_hex_distance(self):
        """Test distance calculation between hexes."""
        h1 = Hex(0, 0, 0)
        h2 = Hex(2, -2, 0) # Distance is 2 steps
        assert h1.distance(h2) == 2
        
        h3 = Hex(-3, 1, 2)
        assert h3.distance(h3) == 0

    def test_hex_neighbors(self):
        """Test finding neighbors."""
        center = Hex(0, 0, 0)
        neighbor_0 = center.neighbor(0) # Direction 0: (1, 0, -1)
        
        assert neighbor_0 == Hex(1, 0, -1)
        assert center.distance(neighbor_0) == 1
        
        # Check if backtracking works (neighbor of a neighbor in opposite direction)
        # Direction 3 is opposite to 0
        assert neighbor_0.neighbor(3) == center

    def test_all_neighbors_count(self):
        """Test if get_all_neighbors returns exactly 6 valid neighbors."""
        center = Hex(0, 0, 0)
        neighbors = center.get_all_neighbors()
        assert len(neighbors) == 6
        # All neighbors must be at distance 1
        for n in neighbors:
            assert center.distance(n) == 1