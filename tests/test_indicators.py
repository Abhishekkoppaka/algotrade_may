"""
Tests for the shared indicators module.

Validates that pivot calculations produce correct values
and that the pivot navigation helpers work as expected.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import pandas as pd
import numpy as np
from strategies.indicators import (
    calculate_floor_pivots_from_ohlc,
    get_next_pivot_above,
    get_next_pivot_below,
    get_sorted_pivot_levels,
)


class TestFloorPivots:
    """Test floor pivot point calculations."""

    def test_basic_pivot_calculation(self):
        """PP = (H + L + C) / 3"""
        result = calculate_floor_pivots_from_ohlc(100.0, 80.0, 90.0)
        expected_pp = (100.0 + 80.0 + 90.0) / 3  # 90.0
        assert abs(result["PP"] - expected_pp) < 0.01

    def test_resistance_levels_ascending(self):
        """R1 < R2 < R3 when price is trending up."""
        result = calculate_floor_pivots_from_ohlc(100.0, 80.0, 95.0)
        assert result["R1"] < result["R2"] < result["R3"]

    def test_support_levels_descending(self):
        """S1 > S2 > S3."""
        result = calculate_floor_pivots_from_ohlc(100.0, 80.0, 95.0)
        assert result["S1"] > result["S2"] > result["S3"]

    def test_pdh_pdl_included(self):
        """Previous day high/low should be in the result."""
        result = calculate_floor_pivots_from_ohlc(150.0, 120.0, 140.0)
        assert result["PDH"] == 150.0
        assert result["PDL"] == 120.0

    def test_cpr_levels_are_normalized(self):
        """BC must be the lower CPR boundary and TC the upper boundary."""
        result = calculate_floor_pivots_from_ohlc(100.0, 80.0, 80.0)
        assert result["BC"] == pytest.approx(83.3333333333)
        assert result["TC"] == 90.0

    def test_symmetric_with_equal_hlc(self):
        """When H=L=C, all pivots collapse to the same value."""
        result = calculate_floor_pivots_from_ohlc(100.0, 100.0, 100.0)
        assert result["PP"] == 100.0
        assert result["BC"] == 100.0
        assert result["TC"] == 100.0
        assert result["R1"] == 100.0
        assert result["S1"] == 100.0


class TestPivotNavigation:
    """Test finding next pivot above/below a price."""

    def setup_method(self):
        """Create a standard set of sorted pivots for testing."""
        self.pivots = [80.0, 90.0, 95.0, 100.0, 105.0, 110.0, 120.0]

    def test_next_above_middle(self):
        """Find first pivot above a mid-range price."""
        result = get_next_pivot_above(97.0, self.pivots)
        assert result == 100.0

    def test_next_above_at_pivot(self):
        """If price equals a pivot, the next one above should be returned."""
        result = get_next_pivot_above(100.0, self.pivots)
        assert result == 105.0

    def test_next_above_beyond_all(self):
        """If price is above all pivots, fallback is price + 100."""
        result = get_next_pivot_above(125.0, self.pivots)
        assert result == 225.0

    def test_next_below_middle(self):
        """Find first pivot below a mid-range price."""
        result = get_next_pivot_below(97.0, self.pivots)
        assert result == 95.0

    def test_next_below_at_pivot(self):
        """If price equals a pivot, the next one below should be returned."""
        result = get_next_pivot_below(100.0, self.pivots)
        assert result == 95.0

    def test_next_below_beyond_all(self):
        """If price is below all pivots, fallback is price - 100."""
        result = get_next_pivot_below(70.0, self.pivots)
        assert result == -30.0


class TestSortedPivotLevels:
    """Test pivot dictionary to sorted list conversion."""

    def test_all_values_included(self):
        """All pivot values should appear in the sorted list."""
        pivot_dict = calculate_floor_pivots_from_ohlc(100.0, 80.0, 90.0)
        sorted_levels = get_sorted_pivot_levels(pivot_dict)
        assert len(sorted_levels) == len(pivot_dict)

    def test_output_is_sorted(self):
        """Output list must be in ascending order."""
        pivot_dict = calculate_floor_pivots_from_ohlc(200.0, 150.0, 180.0)
        sorted_levels = get_sorted_pivot_levels(pivot_dict)
        assert sorted_levels == sorted(sorted_levels)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
