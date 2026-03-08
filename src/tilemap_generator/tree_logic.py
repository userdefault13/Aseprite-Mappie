"""Tree tile resolution for vertical runs. From GotchiCraft map generator.

When T or F (tree/forest) cells are vertically adjacent, use segment tiles:
- 2 adjacent: top=19, bottom=26
- 3+ adjacent: top=13, middle=20 (repeatable), bottom=27
- Single (no vertical run): default=33, 15% chance of 25, 29, 32, 34, 35
"""

from __future__ import annotations

import random
from typing import Any


# Default tile IDs (1-based, for Tiled/CSV output)
DEFAULT_TREE_CONFIG: dict[str, Any] = {
    "single": 33,
    "single_alts": [25, 29, 32, 34, 35],
    "single_alt_chance": 0.15,
    "vertical_2_top": 19,
    "vertical_2_bottom": 26,
    "vertical_3_top": 13,
    "vertical_3_mid": 20,
    "vertical_3_bottom": 27,
}


def find_vertical_runs(
    grid: list[list[str]],
    tree_chars: set[str],
    width: int,
    height: int,
) -> dict[tuple[int, int], int]:
    """Return {(row, col): tile_id} for cells in vertical runs of 2+.
    Single trees are NOT added (they use single-tree logic).
    """
    result: dict[tuple[int, int], int] = {}
    cfg = DEFAULT_TREE_CONFIG
    for col in range(width):
        row = 0
        while row < height:
            if grid[row][col] in tree_chars:
                start = row
                while row < height and grid[row][col] in tree_chars:
                    row += 1
                length = row - start
                if length >= 2:
                    for i in range(length):
                        r = start + i
                        if length == 2:
                            result[(r, col)] = (
                                cfg["vertical_2_top"] if i == 0 else cfg["vertical_2_bottom"]
                            )
                        else:
                            if i == 0:
                                result[(r, col)] = cfg["vertical_3_top"]
                            elif i == length - 1:
                                result[(r, col)] = cfg["vertical_3_bottom"]
                            else:
                                result[(r, col)] = cfg["vertical_3_mid"]
            else:
                row += 1
    return result


def resolve_tree_tile(
    row: int,
    col: int,
    vertical_runs: dict[tuple[int, int], int],
    config: dict[str, Any],
    rng: random.Random,
    fallback: int,
) -> int:
    """Resolve tile ID for a tree cell. Uses vertical_runs if in run, else single logic."""
    if (row, col) in vertical_runs:
        return vertical_runs[(row, col)]
    # Single tree
    if rng.random() < config.get("single_alt_chance", 0.15):
        alts = config.get("single_alts", [25, 29, 32, 34, 35])
        if alts:
            return rng.choice(alts)
    return config.get("single", 33)


def to_tile_rows_with_trees(
    lines: list[str],
    legend: dict[str, int],
    tree_chars: set[str] | None = None,
    tree_config: dict[str, Any] | None = None,
    seed: int = 42,
) -> list[list[int]]:
    """Convert ASCII to tile rows, with contextual tree tile resolution."""
    if tree_chars is None:
        tree_chars = {"T", "F"}
    if tree_config is None:
        tree_config = DEFAULT_TREE_CONFIG.copy()

    # Build grid (row, col) -> char. Mappie uses grid[y][x], x=col, y=row
    grid = [list(line) for line in lines]
    height = len(grid)
    width = len(grid[0]) if grid else 0

    vertical_runs = find_vertical_runs(grid, tree_chars, width, height)
    rng = random.Random(seed)

    rows: list[list[int]] = []
    for y, line in enumerate(lines):
        row: list[int] = []
        for x, char in enumerate(line):
            if char not in legend:
                raise ValueError(
                    f"Character {char!r} at x={x}, y={y} not found in legend."
                )
            if char in tree_chars:
                tile_id = resolve_tree_tile(
                    row=y,
                    col=x,
                    vertical_runs=vertical_runs,
                    config=tree_config,
                    rng=rng,
                    fallback=legend[char],
                )
                row.append(tile_id)
            else:
                row.append(legend[char])
        rows.append(row)
    return rows
