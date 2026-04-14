"""Post-process hill/grass ASCII to reduce thin cliff chokes that isolate grass (4-connectivity).

See ``apply_grass_hill_cliffline_repair`` for the G I G I pattern used after hill placement.
"""
from __future__ import annotations


def apply_grass_hill_cliffline_repair(
    grid: list[list[str]],
    width: int,
    height: int,
    *,
    grass_chars: frozenset[str] | None = None,
    hill_char: str = "I",
) -> int:
    """Swap adjacent hill/grass pairs in ``G I G I`` runs (horizontal and vertical).

    When grass–hill–grass–hill appears on one axis, swap the middle hill with the grass so the
    cliff steps one cell and grass tiles become 4-adjacent (fixes single-cell cliff separating
    grass along a row/column).

    Repeats until stable so overlapping patterns resolve. Returns the number of swaps performed.
    """
    grass = grass_chars or frozenset({"G", "."})
    total = 0
    changed = True
    while changed:
        changed = False
        for y in range(height):
            row = grid[y]
            for x in range(max(0, width - 3)):
                if (
                    row[x] in grass
                    and row[x + 1] == hill_char
                    and row[x + 2] in grass
                    and row[x + 3] == hill_char
                ):
                    row[x + 1], row[x + 2] = row[x + 2], row[x + 1]
                    total += 1
                    changed = True
        for y in range(max(0, height - 3)):
            for x in range(width):
                if (
                    grid[y][x] in grass
                    and grid[y + 1][x] == hill_char
                    and grid[y + 2][x] in grass
                    and grid[y + 3][x] == hill_char
                ):
                    grid[y + 1][x], grid[y + 2][x] = grid[y + 2][x], grid[y + 1][x]
                    total += 1
                    changed = True
    return total
