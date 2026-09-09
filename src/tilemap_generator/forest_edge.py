"""Roughen rectangular forest blobs via edge erode/grow + corner nibble.

Used by open-world map_gen and moba_lanes so forest groups never look boxy.
When ``eligible`` is set (moba collision rects), mutation stays inside that set
so collision AABBs remain valid.
"""
from __future__ import annotations

import random
from typing import Iterable

Point = tuple[int, int]

DEFAULT_FOREST_CHARS = frozenset({"T", "F"})
DEFAULT_GROW_ONTO = frozenset({"G", "."})
# Paths, water, shore, hills, POIs — never overwrite
DEFAULT_PROTECTED_CHARS = frozenset({"B", "L", "R", "~", "`", "I", "P", "J", "M", "H", "C", "D", "S", "N"})


def _neighbors8(x: int, y: int, width: int, height: int) -> list[Point]:
    out: list[Point] = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height:
                out.append((nx, ny))
    return out


def _forest_count(
    grid: list[list[str]],
    x: int,
    y: int,
    width: int,
    height: int,
    forest_chars: frozenset[str],
) -> int:
    return sum(
        1
        for nx, ny in _neighbors8(x, y, width, height)
        if grid[ny][nx] in forest_chars
    )


def _is_forest_edge(
    grid: list[list[str]],
    x: int,
    y: int,
    width: int,
    height: int,
    forest_chars: frozenset[str],
) -> bool:
    if grid[y][x] not in forest_chars:
        return False
    if x in (0, width - 1) or y in (0, height - 1):
        return True
    for nx, ny in _neighbors8(x, y, width, height):
        if grid[ny][nx] not in forest_chars:
            return True
    return False


def _pick_grow_char(
    grid: list[list[str]],
    x: int,
    y: int,
    width: int,
    height: int,
    forest_chars: frozenset[str],
    default_char: str,
) -> str:
    counts: dict[str, int] = {}
    for nx, ny in _neighbors8(x, y, width, height):
        ch = grid[ny][nx]
        if ch in forest_chars:
            counts[ch] = counts.get(ch, 0) + 1
    if not counts:
        return default_char
    return max(counts.items(), key=lambda kv: kv[1])[0]


def roughen_forest_edges(
    grid: list[list[str]],
    *,
    iterations: int = 3,
    seed: int = 42,
    erode_p: float = 0.55,
    grow_p: float = 0.35,
    corner_nibble_p: float = 0.7,
    forest_chars: Iterable[str] | None = None,
    grow_onto: Iterable[str] | None = None,
    protected_chars: Iterable[str] | None = None,
    eligible: set[Point] | None = None,
    default_forest_char: str = "F",
    grass_char: str = "G",
) -> dict[str, int]:
    """Mutate ``grid`` in place to roughen forest edges. Returns change stats.

    Parameters
    ----------
    iterations:
        CA passes (0 = no-op). Default 3.
    eligible:
        If provided, only cells in this set may change (moba forest rects).
    """
    if iterations <= 0:
        return {"eroded": 0, "grown": 0, "nibbled": 0}

    height = len(grid)
    width = len(grid[0]) if grid else 0
    if width == 0 or height == 0:
        return {"eroded": 0, "grown": 0, "nibbled": 0}

    fchars = frozenset(forest_chars) if forest_chars is not None else DEFAULT_FOREST_CHARS
    onto = frozenset(grow_onto) if grow_onto is not None else DEFAULT_GROW_ONTO
    protected = (
        frozenset(protected_chars)
        if protected_chars is not None
        else DEFAULT_PROTECTED_CHARS
    )
    # Prefer grass_char when grow_onto includes it; else first grow target
    if grass_char not in onto and onto:
        # still erode to grass_char only if caller set it; allow "." for hand maps
        pass

    rng = random.Random(seed)
    eroded = grown = 0

    def allowed(x: int, y: int) -> bool:
        if eligible is not None and (x, y) not in eligible:
            return False
        return grid[y][x] not in protected

    for _ in range(iterations):
        changes: list[tuple[int, int, str]] = []
        for y in range(height):
            for x in range(width):
                if not allowed(x, y):
                    continue
                ch = grid[y][x]
                fc = _forest_count(grid, x, y, width, height, fchars)
                if ch in fchars and _is_forest_edge(grid, x, y, width, height, fchars):
                    # Prefer eroding sparse edge; keep dense cores
                    if fc <= 3 and rng.random() < erode_p:
                        # erode to grass_char if G/./eligible grow char present in onto
                        erode_to = grass_char if grass_char in onto or grass_char in (".", "G") else next(iter(onto), grass_char)
                        # Hand maps often use "."; open-world uses "G"
                        if "." in onto and grass_char == "G" and any(
                            grid[ny][nx] == "." for nx, ny in _neighbors8(x, y, width, height)
                        ):
                            erode_to = "."
                        elif grass_char in ("G", ".") or True:
                            # Prefer matching neighboring grass style
                            for nx, ny in _neighbors8(x, y, width, height):
                                if grid[ny][nx] in onto:
                                    erode_to = grid[ny][nx]
                                    break
                            else:
                                erode_to = grass_char
                        changes.append((x, y, erode_to))
                    elif fc <= 5 and rng.random() < erode_p * 0.45:
                        erode_to = grass_char
                        for nx, ny in _neighbors8(x, y, width, height):
                            if grid[ny][nx] in onto:
                                erode_to = grid[ny][nx]
                                break
                        changes.append((x, y, erode_to))
                elif ch in onto:
                    if 2 <= fc <= 5 and rng.random() < grow_p:
                        # avoid smothering protected neighbors
                        near_prot = any(
                            grid[ny][nx] in protected
                            for nx, ny in _neighbors8(x, y, width, height)
                        )
                        if near_prot and fc < 4:
                            continue
                        grow_ch = _pick_grow_char(
                            grid, x, y, width, height, fchars, default_forest_char
                        )
                        changes.append((x, y, grow_ch))
        for x, y, new_ch in changes:
            if not allowed(x, y):
                continue
            old = grid[y][x]
            if old == new_ch:
                continue
            if old in fchars and new_ch in onto:
                eroded += 1
            elif old in onto and new_ch in fchars:
                grown += 1
            grid[y][x] = new_ch

    # Corner nibble pass — breaks remaining boxy corners
    rng2 = random.Random(seed + 99)
    nibbled = 0
    nibble_changes: list[tuple[int, int, str]] = []
    for y in range(height):
        for x in range(width):
            if not allowed(x, y):
                continue
            if grid[y][x] not in fchars:
                continue
            n = y > 0 and grid[y - 1][x] in fchars
            s = y < height - 1 and grid[y + 1][x] in fchars
            e = x < width - 1 and grid[y][x + 1] in fchars
            w = x > 0 and grid[y][x - 1] in fchars
            orth = sum((n, s, e, w))
            is_corner = orth == 2 and (
                (n and e) or (n and w) or (s and e) or (s and w)
            )
            sparse = _forest_count(grid, x, y, width, height, fchars) <= 2
            if (is_corner and rng2.random() < corner_nibble_p) or (
                sparse and rng2.random() < 0.5
            ):
                erode_to = grass_char
                for nx, ny in _neighbors8(x, y, width, height):
                    if grid[ny][nx] in onto:
                        erode_to = grid[ny][nx]
                        break
                nibble_changes.append((x, y, erode_to))
    for x, y, new_ch in nibble_changes:
        if grid[y][x] in fchars:
            grid[y][x] = new_ch
            nibbled += 1

    return {"eroded": eroded, "grown": grown, "nibbled": nibbled}
