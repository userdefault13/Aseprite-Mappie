from __future__ import annotations

import argparse
from collections import deque
import heapq
import json
import os
import random
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import Callable


GRASS_CHAR = "G"
SHORELINE_CHAR = "B"  # Beach: grass adjacent to ocean 2-tile border (tiles 98-118)
LAKE_SHORELINE_CHAR = "L"  # Lake: grass adjacent to inland water (tiles 51-59)
RIVER_CHAR = "R"  # River bank: grass adjacent to narrow river channel (tiles 60-61)
HILL_CHAR = "I"  # Hill: elevated terrain (tiles 14-50)
WATER_CHAR = "~"
DEEP_WATER_CHAR = "`"  # Water surrounded by water (no land adjacent)
WATER_CHARS = frozenset({WATER_CHAR, DEEP_WATER_CHAR})
TREE_CHAR = "T"
FOREST_CHAR = "F"
PATH_CHAR = "P"
SPAWN_CHAR = "S"
JOIN_CHAR = "J"
MINE_CHAR = "M"
SHOP_CHAR = "H"
CREEP_CHAR = "C"
DEAD_END_CHAR = "D"
SECRET_NPC_CHAR = "N"

Point = tuple[int, int]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAC_ASEPRITE_BIN = Path("/Applications/Aseprite.app/Contents/MacOS/aseprite")
PREVIEW_COLORS: dict[str, tuple[int, int, int]] = {
    GRASS_CHAR: (104, 178, 76),
    SHORELINE_CHAR: (194, 178, 128),  # Sandy/beach
    LAKE_SHORELINE_CHAR: (120, 160, 180),  # Lake edge
    RIVER_CHAR: (100, 140, 200),  # River bank
    HILL_CHAR: (90, 120, 70),  # Hill
    ".": (104, 178, 76),
    WATER_CHAR: (72, 132, 224),
    DEEP_WATER_CHAR: (48, 96, 180),  # Darker blue for deep water
    TREE_CHAR: (46, 108, 54),
    FOREST_CHAR: (30, 78, 40),
    PATH_CHAR: (181, 152, 102),
    SPAWN_CHAR: (250, 228, 92),
    JOIN_CHAR: (255, 161, 77),
    MINE_CHAR: (125, 126, 134),
    SHOP_CHAR: (214, 123, 73),
    CREEP_CHAR: (194, 76, 76),
    DEAD_END_CHAR: (240, 95, 95),
    SECRET_NPC_CHAR: (86, 208, 220),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a procedural ASCII map with spawn clearings, Perlin-guided paths, "
            "and gameplay POIs."
        )
    )
    parser.add_argument("--width", type=int, required=True, help="Map width in tiles.")
    parser.add_argument("--height", type=int, required=True, help="Map height in tiles.")
    parser.add_argument(
        "--tree-density",
        type=float,
        required=True,
        help="Fraction of map covered by vegetation (0.0 to 1.0).",
    )
    parser.add_argument(
        "--forest-density",
        type=float,
        required=True,
        help="Fraction of vegetation that becomes forest clusters (0.0 to 1.0).",
    )
    parser.add_argument(
        "--water-density",
        type=float,
        required=True,
        help="Fraction of map covered by water (0.0 to 1.0).",
    )
    parser.add_argument(
        "--hill-density",
        type=float,
        default=0.0,
        help="Fraction of map covered by hills (0.0 to 1.0). Default 0.",
    )
    parser.add_argument("--spawn-count", type=int, default=8, help="Number of spawn points.")
    parser.add_argument(
        "--spawn-clearing-size",
        type=int,
        default=15,
        help="Odd square size of guaranteed grass clearing around each spawn.",
    )
    parser.add_argument(
        "--join-point-count",
        type=int,
        default=0,
        help="Join points for path network (0 = auto based on spawn count).",
    )
    parser.add_argument(
        "--path-width-threshold",
        type=int,
        default=3,
        help="Minimum path width in tiles.",
    )
    parser.add_argument(
        "--path-perlin-scale",
        type=float,
        default=14.0,
        help="Perlin scale for path shaping (larger = smoother).",
    )
    parser.add_argument(
        "--path-perlin-weight",
        type=float,
        default=1.8,
        help="How strongly Perlin field influences routing cost.",
    )
    parser.add_argument("--mine-count", type=int, default=4, help="Number of mines to place.")
    parser.add_argument("--shop-count", type=int, default=3, help="Number of shops to place.")
    parser.add_argument(
        "--creep-zone-count",
        type=int,
        default=6,
        help="Number of creep zones to place.",
    )
    parser.add_argument(
        "--creep-zone-radius",
        type=int,
        default=2,
        help="Creep zone radius in tiles.",
    )
    parser.add_argument(
        "--dead-end-count",
        type=int,
        default=8,
        help="Number of dead-end path branches to add.",
    )
    parser.add_argument(
        "--require-secret-npc-path",
        action="store_true",
        help="If set, adds one secret NPC reachable by exactly one branch path.",
    )
    parser.add_argument(
        "--hide-path",
        action="store_true",
        help="Do not carve paths. Spawns and joins remain, but corridors stay grass.",
    )
    parser.add_argument("--seed", type=int, default=0, help="Optional RNG seed.")
    parser.add_argument(
        "--map-mode",
        choices=["island", "continent"],
        default=None,
        help="Island: 2-tile water border (ocean). Continent: 2-tile land-with-trees border. Default from terrain config or island.",
    )
    parser.add_argument(
        "--water-border-width",
        type=int,
        default=2,
        help="(Island mode) Tiles of water border (default 2). Ignored in continent mode.",
    )
    parser.add_argument(
        "--height-noise-scale",
        type=float,
        default=12.0,
        help="Perlin scale for heightmap (larger = smoother terrain). Used for hills and shoreline depth.",
    )
    parser.add_argument(
        "--hill-threshold",
        type=float,
        default=0.65,
        help="Height above which tiles can become hills (0.0–1.0). Higher = hills only on peaks.",
    )
    parser.add_argument(
        "--beach-height-max",
        type=float,
        default=0.45,
        help="Max height for beach expansion (0.0–1.0). Low land near water gets wider beaches.",
    )
    parser.add_argument(
        "--shoreline-erode-iterations",
        type=int,
        default=2,
        help="Cellular automata iterations to erode water/land boundary (0=off, 2=default). Reduces straight coastlines.",
    )
    parser.add_argument(
        "--shoreline-expand-depth",
        type=int,
        default=0,
        help="Expand shoreline inward by N tiles where land is low (0=strict 1-tile border, default).",
    )
    parser.add_argument("--out", required=True, help="Output ASCII map path.")
    parser.add_argument(
        "--terrain-config",
        default="",
        help="Terrain config JSON. Auto-uses examples/terrain.bitmask.json when omitted. Legend used for output.",
    )
    parser.add_argument(
        "--legend-out",
        default="",
        help="Optional legend JSON path (defaults to <out>.legend.json).",
    )
    parser.add_argument(
        "--preview-out",
        default="",
        help="Optional preview path (defaults to <out>.preview.aseprite or .preview.bmp when preview is enabled).",
    )
    parser.add_argument(
        "--preview-tile-size",
        type=int,
        default=16,
        help="Pixel size per tile in preview image (default 16).",
    )
    parser.add_argument(
        "--preview-in-aseprite",
        action="store_true",
        default=True,
        dest="preview_in_aseprite",
        help="Open a generated map preview in Aseprite when done (default).",
    )
    parser.add_argument(
        "--no-preview-in-aseprite",
        action="store_false",
        dest="preview_in_aseprite",
        help="Do not open preview in Aseprite.",
    )
    parser.add_argument(
        "--preview-layered",
        action="store_true",
        default=True,
        dest="preview_layered",
        help="Output layered .aseprite preview with terrain separated into layers (default).",
    )
    parser.add_argument(
        "--no-preview-layered",
        action="store_false",
        dest="preview_layered",
        help="Output flat BMP preview instead of layered .aseprite.",
    )
    parser.add_argument(
        "--aseprite-bin",
        default="",
        help="Path to Aseprite binary (e.g. /Applications/Aseprite.app/Contents/MacOS/aseprite on macOS). "
        "Also set via ASEPRITE_BIN env var.",
    )
    return parser


def validate_density(value: float, name: str) -> None:
    if value < 0.0 or value > 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0")


def sign(value: int) -> int:
    if value < 0:
        return -1
    if value > 0:
        return 1
    return 0


def clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, value))


def all_positions(width: int, height: int) -> list[Point]:
    return [(x, y) for y in range(height) for x in range(width)]


def neighbors4(x: int, y: int, width: int, height: int) -> list[Point]:
    out: list[Point] = []
    if x > 0:
        out.append((x - 1, y))
    if x < width - 1:
        out.append((x + 1, y))
    if y > 0:
        out.append((x, y - 1))
    if y < height - 1:
        out.append((x, y + 1))
    return out


def neighbors8(x: int, y: int, width: int, height: int) -> list[Point]:
    """8-connected neighbors (including diagonals)."""
    out: list[Point] = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height:
                out.append((nx, ny))
    return out


def erode_water_land_boundary(
    grid: list[list[str]],
    width: int,
    height: int,
    protected: set[Point],
    iterations: int = 2,
    threshold: int = 5,
) -> None:
    """Cellular automata erosion to avoid straight coastlines. Mutates grid."""
    land_chars = frozenset({GRASS_CHAR})
    for _ in range(iterations):
        changes: list[tuple[int, int, str]] = []
        for y in range(height):
            for x in range(width):
                if (x, y) in protected:
                    continue
                ch = grid[y][x]
                n8 = neighbors8(x, y, width, height)
                n_water = sum(1 for nx, ny in n8 if grid[ny][nx] in WATER_CHARS)
                n_land = sum(1 for nx, ny in n8 if grid[ny][nx] in land_chars)
                if ch in land_chars and n_water >= threshold:
                    changes.append((x, y, WATER_CHAR))
                elif ch in WATER_CHARS and n_land >= threshold:
                    changes.append((x, y, GRASS_CHAR))
        for x, y, new_ch in changes:
            grid[y][x] = new_ch


def _is_border_water(px: int, py: int, width: int, height: int, water_border_width: int) -> bool:
    """True if (px,py) is out of bounds and treated as ocean border."""
    if px < 0 or px >= width or py < 0 or py >= height:
        return water_border_width > 0
    return False


def ocean_connected_water_cells(
    grid: list[list[str]],
    width: int,
    height: int,
    water_border_width: int,
) -> set[Point]:
    """Water cells connected via NESW to the ocean (map edge). Used for shoreline vs lake separation."""
    if water_border_width <= 0:
        return set()
    ocean_connected: set[Point] = set()
    # Start from water cells at the map edge (adjacent to out-of-bounds ocean)
    frontier: list[Point] = []
    for y in range(height):
        for x in range(width):
            if grid[y][x] not in WATER_CHARS:
                continue
            at_edge = x == 0 or x == width - 1 or y == 0 or y == height - 1
            if at_edge:
                ocean_connected.add((x, y))
                frontier.append((x, y))
    # BFS: expand to all water reachable via NESW
    while frontier:
        x, y = frontier.pop()
        for nx, ny in neighbors4(x, y, width, height):
            if (nx, ny) in ocean_connected:
                continue
            if grid[ny][nx] not in WATER_CHARS:
                continue
            ocean_connected.add((nx, ny))
            frontier.append((nx, ny))
    return ocean_connected


# Join and POI chars: never place on shoreline (B/L/R)
POI_SHORELINE_EXCLUDE = frozenset({SPAWN_CHAR, JOIN_CHAR, MINE_CHAR, SHOP_CHAR, CREEP_CHAR, DEAD_END_CHAR, SECRET_NPC_CHAR})


def continent_shoreline_cells(
    grid: list[list[str]],
    width: int,
    height: int,
    water_border_width: int = 0,
    ocean_connected: set[Point] | None = None,
    exclude: set[Point] | None = None,
) -> set[Point]:
    """Grass adjacent to ocean (map edge or water connected to ocean via NESW). Sets B."""
    exclude = exclude or set()
    out: set[Point] = set()
    for y in range(height):
        for x in range(width):
            if grid[y][x] != GRASS_CHAR or (x, y) in exclude:
                continue
            # Adjacent to map edge (out-of-bounds ocean)
            if (
                _is_border_water(x - 1, y, width, height, water_border_width)
                or _is_border_water(x + 1, y, width, height, water_border_width)
                or _is_border_water(x, y - 1, width, height, water_border_width)
                or _is_border_water(x, y + 1, width, height, water_border_width)
            ):
                out.add((x, y))
                continue
            # Adjacent to ocean-connected water (water that reaches the ocean)
            if ocean_connected:
                for nx, ny in [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]:
                    if 0 <= nx < width and 0 <= ny < height and (nx, ny) in ocean_connected:
                        out.add((x, y))
                        break
    return out


def lake_shoreline_cells(
    grid: list[list[str]],
    width: int,
    height: int,
    exclude: set[Point],
    ocean_connected: set[Point],
) -> set[Point]:
    """Grass adjacent to inland water (lakes: water NOT connected to ocean). Sets L."""
    out: set[Point] = set()
    for y in range(height):
        for x in range(width):
            if grid[y][x] != GRASS_CHAR or (x, y) in exclude:
                continue
            for nx, ny in [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]:
                if 0 <= nx < width and 0 <= ny < height and grid[ny][nx] in WATER_CHARS:
                    if (nx, ny) not in ocean_connected:  # Inland water only
                        out.add((x, y))
                        break
    return out


LAND_CHARS = frozenset({GRASS_CHAR, "."})
SHORELINE_CHARS = frozenset({SHORELINE_CHAR, LAKE_SHORELINE_CHAR, RIVER_CHAR})


def mark_deep_water(
    grid: list[list[str]],
    width: int,
    height: int,
    ocean_connected: set[Point] | None = None,
) -> None:
    """Convert LAKE water cells (not ocean) with 4 water neighbors to deep water (`).
    Deep water must have min 1-tile shallow border: demote any ` adjacent to land to ~."""
    if ocean_connected is None:
        ocean_connected = set()
    for y in range(height):
        for x in range(width):
            if grid[y][x] != WATER_CHAR:
                continue
            if (x, y) in ocean_connected:
                continue
            n_water = sum(
                1
                for nx, ny in [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]
                if 0 <= nx < width and 0 <= ny < height and grid[ny][nx] in WATER_CHARS
            )
            if n_water == 4:
                grid[y][x] = DEEP_WATER_CHAR
    # Ensure min 1-tile shallow border: demote deep water adjacent to land or shoreline
    non_water_chars = LAND_CHARS | SHORELINE_CHARS
    changed = True
    while changed:
        changed = False
        for y in range(height):
            for x in range(width):
                if grid[y][x] != DEEP_WATER_CHAR:
                    continue
                for nx, ny in [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]:
                    if 0 <= nx < width and 0 <= ny < height:
                        if grid[ny][nx] in non_water_chars:
                            grid[y][x] = WATER_CHAR
                            changed = True
                            break


def river_water_cells(grid: list[list[str]], width: int, height: int) -> set[Point]:
    """Water cells that form narrow channels (2 opposite water neighbors)."""
    out: set[Point] = set()
    for y in range(height):
        for x in range(width):
            if grid[y][x] not in WATER_CHARS:
                continue
            n = sum(1 for nx, ny in [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]
                    if 0 <= nx < width and 0 <= ny < height and grid[ny][nx] in WATER_CHARS)
            if n != 2:
                continue
            # Check opposite: N-S or E-W
            has_n = y > 0 and grid[y - 1][x] in WATER_CHARS
            has_s = y < height - 1 and grid[y + 1][x] in WATER_CHARS
            has_w = x > 0 and grid[y][x - 1] in WATER_CHARS
            has_e = x < width - 1 and grid[y][x + 1] in WATER_CHARS
            if (has_n and has_s) or (has_w and has_e):
                out.add((x, y))
    return out


def river_bank_cells(
    grid: list[list[str]],
    width: int,
    height: int,
    river_cells: set[Point],
    exclude: set[Point],
    ocean_connected: set[Point],
) -> set[Point]:
    """Grass adjacent to river water that does NOT connect to ocean. Sets R. Rivers with ocean outlet use B."""
    out: set[Point] = set()
    for x, y in river_cells:
        if (x, y) in ocean_connected:
            continue  # River connects to ocean; banks handled by continent_shore
        for nx, ny in [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]:
            if 0 <= nx < width and 0 <= ny < height and grid[ny][nx] == GRASS_CHAR and (nx, ny) not in exclude:
                out.add((nx, ny))
    return out


def _is_ocean_border_cell(px: int, py: int, width: int, height: int, border: int) -> bool:
    """True if (px,py) is in the outer border (ocean 2-tile band)."""
    return (
        px < border or px >= width - border or py < border or py >= height - border
    )


# Land terrains that must become B when adjacent to ocean (no trees/dirt on shoreline)
OCEAN_SHORE_CONVERTIBLE = frozenset({
    GRASS_CHAR, LAKE_SHORELINE_CHAR, RIVER_CHAR,
    TREE_CHAR, FOREST_CHAR, PATH_CHAR, HILL_CHAR,
})


def continent_shoreline_after_wrap(
    grid: list[list[str]],
    water_border_width: int,
) -> None:
    """Per terrain rules: mark any land adjacent to ocean water as B. Mutates grid.
    Uses ocean-connected flood fill so shorelines encompass inlets and bays."""
    if water_border_width <= 0:
        return
    height = len(grid)
    width = max(len(row) for row in grid) if grid else 0
    # Ocean-connected: all water reachable from map edge (includes bay/inlet water)
    ocean_connected: set[Point] = set()
    frontier: list[Point] = []
    for y in range(height):
        for x in range(width):
            if grid[y][x] not in WATER_CHARS:
                continue
            if x == 0 or x == width - 1 or y == 0 or y == height - 1:
                ocean_connected.add((x, y))
                frontier.append((x, y))
    while frontier:
        x, y = frontier.pop()
        for nx, ny in neighbors4(x, y, width, height):
            if (nx, ny) in ocean_connected:
                continue
            if grid[ny][nx] not in WATER_CHARS:
                continue
            ocean_connected.add((nx, ny))
            frontier.append((nx, ny))
    # Any land adjacent to ocean-connected water -> B
    for y in range(height):
        for x in range(width):
            if grid[y][x] not in OCEAN_SHORE_CONVERTIBLE or grid[y][x] in POI_SHORELINE_EXCLUDE:
                continue
            for nx, ny in [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]:
                if 0 <= nx < width and 0 <= ny < height and (nx, ny) in ocean_connected:
                    grid[y][x] = SHORELINE_CHAR
                    break


def thin_2x2_shoreline_in_grid(
    grid: list[list[str]],
    width: int,
    height: int,
    shore_chars: frozenset[str] | None = None,
) -> None:
    """Enforce 1-tile-wide shoreline: break 2x2 blocks. Mutates grid.
    Prefer demoting cells not adjacent to water; else demote most interior."""
    shore_chars = shore_chars or frozenset({SHORELINE_CHAR, LAKE_SHORELINE_CHAR})
    while True:
        blocks: list[frozenset[Point]] = []
        for y in range(height - 1):
            for x in range(width - 1):
                quad = frozenset({(x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)})
                if all(grid[py][px] in shore_chars for px, py in quad):
                    blocks.append(quad)
        if not blocks:
            break
        demote_this_round: set[Point] = set()
        for quad in blocks:
            candidates = [(px, py) for px, py in quad if (px, py) not in demote_this_round]
            if not candidates:
                continue

            def _score(p: Point) -> tuple[bool, int]:
                px, py = p
                has_water = any(
                    grid[ny][nx] in WATER_CHARS
                    for nx, ny in neighbors4(px, py, width, height)
                    if 0 <= nx < width and 0 <= ny < height
                )
                n_shore = sum(
                    1
                    for nx, ny in neighbors4(px, py, width, height)
                    if 0 <= nx < width and 0 <= ny < height
                    and grid[ny][nx] in shore_chars
                    and (nx, ny) not in demote_this_round
                )
                return (has_water, -n_shore)

            best = min(candidates, key=_score)
            demote_this_round.add(best)
        for x, y in demote_this_round:
            if grid[y][x] not in POI_SHORELINE_EXCLUDE:
                grid[y][x] = GRASS_CHAR
        if not demote_this_round:
            break


def demote_shoreline_without_ocean_neighbor(
    grid: list[list[str]],
    width: int,
    height: int,
    border: int = 2,
) -> None:
    """If a B (continent beach) tile has no ocean-connected water in its NESW neighborhood, convert to grass."""
    if border <= 0:
        return
    # Ocean-connected: all water reachable from map edge (matches continent_shoreline_after_wrap)
    ocean_connected: set[Point] = set()
    frontier: list[Point] = []
    for y in range(height):
        for x in range(width):
            if grid[y][x] not in WATER_CHARS:
                continue
            if x == 0 or x == width - 1 or y == 0 or y == height - 1:
                ocean_connected.add((x, y))
                frontier.append((x, y))
    while frontier:
        x, y = frontier.pop()
        for nx, ny in neighbors4(x, y, width, height):
            if (nx, ny) in ocean_connected:
                continue
            if grid[ny][nx] not in WATER_CHARS:
                continue
            ocean_connected.add((nx, ny))
            frontier.append((nx, ny))
    for y in range(height):
        for x in range(width):
            if grid[y][x] != SHORELINE_CHAR:
                continue
            has_ocean = any(
                (nx, ny) in ocean_connected
                for nx, ny in [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]
            )
            if not has_ocean:
                grid[y][x] = GRASS_CHAR


def fill_diagonal_only_shore_connectors(
    grid: list[list[str]],
    width: int,
    height: int,
) -> None:
    """Promote land to B/L when a shore tile has water NESW but no shore NESW (diagonal-only).
    Creates 4-connectivity while keeping 1-tile perimeter. Mutates grid."""
    ocean_connected: set[Point] = set()
    frontier: list[Point] = []
    for y in range(height):
        for x in range(width):
            if grid[y][x] not in WATER_CHARS:
                continue
            if x == 0 or x == width - 1 or y == 0 or y == height - 1:
                ocean_connected.add((x, y))
                frontier.append((x, y))
    while frontier:
        x, y = frontier.pop()
        for nx, ny in neighbors4(x, y, width, height):
            if (nx, ny) in ocean_connected:
                continue
            if grid[ny][nx] not in WATER_CHARS:
                continue
            ocean_connected.add((nx, ny))
            frontier.append((nx, ny))

    shore_chars = frozenset({SHORELINE_CHAR, LAKE_SHORELINE_CHAR})

    def _has_shore_nesw(px: int, py: int) -> bool:
        for dx, dy in [(0, -1), (1, 0), (0, 1), (-1, 0)]:
            nx, ny = px + dx, py + dy
            if 0 <= nx < width and 0 <= ny < height and grid[ny][nx] in shore_chars:
                return True
        return False

    def _has_ocean_nesw(px: int, py: int) -> bool:
        for dx, dy in [(0, -1), (1, 0), (0, 1), (-1, 0)]:
            nx, ny = px + dx, py + dy
            if 0 <= nx < width and 0 <= ny < height and (nx, ny) in ocean_connected:
                return True
        return False

    def _has_lake_nesw(px: int, py: int) -> bool:
        for dx, dy in [(0, -1), (1, 0), (0, 1), (-1, 0)]:
            nx, ny = px + dx, py + dy
            if 0 <= nx < width and 0 <= ny < height:
                if grid[ny][nx] in WATER_CHARS and (nx, ny) not in ocean_connected:
                    return True
        return False

    for _ in range(3):
        added = 0
        for y in range(height):
            for x in range(width):
                if grid[y][x] not in shore_chars:
                    continue
                has_water = _has_ocean_nesw(x, y) or _has_lake_nesw(x, y)
                if not has_water or _has_shore_nesw(x, y):
                    continue
                # Diagonal-only: has water NESW but no shore NESW
                candidates: list[tuple[int, int, int]] = []
                for dx, dy in [(0, -1), (1, 0), (0, 1), (-1, 0)]:
                    nx, ny = x + dx, y + dy
                    if not (0 <= nx < width and 0 <= ny < height):
                        continue
                    if grid[ny][nx] in shore_chars or grid[ny][nx] in POI_SHORELINE_EXCLUDE:
                        continue
                    if grid[ny][nx] not in OCEAN_SHORE_CONVERTIBLE:
                        continue
                    n_water = sum(
                        1
                        for ddx, ddy in [(0, -1), (1, 0), (0, 1), (-1, 0)]
                        if 0 <= nx + ddx < width and 0 <= ny + ddy < height
                        and grid[ny + ddy][nx + ddx] in WATER_CHARS
                    )
                    candidates.append((n_water, nx, ny))
                if not candidates:
                    continue
                _, bx, by = max(candidates, key=lambda t: (t[0], -abs(t[1] - x) - abs(t[2] - y)))
                shore_char = SHORELINE_CHAR if grid[y][x] == SHORELINE_CHAR else LAKE_SHORELINE_CHAR
                if grid[by][bx] not in POI_SHORELINE_EXCLUDE:
                    grid[by][bx] = shore_char
                    added += 1
        if added == 0:
            break
        thin_2x2_shoreline_in_grid(grid, width, height)


def demote_lake_shore_without_lake_neighbor(
    grid: list[list[str]],
    width: int,
    height: int,
) -> None:
    """If an L (lake shoreline) tile has no lake water in its NESW neighborhood, convert to grass."""
    ocean_connected: set[Point] = set()
    frontier: list[Point] = []
    for y in range(height):
        for x in range(width):
            if grid[y][x] not in WATER_CHARS:
                continue
            if x == 0 or x == width - 1 or y == 0 or y == height - 1:
                ocean_connected.add((x, y))
                frontier.append((x, y))
    while frontier:
        x, y = frontier.pop()
        for nx, ny in neighbors4(x, y, width, height):
            if (nx, ny) in ocean_connected:
                continue
            if grid[ny][nx] not in WATER_CHARS:
                continue
            ocean_connected.add((nx, ny))
            frontier.append((nx, ny))
    for y in range(height):
        for x in range(width):
            if grid[y][x] != LAKE_SHORELINE_CHAR:
                continue
            has_lake = any(
                0 <= nx < width and 0 <= ny < height
                and grid[ny][nx] in WATER_CHARS
                and (nx, ny) not in ocean_connected
                for nx, ny in [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]
            )
            if not has_lake:
                grid[y][x] = GRASS_CHAR


def relocate_pois_from_ocean_shore(
    grid: list[list[str]],
    width: int,
    height: int,
    border: int = 2,
) -> None:
    """Move POIs (J,S,M,H,C,D,N) off ocean shoreline. Mutates grid."""
    if border <= 0:
        return
    # Ocean-connected: all water reachable from map edge (includes bays/inlets)
    ocean_connected: set[Point] = set()
    frontier: deque[Point] = deque()
    for y in range(height):
        for x in range(width):
            if grid[y][x] not in WATER_CHARS:
                continue
            if x == 0 or x == width - 1 or y == 0 or y == height - 1:
                ocean_connected.add((x, y))
                frontier.append((x, y))
    while frontier:
        x, y = frontier.popleft()
        for nx, ny in neighbors4(x, y, width, height):
            if (nx, ny) in ocean_connected:
                continue
            if grid[ny][nx] not in WATER_CHARS:
                continue
            ocean_connected.add((nx, ny))
            frontier.append((nx, ny))

    inland_chars = {GRASS_CHAR, HILL_CHAR, TREE_CHAR, FOREST_CHAR, PATH_CHAR, "."}
    max_bfs_steps = width * height  # Safety limit

    def cell_has_ocean_neighbor(cx: int, cy: int) -> bool:
        return any((nx, ny) in ocean_connected for nx, ny in neighbors4(cx, cy, width, height))

    def find_inland_neighbor(px: int, py: int) -> Point | None:
        """BFS for nearest inland cell not adjacent to ocean."""
        seen: set[Point] = {(px, py)}
        queue: deque[Point] = deque(neighbors4(px, py, width, height))
        steps = 0
        while queue and steps < max_bfs_steps:
            steps += 1
            cx, cy = queue.popleft()
            if (cx, cy) in seen:
                continue
            seen.add((cx, cy))
            c = grid[cy][cx]
            if c in inland_chars and not cell_has_ocean_neighbor(cx, cy):
                return (cx, cy)
            if c in WATER_CHARS or c in POI_SHORELINE_EXCLUDE:
                continue
            for n in neighbors4(cx, cy, width, height):
                if n not in seen:
                    seen.add(n)
                    queue.append(n)
        return None

    to_relocate: list[tuple[int, int, str]] = []
    for y in range(height):
        for x in range(width):
            ch = grid[y][x]
            if ch not in POI_SHORELINE_EXCLUDE:
                continue
            if any((nx, ny) in ocean_connected for nx, ny in neighbors4(x, y, width, height)):
                to_relocate.append((x, y, ch))

    def fallback_step_inward(px: int, py: int) -> Point | None:
        """When BFS finds nothing, move to neighbor with strictly fewer ocean neighbors (step inward only)."""
        n_ocean_here = sum(
            1 for nnx, nny in neighbors4(px, py, width, height)
            if (nnx, nny) in ocean_connected
        )
        best: Point | None = None
        best_n = 999
        for nx, ny in neighbors4(px, py, width, height):
            if grid[ny][nx] in WATER_CHARS or grid[ny][nx] in POI_SHORELINE_EXCLUDE:
                continue
            n_ocean = sum(
                1 for nnx, nny in neighbors4(nx, ny, width, height)
                if (nnx, nny) in ocean_connected
            )
            if n_ocean < n_ocean_here and n_ocean < best_n:
                best_n = n_ocean
                best = (nx, ny)
        return best

    for x, y, ch in to_relocate:
        best = find_inland_neighbor(x, y)
        if best is None:
            best = fallback_step_inward(x, y)
        if best is not None:
            grid[y][x] = SHORELINE_CHAR
            grid[best[1]][best[0]] = ch

    # Repeat until no POI is adjacent to ocean (handles corners, narrow peninsulas)
    for _ in range(60):  # Max iterations to prevent runaway
        again = False
        for y in range(height):
            for x in range(width):
                ch = grid[y][x]
                if ch not in POI_SHORELINE_EXCLUDE:
                    continue
                has_ocean = any(
                    (nx, ny) in ocean_connected for nx, ny in neighbors4(x, y, width, height)
                )
                if not has_ocean:
                    continue
                best = find_inland_neighbor(x, y)
                if best is None:
                    best = fallback_step_inward(x, y)
                if best is not None:
                    grid[y][x] = SHORELINE_CHAR
                    grid[best[1]][best[0]] = ch
                    again = True
                    break
        if not again:
            break


def shoreline_cells(
    grid: list[list[str]],
    width: int,
    height: int,
    water_border_width: int = 0,
    ocean_connected: set[Point] | None = None,
) -> set[Point]:
    """All grass adjacent to water (continent + lake). For vegetation_blocked."""
    if ocean_connected is None:
        ocean_connected = ocean_connected_water_cells(grid, width, height, water_border_width)
    continent = continent_shoreline_cells(
        grid, width, height, water_border_width, ocean_connected
    )
    lake = lake_shoreline_cells(grid, width, height, continent, ocean_connected)
    return continent | lake


def manhattan(a: Point, b: Point) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def square_cells(center: Point, half: int, width: int, height: int) -> set[Point]:
    cx, cy = center
    out: set[Point] = set()
    for y in range(cy - half, cy + half + 1):
        for x in range(cx - half, cx + half + 1):
            if 0 <= x < width and 0 <= y < height:
                out.add((x, y))
    return out


def dilate_cells(cells: set[Point], radius: int, width: int, height: int) -> set[Point]:
    if radius <= 0:
        return set(cells)
    out: set[Point] = set()
    for cx, cy in cells:
        for y in range(cy - radius, cy + radius + 1):
            if y < 0 or y >= height:
                continue
            for x in range(cx - radius, cx + radius + 1):
                if x < 0 or x >= width:
                    continue
                out.add((x, y))
    return out


def place_spawn_points(
    width: int, height: int, spawn_count: int, clearing_size: int, rng: random.Random
) -> list[Point]:
    if spawn_count <= 0:
        raise ValueError("--spawn-count must be > 0")
    if clearing_size <= 0 or clearing_size % 2 == 0:
        raise ValueError("--spawn-clearing-size must be a positive odd integer.")
    if width < clearing_size or height < clearing_size:
        raise ValueError(
            f"Map {width}x{height} is too small for clearing size {clearing_size}."
        )

    half = clearing_size // 2
    candidates = [
        (x, y)
        for y in range(half, height - half)
        for x in range(half, width - half)
    ]
    rng.shuffle(candidates)

    spawn_points: list[Point] = []
    for candidate in candidates:
        overlap = False
        for existing in spawn_points:
            if (
                abs(candidate[0] - existing[0]) <= clearing_size
                and abs(candidate[1] - existing[1]) <= clearing_size
            ):
                overlap = True
                break
        if overlap:
            continue
        spawn_points.append(candidate)
        if len(spawn_points) == spawn_count:
            return spawn_points

    raise ValueError(
        f"Could not place {spawn_count} spawn points with {clearing_size}x{clearing_size} clearings. "
        "Increase canvas size or reduce spawn count/clearing size."
    )


def build_clearing_cells(
    spawn_points: list[Point], clearing_size: int, width: int, height: int
) -> set[Point]:
    half = clearing_size // 2
    cells: set[Point] = set()
    for point in spawn_points:
        cells.update(square_cells(point, half, width, height))
    return cells


def place_join_points(
    width: int, height: int, join_count: int, forbidden: set[Point], rng: random.Random
) -> list[Point]:
    if join_count <= 0:
        return []

    candidates = [point for point in all_positions(width, height) if point not in forbidden]
    if len(candidates) < join_count:
        raise ValueError(
            f"Not enough space for {join_count} join points after spawn clearings."
        )

    selected: list[Point] = [rng.choice(candidates)]
    remaining = set(candidates)
    remaining.remove(selected[0])

    while len(selected) < join_count:
        best_point: Point | None = None
        best_score = -1
        for point in remaining:
            score = min(manhattan(point, chosen) for chosen in selected)
            if score > best_score:
                best_score = score
                best_point = point
        if best_point is None:
            break
        selected.append(best_point)
        remaining.remove(best_point)

    if len(selected) < join_count:
        raise ValueError(f"Could not place all {join_count} join points.")
    return selected


def build_mst(points: list[Point]) -> list[tuple[Point, Point]]:
    if len(points) < 2:
        return []

    visited = {0}
    edges: list[tuple[Point, Point]] = []
    while len(visited) < len(points):
        best: tuple[int, int, int] | None = None
        for i in visited:
            for j in range(len(points)):
                if j in visited:
                    continue
                dist = manhattan(points[i], points[j])
                if best is None or dist < best[0]:
                    best = (dist, i, j)
        if best is None:
            break
        _, i, j = best
        visited.add(j)
        edges.append((points[i], points[j]))
    return edges


def spawn_anchor_outside_clearing(
    spawn: Point,
    target: Point,
    clearing_half: int,
    path_radius: int,
    width: int,
    height: int,
) -> Point:
    sx, sy = spawn
    tx, ty = target
    dx = tx - sx
    dy = ty - sy
    offset = clearing_half + path_radius + 1

    if abs(dx) >= abs(dy):
        step = sign(dx) or 1
        anchor = (sx + step * offset, sy)
    else:
        step = sign(dy) or 1
        anchor = (sx, sy + step * offset)

    return (
        clamp(anchor[0], 0, width - 1),
        clamp(anchor[1], 0, height - 1),
    )


def fade(t: float) -> float:
    return t * t * t * (t * (t * 6 - 15) + 10)


def lerp(a: float, b: float, t: float) -> float:
    return a + t * (b - a)


def hash01(ix: int, iy: int, seed: int) -> float:
    n = ix * 374761393 + iy * 668265263 + seed * 700001
    n = (n ^ (n >> 13)) * 1274126177
    n = n ^ (n >> 16)
    return (n & 0xFFFFFFFF) / 0xFFFFFFFF


def value_noise_2d(x: float, y: float, seed: int) -> float:
    x0 = int(x // 1)
    y0 = int(y // 1)
    x1 = x0 + 1
    y1 = y0 + 1
    sx = fade(x - x0)
    sy = fade(y - y0)
    n00 = hash01(x0, y0, seed)
    n10 = hash01(x1, y0, seed)
    n01 = hash01(x0, y1, seed)
    n11 = hash01(x1, y1, seed)
    nx0 = lerp(n00, n10, sx)
    nx1 = lerp(n01, n11, sx)
    return lerp(nx0, nx1, sy)


def perlin_like(x: float, y: float, seed: int) -> float:
    total = 0.0
    amplitude = 1.0
    frequency = 1.0
    norm = 0.0
    for octave in range(3):
        total += amplitude * value_noise_2d(x * frequency, y * frequency, seed + octave * 9973)
        norm += amplitude
        amplitude *= 0.5
        frequency *= 2.0
    return total / norm if norm > 0 else 0.5


def generate_heightmap(
    width: int,
    height: int,
    seed: int,
    scale: float = 12.0,
) -> list[list[float]]:
    """Generate a 0..1 heightmap using Perlin-like noise. Used for hills and shoreline depth."""
    scale = max(scale, 1.0)
    out: list[list[float]] = []
    for y in range(height):
        row: list[float] = []
        for x in range(width):
            v = perlin_like(x / scale, y / scale, seed)
            row.append(max(0.0, min(1.0, v)))
        out.append(row)
    return out


def expand_shoreline_by_height(
    shore_cells: set[Point],
    heightmap: list[list[float]],
    grid: list[list[str]],
    width: int,
    height: int,
    beach_height_max: float,
    max_depth: int = 0,
    exclude: set[Point] | None = None,
) -> set[Point]:
    """Expand shoreline inward where land height is low. max_depth=0: only 1 tile (no expansion)."""
    exclude = exclude or set()
    expanded = set(shore_cells)
    frontier = list(shore_cells)
    depth = 0
    while depth < max_depth and frontier:
        next_frontier: list[Point] = []
        for x, y in frontier:
            for nx, ny in neighbors4(x, y, width, height):
                if (nx, ny) in expanded or (nx, ny) in exclude:
                    continue
                if grid[ny][nx] != GRASS_CHAR:
                    continue
                h = heightmap[ny][nx]
                if h > beach_height_max:
                    continue
                expanded.add((nx, ny))
                next_frontier.append((nx, ny))
        frontier = next_frontier
        depth += 1
    return expanded


def fallback_l_path(start: Point, end: Point) -> list[Point]:
    x, y = start
    tx, ty = end
    out = [(x, y)]
    while x != tx:
        x += sign(tx - x)
        out.append((x, y))
    while y != ty:
        y += sign(ty - y)
        out.append((x, y))
    return out


def find_perlin_path(
    start: Point,
    end: Point,
    width: int,
    height: int,
    forbidden: set[Point],
    seed: int,
    scale: float,
    weight: float,
) -> list[Point]:
    if start == end:
        return [start]

    scale = max(scale, 1.0)
    open_heap: list[tuple[float, Point]] = []
    heapq.heappush(open_heap, (0.0, start))
    came_from: dict[Point, Point] = {}
    g_score: dict[Point, float] = {start: 0.0}

    while open_heap:
        _, current = heapq.heappop(open_heap)
        if current == end:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()
            return path

        cx, cy = current
        for nx, ny in neighbors4(cx, cy, width, height):
            neighbor = (nx, ny)
            if neighbor in forbidden and neighbor not in (start, end):
                continue
            noise = perlin_like(nx / scale, ny / scale, seed)
            step_cost = 1.0 + (1.0 - noise) * max(weight, 0.0)
            tentative = g_score[current] + step_cost
            if tentative >= g_score.get(neighbor, float("inf")):
                continue
            came_from[neighbor] = current
            g_score[neighbor] = tentative
            heuristic = manhattan(neighbor, end)
            heapq.heappush(open_heap, (tentative + heuristic, neighbor))

    return fallback_l_path(start, end)


def carve_path(
    grid: list[list[str]],
    route: list[Point],
    path_width: int,
    path_cells: set[Point],
    forbidden: set[Point],
) -> None:
    height = len(grid)
    width = len(grid[0])
    radius = path_width // 2
    for cx, cy in route:
        for y in range(cy - radius, cy + radius + 1):
            if y < 0 or y >= height:
                continue
            for x in range(cx - radius, cx + radius + 1):
                if x < 0 or x >= width:
                    continue
                cell = (x, y)
                if cell in forbidden:
                    continue
                if grid[y][x] in (SPAWN_CHAR, JOIN_CHAR):
                    continue
                grid[y][x] = PATH_CHAR
                path_cells.add(cell)


def route_is_valid(route: list[Point], forbidden: set[Point], blocked_paths: set[Point]) -> bool:
    if len(route) < 2:
        return False
    for cell in route:
        if cell in forbidden:
            return False
        if cell in blocked_paths:
            return False
    return True


def path_degree(cell: Point, path_cells: set[Point], width: int, height: int) -> int:
    x, y = cell
    return sum(1 for n in neighbors4(x, y, width, height) if n in path_cells)


def build_branch(
    grid: list[list[str]],
    path_cells: set[Point],
    base_forbidden: set[Point],
    rng: random.Random,
    seed: int,
    scale: float,
    weight: float,
    path_width: int,
    min_length: int,
    max_length: int,
    search_attempts: int,
) -> list[Point] | None:
    height = len(grid)
    width = len(grid[0])
    path_radius = path_width // 2

    connector_pool = [
        c for c in path_cells if path_degree(c, path_cells, width, height) <= 2
    ]
    if not connector_pool:
        connector_pool = list(path_cells)
    if not connector_pool:
        return None

    candidate_targets = [
        p
        for p in all_positions(width, height)
        if p not in base_forbidden and p not in path_cells and grid[p[1]][p[0]] == GRASS_CHAR
    ]
    if not candidate_targets:
        return None

    path_buffer = dilate_cells(path_cells, max(path_radius, 1), width, height)

    for attempt in range(search_attempts):
        connector = rng.choice(connector_pool)
        cx, cy = connector
        starts = [
            n
            for n in neighbors4(cx, cy, width, height)
            if n not in base_forbidden and n not in path_cells and grid[n[1]][n[0]] == GRASS_CHAR
        ]
        if not starts:
            continue
        start = rng.choice(starts)

        local_targets = [
            p
            for p in candidate_targets
            if min_length <= manhattan(p, connector) <= max_length
        ]
        if not local_targets:
            continue
        rng.shuffle(local_targets)
        local_targets = local_targets[: min(120, len(local_targets))]

        branch_forbidden = set(base_forbidden) | (path_buffer - {start})
        for target in local_targets:
            route = find_perlin_path(
                start,
                target,
                width,
                height,
                forbidden=branch_forbidden,
                seed=seed + attempt * 17,
                scale=scale,
                weight=weight,
            )
            if len(route) < min_length:
                continue
            if not route_is_valid(route, branch_forbidden, path_cells):
                continue
            return route

    return None


def place_clustered(
    grid: list[list[str]],
    fill_char: str,
    target_count: int,
    rng: random.Random,
    blocked: set[Point],
    eligible: set[Point] | None = None,
    *,
    maintain_connectivity: bool = False,
) -> int:
    """Place fill_char in clusters. When maintain_connectivity=True, fallback only adds
    cells NESW-adjacent to existing placements (perimeter stays connected)."""
    if target_count <= 0:
        return 0

    height = len(grid)
    width = len(grid[0])
    available = [
        (x, y)
        for x, y in all_positions(width, height)
        if grid[y][x] == GRASS_CHAR
        and (x, y) not in blocked
        and (eligible is None or (x, y) in eligible)
    ]
    if not available:
        return 0

    seed_count = max(1, min(len(available), target_count, int(target_count * 0.08) + 1))
    seeds = rng.sample(available, k=seed_count)
    frontier = list(seeds)

    placed = 0
    for x, y in seeds:
        if grid[y][x] == GRASS_CHAR and (x, y) not in blocked:
            grid[y][x] = fill_char
            placed += 1
            if placed >= target_count:
                return placed

    while placed < target_count and frontier:
        idx = rng.randrange(len(frontier))
        x, y = frontier[idx]
        expanded = False
        neighbors = neighbors4(x, y, width, height)
        rng.shuffle(neighbors)
        for nx, ny in neighbors:
            if grid[ny][nx] != GRASS_CHAR or (nx, ny) in blocked:
                continue
            if eligible is not None and (nx, ny) not in eligible:
                continue
            grid[ny][nx] = fill_char
            frontier.append((nx, ny))
            placed += 1
            expanded = True
            break
        if not expanded:
            frontier.pop(idx)

    if placed < target_count and maintain_connectivity:
        # Only add from cells NESW-adjacent to existing fill_char (keep perimeter connected)
        while placed < target_count:
            adjacent = []
            for x, y in all_positions(width, height):
                if grid[y][x] != fill_char:
                    continue
                for nx, ny in neighbors4(x, y, width, height):
                    if (
                        grid[ny][nx] == GRASS_CHAR
                        and (nx, ny) not in blocked
                        and (eligible is None or (nx, ny) in eligible)
                    ):
                        adjacent.append((nx, ny))
            if not adjacent:
                break
            rng.shuffle(adjacent)
            for x, y in adjacent:
                if placed >= target_count:
                    break
                if grid[y][x] == GRASS_CHAR:
                    grid[y][x] = fill_char
                    placed += 1

    elif placed < target_count:
        available = [
            (x, y)
            for x, y in all_positions(width, height)
            if grid[y][x] == GRASS_CHAR
            and (x, y) not in blocked
            and (eligible is None or (x, y) in eligible)
        ]
        rng.shuffle(available)
        for x, y in available[: target_count - placed]:
            grid[y][x] = fill_char
            placed += 1

    return placed


def fill_hill_interior(
    grid: list[list[str]],
    width: int,
    height: int,
) -> int:
    """Fill grass holes inside hill formations. G with 4 I neighbors -> I.
    Ensures solid hill blobs and a single connected perimeter. Returns cells filled."""
    filled = 0
    changed = True
    while changed:
        changed = False
        to_fill: list[Point] = []
        for y in range(height):
            for x in range(width):
                if grid[y][x] != GRASS_CHAR:
                    continue
                n_hill = sum(
                    1
                    for nx, ny in neighbors4(x, y, width, height)
                    if 0 <= nx < width and 0 <= ny < height and grid[ny][nx] == HILL_CHAR
                )
                if n_hill == 4:
                    to_fill.append((x, y))
        for x, y in to_fill:
            if grid[y][x] == GRASS_CHAR:
                grid[y][x] = HILL_CHAR
                filled += 1
                changed = True
    return filled


def pick_spread_points(candidates: list[Point], count: int, rng: random.Random) -> list[Point]:
    if count <= 0:
        return []
    if len(candidates) < count:
        raise ValueError(f"Not enough valid positions for count={count}.")

    selected: list[Point] = [rng.choice(candidates)]
    remaining = set(candidates)
    remaining.remove(selected[0])

    while len(selected) < count:
        best: Point | None = None
        best_score = -1
        for point in remaining:
            score = min(manhattan(point, chosen) for chosen in selected)
            if score > best_score:
                best_score = score
                best = point
        if best is None:
            break
        selected.append(best)
        remaining.remove(best)

    if len(selected) < count:
        raise ValueError(f"Could not place all {count} spread points.")
    return selected


def place_access_pois(
    grid: list[list[str]],
    path_cells: set[Point],
    blocked: set[Point],
    count: int,
    marker: str,
    label: str,
    rng: random.Random,
) -> list[Point]:
    if count <= 0:
        return []

    height = len(grid)
    width = len(grid[0])
    candidates: list[Point] = []
    for x, y in all_positions(width, height):
        if (x, y) in blocked:
            continue
        if grid[y][x] in WATER_CHARS:
            continue
        if grid[y][x] in SHORELINE_CHARS:
            continue
        if not any(n in path_cells for n in neighbors4(x, y, width, height)):
            continue
        candidates.append((x, y))

    actual_count = min(count, len(candidates))
    if actual_count < count:
        import sys
        print(
            f"Warning: Only {len(candidates)} accessible tiles for {label} (requested {count}). "
            f"Placing {actual_count}.",
            file=sys.stderr,
        )

    points = pick_spread_points(candidates, actual_count, rng)
    for x, y in points:
        grid[y][x] = marker
    return points


def place_creep_zones(
    grid: list[list[str]],
    count: int,
    radius: int,
    blocked: set[Point],
    rng: random.Random,
) -> tuple[list[Point], set[Point]]:
    if count <= 0:
        return [], set()
    if radius <= 0:
        raise ValueError("--creep-zone-radius must be > 0")

    height = len(grid)
    width = len(grid[0])
    candidates = [
        p
        for p in all_positions(width, height)
        if p not in blocked
        and grid[p[1]][p[0]] not in WATER_CHARS
        and grid[p[1]][p[0]] not in SHORELINE_CHARS
    ]
    if len(candidates) < count:
        raise ValueError(
            f"Not enough free cells for creep-zone-count={count}. "
            "Increase map size or reduce feature counts."
        )

    centers = pick_spread_points(candidates, count, rng)
    creep_cells: set[Point] = set()

    for cx, cy in centers:
        for y in range(cy - radius, cy + radius + 1):
            if y < 0 or y >= height:
                continue
            for x in range(cx - radius, cx + radius + 1):
                if x < 0 or x >= width:
                    continue
                if manhattan((cx, cy), (x, y)) > radius:
                    continue
                cell = (x, y)
                if cell in blocked:
                    continue
                if grid[y][x] in WATER_CHARS:
                    continue
                if grid[y][x] in SHORELINE_CHARS:
                    continue
                grid[y][x] = CREEP_CHAR
                creep_cells.add(cell)
    return centers, creep_cells


def resolve_aseprite_bin(explicit: str) -> Path:
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)

    env_candidate = os.getenv("ASEPRITE_BIN")
    if env_candidate:
        candidates.append(env_candidate)

    in_path = shutil.which("aseprite")
    if in_path:
        candidates.append(in_path)

    if MAC_ASEPRITE_BIN.exists():
        candidates.append(str(MAC_ASEPRITE_BIN))

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        path = Path(candidate).expanduser()
        if path.exists() and path.is_file():
            return path

    raise FileNotFoundError(
        "Aseprite binary not found. Set --aseprite-bin or ASEPRITE_BIN."
    )


def write_preview_bmp(path: Path, grid: list[list[str]], tile_size: int) -> None:
    if tile_size <= 0:
        raise ValueError("--preview-tile-size must be > 0")
    if not grid or not grid[0]:
        raise ValueError("Cannot preview empty grid.")

    tiles_h = len(grid)
    tiles_w = len(grid[0])
    img_w = tiles_w * tile_size
    img_h = tiles_h * tile_size
    row_bytes = img_w * 3
    padding = (4 - (row_bytes % 4)) % 4
    pixel_data_size = (row_bytes + padding) * img_h
    file_size = 14 + 40 + pixel_data_size

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.write(struct.pack("<2sIHHI", b"BM", file_size, 0, 0, 54))
        f.write(struct.pack("<IIIHHIIIIII", 40, img_w, img_h, 1, 24, 0, pixel_data_size, 2835, 2835, 0, 0))

        for py in range(img_h - 1, -1, -1):
            tile_y = py // tile_size
            row = bytearray()
            for px in range(img_w):
                tile_x = px // tile_size
                char = grid[tile_y][tile_x]
                r, g, b = PREVIEW_COLORS.get(char, (255, 0, 255))
                row.extend((b, g, r))
            if padding:
                row.extend(b"\x00" * padding)
            f.write(row)


# Per-layer character sets for layered preview (bottom to top)
_PREVIEW_LAYERS: list[tuple[str, frozenset[str]]] = [
    ("Water", frozenset({WATER_CHAR, DEEP_WATER_CHAR})),
    ("Grass", frozenset({GRASS_CHAR, "."})),
    ("Shoreline", frozenset({SHORELINE_CHAR})),
    ("Lake", frozenset({LAKE_SHORELINE_CHAR})),
    ("River", frozenset({RIVER_CHAR})),
    ("Hill", frozenset({HILL_CHAR})),
    ("Trees", frozenset({TREE_CHAR, FOREST_CHAR})),
    ("Dirt", frozenset({PATH_CHAR})),
    ("POI", frozenset({SPAWN_CHAR, JOIN_CHAR, MINE_CHAR, SHOP_CHAR, CREEP_CHAR, DEAD_END_CHAR, SECRET_NPC_CHAR})),
]


def write_preview_layered(
    path: Path,
    grid: list[list[str]],
    tile_size: int,
    aseprite_bin: str = "",
) -> None:
    """Write a layered .aseprite preview with terrain separated into layers."""
    from PIL import Image

    from tilemap_generator.paint_map_png import (
        HILL_INTERIOR_MASK,
        get_hill_adjacency_bitmask,
    )

    # Convert grid to list of strings for get_hill_adjacency_bitmask
    ascii_lines = ["".join(row) if isinstance(row, (list, tuple)) else row for row in grid]

    if tile_size <= 0:
        raise ValueError("--preview-tile-size must be > 0")
    if not grid or not grid[0]:
        raise ValueError("Cannot preview empty grid.")

    tiles_h = len(grid)
    tiles_w = len(grid[0])
    img_w = tiles_w * tile_size
    img_h = tiles_h * tile_size

    binary = resolve_aseprite_bin(aseprite_bin)
    lua_script = PROJECT_ROOT / "assets/lua/paint_preview_layered.lua"
    if not lua_script.exists():
        raise FileNotFoundError(f"Missing Lua script: {lua_script}")

    path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        layer_paths: dict[str, Path] = {}

        def _is_adjacent_to_water_or_shoreline(g: list[list[str]], px: int, py: int) -> bool:
            """True if (px,py) has a NESW neighbor that is water or shoreline (B/L/R)."""
            for nx, ny in neighbors4(px, py, tiles_w, tiles_h):
                c = g[ny][nx] if ny < len(g) and nx < len(g[ny]) else "."
                if c in WATER_CHARS or c in (SHORELINE_CHAR, LAKE_SHORELINE_CHAR, RIVER_CHAR):
                    return True
            return False

        for layer_name, chars in _PREVIEW_LAYERS:
            layer_img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
            for ty in range(tiles_h):
                for tx in range(tiles_w):
                    ch = grid[ty][tx] if ty < len(grid) and tx < len(grid[ty]) else "."
                    # Shoreline: also draw P adjacent to water/shoreline (path on beach → reserve for shoreline)
                    if layer_name == "Shoreline" and ch == PATH_CHAR and _is_adjacent_to_water_or_shoreline(grid, tx, ty):
                        r, g, b = PREVIEW_COLORS[SHORELINE_CHAR]
                    elif layer_name == "Hill" and ch == HILL_CHAR:
                        # Interior hill (all 4 neighbors hills): grass, not hill cliff
                        hmask = get_hill_adjacency_bitmask(ascii_lines, tx, ty)
                        if hmask == HILL_INTERIOR_MASK:
                            continue  # Don't draw on Hill layer; Grass will show through
                        r, g, b = PREVIEW_COLORS[HILL_CHAR]
                    elif layer_name == "Grass" and ch == HILL_CHAR:
                        # Interior hill: draw as grass
                        hmask = get_hill_adjacency_bitmask(ascii_lines, tx, ty)
                        if hmask == HILL_INTERIOR_MASK:
                            r, g, b = PREVIEW_COLORS[GRASS_CHAR]
                        else:
                            continue
                    elif ch not in chars:
                        continue
                    else:
                        # Dirt: skip path cells adjacent to water or shoreline (reserve for shoreline)
                        if layer_name == "Dirt" and _is_adjacent_to_water_or_shoreline(grid, tx, ty):
                            continue
                        r, g, b = PREVIEW_COLORS.get(ch, (255, 0, 255))
                    x0, y0 = tx * tile_size, ty * tile_size
                    for dy in range(tile_size):
                        for dx in range(tile_size):
                            layer_img.putpixel((x0 + dx, y0 + dy), (r, g, b, 255))

            png_path = tmp_path / f"{layer_name.lower()}.png"
            layer_img.save(png_path)
            layer_paths[layer_name] = png_path

        env = os.environ.copy()
        env["OUT"] = str(path.resolve())
        env["WIDTH"] = str(img_w)
        env["HEIGHT"] = str(img_h)
        for layer_name, png_path in layer_paths.items():
            env[f"{layer_name.upper()}_PNG"] = str(png_path)

        subprocess.run(
            [str(binary), "-b", "--script", str(lua_script)],
            env=env,
            check=True,
        )


def open_in_aseprite(path: Path, aseprite_bin: str) -> None:
    """Launch Aseprite with the given path. Runs in background so the CLI prompt appears immediately."""
    binary = resolve_aseprite_bin(aseprite_bin)
    subprocess.Popen(
        [str(binary), str(path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def mark_ocean_deep_water(grid: list[list[str]], width: int, height: int) -> None:
    """Apply lake-style deep water logic to ocean: interior ocean (4 water neighbors) -> deep.
    Min 1-tile shallow border next to land/shoreline. Mutates grid in place."""
    ocean_connected: set[Point] = set()
    frontier: list[Point] = []
    for y in range(height):
        for x in range(width):
            if grid[y][x] not in WATER_CHARS:
                continue
            if x == 0 or x == width - 1 or y == 0 or y == height - 1:
                ocean_connected.add((x, y))
                frontier.append((x, y))
    while frontier:
        x, y = frontier.pop()
        for nx, ny in neighbors4(x, y, width, height):
            if (nx, ny) in ocean_connected:
                continue
            if grid[ny][nx] not in WATER_CHARS:
                continue
            ocean_connected.add((nx, ny))
            frontier.append((nx, ny))

    for y in range(height):
        for x in range(width):
            if (x, y) not in ocean_connected or grid[y][x] != WATER_CHAR:
                continue
            n_water = sum(
                1
                for nx, ny in [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]
                if 0 <= nx < width and 0 <= ny < height and grid[ny][nx] in WATER_CHARS
            )
            if n_water == 4:
                grid[y][x] = DEEP_WATER_CHAR

    non_water_chars = LAND_CHARS | SHORELINE_CHARS
    changed = True
    while changed:
        changed = False
        for y in range(height):
            for x in range(width):
                if grid[y][x] != DEEP_WATER_CHAR:
                    continue
                for nx, ny in [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]:
                    if 0 <= nx < width and 0 <= ny < height:
                        if grid[ny][nx] in non_water_chars:
                            grid[y][x] = WATER_CHAR
                            changed = True
                            break


def wrap_with_water_border(grid: list[list[str]], border: int) -> list[list[str]]:
    """Wrap content grid with water border. Returns expanded grid.
    Ocean priority order: outermost perimeter = deep water (`), inner ring = shallow (~).
    Min 2 tiles wide. Land (B) touches shallow water only."""
    if border <= 0:
        return grid
    h = len(grid)
    w = len(grid[0]) if grid else 0
    out_w = w + 2 * border
    out_h = h + 2 * border
    out: list[list[str]] = []

    def ocean_cell(ox: int, oy: int) -> str:
        dist = min(ox, oy, out_w - 1 - ox, out_h - 1 - oy)
        return DEEP_WATER_CHAR if dist == 0 else WATER_CHAR

    for oy in range(out_h):
        row: list[str] = []
        for ox in range(out_w):
            if ox < border or ox >= out_w - border or oy < border or oy >= out_h - border:
                row.append(ocean_cell(ox, oy))
            else:
                row.append(grid[oy - border][ox - border])
        out.append(row)
    return out


def wrap_with_land_border(
    grid: list[list[str]],
    border: int,
    rng: random.Random,
    tree_fraction: float = 0.7,
) -> list[list[str]]:
    """Wrap content grid with land border (grass + trees). Returns expanded grid."""
    if border <= 0:
        return grid
    h = len(grid)
    w = len(grid[0]) if grid else 0
    out_w = w + 2 * border
    out_h = h + 2 * border
    out: list[list[str]] = []

    def border_cell() -> str:
        return FOREST_CHAR if rng.random() < tree_fraction else TREE_CHAR

    for _ in range(border):
        out.append([border_cell() for _ in range(out_w)])
    for row in grid:
        left = [border_cell() for _ in range(border)]
        right = [border_cell() for _ in range(border)]
        out.append(left + row + right)
    for _ in range(border):
        out.append([border_cell() for _ in range(out_w)])
    return out


def write_ascii(path: Path, grid: list[list[str]]) -> None:
    lines = ["".join(row) for row in grid]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_legend(path: Path, legend: dict[str, int] | None = None) -> None:
    from tilemap_generator.legend import DEFAULT_LEGEND

    if legend is None:
        legend = DEFAULT_LEGEND.copy()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(legend, indent=2) + "\n", encoding="utf-8")


def run_from_args(args: argparse.Namespace) -> None:
    if args.width <= 0 or args.height <= 0:
        raise ValueError("--width and --height must be positive integers.")

    # Apply terrain config rules: water_border_width from config when using terrain config
    terrain_config = getattr(args, "terrain_config", "") or ""
    tc_path: Path | None = None
    if terrain_config:
        tc_path = Path(terrain_config)
        if not tc_path.exists():
            for base in (PROJECT_ROOT / "examples", PROJECT_ROOT):
                candidate = base / tc_path
                if candidate.exists():
                    tc_path = candidate
                    break
    if not tc_path or not tc_path.exists():
        for candidate in (
            PROJECT_ROOT / "examples" / "terrain.bitmask.json",
            PROJECT_ROOT / "terrain.bitmask.json",
        ):
            if candidate.exists():
                tc_path = candidate
                break
    if tc_path and tc_path.exists():
        from tilemap_generator.paint_map_png import load_terrain_config

        terrain_cfg = load_terrain_config(tc_path, project_root=PROJECT_ROOT)
        if args.map_mode is None:
            cfg_map_mode = terrain_cfg.get("map_mode")
            args.map_mode = cfg_map_mode if cfg_map_mode in ("island", "continent") else "island"
        cfg_border = terrain_cfg.get("water_border_width")
        if cfg_border is not None and isinstance(cfg_border, (int, float)):
            args.water_border_width = max(0, int(cfg_border))
    if args.map_mode is None:
        args.map_mode = "island"
    if not args.hide_path and args.path_width_threshold <= 0:
        raise ValueError("--path-width-threshold must be > 0.")
    if args.preview_tile_size <= 0:
        raise ValueError("--preview-tile-size must be > 0.")
    if args.mine_count < 0 or args.shop_count < 0 or args.creep_zone_count < 0:
        raise ValueError("Mine/shop/creep counts must be non-negative.")
    if args.dead_end_count < 0:
        raise ValueError("--dead-end-count must be non-negative.")

    validate_density(args.tree_density, "--tree-density")
    validate_density(args.forest_density, "--forest-density")
    validate_density(args.water_density, "--water-density")
    validate_density(getattr(args, "hill_density", 0.0), "--hill-density")
    if args.tree_density + args.water_density > 1.0:
        raise ValueError("--tree-density + --water-density cannot exceed 1.0")

    rng = random.Random(args.seed)
    path_width = args.path_width_threshold
    if path_width % 2 == 0:
        path_width += 1
    path_radius = path_width // 2

    spawn_points = place_spawn_points(
        args.width, args.height, args.spawn_count, args.spawn_clearing_size, rng
    )
    clearing_half = args.spawn_clearing_size // 2
    clearing_cells = build_clearing_cells(
        spawn_points, args.spawn_clearing_size, args.width, args.height
    )

    join_count = args.join_point_count if args.join_point_count > 0 else max(2, args.spawn_count // 2)
    join_forbidden = set(clearing_cells)
    if getattr(args, "map_mode", "island") == "island":
        edge = 2
        for x in range(args.width):
            for y in range(args.height):
                if x < edge or x >= args.width - edge or y < edge or y >= args.height - edge:
                    join_forbidden.add((x, y))
    join_points = place_join_points(
        args.width, args.height, join_count, forbidden=join_forbidden, rng=rng
    )

    grid = [[GRASS_CHAR for _ in range(args.width)] for _ in range(args.height)]
    for x, y in join_points:
        grid[y][x] = JOIN_CHAR
    for x, y in spawn_points:
        grid[y][x] = SPAWN_CHAR

    # Order: water → shorelines → paths → hills → trees → dirt rule
    # (Paths must avoid water/shore so lakes aren't cut by dirt)
    protected_cells_pre = set(clearing_cells) | set(spawn_points) | set(join_points)
    terrain_blocked = protected_cells_pre
    total_tiles = args.width * args.height
    placeable = sum(
        1
        for x, y in all_positions(args.width, args.height)
        if grid[y][x] == GRASS_CHAR and (x, y) not in terrain_blocked
    )
    water_target = min(int(round(total_tiles * args.water_density)), placeable)
    water_placed = place_clustered(grid, WATER_CHAR, water_target, rng, terrain_blocked)

    erode_iterations = getattr(args, "shoreline_erode_iterations", 2)
    if erode_iterations > 0:
        erode_water_land_boundary(
            grid, args.width, args.height,
            protected=terrain_blocked,
            iterations=erode_iterations,
        )
    map_mode = getattr(args, "map_mode", "island")
    is_island = map_mode == "island"
    water_border = max(0, args.water_border_width) if is_island else 0
    ocean_connected = ocean_connected_water_cells(grid, args.width, args.height, water_border)
    mark_deep_water(grid, args.width, args.height, ocean_connected)

    heightmap = generate_heightmap(
        args.width, args.height,
        args.seed + 5555,
        getattr(args, "height_noise_scale", 12.0),
    )

    poi_protected = set(spawn_points) | set(join_points)
    continent_shore = continent_shoreline_cells(
        grid, args.width, args.height,
        water_border_width=water_border,
        ocean_connected=ocean_connected,
        exclude=poi_protected,
    )
    lake_shore = lake_shoreline_cells(
        grid, args.width, args.height,
        exclude=continent_shore | poi_protected,
        ocean_connected=ocean_connected,
    )
    river_cells = river_water_cells(grid, args.width, args.height)
    river_bank = river_bank_cells(
        grid, args.width, args.height, river_cells,
        exclude=continent_shore | lake_shore | poi_protected,
        ocean_connected=ocean_connected,
    )
    beach_height_max = getattr(args, "beach_height_max", 0.45)
    shoreline_expand_depth = getattr(args, "shoreline_expand_depth", 0)
    continent_shore = expand_shoreline_by_height(
        continent_shore, heightmap, grid, args.width, args.height, beach_height_max,
        max_depth=shoreline_expand_depth,
        exclude=poi_protected,
    )
    lake_shore = expand_shoreline_by_height(
        lake_shore, heightmap, grid, args.width, args.height, beach_height_max,
        max_depth=shoreline_expand_depth,
        exclude=poi_protected,
    )
    lake_shore = lake_shore - continent_shore
    river_bank = expand_shoreline_by_height(
        river_bank, heightmap, grid, args.width, args.height, beach_height_max,
        max_depth=shoreline_expand_depth,
        exclude=poi_protected,
    )
    river_bank = river_bank - continent_shore - lake_shore

    for x, y in continent_shore:
        if grid[y][x] not in POI_SHORELINE_EXCLUDE:
            grid[y][x] = SHORELINE_CHAR
    for x, y in lake_shore:
        if grid[y][x] not in POI_SHORELINE_EXCLUDE:
            grid[y][x] = LAKE_SHORELINE_CHAR
    for x, y in river_bank:
        if grid[y][x] not in POI_SHORELINE_EXCLUDE:
            grid[y][x] = RIVER_CHAR

    _land_chars = frozenset({GRASS_CHAR, "."})
    for _ in range(2):
        added_continent, added_lake = set(), set()
        for y in range(args.height):
            for x in range(args.width):
                if grid[y][x] not in _land_chars:
                    continue
                if (x, y) in poi_protected:
                    continue
                if (x, y) in continent_shore or (x, y) in lake_shore or (x, y) in river_bank:
                    continue
                for nx, ny in [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]:
                    if 0 <= nx < args.width and 0 <= ny < args.height and grid[ny][nx] in WATER_CHARS:
                        if (nx, ny) in ocean_connected:
                            added_continent.add((x, y))
                        else:
                            added_lake.add((x, y))
                        break
        for x, y in added_continent:
            continent_shore.add((x, y))
            if grid[y][x] not in POI_SHORELINE_EXCLUDE:
                grid[y][x] = SHORELINE_CHAR
        for x, y in added_lake:
            if (x, y) not in continent_shore:
                lake_shore.add((x, y))
                if grid[y][x] not in POI_SHORELINE_EXCLUDE:
                    grid[y][x] = LAKE_SHORELINE_CHAR
        if not added_continent and not added_lake:
            break

    # Fill diagonal shoreline gaps: promote G to B/L when it bridges two diagonally-adjacent shore cells
    # Ensures shoreline connects via NESW only (no diagonal-only links)
    def _shore_neighbors_diagonally_adjacent(px: int, py: int, shore_set: set[Point]) -> bool:
        """True if cell has 2+ shore neighbors that touch each other (form an inside corner)."""
        neighbors: list[tuple[int, int]] = []
        for dx, dy in [(0, -1), (1, 0), (0, 1), (-1, 0)]:
            nx, ny = px + dx, py + dy
            if 0 <= nx < args.width and 0 <= ny < args.height and (nx, ny) in shore_set:
                neighbors.append((nx, ny))
        if len(neighbors) < 2:
            return False
        for i, (ax, ay) in enumerate(neighbors):
            for (bx, by) in neighbors[i + 1 :]:
                if abs(ax - bx) == 1 and abs(ay - by) == 1:
                    return True
        return False

    for _ in range(4):  # Multiple passes to handle stepped coastlines
        continent_connectors: set[Point] = set()
        lake_connectors: set[Point] = set()
        for y in range(args.height):
            for x in range(args.width):
                if grid[y][x] not in _land_chars or (x, y) in poi_protected:
                    continue
                if (x, y) not in continent_shore and _shore_neighbors_diagonally_adjacent(x, y, continent_shore):
                    continent_connectors.add((x, y))
                elif (x, y) not in lake_shore and (x, y) not in continent_shore and _shore_neighbors_diagonally_adjacent(x, y, lake_shore):
                    lake_connectors.add((x, y))
        if not continent_connectors and not lake_connectors:
            break
        for x, y in continent_connectors:
            continent_shore.add((x, y))
            if grid[y][x] not in POI_SHORELINE_EXCLUDE:
                grid[y][x] = SHORELINE_CHAR
        for x, y in lake_connectors:
            if (x, y) not in continent_shore:
                lake_shore.add((x, y))
                if grid[y][x] not in POI_SHORELINE_EXCLUDE:
                    grid[y][x] = LAKE_SHORELINE_CHAR

    def _has_ocean_water_nesw(px: int, py: int) -> bool:
        for dx, dy in [(0, -1), (1, 0), (0, 1), (-1, 0)]:
            nx, ny = px + dx, py + dy
            if 0 <= nx < args.width and 0 <= ny < args.height:
                if grid[ny][nx] in WATER_CHARS and (nx, ny) in ocean_connected:
                    return True
        return False

    def _has_lake_water_nesw(px: int, py: int) -> bool:
        for dx, dy in [(0, -1), (1, 0), (0, 1), (-1, 0)]:
            nx, ny = px + dx, py + dy
            if 0 <= nx < args.width and 0 <= ny < args.height:
                if grid[ny][nx] in WATER_CHARS and (nx, ny) not in ocean_connected:
                    return True
        return False

    # Fill diagonal-only shore gaps (staircase): shore tiles with water NESW but no shore NESW
    # connect only diagonally. Promote a NESW land neighbor to create 4-connectivity.
    def _has_shore_nesw(px: int, py: int, shore_set: set[Point]) -> bool:
        for dx, dy in [(0, -1), (1, 0), (0, 1), (-1, 0)]:
            nx, ny = px + dx, py + dy
            if 0 <= nx < args.width and 0 <= ny < args.height and (nx, ny) in shore_set:
                return True
        return False

    def _promote_diagonal_only_connectors(
        shore_set: set[Point],
        has_water_nesw: Callable[[int, int], bool],
        shore_char: str,
        exclude: set[Point] | None = None,
    ) -> None:
        exclude = exclude or set()
        diagonal_only = [
            (x, y)
            for x, y in shore_set
            if has_water_nesw(x, y) and not _has_shore_nesw(x, y, shore_set)
        ]
        for x, y in diagonal_only:
            if (x, y) not in shore_set:
                continue
            candidates: list[tuple[int, int, int]] = []
            for dx, dy in [(0, -1), (1, 0), (0, 1), (-1, 0)]:
                nx, ny = x + dx, y + dy
                if not (0 <= nx < args.width and 0 <= ny < args.height):
                    continue
                if (nx, ny) in shore_set or (nx, ny) in exclude or (nx, ny) in poi_protected:
                    continue
                if grid[ny][nx] not in OCEAN_SHORE_CONVERTIBLE:
                    continue
                n_water = sum(
                    1
                    for ddx, ddy in [(0, -1), (1, 0), (0, 1), (-1, 0)]
                    if 0 <= nx + ddx < args.width and 0 <= ny + ddy < args.height
                    and grid[ny + ddy][nx + ddx] in WATER_CHARS
                )
                candidates.append((n_water, nx, ny))
            if not candidates:
                continue
            # Prefer neighbor adjacent to water (minimize perimeter width)
            _, bx, by = max(candidates, key=lambda t: (t[0], -abs(t[1] - x) - abs(t[2] - y)))
            shore_set.add((bx, by))
            if grid[by][bx] not in POI_SHORELINE_EXCLUDE:
                grid[by][bx] = shore_char

    for _ in range(3):
        added_c = continent_shore.copy()
        added_l = lake_shore.copy()
        _promote_diagonal_only_connectors(
            continent_shore, _has_ocean_water_nesw, SHORELINE_CHAR
        )
        _promote_diagonal_only_connectors(
            lake_shore, _has_lake_water_nesw, LAKE_SHORELINE_CHAR, exclude=continent_shore
        )
        if continent_shore == added_c and lake_shore == added_l:
            break

    # Continent shoreline (B): 1 tile border, NESW-connected (no diagonal-only links).
    # No grass, trees, hills, dirt on shoreline; path_forbidden, hill_blocked, vegetation_blocked enforce.
    # Keep only B adjacent to ocean water (NESW) or diagonal connectors; demote inland B.
    while True:
        thin_demote: set[Point] = set()
        for x, y in continent_shore:
            if (x, y) in poi_protected or grid[y][x] in POI_SHORELINE_EXCLUDE:
                continue
            if _has_ocean_water_nesw(x, y):
                continue  # Keep ocean-adjacent B
            if _shore_neighbors_diagonally_adjacent(x, y, continent_shore):
                continue  # Keep diagonal connectors for NESW connectivity
            thin_demote.add((x, y))
        if not thin_demote:
            break
        for x, y in thin_demote:
            continent_shore.discard((x, y))
            grid[y][x] = GRASS_CHAR

    # Enforce 1-tile-wide shoreline: break 2x2 blocks at corners and inlets
    def _thin_2x2_shore_blocks(
        shore_set: set[Point],
        has_water_adjacent: Callable[[int, int], bool],
        width: int,
        height: int,
    ) -> None:
        checker = has_water_adjacent
        while True:
            blocks: list[frozenset[Point]] = []
            for y in range(height - 1):
                for x in range(width - 1):
                    quad = frozenset({(x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)})
                    if quad <= shore_set:
                        blocks.append(quad)
            if not blocks:
                break
            demote_this_round: set[Point] = set()
            for quad in blocks:
                candidates = [(px, py) for px, py in quad if (px, py) not in demote_this_round]
                if not candidates:
                    continue
                # Only demote cells NOT adjacent to water (avoid creating land-water gaps)
                safe_to_demote = [p for p in candidates if not checker(p[0], p[1])]
                if not safe_to_demote:
                    continue
                # Among those, demote the most interior (most shore neighbors)
                def _score(p: Point) -> int:
                    px, py = p
                    return -sum(
                        1
                        for nx, ny in neighbors4(px, py, width, height)
                        if (nx, ny) in shore_set and (nx, ny) not in demote_this_round
                    )
                best = min(safe_to_demote, key=_score)
                demote_this_round.add(best)
            for x, y in demote_this_round:
                shore_set.discard((x, y))
                if grid[y][x] not in POI_SHORELINE_EXCLUDE:
                    grid[y][x] = GRASS_CHAR
            if not demote_this_round:
                break

    _thin_2x2_shore_blocks(
        continent_shore,
        _has_ocean_water_nesw,
        args.width,
        args.height,
    )

    # Lake shoreline (L): 1-tile border, NESW-connected (same as continent).
    # Keep only L adjacent to lake water (NESW) or diagonal connectors; demote inland L.
    lake_chars = WATER_CHARS | {LAKE_SHORELINE_CHAR}

    while True:
        thin_demote: set[Point] = set()
        for x, y in lake_shore:
            if (x, y) in poi_protected or grid[y][x] in POI_SHORELINE_EXCLUDE:
                continue
            if _has_lake_water_nesw(x, y):
                continue  # Keep lake-adjacent L
            if _shore_neighbors_diagonally_adjacent(x, y, lake_shore):
                continue  # Keep diagonal connectors for NESW connectivity
            thin_demote.add((x, y))
        if not thin_demote:
            break
        for x, y in thin_demote:
            lake_shore.discard((x, y))
            grid[y][x] = GRASS_CHAR

    _thin_2x2_shore_blocks(
        lake_shore,
        _has_lake_water_nesw,
        args.width,
        args.height,
    )

    # Re-assert lake perimeter: any land adjacent to lake water -> L (fixes gaps)
    for _ in range(4):
        added = set()
        for y in range(args.height):
            for x in range(args.width):
                if grid[y][x] not in OCEAN_SHORE_CONVERTIBLE or grid[y][x] in POI_SHORELINE_EXCLUDE:
                    continue
                if (x, y) in continent_shore:
                    continue
                for nx, ny in [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]:
                    if 0 <= nx < args.width and 0 <= ny < args.height:
                        if grid[ny][nx] in WATER_CHARS and (nx, ny) not in ocean_connected:
                            added.add((x, y))
                            break
        if not added:
            break
        for x, y in added:
            lake_shore.add((x, y))
            if grid[y][x] not in POI_SHORELINE_EXCLUDE:
                grid[y][x] = LAKE_SHORELINE_CHAR
        _thin_2x2_shore_blocks(lake_shore, _has_lake_water_nesw, args.width, args.height)

    shoreline_all = continent_shore | lake_shore | river_bank
    path_forbidden = set(clearing_cells)
    for x, y in all_positions(args.width, args.height):
        if grid[y][x] in WATER_CHARS or (x, y) in shoreline_all:
            path_forbidden.add((x, y))

    path_cells: set[Point] = set()
    if not args.hide_path:
        for spawn in spawn_points:
            target = min(join_points, key=lambda p: manhattan(spawn, p))
            anchor = spawn_anchor_outside_clearing(
                spawn, target, clearing_half, path_radius, args.width, args.height
            )
            route = find_perlin_path(
                anchor,
                target,
                args.width,
                args.height,
                path_forbidden,
                seed=args.seed + 911,
                scale=args.path_perlin_scale,
                weight=args.path_perlin_weight,
            )
            carve_path(grid, route, path_width, path_cells, path_forbidden)

        for a, b in build_mst(join_points):
            route = find_perlin_path(
                a,
                b,
                args.width,
                args.height,
                path_forbidden,
                seed=args.seed + 1911,
                scale=args.path_perlin_scale,
                weight=args.path_perlin_weight,
            )
            carve_path(grid, route, path_width, path_cells, path_forbidden)

        dead_end_points: list[Point] = []
        branch_forbidden = set(path_forbidden) | dilate_cells(
            shoreline_all, 1, args.width, args.height
        )
        if is_island:
            edge = 2
            for x in range(args.width):
                for y in range(args.height):
                    if x < edge or x >= args.width - edge or y < edge or y >= args.height - edge:
                        branch_forbidden.add((x, y))
        for i in range(args.dead_end_count):
            route = build_branch(
                grid=grid,
                path_cells=path_cells,
                base_forbidden=branch_forbidden,
                rng=rng,
                seed=args.seed + 3000 + i * 29,
                scale=args.path_perlin_scale,
                weight=args.path_perlin_weight,
                path_width=path_width,
                min_length=max(8, args.spawn_clearing_size // 2),
                max_length=max(14, min(args.width, args.height) // 3),
                search_attempts=180,
            )
            if route is None:
                continue  # Skip this branch; proceed with fewer dead-ends
            carve_path(grid, route, path_width, path_cells, branch_forbidden)
            dead_end_points.append(route[-1])

        secret_npc_point: Point | None = None
        if args.require_secret_npc_path:
            route = build_branch(
                grid=grid,
                path_cells=path_cells,
                base_forbidden=branch_forbidden,
                rng=rng,
                seed=args.seed + 9001,
                scale=args.path_perlin_scale,
                weight=args.path_perlin_weight,
                path_width=path_width,
                min_length=max(12, args.spawn_clearing_size),
                max_length=max(20, min(args.width, args.height) // 2),
                search_attempts=260,
            )
            if route is None:
                pass  # Skip secret NPC; proceed without it
            else:
                carve_path(grid, route, path_width, path_cells, branch_forbidden)
                secret_npc_point = route[-1]
    else:
        dead_end_points = []
        secret_npc_point = None
        # For POI placement when path is hidden, use spawns, joins, and their neighbors
        path_cells = set(spawn_points) | set(join_points)
        for px, py in list(path_cells):
            for nx, ny in neighbors4(px, py, args.width, args.height):
                if grid[ny][nx] == GRASS_CHAR:
                    path_cells.add((nx, ny))

    # Enforce spawn clearings and key markers after all path carving.
    # Rule: grass cannot be placed on water
    for x, y in clearing_cells:
        if grid[y][x] not in WATER_CHARS:
            grid[y][x] = GRASS_CHAR
    for x, y in join_points:
        grid[y][x] = JOIN_CHAR
    for x, y in spawn_points:
        grid[y][x] = SPAWN_CHAR
    for x, y in dead_end_points:
        grid[y][x] = DEAD_END_CHAR
    if secret_npc_point is not None:
        grid[secret_npc_point[1]][secret_npc_point[0]] = SECRET_NPC_CHAR

    protected_cells = (
        set(clearing_cells)
        | set(spawn_points)
        | set(join_points)
        | set(dead_end_points)
        | ({secret_npc_point} if secret_npc_point else set())
    )

    terrain_blocked = protected_cells | set(path_cells)

    # Dirt rule: convert P within 1 tile of shoreline to G (per terrain rules)
    # Rule: grass cannot be placed on water
    shoreline_all = continent_shore | lake_shore | river_bank
    for x, y in list(all_positions(args.width, args.height)):
        if grid[y][x] != PATH_CHAR:
            continue
        for dx, dy in [(0, -1), (1, 0), (0, 1), (-1, 0)]:
            nx, ny = x + dx, y + dy
            if 0 <= nx < args.width and 0 <= ny < args.height and (nx, ny) in shoreline_all:
                if grid[y][x] not in WATER_CHARS:
                    grid[y][x] = GRASS_CHAR
                    path_cells.discard((x, y))
                break

    terrain_blocked = protected_cells | set(path_cells)
    water_cells = {
        (x, y)
        for x, y in all_positions(args.width, args.height)
        if grid[y][x] in WATER_CHARS
    }
    vegetation_blocked = terrain_blocked | water_cells | continent_shore | lake_shore | river_bank
    shoreline_blocked = continent_shore | lake_shore | river_bank
    # POI buffer: avoid mines, shops, creeps on shoreline or within 1 tile of it
    poi_shoreline_blocked = dilate_cells(
        shoreline_blocked, 1, args.width, args.height
    )
    # Island mode: wrap adds 2-tile water border; exclude edge band so POIs don't end up on new shore
    if is_island:
        edge = 2
        for x in range(args.width):
            for y in range(args.height):
                if x < edge or x >= args.width - edge or y < edge or y >= args.height - edge:
                    poi_shoreline_blocked.add((x, y))

    # Hills (I) on remaining grass, only where height > hill_threshold
    hill_blocked = terrain_blocked | continent_shore | lake_shore | river_bank
    hill_threshold = getattr(args, "hill_threshold", 0.65)
    hill_eligible = {
        (x, y)
        for x, y in all_positions(args.width, args.height)
        if heightmap[y][x] >= hill_threshold
    }
    hill_placeable = sum(
        1 for x, y in all_positions(args.width, args.height)
        if grid[y][x] == GRASS_CHAR and (x, y) not in hill_blocked and (x, y) in hill_eligible
    )
    hill_target = min(int(round(total_tiles * getattr(args, "hill_density", 0.0))), hill_placeable)
    hill_placed = place_clustered(
        grid, HILL_CHAR, hill_target, rng, hill_blocked, eligible=hill_eligible,
        maintain_connectivity=True,
    )
    hill_holes_filled = fill_hill_interior(grid, args.width, args.height)

    remaining_placeable = sum(
        1
        for x, y in all_positions(args.width, args.height)
        if grid[y][x] == GRASS_CHAR and (x, y) not in vegetation_blocked
    )
    vegetation_target = min(int(round(total_tiles * args.tree_density)), remaining_placeable)
    forest_target = int(round(vegetation_target * args.forest_density))
    tree_target = max(0, vegetation_target - forest_target)
    forest_placed = place_clustered(grid, FOREST_CHAR, forest_target, rng, vegetation_blocked)

    tree_candidates = [
        (x, y)
        for x, y in all_positions(args.width, args.height)
        if grid[y][x] == GRASS_CHAR and (x, y) not in vegetation_blocked
    ]
    rng.shuffle(tree_candidates)
    tree_placed = 0
    for x, y in tree_candidates[:tree_target]:
        grid[y][x] = TREE_CHAR
        tree_placed += 1

    creep_centers, creep_cells = place_creep_zones(
        grid=grid,
        count=args.creep_zone_count,
        radius=args.creep_zone_radius,
        blocked=terrain_blocked | poi_shoreline_blocked,
        rng=rng,
    )

    poi_blocked = terrain_blocked | creep_cells | poi_shoreline_blocked
    mine_points = place_access_pois(
        grid=grid,
        path_cells=path_cells,
        blocked=poi_blocked,
        count=args.mine_count,
        marker=MINE_CHAR,
        label="mines",
        rng=rng,
    )
    poi_blocked |= set(mine_points)

    shop_points = place_access_pois(
        grid=grid,
        path_cells=path_cells,
        blocked=poi_blocked,
        count=args.shop_count,
        marker=SHOP_CHAR,
        label="shops",
        rng=rng,
    )

    # Relocate join points (orange) off shoreline: move to nearest inland neighbor
    shoreline_all = continent_shore | lake_shore | river_bank
    relocated_joins: list[Point] = []
    for jx, jy in join_points:
        if (jx, jy) not in shoreline_all:
            relocated_joins.append((jx, jy))
            continue
        # Find NESW neighbor not on shoreline, not water
        best: Point | None = None
        for nx, ny in neighbors4(jx, jy, args.width, args.height):
            if (nx, ny) in shoreline_all or grid[ny][nx] in WATER_CHARS:
                continue
            # Prefer path-adjacent or grass
            best = (nx, ny)
            if (nx, ny) in path_cells:
                break
        if best is not None:
            if (jx, jy) in continent_shore:
                grid[jy][jx] = SHORELINE_CHAR
            elif (jx, jy) in lake_shore:
                grid[jy][jx] = LAKE_SHORELINE_CHAR
            else:
                grid[jy][jx] = RIVER_CHAR
            relocated_joins.append(best)
        else:
            relocated_joins.append((jx, jy))
    join_points = relocated_joins

    # Shoreline inviolability: no grass, trees, hills, dirt on shoreline. Re-assert B/L/R.
    for x, y in continent_shore:
        if grid[y][x] not in POI_SHORELINE_EXCLUDE and grid[y][x] not in (SHORELINE_CHAR, LAKE_SHORELINE_CHAR, RIVER_CHAR):
            grid[y][x] = SHORELINE_CHAR
    for x, y in lake_shore:
        if grid[y][x] not in POI_SHORELINE_EXCLUDE and grid[y][x] not in (SHORELINE_CHAR, LAKE_SHORELINE_CHAR, RIVER_CHAR):
            grid[y][x] = LAKE_SHORELINE_CHAR
    for x, y in river_bank:
        if grid[y][x] not in POI_SHORELINE_EXCLUDE and grid[y][x] not in (SHORELINE_CHAR, LAKE_SHORELINE_CHAR, RIVER_CHAR):
            grid[y][x] = RIVER_CHAR

    # Re-assert protected markers in case any placement touched them.
    for x, y in spawn_points:
        grid[y][x] = SPAWN_CHAR
    for x, y in join_points:
        grid[y][x] = JOIN_CHAR
    for x, y in dead_end_points:
        grid[y][x] = DEAD_END_CHAR
    if secret_npc_point is not None:
        grid[secret_npc_point[1]][secret_npc_point[0]] = SECRET_NPC_CHAR

    border_width = 2  # Min 2-tile border for both modes
    if is_island:
        water_border = max(border_width, args.water_border_width)
        grid = wrap_with_water_border(grid, water_border)
        # Terrain rules: any grass/L adjacent to ocean 2-tile border is B
        continent_shoreline_after_wrap(grid, water_border)
        # Move POIs (joins, etc.) off ocean shoreline
        h, w = len(grid), len(grid[0]) if grid else 0
        relocate_pois_from_ocean_shore(grid, w, h, water_border)
        # Enforce 1-tile-wide shoreline (breaks 2x2 blocks created at wrap edge)
        thin_2x2_shoreline_in_grid(grid, w, h)
        # B without ocean in neighborhood -> grass
        demote_shoreline_without_ocean_neighbor(grid, w, h, water_border)
        # L without lake water in neighborhood -> grass
        demote_lake_shore_without_lake_neighbor(grid, w, h)
        # Re-assert shorelines (thinning/demote may have created grass-ocean gaps around bays)
        continent_shoreline_after_wrap(grid, water_border)
        # Fill diagonal-only shore gaps: promote land so shoreline is 4-connected (NESW only)
        fill_diagonal_only_shore_connectors(grid, w, h)
        # Ocean deep water (same as lake): interior ocean -> deep, min 1-tile shallow next to land/B
        mark_ocean_deep_water(grid, w, h)
    else:
        # Continent mode: 2-tile land-with-trees border
        grid = wrap_with_land_border(grid, border_width, rng, tree_fraction=0.7)

    out_path = Path(args.out)
    legend_path = Path(args.legend_out) if args.legend_out else out_path.with_suffix(".legend.json")

    legend: dict[str, int] | None = None
    terrain_config = getattr(args, "terrain_config", "") or ""
    tc_path: Path | None = None
    if terrain_config:
        tc_path = Path(terrain_config)
        if not tc_path.exists():
            for base in (PROJECT_ROOT / "examples", PROJECT_ROOT):
                candidate = base / tc_path
                if candidate.exists():
                    tc_path = candidate
                    break
    else:
        # Auto-use terrain config when not provided
        for candidate in (
            PROJECT_ROOT / "examples" / "terrain.bitmask.json",
            PROJECT_ROOT / "terrain.bitmask.json",
        ):
            if candidate.exists():
                tc_path = candidate
                break
    if tc_path and tc_path.exists():
        from tilemap_generator.legend import (
            DEFAULT_LEGEND,
            get_legend_from_config,
            get_terrain_rules,
        )
        from tilemap_generator.paint_map_png import load_terrain_config

        terrain_cfg = load_terrain_config(tc_path, project_root=PROJECT_ROOT)
        legend = get_legend_from_config(terrain_cfg)
        rules = get_terrain_rules(terrain_cfg)
        if rules:
            # Terrain rules enforced: shorelines block trees; legend from config
            pass
    if legend is None:
        legend = DEFAULT_LEGEND.copy()

    write_ascii(out_path, grid)
    write_legend(legend_path, legend)

    # CSV tile export (legend -> tile IDs, with water-in-neighborhood rule for B/L/R)
    csv_path = out_path.with_suffix(".csv")
    lines = ["".join(row) for row in grid]
    from tilemap_generator.tree_logic import to_tile_rows_with_trees

    tile_rows = to_tile_rows_with_trees(
        lines,
        legend,
        tree_chars={"T", "F"},
        seed=args.seed,
        strict=getattr(args, "strict", False),
    )
    csv_content = "\n".join(",".join(str(tid) for tid in row) for row in tile_rows) + "\n"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text(csv_content, encoding="utf-8")
    print(f"Wrote {csv_path}")

    preview_path: Path | None = None
    if args.preview_in_aseprite or args.preview_out:
        use_layered = getattr(args, "preview_layered", True)
        if args.preview_out:
            preview_path = Path(args.preview_out)
            if preview_path.suffix.lower() == ".bmp":
                use_layered = False
            elif preview_path.suffix.lower() in (".aseprite", ".ase"):
                use_layered = True
        else:
            ext = ".preview.aseprite" if use_layered else ".preview.bmp"
            preview_path = out_path.with_suffix(ext)

        aseprite_bin = getattr(args, "aseprite_bin", "") or ""
        aseprite_available = False
        try:
            resolve_aseprite_bin(aseprite_bin)
            aseprite_available = True
        except FileNotFoundError:
            pass

        if use_layered and not aseprite_available:
            print("Note: Aseprite CLI not found. Using flat BMP preview (use --aseprite-bin or ASEPRITE_BIN to enable layered).")
            use_layered = False
            if preview_path.suffix.lower() in (".aseprite", ".ase"):
                preview_path = preview_path.with_suffix(".preview.bmp")

        if use_layered:
            try:
                write_preview_layered(
                    preview_path,
                    grid,
                    args.preview_tile_size,
                    aseprite_bin,
                )
            except FileNotFoundError as exc:
                if "Aseprite" in str(exc) or "aseprite" in str(exc).lower():
                    print(f"Warning: {exc}. Falling back to flat BMP preview.")
                    preview_path = out_path.with_suffix(".preview.bmp")
                    write_preview_bmp(preview_path, grid, args.preview_tile_size)
                else:
                    raise
        else:
            write_preview_bmp(preview_path, grid, args.preview_tile_size)

        print(f"Wrote {preview_path}")
        if args.preview_in_aseprite and aseprite_available:
            try:
                open_in_aseprite(preview_path, aseprite_bin)
            except (FileNotFoundError, subprocess.CalledProcessError) as exc:
                print(f"Warning: failed to open preview in Aseprite: {exc}")

    print(f"Wrote {out_path}")
    print(f"Wrote {legend_path}")
    print(
        "Stats: "
        f"spawns={len(spawn_points)}, joins={len(join_points)}, "
        f"dead_ends={len(dead_end_points)}, secret_npc={'1' if secret_npc_point else '0'}, "
        f"path_tiles={len(path_cells)}, mines={len(mine_points)}, shops={len(shop_points)}, "
        f"creep_zones={len(creep_centers)}, water={water_placed}, hills={hill_placed + hill_holes_filled}, "
        f"forest={forest_placed}, trees={tree_placed}, path_width={path_width}"
    )


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    run_from_args(args)


if __name__ == "__main__":
    main()
