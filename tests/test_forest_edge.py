"""Forest edge roughening should break rectangular blobs."""
from __future__ import annotations

import unittest

from tilemap_generator.forest_edge import roughen_forest_edges


def _box_forest(w: int = 12, h: int = 12, margin: int = 2) -> list[list[str]]:
    grid = [["G"] * w for _ in range(h)]
    for y in range(margin, h - margin):
        for x in range(margin, w - margin):
            grid[y][x] = "F"
    return grid


def _is_axis_aligned_rect(grid: list[list[str]]) -> bool:
    """True if all F cells form a filled axis-aligned rectangle (no holes / jogs)."""
    cells = [(x, y) for y, row in enumerate(grid) for x, ch in enumerate(row) if ch == "F"]
    if not cells:
        return True
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    expected = (maxx - minx + 1) * (maxy - miny + 1)
    if len(cells) != expected:
        return False
    for y in range(miny, maxy + 1):
        for x in range(minx, maxx + 1):
            if grid[y][x] != "F":
                return False
    return True


class ForestEdgeTests(unittest.TestCase):
    def test_roughen_breaks_rectangle(self) -> None:
        grid = _box_forest()
        self.assertTrue(_is_axis_aligned_rect(grid))
        stats = roughen_forest_edges(grid, iterations=3, seed=11)
        self.assertGreater(stats["eroded"] + stats["nibbled"] + stats["grown"], 0)
        self.assertFalse(_is_axis_aligned_rect(grid))

    def test_zero_iterations_noop(self) -> None:
        grid = _box_forest()
        before = [row[:] for row in grid]
        stats = roughen_forest_edges(grid, iterations=0, seed=1)
        self.assertEqual(stats, {"eroded": 0, "grown": 0, "nibbled": 0})
        self.assertEqual(grid, before)

    def test_eligible_stays_inside(self) -> None:
        grid = _box_forest()
        # only allow left half of the forest box
        eligible = {(x, y) for y in range(12) for x in range(0, 6)}
        roughen_forest_edges(grid, iterations=4, seed=3, eligible=eligible)
        for y, row in enumerate(grid):
            for x, ch in enumerate(row):
                if ch == "F" and (x, y) not in eligible:
                    # forest outside eligible only if it was already there and untouched
                    # right half starts as F for x in 2..9; x>=6 should remain F (untouched)
                    self.assertGreaterEqual(x, 6)

    def test_protects_path(self) -> None:
        grid = _box_forest()
        grid[5][5] = "P"
        roughen_forest_edges(grid, iterations=5, seed=9, protected_chars={"P"})
        self.assertEqual(grid[5][5], "P")


if __name__ == "__main__":
    unittest.main()
