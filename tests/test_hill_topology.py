"""Tests for hill/grass cliffline repair (plan: grass connectivity / red-swap pattern)."""
from __future__ import annotations

import unittest

from tilemap_generator.hill_topology import apply_grass_hill_cliffline_repair


class GrassHillClifflineRepairTests(unittest.TestCase):
    """Minimal fixtures: G I G I along row/column → swap middle pair (cliffline plan)."""

    def test_horizontal_gigig_becomes_ggiig(self) -> None:
        # Fixture: thin choke G I G I … swaps to G G I I so grass connects at x,x+1
        grid = [list("GIGIG")]
        w, h = 5, 1
        n = apply_grass_hill_cliffline_repair(grid, w, h)
        self.assertEqual(n, 1)
        self.assertEqual("".join(grid[0]), "GGIIG")

    def test_vertical_same_pattern(self) -> None:
        grid = [list("G"), list("I"), list("G"), list("I"), list("G")]
        w, h = 1, 5
        n = apply_grass_hill_cliffline_repair(grid, w, h)
        self.assertEqual(n, 1)
        self.assertEqual(["".join(r) for r in grid], ["G", "G", "I", "I", "G"])

    def test_dot_counts_as_grass(self) -> None:
        grid = [list(".I.I")]
        n = apply_grass_hill_cliffline_repair(grid, 4, 1)
        self.assertEqual(n, 1)
        self.assertEqual("".join(grid[0]), "..II")

    def test_no_match_returns_zero(self) -> None:
        grid = [list("GIIIG")]
        self.assertEqual(apply_grass_hill_cliffline_repair(grid, 5, 1), 0)
        self.assertEqual("".join(grid[0]), "GIIIG")


if __name__ == "__main__":
    unittest.main()
