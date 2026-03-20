"""Paint ASCII map to grass + trees PNGs using PIL (GotchiCraft-style pipeline)."""
from __future__ import annotations

import json
import random
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from tilemap_generator.tree_logic import to_tile_rows_with_trees


def load_bitmask_config(path: Path) -> dict[str, Any]:
    """Load grass bitmask config from JSON. Used for shoreline autotiling."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Bitmask config must be a JSON object")
    return data


def load_terrain_config(path: Path, project_root: Path | None = None) -> dict[str, Any]:
    """Load terrain config from JSON. Includes paths (grass, water, dirt) and bitmask settings.
    Paths in the config are relative to the config file's directory. Falls back to project_root if provided."""
    data = load_bitmask_config(path)
    base = path.parent.resolve()
    for key in ("grass_path", "shoreline_path", "lakesrivers_path", "water_path", "hill_path", "dirt_path", "trees_path"):
        if key not in data or not isinstance(data[key], str) or not data[key]:
            continue
        rel = data[key]
        resolved = (base / rel).resolve()
        if not resolved.exists() and project_root:
            resolved = (project_root / rel).resolve()
        if resolved.exists():
            data[key] = str(resolved)
    return data

# Default grass tile names (GotchiCraft Sprout Lands)
DEFAULT_GRASS_TILES = [
    "Grass_tiles_v2_Mid",
    "Grass_tiles_v2_Mid_Grass1",
    "Grass_tiles_v2_Mid_Grass2",
    "Grass_tiles_v2_Mid_Flowers1",
    "Grass_tiles_v2_Mid_Sprouts1",
]

# Solid colors for ground (RGBA) - match paint_ascii_map.lua
SOLID_TILE_COLORS: dict[str, tuple[int, int, int, int]] = {
    "G": (104, 178, 76, 255),
    ".": (104, 178, 76, 255),
    "B": (194, 178, 128, 255),  # Continent shoreline/beach
    "L": (120, 160, 180, 255),  # Lake shoreline
    "R": (100, 140, 200, 255),  # River bank
    "I": (90, 120, 70, 255),   # Hill
    "~": (72, 132, 224, 255),
    "T": (46, 108, 54, 255),
    "F": (30, 78, 40, 255),
    "P": (181, 152, 102, 255),
    "S": (250, 228, 92, 255),
    "J": (255, 161, 77, 255),
    "M": (125, 126, 134, 255),
    "H": (214, 123, 73, 255),
    "C": (194, 76, 76, 255),
    "D": (240, 95, 95, 255),
    "N": (86, 208, 220, 255),
}
DEFAULT_COLOR = (255, 0, 255, 255)

TREESET_COLS = 7
TREESET_ROWS = 5

# Path tile bitmask: N=1, E=2, S=4, W=8 (standard 4-bit autotile).
# Tile layout reference: examples/Bitmask references 1.png, Bitmask references 2.png
#
# Extended grass shoreline layout:
#   Ocean (continent border): 1-15 (3x3 grid)
#   Lake (interior water): 4-18 (3x3 around center 11)
#   River (water on opposite sides): mask 5=N+S, 10=E+W -> optional river bank tiles
#   Peninsula/island: masks 7,11,13,14,15 -> optional extended range (e.g. 19-23)
#
PATH_CHARS = frozenset("P")
WATER_CHAR = "~"
DEEP_WATER_CHAR = "`"
WATER_CHARS = frozenset([WATER_CHAR, DEEP_WATER_CHAR])
# For lake shoreline bitmask: L/R count as water (they're part of the lake edge)
LAKE_WATER_CHARS = WATER_CHARS | frozenset("LR")

# POI chars: spawn, join, mine, shop, creep, dead end, secret NPC
POI_CHARS = frozenset("SJMHCDN")
# Base terrain for POI cells: S,C=grass; J,M,H,D,N=path
POI_GRASS_BASE = frozenset("SC")
POI_PATH_BASE = frozenset("JMHDN")
# POI layer names and chars
POI_LAYERS: dict[str, str] = {
    "Spawn": "S",
    "Join": "J",
    "Mine": "M",
    "Shop": "H",
    "Creep": "C",
    "DeadEnd": "D",
    "Secret": "N",
}

# River bank masks: water on opposite sides (narrow channel)
RIVER_MASKS = (5, 10)  # 5=N+S (vertical river), 10=E+W (horizontal river)
SHORE_CHARS = frozenset({"B", "L", "R"})
SHORE_MASK_PROPAGATION_RULES = (
    (0, -1, 1, 4),   # N neighbor has water S -> we have water N (between)
    (0, -1, 1, 1),   # N neighbor has water N -> we have water N (same dir)
    (0, -1, 2, 2),   # N neighbor has water E -> we have water E (same dir)
    (0, -1, 8, 8),   # N neighbor has water W -> we have water W (same dir)
    (1, 0, 2, 8),    # E neighbor has water W -> we have water E (between)
    (1, 0, 1, 1),    # E neighbor has water N -> we have water N (same dir)
    (1, 0, 2, 2),    # E neighbor has water E -> we have water E (same dir)
    (1, 0, 4, 4),    # E neighbor has water S -> we have water S (same dir)
    (0, 1, 4, 1),    # S neighbor has water N -> we have water S (between)
    (0, 1, 2, 2),    # S neighbor has water E -> we have water E (same dir)
    (0, 1, 4, 4),    # S neighbor has water S -> we have water S (same dir)
    (0, 1, 8, 8),    # S neighbor has water W -> we have water W (same dir)
    (-1, 0, 8, 2),   # W neighbor has water E -> we have water W (between)
    (-1, 0, 1, 1),   # W neighbor has water N -> we have water N (same dir)
    (-1, 0, 4, 4),   # W neighbor has water S -> we have water S (same dir)
    (-1, 0, 8, 8),   # W neighbor has water W -> we have water W (same dir)
)


def match_ocean_inset_special_tile(
    has_n: bool,
    has_e: bool,
    has_s: bool,
    has_w: bool,
    edge_tiles: dict[str, int],
    corner_tiles: dict[str, int],
    *,
    direct_corner_tiles: dict[str, int] | None = None,
    has_ne: bool = False,
    has_se: bool = False,
    has_sw: bool = False,
    has_nw: bool = False,
) -> int | None:
    """Map inland ocean inset neighborhoods to dedicated shoreline tiles."""
    pattern = get_ocean_inset_pattern(
        has_n,
        has_e,
        has_s,
        has_w,
        has_ne=has_ne,
        has_se=has_se,
        has_sw=has_sw,
        has_nw=has_nw,
    )
    if pattern is None:
        return None
    if pattern in edge_tiles:
        return edge_tiles.get(pattern)
    if direct_corner_tiles and pattern in direct_corner_tiles:
        return direct_corner_tiles.get(pattern)
    if pattern.startswith("direct_"):
        return corner_tiles.get(pattern[len("direct_"):])
    return corner_tiles.get(pattern)


def resolve_bottom_ocean_inset_tile(
    north_tile: int | None,
    edge_tiles: dict[str, int],
    direct_corner_tiles: dict[str, int] | None = None,
) -> int | None:
    """Choose the bottom inset helper tile from the shoreline tile above it."""
    if north_tile == 10 and direct_corner_tiles:
        return direct_corner_tiles.get("direct_bottom_left", edge_tiles.get("bottom"))
    if north_tile == 4 and direct_corner_tiles:
        return direct_corner_tiles.get("direct_bottom_right", edge_tiles.get("bottom"))
    return edge_tiles.get("bottom")


def resolve_center_ocean_inset_tile(
    north_tile: int | None,
    east_tile: int | None,
    edge_tiles: dict[str, int],
) -> int | None:
    """Choose the surrounded inset helper tile from neighboring shoreline tiles."""
    if north_tile == 10 and east_tile == 7:
        return edge_tiles.get("center")
    return None


def match_ocean_shoreline_special_tile(
    has_n: bool,
    has_e: bool,
    has_s: bool,
    has_w: bool,
    water_mask: int,
    special_tiles: dict[str, int],
) -> int | None:
    """Map explicit shoreline junctions to dedicated tiles."""
    if water_mask == 8 and has_n and has_s and not has_e and not has_w:
        return special_tiles.get("lake_east")
    if water_mask == 8 and has_n and has_e and has_s and not has_w:
        return special_tiles.get("tee_west")
    if water_mask == 2 and has_n and has_s and has_w and not has_e:
        return special_tiles.get("tee_east")
    return None


def match_lake_shoreline_special_tile(
    has_n: bool,
    has_e: bool,
    has_s: bool,
    has_w: bool,
    water_mask: int,
    special_tiles: dict[str, int],
    *,
    has_n_beach: bool = False,
    has_e_beach: bool = False,
    has_s_beach: bool = False,
    has_w_beach: bool = False,
) -> int | None:
    """Map explicit lake shoreline junctions to dedicated lakesrivers tiles."""
    if water_mask == 2 and has_w_beach and not has_e:
        return special_tiles.get("beach_west")
    if water_mask == 8 and has_n and has_s and has_e_beach and not has_w:
        return special_tiles.get("beach_east")
    return None


def get_ocean_inset_pattern(
    has_n: bool,
    has_e: bool,
    has_s: bool,
    has_w: bool,
    *,
    has_ne: bool = False,
    has_se: bool = False,
    has_sw: bool = False,
    has_nw: bool = False,
) -> str | None:
    """Classify an inland ocean inset candidate from neighboring B cells."""
    if has_e and has_s and has_w and not has_n:
        return "top"
    if has_n and has_s and has_w and not has_e:
        return "left"
    if has_n and has_e and has_s and not has_w:
        return "right"
    if has_n and has_e and has_w and not has_s:
        return "bottom"
    if has_w and has_s and not has_n and not has_e:
        return "direct_top_left"
    if has_e and has_s and not has_n and not has_w:
        return "direct_top_right"
    if has_w and has_n and not has_s and not has_e:
        return "direct_bottom_left"
    if has_e and has_n and not has_s and not has_w:
        return "direct_bottom_right"
    # Ambiguous opposite-side inset connectors: use diagonal shoreline continuity
    # to pick the matching inset corner tile (36-39).
    if has_e and has_w and not has_n and not has_s:
        if has_nw and not has_ne and not has_se and not has_sw:
            return "top_left"
        if has_ne and not has_nw and not has_se and not has_sw:
            return "top_right"
        if has_sw and not has_nw and not has_ne and not has_se:
            return "bottom_left"
        if has_se and not has_nw and not has_ne and not has_sw:
            return "bottom_right"
    if has_n and has_s and not has_e and not has_w:
        if has_nw and not has_ne and not has_se and not has_sw:
            return "top_left"
        if has_ne and not has_nw and not has_se and not has_sw:
            return "top_right"
        if has_sw and not has_nw and not has_ne and not has_se:
            return "bottom_left"
        if has_se and not has_nw and not has_ne and not has_sw:
            return "bottom_right"
    return None


# Continent shoreline: matches examples/grass.png (6x23, 1-based).
# Outer convex corners: 42=N+W, 44=N+E, 48=S+W, 50=S+E. Edges: 43=N, 45=W, 47=E, 49=S.
# Mask 9 (N+W) = top-left grass corner (water on top+left) -> tile 42
GRASS_SHORELINE_MAP: dict[int, int] = {
    0: 46,  # no water (center grass)
    1: 43,  # N
    2: 47,  # E (right edge)
    3: 44,  # N+E (outer top-right)
    4: 49,  # S
    5: 43,  # N+S (vertical)
    6: 50,  # S+E (outer bottom-right)
    7: 44,  # N+E+S
    8: 45,  # W (left edge)
    9: 42,  # N+W (outer top-left corner)
    10: 47, # E+W (horizontal)
    11: 42, # N+E+W
    12: 48, # S+W (outer bottom-left)
    13: 48, # S+W+N
    14: 50, # S+E+W
    15: 46, # all four
}

# Extended shoreline: peninsula (3 water neighbors) and isolated island (4 water neighbors)
# Mask 7=N+E+S, 11=N+E+W, 13=S+W+N, 14=S+E+W, 15=all four
# Maps to tile indices when grass_shoreline_extended_range is provided (e.g. 19-23)
EXTENDED_SHORELINE_MASKS = (7, 11, 13, 14, 15)

# Interior shore corners (concave): masks 3,6,9,12 -> tiles 4,6,16,18 (rocky corner pieces)
INTERIOR_CORNER_MASKS = (3, 6, 9, 12)  # N+E, S+E, N+W, S+W

# Hill autotile: N=1,E=2,S=4,W=8. Maps mask to 1-based tile ID in hill range (14-50).
# 3x3 grid: top [15,19,16], mid [20,20,21], bot [17,31,18]
HILL_MAP: dict[int, int] = {
    0: 14,   # isolated (single)
    1: 19,   # N
    2: 21,   # E
    3: 16,   # N+E (top-right)
    4: 31,   # S
    5: 19,   # N+S (vertical)
    6: 18,   # S+E (bottom-right)
    7: 19,   # N+E+S
    8: 20,   # W
    9: 15,   # N+W (top-left)
    10: 21,  # E+W (horizontal)
    11: 21,  # N+E+W
    12: 17,  # S+W (bottom-left)
    13: 20,  # S+W+N
    14: 21,  # S+E+W
    15: 20,  # all four (center)
}

# Lake/pond shoreline (3x3 around center 11): 4,5,6 top, 10,12 mid, 16,17,18 bottom
# Interior corners use 4,6,16,18. Same N=1,E=2,S=4,W=8 bitmask -> lake tile index (1-based)
LAKE_SHORELINE_MAP: dict[int, int] = {
    0: 8,   # no water (fallback to interior)
    1: 17,  # N
    2: 10,  # E (right edge)
    3: 16,  # N+E
    4: 5,   # S
    5: 17,  # N+S
    6: 4,   # S+E
    7: 16,  # N+E+S
    8: 12,  # W (left edge)
    9: 18,  # N+W
    10: 10, # E+W
    11: 18, # N+E+W
    12: 6,  # S+W
    13: 18, # S+W+N
    14: 4,  # S+E+W
    15: 8,  # all four
}


def _ensure_pillow() -> Any:
    try:
        from PIL import Image
        return Image
    except ImportError as e:
        raise ImportError(
            "Pillow required for tree painting. Install with: pip install Pillow"
        ) from e


def load_grass_tiles(
    grass_dir: Path,
    tile_size: int,
    names: list[str] | None = None,
) -> list[Any]:
    """Load grass tile PNGs from directory. Returns list of RGBA images resized to tile_size."""
    Image = _ensure_pillow()
    if names is None:
        names = DEFAULT_GRASS_TILES
    tiles: list[Any] = []
    for name in names:
        path = grass_dir / f"{name}.png"
        if not path.exists():
            continue
        img = Image.open(path)
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        if img.width != tile_size or img.height != tile_size:
            img = img.resize((tile_size, tile_size), Image.Resampling.NEAREST)
        tiles.append(img)
    if not tiles:
        # Fallback: load any PNG in directory
        for path in sorted(grass_dir.glob("*.png")):
            img = Image.open(path)
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            if img.width != tile_size or img.height != tile_size:
                img = img.resize((tile_size, tile_size), Image.Resampling.NEAREST)
            tiles.append(img)
            if len(tiles) >= 5:
                break
    return tiles


def load_grass_from_sheet(
    sheet_path: Path,
    tile_size: int,
    tile_range: tuple[int, int] | None = None,
    tileset_json_path: Path | None = None,
) -> list[Any]:
    """Load grass tiles from a PNG sheet (grid of tiles). Returns list of RGBA images.
    tile_range: optional (start, end) 1-based inclusive, e.g. (1, 13) for tiles 1-13 only.
    tileset_json_path: optional path to grass.json from Aseprite export; when provided,
    loads tiles by exact (x,y) position from JSON to ensure correct tile indexing."""
    Image = _ensure_pillow()
    img = Image.open(sheet_path)
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    w, h = img.size
    cols = max(1, w // tile_size)
    rows = max(1, h // tile_size)

    # When JSON is available, load by exact tile position to guarantee correct order
    if tileset_json_path and tileset_json_path.exists() and tile_range:
        try:
            data = json.loads(tileset_json_path.read_text(encoding="utf-8"))
            tiles_arr = data.get("tiles") or data.get("frames")
            tw = data.get("tile_width") or data.get("frame", {}).get("w") or tile_size
            th = data.get("tile_height") or data.get("frame", {}).get("h") or tile_size
            if isinstance(tiles_arr, list):
                id_to_xy: dict[int, tuple[int, int]] = {}
                for t in tiles_arr:
                    tid = t.get("id") or t.get("index")
                    if tid is None:
                        continue
                    tx = t.get("x", 0)
                    ty = t.get("y", 0)
                    if isinstance(t.get("frame"), dict):
                        tx = t["frame"].get("x", tx)
                        ty = t["frame"].get("y", ty)
                    id_to_xy[int(tid)] = (tx, ty)
                start, end = tile_range
                out: list[Any] = []
                for tid in range(start, end + 1):
                    xy = id_to_xy.get(tid)
                    if xy is None:
                        continue
                    px, py = xy[0] * tw, xy[1] * th
                    if px + tile_size <= w and py + tile_size <= h:
                        tile = img.crop((px, py, px + tile_size, py + tile_size))
                        out.append(tile)
                if out:
                    return out
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    all_tiles: list[Any] = []
    for r in range(rows):
        for c in range(cols):
            x, y = c * tile_size, r * tile_size
            if x + tile_size > w or y + tile_size > h:
                continue
            tile = img.crop((x, y, x + tile_size, y + tile_size))
            all_tiles.append(tile)
    if tile_range:
        start, end = tile_range
        start = max(1, min(start, len(all_tiles)))
        end = max(start, min(end, len(all_tiles)))
        return all_tiles[start - 1 : end]
    return all_tiles


def _ocean_connected_water_cells(
    ascii_lines: list[str],
    width: int,
    height: int,
    water_chars: frozenset[str] = WATER_CHARS,
) -> set[tuple[int, int]]:
    """Water cells connected via NESW to the map edge (ocean)."""
    ocean: set[tuple[int, int]] = set()
    frontier: list[tuple[int, int]] = []
    for y in range(height):
        for x in range(width):
            if (ascii_lines[y][x] if x < len(ascii_lines[y]) else ".") not in water_chars:
                continue
            if x == 0 or x == width - 1 or y == 0 or y == height - 1:
                ocean.add((x, y))
                frontier.append((x, y))
    while frontier:
        x, y = frontier.pop()
        for dx, dy in [(0, -1), (1, 0), (0, 1), (-1, 0)]:
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in ocean:
                ch = ascii_lines[ny][nx] if nx < len(ascii_lines[ny]) else "."
                if ch in water_chars:
                    ocean.add((nx, ny))
                    frontier.append((nx, ny))
    return ocean


def _river_water_cells(
    ascii_lines: list[str],
    width: int,
    height: int,
    water_chars: frozenset[str] = WATER_CHARS,
) -> set[tuple[int, int]]:
    """Water cells that form narrow channels (2 opposite water neighbors)."""
    out: set[tuple[int, int]] = set()
    for y in range(height):
        row = ascii_lines[y] if y < len(ascii_lines) else ""
        for x in range(width):
            ch = row[x] if x < len(row) else "."
            if ch not in water_chars:
                continue
            n = sum(
                1
                for dx, dy in [(0, -1), (1, 0), (0, 1), (-1, 0)]
                if 0 <= x + dx < width and 0 <= y + dy < height
                and (ascii_lines[y + dy][x + dx] if x + dx < len(ascii_lines[y + dy]) else ".") in water_chars
            )
            if n != 2:
                continue
            has_n = y > 0 and (ascii_lines[y - 1][x] if x < len(ascii_lines[y - 1]) else ".") in water_chars
            has_s = y < height - 1 and (ascii_lines[y + 1][x] if x < len(ascii_lines[y + 1]) else ".") in water_chars
            has_w = x > 0 and (row[x - 1] if x - 1 < len(row) else ".") in water_chars
            has_e = x < width - 1 and (row[x + 1] if x + 1 < len(row) else ".") in water_chars
            if (has_n and has_s) or (has_w and has_e):
                out.add((x, y))
    return out


def _lake_mask_with_diagonal_inference(
    ascii_lines: list[str],
    x: int,
    y: int,
    base_mask: int,
    water_chars: frozenset[str] = WATER_CHARS,
) -> int:
    """Upgrade single-edge lake mask to corner when diagonal neighbor is water.
    E.g. mask 1 (N) + NE water -> mask 3 (N+E corner) for tile 2."""
    if base_mask not in (1, 2, 4, 8):
        return base_mask
    height = len(ascii_lines)
    width = max((len(row) for row in ascii_lines), default=0)

    def _is_water(px: int, py: int) -> bool:
        if not (0 <= px < width and 0 <= py < height):
            return False
        row = ascii_lines[py]
        ch = row[px] if px < len(row) else "."
        return ch in water_chars

    upgraded = base_mask
    if base_mask == 1:  # N
        if _is_water(x + 1, y - 1):
            upgraded = 3  # N+E corner
        elif _is_water(x - 1, y - 1):
            upgraded = 9  # N+W corner
    elif base_mask == 2:  # E
        if _is_water(x + 1, y - 1):
            upgraded = 3  # N+E corner
        elif _is_water(x + 1, y + 1):
            upgraded = 6  # S+E corner
    elif base_mask == 4:  # S
        if _is_water(x + 1, y + 1):
            upgraded = 6  # S+E corner
        elif _is_water(x - 1, y + 1):
            upgraded = 12  # S+W corner
    elif base_mask == 8:  # W
        if _is_water(x - 1, y - 1):
            upgraded = 9  # N+W corner
        elif _is_water(x - 1, y + 1):
            upgraded = 12  # S+W corner
    return upgraded


def get_water_adjacency_bitmask(
    ascii_lines: list[str],
    x: int,
    y: int,
    water_chars: frozenset[str] = WATER_CHARS,
    border_width: int = 2,
) -> int:
    """Compute 4-bit water adjacency for grass shoreline. N=1, E=2, S=4, W=8.
    Out-of-bounds (map edge) counts as water when border_width > 0."""
    height = len(ascii_lines)
    width = max(len(row) for row in ascii_lines) if ascii_lines else 0

    def is_water(px: int, py: int) -> bool:
        if py < 0 or py >= height or px < 0 or px >= width:
            return border_width > 0
        row = ascii_lines[py]
        ch = row[px] if px < len(row) else "."
        return ch in water_chars

    mask = 0
    if is_water(x, y - 1):
        mask |= 1  # North
    if is_water(x + 1, y):
        mask |= 2  # East
    if is_water(x, y + 1):
        mask |= 4  # South
    if is_water(x - 1, y):
        mask |= 8  # West
    return mask


def get_water_adjacency_with_type(
    ascii_lines: list[str],
    x: int,
    y: int,
    water_chars: frozenset[str] = WATER_CHARS,
    border_width: int = 2,
    ascii_water_border: int = 2,
    ocean_connected: set[tuple[int, int]] | None = None,
) -> tuple[int, bool]:
    """Returns (mask, is_lake). is_lake=True if adjacent water is internal (lake/pond), False if map border."""
    height = len(ascii_lines)
    width = max(len(row) for row in ascii_lines) if ascii_lines else 0
    has_border_water = False
    has_lake_water = False
    mask = 0

    for dx, dy, bit in [(0, -1, 1), (1, 0, 2), (0, 1, 4), (-1, 0, 8)]:
        px, py = x + dx, y + dy
        if py < 0 or py >= height or px < 0 or px >= width:
            if border_width > 0:
                mask |= bit
                has_border_water = True
            continue
        row = ascii_lines[py]
        ch = row[px] if px < len(row) else "."
        if ch in water_chars:
            mask |= bit
            if ocean_connected is not None:
                if (px, py) in ocean_connected:
                    has_border_water = True
                else:
                    has_lake_water = True
            else:
                # Border water: in outer ascii_water_border rows/cols
                if (
                    px < ascii_water_border
                    or px >= width - ascii_water_border
                    or py < ascii_water_border
                    or py >= height - ascii_water_border
                ):
                    has_border_water = True
                else:
                    has_lake_water = True

    is_lake = has_lake_water and not has_border_water
    return mask, is_lake


def count_adjacent_shoreline_cells(
    ascii_lines: list[str],
    x: int,
    y: int,
    shore_chars: frozenset[str] = SHORE_CHARS,
) -> int:
    """Count NESW-adjacent shoreline cells."""
    height = len(ascii_lines)
    width = max((len(row) for row in ascii_lines), default=0)
    count = 0
    for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
        nx, ny = x + dx, y + dy
        if not (0 <= nx < width and 0 <= ny < height):
            continue
        row = ascii_lines[ny] if ny < len(ascii_lines) else ""
        ch = row[nx] if nx < len(row) else "."
        if ch in shore_chars:
            count += 1
    return count


def close_ocean_shoreline_gaps(
    ascii_lines: list[str],
    shore_char: str = "B",
    land_chars: frozenset[str] = frozenset("G.PTF") | POI_CHARS,
    max_search_distance: int = 4,
    max_passes: int = 12,
) -> list[str]:
    """Promote nearby land cells into ocean shoreline to keep shoreline chains connected."""
    height = len(ascii_lines)
    width = max((len(row) for row in ascii_lines), default=0)
    if width == 0 or height == 0:
        return ascii_lines

    ocean_connected = _ocean_connected_water_cells(ascii_lines, width, height)

    shore_cells: set[tuple[int, int]] = set()
    for y in range(height):
        row = ascii_lines[y]
        for x in range(width):
            ch = row[x] if x < len(row) else "."
            if ch == shore_char:
                shore_cells.add((x, y))

    def _cell(px: int, py: int) -> str:
        if not (0 <= py < height and 0 <= px < width):
            return "."
        row = ascii_lines[py] if py < len(ascii_lines) else ""
        return row[px] if px < len(row) else "."

    def _output_cell(px: int, py: int) -> str:
        if (px, py) in shore_cells:
            return shore_char
        return _cell(px, py)

    def _is_land_candidate(px: int, py: int) -> bool:
        return _cell(px, py) in land_chars and (px, py) not in shore_cells

    def _shore_degree(px: int, py: int) -> int:
        count = 0
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            if (px + dx, py + dy) in shore_cells:
                count += 1
        return count

    def _shore_dirs(px: int, py: int) -> set[str]:
        dirs: set[str] = set()
        for name, dx, dy in (("N", 0, -1), ("E", 1, 0), ("S", 0, 1), ("W", -1, 0)):
            if (px + dx, py + dy) in shore_cells:
                dirs.add(name)
        return dirs

    def _candidate_score(px: int, py: int) -> tuple[int, int]:
        shore_neighbors = 0
        water_neighbors = 0
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            nx, ny = px + dx, py + dy
            if (nx, ny) in shore_cells:
                shore_neighbors += 1
            if _cell(nx, ny) in WATER_CHARS:
                water_neighbors += 1
        return (shore_neighbors, water_neighbors)

    def _adjacent_water_count(px: int, py: int) -> int:
        count = 0
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            if _cell(px + dx, py + dy) in WATER_CHARS:
                count += 1
        return count

    def _consider_best_candidate(
        best: tuple[tuple[int, int, int, int], tuple[int, int]] | None,
        px: int,
        py: int,
        tier: int,
        distance: int,
    ) -> tuple[tuple[int, int, int, int], tuple[int, int]] | None:
        shore_neighbors, water_neighbors = _candidate_score(px, py)
        score = (tier, shore_neighbors, water_neighbors, -distance)
        ranked = (score, (px, py))
        if best is None or ranked[0] > best[0]:
            return ranked
        return best

    for _ in range(max_passes):
        additions: set[tuple[int, int]] = set()

        for y in range(height):
            for x in range(width):
                if not _is_land_candidate(x, y):
                    continue
                dirs = _shore_dirs(x, y)
                if len(dirs) >= 3 or {"N", "S"}.issubset(dirs) or {"E", "W"}.issubset(dirs):
                    additions.add((x, y))

        endpoints = [
            (x, y)
            for (x, y) in shore_cells
            if _shore_degree(x, y) < 2
        ]

        for x, y in endpoints:
            best: tuple[tuple[int, int, int, int], tuple[int, int]] | None = None
            for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                intermediates: list[tuple[int, int]] = []
                for dist in range(1, max_search_distance + 1):
                    nx, ny = x + dx * dist, y + dy * dist
                    if not (0 <= nx < width and 0 <= ny < height):
                        break
                    if (nx, ny) in shore_cells:
                        if intermediates:
                            cand_x, cand_y = intermediates[0]
                            best = _consider_best_candidate(best, cand_x, cand_y, 3, dist)
                        break
                    if not _is_land_candidate(nx, ny):
                        break
                    intermediates.append((nx, ny))

            for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                nx, ny = x + dx, y + dy
                if (nx, ny) not in shore_cells:
                    continue
                candidates = [
                    (x + dx, y),
                    (x, y + dy),
                ]
                valid = [pt for pt in candidates if _is_land_candidate(*pt)]
                if not valid:
                    continue
                valid.sort(key=lambda pt: _candidate_score(*pt), reverse=True)
                cand_x, cand_y = valid[0]
                best = _consider_best_candidate(best, cand_x, cand_y, 2, 1)

            for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                cx, cy = x + dx, y + dy
                if not _is_land_candidate(cx, cy):
                    continue
                if _shore_degree(cx, cy) >= 2:
                    best = _consider_best_candidate(best, cx, cy, 1, 1)

            dirs = _shore_dirs(x, y)
            if len(dirs) == 1:
                only_dir = next(iter(dirs))
                opposite = {
                    "N": (0, 1),
                    "E": (-1, 0),
                    "S": (0, -1),
                    "W": (1, 0),
                }[only_dir]
                cx, cy = x + opposite[0], y + opposite[1]
                if _is_land_candidate(cx, cy) and _adjacent_water_count(cx, cy) > 0:
                    best = _consider_best_candidate(best, cx, cy, 0, 1)

            if best is not None:
                additions.add(best[1])

        if not additions:
            break
        shore_cells |= additions

    changed = True
    while changed:
        changed = False
        removals: set[tuple[int, int]] = set()
        for y in range(height - 1):
            for x in range(width - 1):
                block = {(x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)}
                if not block.issubset(shore_cells):
                    continue

                north_land = any(_output_cell(px, y - 1) not in WATER_CHARS for px in (x, x + 1))
                east_land = any(_output_cell(x + 2, py) not in WATER_CHARS for py in (y, y + 1))
                south_land = any(_output_cell(px, y + 2) not in WATER_CHARS for px in (x, x + 1))
                west_land = any(_output_cell(x - 1, py) not in WATER_CHARS for py in (y, y + 1))

                trim_target: tuple[int, int] | None = None
                if north_land and east_land and not south_land and not west_land:
                    trim_target = (x + 1, y)
                elif north_land and west_land and not south_land and not east_land:
                    trim_target = (x, y)
                elif south_land and west_land and not north_land and not east_land:
                    trim_target = (x, y + 1)
                elif south_land and east_land and not north_land and not west_land:
                    trim_target = (x + 1, y + 1)

                if trim_target is not None:
                    removals.add(trim_target)

        if removals:
            shore_cells -= removals
            changed = True

    # Enforce the shoreline-band invariant: any non-water terrain directly
    # adjacent to ocean-connected water must be shoreline.
    for y in range(height):
        for x in range(width):
            if (x, y) in shore_cells:
                continue
            ch = _cell(x, y)
            if ch not in land_chars:
                continue
            for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                if (x + dx, y + dy) in ocean_connected:
                    shore_cells.add((x, y))
                    break

    if shore_cells == {
        (x, y)
        for y in range(height)
        for x in range(width)
        if (ascii_lines[y][x] if x < len(ascii_lines[y]) else ".") == shore_char
    }:
        return ascii_lines

    new_lines = [list(row.ljust(width, ".")) for row in ascii_lines]
    for x, y in shore_cells:
        if new_lines[y][x] in land_chars:
            new_lines[y][x] = shore_char
        elif new_lines[y][x] == shore_char:
            new_lines[y][x] = shore_char
    for y in range(height):
        for x in range(width):
            if new_lines[y][x] == shore_char and (x, y) not in shore_cells:
                new_lines[y][x] = "G"
    return ["".join(row) for row in new_lines]


def close_lake_shoreline_gaps(
    ascii_lines: list[str],
    shore_char: str = "L",
    water_chars: frozenset[str] = WATER_CHARS,
    max_search_distance: int = 4,
    max_passes: int = 12,
) -> list[str]:
    """Promote water cells between L (lake shoreline) segments to L so the shoreline path is continuous via NESW."""
    height = len(ascii_lines)
    width = max((len(row) for row in ascii_lines), default=0)
    if width == 0 or height == 0:
        return ascii_lines

    shore_cells: set[tuple[int, int]] = set()
    for y in range(height):
        row = ascii_lines[y]
        for x in range(width):
            ch = row[x] if x < len(row) else "."
            if ch == shore_char:
                shore_cells.add((x, y))

    def _cell(px: int, py: int) -> str:
        if not (0 <= py < height and 0 <= px < width):
            return "."
        row = ascii_lines[py] if py < len(ascii_lines) else ""
        return row[px] if px < len(row) else "."

    def _is_water_candidate(px: int, py: int) -> bool:
        return _cell(px, py) in water_chars and (px, py) not in shore_cells

    def _shore_degree(px: int, py: int) -> int:
        count = 0
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            if (px + dx, py + dy) in shore_cells:
                count += 1
        return count

    def _shore_dirs(px: int, py: int) -> set[str]:
        dirs: set[str] = set()
        for name, dx, dy in (("N", 0, -1), ("E", 1, 0), ("S", 0, 1), ("W", -1, 0)):
            if (px + dx, py + dy) in shore_cells:
                dirs.add(name)
        return dirs

    def _candidate_score(px: int, py: int) -> tuple[int, int]:
        shore_neighbors = 0
        water_neighbors = 0
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            nx, ny = px + dx, py + dy
            if (nx, ny) in shore_cells:
                shore_neighbors += 1
            if _cell(nx, ny) in water_chars:
                water_neighbors += 1
        return (shore_neighbors, water_neighbors)

    def _adjacent_shore_count(px: int, py: int) -> int:
        count = 0
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            if (px + dx, py + dy) in shore_cells:
                count += 1
        return count

    def _consider_best_candidate(
        best: tuple[tuple[int, int, int, int], tuple[int, int]] | None,
        px: int,
        py: int,
        tier: int,
        distance: int,
    ) -> tuple[tuple[int, int, int, int], tuple[int, int]] | None:
        shore_neighbors, water_neighbors = _candidate_score(px, py)
        score = (tier, shore_neighbors, water_neighbors, -distance)
        ranked = (score, (px, py))
        if best is None or ranked[0] > best[0]:
            return ranked
        return best

    for _ in range(max_passes):
        additions: set[tuple[int, int]] = set()

        for y in range(height):
            for x in range(width):
                if not _is_water_candidate(x, y):
                    continue
                dirs = _shore_dirs(x, y)
                # Do NOT promote when water has L on all 4 sides: that's interior lake, not a gap.
                if len(dirs) == 4:
                    continue
                if len(dirs) >= 3 or {"N", "S"}.issubset(dirs) or {"E", "W"}.issubset(dirs):
                    additions.add((x, y))

        endpoints = [
            (x, y)
            for (x, y) in shore_cells
            if _shore_degree(x, y) < 2
        ]

        for x, y in endpoints:
            best: tuple[tuple[int, int, int, int], tuple[int, int]] | None = None
            for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                intermediates: list[tuple[int, int]] = []
                for dist in range(1, max_search_distance + 1):
                    nx, ny = x + dx * dist, y + dy * dist
                    if not (0 <= nx < width and 0 <= ny < height):
                        break
                    if (nx, ny) in shore_cells:
                        if intermediates:
                            cand_x, cand_y = intermediates[0]
                            best = _consider_best_candidate(best, cand_x, cand_y, 3, dist)
                        break
                    if not _is_water_candidate(nx, ny):
                        break
                    intermediates.append((nx, ny))

            for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                nx, ny = x + dx, y + dy
                if (nx, ny) not in shore_cells:
                    continue
                candidates = [
                    (x + dx, y),
                    (x, y + dy),
                ]
                valid = [pt for pt in candidates if _is_water_candidate(*pt)]
                if not valid:
                    continue
                valid.sort(key=lambda pt: _candidate_score(*pt), reverse=True)
                cand_x, cand_y = valid[0]
                best = _consider_best_candidate(best, cand_x, cand_y, 2, 1)

            for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                cx, cy = x + dx, y + dy
                if not _is_water_candidate(cx, cy):
                    continue
                if _shore_degree(cx, cy) >= 2:
                    best = _consider_best_candidate(best, cx, cy, 1, 1)

            dirs = _shore_dirs(x, y)
            if len(dirs) == 1:
                only_dir = next(iter(dirs))
                opposite = {
                    "N": (0, 1),
                    "E": (-1, 0),
                    "S": (0, -1),
                    "W": (1, 0),
                }[only_dir]
                cx, cy = x + opposite[0], y + opposite[1]
                if _is_water_candidate(cx, cy) and _adjacent_shore_count(cx, cy) > 0:
                    best = _consider_best_candidate(best, cx, cy, 0, 1)

            if best is not None:
                cand_x, cand_y = best[1]
                # Don't promote interior: water with L on all 4 sides stays water
                if len(_shore_dirs(cand_x, cand_y)) < 4:
                    additions.add(best[1])

        if not additions:
            break
        shore_cells |= additions

    if shore_cells == {
        (x, y)
        for y in range(height)
        for x in range(width)
        if (ascii_lines[y][x] if x < len(ascii_lines[y]) else ".") == shore_char
    }:
        return ascii_lines

    new_lines = [list(row.ljust(width, ".")) for row in ascii_lines]
    for x, y in shore_cells:
        if new_lines[y][x] in water_chars:
            new_lines[y][x] = shore_char
        elif new_lines[y][x] == shore_char:
            new_lines[y][x] = shore_char
    for y in range(height):
        for x in range(width):
            if new_lines[y][x] == shore_char and (x, y) not in shore_cells:
                new_lines[y][x] = "~"
    return ["".join(row) for row in new_lines]


def filter_isolated_lake_shoreline(
    ascii_lines: list[str],
    shore_char: str = "L",
    lake_chars: frozenset[str] | None = None,
    min_lake_neighbors: int = 1,
) -> list[str]:
    """Demote L cells with fewer than min_lake_neighbors NESW lake neighbors to G.
    Lake neighbors = water (~, `) or L. min=1 preserves single-edge shorelines (S, E, W banks)."""
    if lake_chars is None:
        lake_chars = WATER_CHARS | frozenset({shore_char})
    height = len(ascii_lines)
    width = max((len(row) for row in ascii_lines), default=0)
    if width == 0 or height == 0:
        return ascii_lines

    def _cell(lines_ref: list[list[str]], px: int, py: int) -> str:
        if not (0 <= py < height and 0 <= px < width):
            return "."
        row = lines_ref[py] if py < len(lines_ref) else []
        return row[px] if px < len(row) else "."

    def _lake_neighbor_count(lines_ref: list[list[str]], px: int, py: int) -> int:
        count = 0
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            if _cell(lines_ref, px + dx, py + dy) in lake_chars:
                count += 1
        return count

    lines = [list(row.ljust(width, ".")) for row in ascii_lines]
    changed = True
    while changed:
        changed = False
        for y in range(height):
            for x in range(width):
                if lines[y][x] != shore_char:
                    continue
                if _lake_neighbor_count(lines, x, y) < min_lake_neighbors:
                    lines[y][x] = "G"
                    changed = True
    return ["".join(row) for row in lines]


def propagate_shore_masks(
    ascii_lines: list[str],
    water_mask_grid: list[list[int]],
    shore_chars: frozenset[str] = SHORE_CHARS,
) -> list[list[int]]:
    """Propagate shoreline masks across connected B/L/R regions.

    The direct water mask is only non-zero for cells touching water. Expanded beach
    bands need that mask to continue through the rest of the connected shoreline
    region so dedicated shoreline sheets still paint correctly.
    """
    height = len(ascii_lines)
    width = max((len(row) for row in ascii_lines), default=0)
    propagated = [row[:] for row in water_mask_grid]
    pending: set[tuple[int, int]] = set()

    for y in range(height):
        row = ascii_lines[y]
        for x in range(width):
            ch = row[x] if x < len(row) else "."
            if ch in shore_chars and propagated[y][x] == 0:
                pending.add((x, y))

    while pending:
        changed = False
        next_pending: set[tuple[int, int]] = set()
        for x, y in pending:
            row = ascii_lines[y] if y < height else ""
            ch = row[x] if x < len(row) else "."
            if ch not in shore_chars:
                continue

            inferred = 0
            for dx, dy, our_bit, their_bit in SHORE_MASK_PROPAGATION_RULES:
                nx, ny = x + dx, y + dy
                if not (0 <= nx < width and 0 <= ny < height):
                    continue
                nrow = ascii_lines[ny] if ny < height else ""
                nch = nrow[nx] if nx < len(nrow) else "."
                if nch != ch:
                    continue
                if propagated[ny][nx] & their_bit:
                    inferred |= our_bit

            if inferred:
                propagated[y][x] = inferred
                changed = True
            else:
                next_pending.add((x, y))

        if not changed:
            break
        pending = next_pending

    return propagated


def get_hill_adjacency_bitmask(
    ascii_lines: list[str],
    x: int,
    y: int,
    hill_char: str = "I",
) -> int:
    """Compute 4-bit hill adjacency. N=1, E=2, S=4, W=8. Returns 0-15."""
    height = len(ascii_lines)
    width = max(len(row) for row in ascii_lines) if ascii_lines else 0

    def is_hill(px: int, py: int) -> bool:
        if py < 0 or py >= height or px < 0 or px >= width:
            return False
        row = ascii_lines[py]
        ch = row[px] if px < len(row) else "."
        return ch == hill_char

    mask = 0
    if is_hill(x, y - 1):
        mask |= 1  # North
    if is_hill(x + 1, y):
        mask |= 2  # East
    if is_hill(x, y + 1):
        mask |= 4  # South
    if is_hill(x - 1, y):
        mask |= 8  # West
    return mask


def get_path_bitmask(
    ascii_lines: list[str],
    x: int,
    y: int,
    path_chars: frozenset[str] = PATH_CHARS,
) -> int:
    """Compute 4-bit path connectivity bitmask for cell (x,y).
    Bits: N=1, E=2, S=4, W=8. Returns 0-15."""
    height = len(ascii_lines)
    width = max(len(row) for row in ascii_lines) if ascii_lines else 0

    def is_path(px: int, py: int) -> bool:
        if py < 0 or py >= height or px < 0 or px >= width:
            return False
        row = ascii_lines[py]
        ch = row[px] if px < len(row) else "."
        return ch in path_chars

    mask = 0
    if is_path(x, y - 1):
        mask |= 1  # North
    if is_path(x + 1, y):
        mask |= 2  # East
    if is_path(x, y + 1):
        mask |= 4  # South
    if is_path(x - 1, y):
        mask |= 8  # West
    return mask


def load_water_tiles(
    water_path: Path,
    tile_size: int,
) -> list[Any]:
    """Load water tiles from PNG. If sheet has 2+ tiles (horizontal), returns [shallow, deep, ...].
    Otherwise returns single-tile list (shallow only)."""
    Image = _ensure_pillow()
    img = Image.open(water_path)
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    w, h = img.size
    cols = w // tile_size
    rows = h // tile_size
    if cols * rows >= 2:
        tiles: list[Any] = []
        for r in range(rows):
            for c in range(cols):
                x, y = c * tile_size, r * tile_size
                if x + tile_size > w or y + tile_size > h:
                    continue
                tile = img.crop((x, y, x + tile_size, y + tile_size))
                if tile.width != tile_size or tile.height != tile_size:
                    tile = tile.resize(
                        (tile_size, tile_size), Image.Resampling.NEAREST
                    )
                tiles.append(tile)
        return tiles
    if w != tile_size or h != tile_size:
        img = img.resize((tile_size, tile_size), Image.Resampling.NEAREST)
    return [img]


def load_dirt_tiles(
    dirt_path: Path,
    tile_size: int,
) -> list[Any]:
    """Load dirt tiles from PNG. If image is a 4x4 sheet (64x64 for 16px tiles),
    returns 16 tiles in row-major order (bitmask index 0-15). Otherwise returns
    a single-tile list (replicated for fallback)."""
    Image = _ensure_pillow()
    img = Image.open(dirt_path)
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    w, h = img.size
    cols = w // tile_size
    rows = h // tile_size
    if cols >= 4 and rows >= 4:
        # Treat as 16-tile autotile sheet (4x4)
        tiles: list[Any] = []
        for r in range(4):
            for c in range(4):
                x, y = c * tile_size, r * tile_size
                tile = img.crop((x, y, x + tile_size, y + tile_size))
                if tile.width != tile_size or tile.height != tile_size:
                    tile = tile.resize(
                        (tile_size, tile_size), Image.Resampling.NEAREST
                    )
                tiles.append(tile)
        return tiles
    # Single tile
    if w != tile_size or h != tile_size:
        img = img.resize((tile_size, tile_size), Image.Resampling.NEAREST)
    return [img]


def export_treeset_to_png(
    treeset_path: Path,
    out_png: Path,
    aseprite_bin: Path,
    *,
    sheet_columns: int | None = None,
    out_json: Path | None = None,
) -> None:
    """Export treeset .aseprite to PNG sheet via Aseprite CLI.
    sheet_columns: use rows layout with this many columns to match tileset grid (e.g. 11 for grass).
    out_json: optional path to export --data JSON for tile positions."""
    cmd = [
        str(aseprite_bin),
        "-b",
        str(treeset_path),
        "--sheet",
        str(out_png),
        "--sheet-type",
        "rows" if sheet_columns else "horizontal",
    ]
    if sheet_columns:
        cmd.extend(["--sheet-columns", str(sheet_columns)])
    if out_json:
        cmd.extend(["--data", str(out_json)])
    subprocess.run(cmd, check=True, capture_output=True)


def paint_map_to_png(
    *,
    ascii_lines: list[str],
    legend: dict[str, int],
    tile_rows: list[list[int]],
    tile_size: int,
    trees_sheet_path: Path,
    treeset_cols: int = TREESET_COLS,
    treeset_rows: int = TREESET_ROWS,
    water_out: Path,
    grass_out: Path,
    water_shallow_out: Path | None = None,
    water_deep_out: Path | None = None,
    water_lake_out: Path | None = None,
    water_river_out: Path | None = None,
    dirt_out: Path,
    trees_out: Path,
    poi_out: Path | None = None,
    poi_layers_out: dict[str, Path] | None = None,
    shoreline_out: Path | None = None,
    lakebank_out: Path | None = None,
    hill_out: Path | None = None,
    grass_dir: Path | None = None,
    grass_sheet_path: Path | None = None,
    grass_tile_range: tuple[int, int] | None = (19, 30),
    grass_shoreline_range: tuple[int, int] | None = (1, 56),
    grass_shoreline_lake_range: tuple[int, int] | None = (4, 18),
    grass_shoreline_extended_range: tuple[int, int] | None = None,
    grass_shoreline_river_range: tuple[int, int] | None = None,
    grass_bitmask_config: dict[str, Any] | None = None,
    grass_json_path: Path | None = None,
    shoreline_sheet_path: Path | None = None,
    lakesrivers_sheet_path: Path | None = None,
    water_path: Path | None = None,
    dirt_path: Path | None = None,
    hill_path: Path | None = None,
    grass_tile_names: list[str] | None = None,
    water_border_width: int = 2,
    ascii_water_border: int = 2,
    seed: int = 42,
    strict: bool = False,
) -> None:
    """Composite grass and trees layers to PNGs using PIL."""
    Image = _ensure_pillow()
    rng = random.Random(seed)

    # Apply bitmask config overrides when provided
    cfg = grass_bitmask_config or {}
    if cfg.get("grass_tile_range"):
        r = cfg["grass_tile_range"]
        grass_tile_range = (r[0], r[1]) if len(r) >= 2 else grass_tile_range
    if cfg.get("grass_shoreline_range"):
        r = cfg["grass_shoreline_range"]
        grass_shoreline_range = (r[0], r[1]) if len(r) >= 2 else grass_shoreline_range
    if cfg.get("grass_shoreline_lake_range"):
        r = cfg["grass_shoreline_lake_range"]
        grass_shoreline_lake_range = (r[0], r[1]) if len(r) >= 2 else grass_shoreline_lake_range
    if cfg.get("grass_shoreline_extended_range"):
        r = cfg["grass_shoreline_extended_range"]
        grass_shoreline_extended_range = (r[0], r[1]) if len(r) >= 2 else grass_shoreline_extended_range
    if cfg.get("grass_shoreline_river_range"):
        r = cfg["grass_shoreline_river_range"]
        grass_shoreline_river_range = (r[0], r[1]) if len(r) >= 2 else grass_shoreline_river_range
    grass_hill_range: tuple[int, int] | None = None
    if cfg.get("hill") and isinstance(cfg["hill"], dict):
        hr = cfg["hill"].get("range")
        if isinstance(hr, (list, tuple)) and len(hr) >= 2:
            grass_hill_range = (int(hr[0]), int(hr[1]))
    def _to_int_map(d: dict | None) -> dict[int, int]:
        out: dict[int, int] = {}
        for k, v in (d or {}).items():
            try:
                out[int(k)] = int(v)
            except (ValueError, TypeError):
                continue
        return out

    _gs = _to_int_map(cfg.get("grass_shoreline"))
    grass_shoreline_map = _gs if _gs else dict(GRASS_SHORELINE_MAP)
    # When using dedicated shoreline sheet: optional direct bitmask->tile mapping (1-based in that sheet)
    shoreline_cfg = cfg.get("shoreline")
    shoreline_map: dict[int, int] | None = None
    shoreline_range: tuple[int, int] = (1, 21)
    shoreline_special_tiles: dict[str, int] = {}
    shoreline_inset_edge_tiles: dict[str, int] = {}
    shoreline_inset_direct_corner_tiles: dict[str, int] = {}
    shoreline_inset_corner_tiles: dict[str, int] = {}
    if isinstance(shoreline_cfg, dict):
        _sm = _to_int_map(shoreline_cfg.get("shoreline_map"))
        if _sm:
            shoreline_map = _sm
        sr = shoreline_cfg.get("range")
        if isinstance(sr, (list, tuple)) and len(sr) >= 2:
            shoreline_range = (int(sr[0]), int(sr[1]))
        special_tiles_cfg = shoreline_cfg.get("special_tiles")
        if isinstance(special_tiles_cfg, dict):
            for key in ("lake_east", "tee_west", "tee_east"):
                try:
                    if special_tiles_cfg.get(key) is not None:
                        shoreline_special_tiles[key] = int(special_tiles_cfg[key])
                except (TypeError, ValueError):
                    continue
        inset_corner_cfg = shoreline_cfg.get("inset_corner_tiles")
        if isinstance(inset_corner_cfg, dict):
            for key in ("top_left", "top_right", "bottom_left", "bottom_right"):
                try:
                    if inset_corner_cfg.get(key) is not None:
                        shoreline_inset_corner_tiles[key] = int(inset_corner_cfg[key])
                except (TypeError, ValueError):
                    continue
        inset_direct_corner_cfg = shoreline_cfg.get("inset_direct_corner_tiles")
        if isinstance(inset_direct_corner_cfg, dict):
            for key in ("top_left", "top_right", "bottom_left", "bottom_right"):
                try:
                    if inset_direct_corner_cfg.get(key) is not None:
                        shoreline_inset_direct_corner_tiles[f"direct_{key}"] = int(inset_direct_corner_cfg[key])
                except (TypeError, ValueError):
                    continue
        inset_edge_cfg = shoreline_cfg.get("inset_edge_tiles")
        if isinstance(inset_edge_cfg, dict):
            for key in ("top", "right", "bottom", "left", "center"):
                try:
                    if inset_edge_cfg.get(key) is not None:
                        shoreline_inset_edge_tiles[key] = int(inset_edge_cfg[key])
                except (TypeError, ValueError):
                    continue
    _ls = _to_int_map(cfg.get("lake_shoreline"))
    lake_shoreline_map = _ls if _ls else dict(LAKE_SHORELINE_MAP)
    # When using lakesrivers.aseprite: optional direct bitmask->tile mapping
    lake_cfg = cfg.get("lake")
    lake_map_override: dict[int, int] | None = None
    lake_special_tiles: dict[str, int] = {}
    lake_range_override: tuple[int, int] = (1, 9)
    if isinstance(lake_cfg, dict):
        _lm = _to_int_map(lake_cfg.get("lake_map"))
        if _lm:
            lake_map_override = _lm
        _lst = _to_int_map(lake_cfg.get("special_tiles"))
        if _lst:
            lake_special_tiles = _lst
        lr = lake_cfg.get("range")
        if isinstance(lr, (list, tuple)) and len(lr) >= 2:
            lake_range_override = (int(lr[0]), int(lr[1]))
    # Extend lake range to include special tiles and interior lake tiles (49-52)
    lake_load_end = lake_range_override[1]
    if lake_special_tiles:
        lake_load_end = max(lake_load_end, max(lake_special_tiles.values()))
    interior_lake_tiles: list[int] = []
    if isinstance(lake_cfg, dict):
        _ilt = lake_cfg.get("interior_lake_tiles")
        if isinstance(_ilt, (list, tuple)) and len(_ilt) >= 4:
            interior_lake_tiles = [int(_ilt[i]) for i in range(4)]
            lake_load_end = max(lake_load_end, max(interior_lake_tiles))
    lake_load_range: tuple[int, int] = (lake_range_override[0], lake_load_end)
    river_cfg = cfg.get("river")
    river_map_override: dict[int, int] | None = None
    river_range_override: tuple[int, int] = (10, 11)
    if isinstance(river_cfg, dict):
        _rm = _to_int_map(river_cfg.get("river_map"))
        if _rm:
            river_map_override = _rm
        rr = river_cfg.get("range")
        if isinstance(rr, (list, tuple)) and len(rr) >= 2:
            river_range_override = (int(rr[0]), int(rr[1]))
    _hill = _to_int_map(cfg.get("hill_map") or (cfg.get("hill") or {}).get("hill_map"))
    hill_map = _hill if _hill else dict(HILL_MAP)
    extended_masks = tuple(cfg.get("extended_shoreline_masks") or EXTENDED_SHORELINE_MASKS)
    river_masks = tuple(cfg.get("river_masks") or RIVER_MASKS)
    interior_corner_masks = tuple(cfg.get("interior_corner_masks") or INTERIOR_CORNER_MASKS)

    width = max(len(row) for row in ascii_lines) if ascii_lines else 0
    height = len(ascii_lines)
    if width == 0 or height == 0:
        raise ValueError("ASCII map is empty")

    # If ASCII already has water border (first row all ~), don't add another
    first_row = ascii_lines[0] if ascii_lines else ""
    ascii_has_border = len(first_row) >= 2 and all(c == WATER_CHAR for c in first_row)
    border = 0 if ascii_has_border else max(0, water_border_width)
    # For water adjacency: treat map edge as water so bottom/right edge tiles get shoreline
    adjacency_border = ascii_water_border if ascii_has_border else max(0, water_border_width)
    out_w = (width + 2 * border) * tile_size
    out_h = (height + 2 * border) * tile_size
    ox, oy = border * tile_size, border * tile_size

    # Load grass tiles: interior, continent, lake, river, extended (peninsula/island)
    grass_interior: list[Any] = []
    grass_shoreline: list[Any] = []
    grass_shoreline_lake: list[Any] = []
    grass_shoreline_river: list[Any] = []
    grass_shoreline_extended: list[Any] = []
    grass_hill: list[Any] = []
    if grass_sheet_path and grass_sheet_path.exists():
        _json = grass_json_path
        grass_interior = load_grass_from_sheet(
            grass_sheet_path, tile_size, tile_range=grass_tile_range, tileset_json_path=_json
        )
        if grass_shoreline_range:
            if shoreline_sheet_path and shoreline_sheet_path.exists():
                # Use dedicated shorelines.aseprite; range from config (default 1-21)
                grass_shoreline = load_grass_from_sheet(
                    shoreline_sheet_path, tile_size, tile_range=shoreline_range, tileset_json_path=None
                )
            else:
                grass_shoreline = load_grass_from_sheet(
                    grass_sheet_path, tile_size, tile_range=grass_shoreline_range, tileset_json_path=_json
                )
        if grass_shoreline_lake_range or lakesrivers_sheet_path:
            if lakesrivers_sheet_path and lakesrivers_sheet_path.exists():
                grass_shoreline_lake = load_grass_from_sheet(
                    lakesrivers_sheet_path, tile_size, tile_range=lake_load_range, tileset_json_path=None
                )
            elif grass_shoreline_lake_range:
                grass_shoreline_lake = load_grass_from_sheet(
                    grass_sheet_path, tile_size, tile_range=grass_shoreline_lake_range, tileset_json_path=_json
                )
        if grass_shoreline_extended_range:
            grass_shoreline_extended = load_grass_from_sheet(
                grass_sheet_path, tile_size, tile_range=grass_shoreline_extended_range, tileset_json_path=_json
            )
        if grass_shoreline_river_range or lakesrivers_sheet_path:
            if lakesrivers_sheet_path and lakesrivers_sheet_path.exists():
                grass_shoreline_river = load_grass_from_sheet(
                    lakesrivers_sheet_path, tile_size, tile_range=river_range_override, tileset_json_path=None
                )
            elif grass_shoreline_river_range:
                grass_shoreline_river = load_grass_from_sheet(
                    grass_sheet_path, tile_size, tile_range=grass_shoreline_river_range, tileset_json_path=_json
                )
        if grass_hill_range and not hill_path:
            grass_hill = load_grass_from_sheet(
                grass_sheet_path, tile_size, tile_range=grass_hill_range, tileset_json_path=_json
            )
    # Load lake/river from lakesrivers when set (even without grass_sheet_path)
    if lakesrivers_sheet_path and lakesrivers_sheet_path.exists():
        if not grass_shoreline_lake:
            grass_shoreline_lake = load_grass_from_sheet(
                lakesrivers_sheet_path, tile_size, tile_range=lake_load_range, tileset_json_path=None
            )
        if not grass_shoreline_river:
            grass_shoreline_river = load_grass_from_sheet(
                lakesrivers_sheet_path, tile_size, tile_range=river_range_override, tileset_json_path=None
            )
    if hill_path and hill_path.exists():
        hill_range = grass_hill_range or (1, 37)
        hill_json = hill_path.parent / (hill_path.stem + ".json")
        grass_hill = load_grass_from_sheet(
            hill_path, tile_size, tile_range=hill_range, tileset_json_path=hill_json if hill_json.exists() else None
        )
        grass_hill_range = hill_range
    elif grass_dir and grass_dir.exists() and grass_dir.is_dir():
        grass_interior = load_grass_tiles(grass_dir, tile_size, grass_tile_names)
        grass_shoreline = grass_interior
        if not grass_shoreline_lake:
            grass_shoreline_lake = grass_interior
        if not grass_shoreline_river:
            grass_shoreline_river = grass_interior
        grass_shoreline_extended = grass_interior
        if not grass_hill:
            grass_hill = grass_interior
    grass_imgs = grass_interior if grass_interior else []
    grass_cfg = cfg.get("grass") if isinstance(cfg.get("grass"), dict) else {}
    grass_default_weight = float(grass_cfg.get("default_weight", 0.55))
    grass_default_weight = max(0.5, min(1.0, grass_default_weight))
    # Use grass.default (1-based tile id, e.g. 1) so tile 1 is default, not tile 13
    grass_default_tile = int(grass_cfg.get("default", 1))
    grass_default_idx = max(0, grass_default_tile - grass_tile_range[0]) if grass_tile_range else 0

    def _pick_interior_grass() -> Any:
        if not grass_imgs:
            return None
        # strict: always use grass.default (legend-based, deterministic)
        if strict:
            idx = min(grass_default_idx, len(grass_imgs) - 1)
            return grass_imgs[idx]
        # Use grass.default (tile 1) as default; config ensures correct index
        if rng.random() < grass_default_weight or len(grass_imgs) == 1:
            idx = min(grass_default_idx, len(grass_imgs) - 1)
            return grass_imgs[idx]
        # Variations: prefer tile 2 (index 1) when available, else random
        if grass_default_idx == 0 and len(grass_imgs) >= 2 and rng.random() < 0.6:
            return grass_imgs[1]
        idx = rng.randint(1, len(grass_imgs) - 1)
        return grass_imgs[idx]

    # Load water tiles (optional): [shallow, deep] or [shallow] for single-tile
    water_tiles: list[Any] = []
    if water_path and water_path.exists():
        water_tiles = load_water_tiles(water_path, tile_size)

    # Load dirt tiles (optional, for P = path cells). Sheet = 16 tiles by connectivity.
    dirt_tiles: list[Any] = []
    if dirt_path and dirt_path.exists():
        dirt_tiles = load_dirt_tiles(dirt_path, tile_size)

    # Load trees sheet and split into tiles (row-major: index = row*cols + col)
    trees_img = Image.open(trees_sheet_path)
    if trees_img.mode != "RGBA":
        trees_img = trees_img.convert("RGBA")
    sheet_w, sheet_h = trees_img.size
    tw = sheet_w // treeset_cols
    th = sheet_h // treeset_rows
    tree_tiles: list[Any] = []
    for r in range(treeset_rows):
        for c in range(treeset_cols):
            x, y = c * tw, r * th
            tile = trees_img.crop((x, y, x + tw, y + th))
            if tw != tile_size or th != tile_size:
                tile = tile.resize((tile_size, tile_size), Image.Resampling.NEAREST)
            tree_tiles.append(tile)

    # Build layers (order: water, grass, dirt, trees - ascending)
    color_tiles: dict[tuple[int, int, int, int], Any] = {}

    use_separate_water = all(
        p is not None for p in (water_shallow_out, water_deep_out, water_lake_out, water_river_out)
    )
    water_layer = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
    water_shallow_layer = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0)) if use_separate_water else None
    water_deep_layer = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0)) if use_separate_water else None
    water_lake_layer = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0)) if use_separate_water else None
    water_river_layer = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0)) if use_separate_water else None

    # Precompute ocean and river water for separate layers
    ocean_connected: set[tuple[int, int]] = set()
    river_cells: set[tuple[int, int]] = set()
    if width > 0 and height > 0:
        ocean_connected = _ocean_connected_water_cells(ascii_lines, width, height)
    if use_separate_water and width > 0 and height > 0:
        river_cells = _river_water_cells(ascii_lines, width, height)
    grass_layer = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
    shoreline_layer = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0)) if shoreline_out else None
    lakebank_layer = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0)) if lakebank_out else None
    hill_layer = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0)) if hill_out else None
    dirt_layer = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
    trees_layer = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
    poi_layer = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
    poi_layers: dict[str, Any] = {
        name: Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
        for name in POI_LAYERS
    }

    def _is_water_in_output(gx: int, gy: int) -> bool:
        """True if output cell (gx, gy) is water (border or ~ or `)."""
        if gx < border or gx >= width + border or gy < border or gy >= height + border:
            return True
        cx, cy = gx - border, gy - border
        ch = ascii_lines[cy][cx] if cy < len(ascii_lines) and cx < len(ascii_lines[cy]) else "."
        return ch in WATER_CHARS

    water_shallow = water_tiles[0] if water_tiles else None
    water_deep = water_tiles[1] if len(water_tiles) >= 2 else water_shallow

    def _paste_water(dest: Any, tile: Any, px: int, py: int) -> None:
        if dest is None:
            return
        dest.paste(tile, (px, py))

    # Precompute water masks for all cells (for B/L/R propagation when wmask=0)
    water_mask_grid: list[list[int]] = [
        [0] * width
        for _ in range(height)
    ]
    for py in range(height):
        for px in range(width):
            m, _ = get_water_adjacency_with_type(
                ascii_lines, px, py,
                border_width=adjacency_border, ascii_water_border=ascii_water_border,
                ocean_connected=ocean_connected,
            )
            water_mask_grid[py][px] = m
    shore_ascii_lines = close_ocean_shoreline_gaps(ascii_lines)
    # Only promote shallow water (~) to L; never promote deep water (`) - lake shorelines cannot be on deep water
    shore_ascii_lines = close_lake_shoreline_gaps(
        shore_ascii_lines, water_chars=frozenset([WATER_CHAR])
    )
    shore_ascii_lines = filter_isolated_lake_shoreline(shore_ascii_lines)
    shore_mask_grid = propagate_shore_masks(shore_ascii_lines, water_mask_grid)

    def _adjacent_to_shoreline_cell(ax: int, ay: int) -> bool:
        """True if cell (ax, ay) touches any B/L/R cell."""
        for ddx, ddy in [(0, -1), (1, 0), (0, 1), (-1, 0)]:
            nx, ny = ax + ddx, ay + ddy
            if 0 <= ny < height and 0 <= nx < width:
                nrow = shore_ascii_lines[ny] if ny < len(shore_ascii_lines) else ""
                nch = nrow[nx] if nx < len(nrow) else "."
                if nch in SHORE_CHARS:
                    return True
        return False

    def _adjacent_to_lake_shoreline_cell(ax: int, ay: int) -> bool:
        """True if cell (ax, ay) touches an L/R shoreline cell."""
        for ddx, ddy in [(0, -1), (1, 0), (0, 1), (-1, 0)]:
            nx, ny = ax + ddx, ay + ddy
            if 0 <= ny < height and 0 <= nx < width:
                nrow = ascii_lines[ny] if ny < len(ascii_lines) else ""
                nch = nrow[nx] if nx < len(nrow) else "."
                if nch in ("L", "R"):
                    return True
        return False

    def _get_ascii_cell(ax: int, ay: int) -> str:
        if not (0 <= ay < height and 0 <= ax < width):
            return "."
        row = shore_ascii_lines[ay] if ay < len(shore_ascii_lines) else ""
        return row[ax] if ax < len(row) else "."

    def _shoreline_sheet_tile_for_mask(mask: int) -> int:
        if shoreline_map is not None:
            return shoreline_map.get(mask, shoreline_range[0])
        tile_idx = grass_shoreline_map.get(mask, grass_shoreline_range[0])
        return (tile_idx - 97) if tile_idx >= 98 else tile_idx

    def _get_ocean_shoreline_tile_index(ax: int, ay: int) -> int | None:
        if _get_ascii_cell(ax, ay) != "B":
            return None
        base_mask = 0
        if 0 <= ay < len(water_mask_grid) and 0 <= ax < len(water_mask_grid[ay]):
            base_mask = water_mask_grid[ay][ax]
        eff_mask = (
            base_mask
            if base_mask != 0
            else shore_mask_grid[ay][ax]
            if 0 <= ay < len(shore_mask_grid) and 0 <= ax < len(shore_mask_grid[ay])
            else 0
        )
        eff_mask = _propagated_shore_mask(ax, ay, eff_mask)
        if eff_mask == 0:
            return None
        return _shoreline_sheet_tile_for_mask(eff_mask)

    def _get_ocean_inset_special_tile(ax: int, ay: int, *, allow_shore_cell: bool = False) -> int | None:
        """Return a special ocean inset edge/corner shoreline tile for inland connector cells."""
        if not shoreline_inset_corner_tiles and not shoreline_inset_edge_tiles:
            return None
        if _adjacent_to_lake_shoreline_cell(ax, ay):
            return None
        ch = _get_ascii_cell(ax, ay)
        if allow_shore_cell:
            if ch != "B":
                return None
        elif ch not in frozenset("G.PITF") | POI_CHARS:
            return None
        has_n = _get_ascii_cell(ax, ay - 1) == "B"
        has_e = _get_ascii_cell(ax + 1, ay) == "B"
        has_s = _get_ascii_cell(ax, ay + 1) == "B"
        has_w = _get_ascii_cell(ax - 1, ay) == "B"
        has_ne = _get_ascii_cell(ax + 1, ay - 1) == "B"
        has_se = _get_ascii_cell(ax + 1, ay + 1) == "B"
        has_sw = _get_ascii_cell(ax - 1, ay + 1) == "B"
        has_nw = _get_ascii_cell(ax - 1, ay - 1) == "B"
        if has_n and has_e and has_s and has_w:
            return resolve_center_ocean_inset_tile(
                _get_ocean_shoreline_tile_index(ax, ay - 1),
                _get_ocean_shoreline_tile_index(ax + 1, ay),
                shoreline_inset_edge_tiles,
            )
        pattern = get_ocean_inset_pattern(
            has_n,
            has_e,
            has_s,
            has_w,
            has_ne=has_ne,
            has_se=has_se,
            has_sw=has_sw,
            has_nw=has_nw,
        )
        if pattern is None:
            return None
        if not allow_shore_cell and _ocean_inset_notch_continues(ax, ay, pattern):
            return None
        if pattern == "bottom":
            return resolve_bottom_ocean_inset_tile(
                _get_ocean_shoreline_tile_index(ax, ay - 1),
                shoreline_inset_edge_tiles,
                shoreline_inset_direct_corner_tiles,
            )
        return match_ocean_inset_special_tile(
            has_n,
            has_e,
            has_s,
            has_w,
            shoreline_inset_edge_tiles,
            shoreline_inset_corner_tiles,
            direct_corner_tiles=shoreline_inset_direct_corner_tiles,
            has_ne=has_ne,
            has_se=has_se,
            has_sw=has_sw,
            has_nw=has_nw,
        )

    def _ocean_inset_notch_continues(ax: int, ay: int, pattern: str) -> bool:
        """Treat inset helpers as connectors only when they have less than two shoreline links."""
        return count_adjacent_shoreline_cells(shore_ascii_lines, ax, ay) >= 2

    def _propagated_shore_mask(cx: int, cy: int, base_mask: int) -> int:
        """Infer shoreline mask from neighboring B/L/R cells for inset connectors."""
        if base_mask != 0:
            return base_mask
        row = shore_ascii_lines[cy] if cy < len(shore_ascii_lines) else ""
        ch = row[cx] if cx < len(row) else "."
        if ch not in SHORE_CHARS and not _adjacent_to_shoreline_cell(cx, cy):
            return base_mask
        propagated = 0
        for dx, dy, our_bit, their_bit in SHORE_MASK_PROPAGATION_RULES:
            nx, ny = cx + dx, cy + dy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            nrow = shore_ascii_lines[ny] if ny < len(shore_ascii_lines) else ""
            nch = nrow[nx] if nx < len(nrow) else "."
            if nch not in SHORE_CHARS:
                continue
            nmask = shore_mask_grid[ny][nx]
            if nmask & their_bit:
                propagated |= our_bit
        return propagated if propagated else base_mask

    def _lake_mask_at(px: int, py: int) -> int:
        m = get_water_adjacency_bitmask(
            shore_ascii_lines, px, py, water_chars=LAKE_WATER_CHARS, border_width=0
        )
        return _lake_mask_with_diagonal_inference(
            shore_ascii_lines, px, py, m, LAKE_WATER_CHARS
        )

    # Fill water border (2 tiles wide around map) - shallow water; no grass (grass covers water)
    if border > 0 and water_shallow is not None:
        for by in range(out_h // tile_size):
            for bx in range(out_w // tile_size):
                if bx < border or bx >= width + border or by < border or by >= height + border:
                    _paste_water(water_layer, water_shallow, bx * tile_size, by * tile_size)
                    if water_shallow_layer is not None:
                        _paste_water(water_shallow_layer, water_shallow, bx * tile_size, by * tile_size)

    for y, row in enumerate(ascii_lines):
        for x in range(width):
            ch = row[x] if x < len(row) else "."
            if ch == "":
                ch = "."
            shore_row = shore_ascii_lines[y] if y < len(shore_ascii_lines) else ""
            shore_ch = shore_row[x] if x < len(shore_row) else ch
            # Use shore_ch for B/L/R (promoted water->L); never paint grass/trees on pure water
            display_ch = shore_ch if shore_ch in ("B", "L", "R") else ("G" if ch in ("T", "F") else ch)
            is_pure_water = ch in WATER_CHARS and shore_ch not in ("B", "L", "R")
            dx, dy = ox + x * tile_size, oy + y * tile_size

            # Water layer: ~ cells and underneath shoreline tiles (G, ., P, T, F adjacent to water)
            wmask, is_lake = get_water_adjacency_with_type(
                ascii_lines,
                x,
                y,
                border_width=adjacency_border,
                ascii_water_border=ascii_water_border,
                ocean_connected=ocean_connected,
            )

            # Dirt: skip on shoreline and within 1 tile of shoreline (per terrain rules)
            def _within_1_of_shoreline(px: int, py: int) -> bool:
                for ddx, ddy in [(0, 0), (0, -1), (1, 0), (0, 1), (-1, 0)]:
                    nx, ny = px + ddx, py + ddy
                    if 0 <= nx < width and 0 <= ny < height:
                        nr = shore_ascii_lines[ny] if ny < len(shore_ascii_lines) else ""
                        nc = nr[nx] if nx < len(nr) else "."
                        if nc in ("B", "L", "R"):
                            return True
                return False

            skip_dirt = _within_1_of_shoreline(x, y)

            # Land with 3+ water neighbors: treat as water (water already pasted), skip grass
            # Prevents grass from being painted on water tiles
            def _water_neighbor_count(px: int, py: int) -> int:
                count = 0
                for ddx, ddy in [(0, -1), (1, 0), (0, 1), (-1, 0)]:
                    nx, ny = px + ddx, py + ddy
                    if 0 <= nx < width and 0 <= ny < height:
                        r = ascii_lines[ny] if ny < len(ascii_lines) else ""
                        nc = r[nx] if nx < len(r) else "."
                        if nc in LAKE_WATER_CHARS:
                            count += 1
                return count

            _water_count = _water_neighbor_count(x, y)
            is_land_surrounded_by_water = (
                (ch in ("G", ".", "P", "T", "F") or ch in POI_CHARS)
                and (x, y) not in ocean_connected
                and _water_count >= 3
            )

            if water_shallow is not None:
                if ch in WATER_CHARS:
                    wt = water_deep if ch == DEEP_WATER_CHAR else water_shallow
                    water_layer.paste(wt, (dx, dy))
                    if use_separate_water:
                        if (x, y) in river_cells:
                            _paste_water(water_river_layer, water_shallow, dx, dy)
                        elif (x, y) in ocean_connected:
                            _paste_water(water_deep_layer if ch == DEEP_WATER_CHAR else water_shallow_layer, wt, dx, dy)
                        else:
                            _paste_water(water_lake_layer, wt, dx, dy)
                elif wmask != 0 and (ch in ("G", ".", "B", "L", "R", "P", "T", "F") or ch in POI_CHARS):
                    water_layer.paste(water_shallow, (dx, dy))
                    if use_separate_water:
                        adj_river = any(
                            (x + ddx, y + ddy) in river_cells
                            for ddx, ddy in [(0, -1), (1, 0), (0, 1), (-1, 0)]
                            if 0 <= x + ddx < width and 0 <= y + ddy < height
                        )
                        adj_ocean = any(
                            (x + ddx, y + ddy) in ocean_connected
                            for ddx, ddy in [(0, -1), (1, 0), (0, 1), (-1, 0)]
                            if 0 <= x + ddx < width and 0 <= y + ddy < height
                        )
                        if adj_river:
                            _paste_water(water_river_layer, water_shallow, dx, dy)
                        elif adj_ocean:
                            _paste_water(water_shallow_layer, water_shallow, dx, dy)
                        else:
                            _paste_water(water_lake_layer, water_shallow, dx, dy)
                # Shallow water with N=deep, E=shallow, S=land, W=shallow: use tile 6 (deep-to-land transition)
                if (
                    ch == WATER_CHAR
                    and (x, y) not in ocean_connected
                    and lakebank_layer
                    and grass_shoreline_lake
                    and lake_special_tiles
                ):
                    def _raw_cell(px: int, py: int) -> str:
                        if not (0 <= py < height and 0 <= px < width):
                            return "."
                        r = ascii_lines[py] if py < len(ascii_lines) else ""
                        return r[px] if px < len(r) else "."
                    n_raw = _raw_cell(x, y - 1)
                    e_raw = _raw_cell(x + 1, y)
                    s_raw = _raw_cell(x, y + 1)
                    w_raw = _raw_cell(x - 1, y)
                    deep_n_shallow_ew_land_s = lake_special_tiles.get("deep_n_shallow_ew_land_s")
                    if (
                        deep_n_shallow_ew_land_s is not None
                        and n_raw == DEEP_WATER_CHAR
                        and e_raw == WATER_CHAR
                        and s_raw not in WATER_CHARS
                        and w_raw == WATER_CHAR
                    ):
                        if lake_load_range[0] <= deep_n_shallow_ew_land_s <= lake_load_range[1]:
                            idx = deep_n_shallow_ew_land_s - lake_load_range[0]
                            if 0 <= idx < len(grass_shoreline_lake):
                                lakebank_layer.paste(grass_shoreline_lake[idx], (dx, dy))
            # Grass layer: shoreline tiles for water-adjacent land, explicit B/L/R, and inset connectors.
            def _pick_grass_tile() -> tuple[Any, bool]:
                """Returns (tile, is_shoreline). is_shoreline=True when tile is from shoreline set."""
                if not grass_imgs:
                    return None, False
                land_chars = frozenset("G.P") | POI_CHARS | frozenset("ITF")
                adj_lake = _adjacent_to_lake_shoreline_cell(x, y)
                explicit_shore = shore_ch in ("B", "L", "R")
                inset_candidate = (ch in land_chars) and wmask == 0 and _adjacent_to_shoreline_cell(x, y)
                use_shoreline = explicit_shore or inset_candidate
                if (grass_shoreline or grass_shoreline_lake or grass_shoreline_river or grass_shoreline_extended) and use_shoreline:
                    # Direct coastlines use water adjacency; inland connectors infer from nearby shore cells.
                    eff_mask = (
                        water_mask_grid[y][x]
                        if explicit_shore and wmask != 0 and y < len(water_mask_grid) and x < len(water_mask_grid[y])
                        else shore_mask_grid[y][x]
                        if explicit_shore and y < len(shore_mask_grid) and x < len(shore_mask_grid[y])
                        else _propagated_shore_mask(x, y, wmask)
                    )
                    direct_shore_special_tile = None
                    if shore_ch == "B" and shoreline_special_tiles:
                        north_cell = _get_ascii_cell(x, y - 1)
                        east_cell = _get_ascii_cell(x + 1, y)
                        south_cell = _get_ascii_cell(x, y + 1)
                        west_cell = _get_ascii_cell(x - 1, y)
                        has_n = north_cell == "B"
                        has_e = east_cell == "B"
                        has_s = south_cell == "B"
                        has_w = west_cell == "B"
                        direct_shore_special_tile = match_ocean_shoreline_special_tile(
                            has_n,
                            has_e,
                            has_s,
                            has_w,
                            eff_mask,
                            shoreline_special_tiles,
                        )
                    if (
                        direct_shore_special_tile is not None
                        and shoreline_sheet_path
                        and shoreline_sheet_path.exists()
                    ):
                        shore_start, shore_end = shoreline_range
                        if shore_start <= direct_shore_special_tile <= shore_end:
                            idx = direct_shore_special_tile - shore_start
                            if 0 <= idx < len(grass_shoreline):
                                return grass_shoreline[idx], True
                    direct_lake_special_tile = None
                    if shore_ch == "L" and lake_special_tiles:
                        north_raw = ascii_lines[y - 1][x] if y - 1 >= 0 and x < len(ascii_lines[y - 1]) else "."
                        east_raw = ascii_lines[y][x + 1] if x + 1 < len(ascii_lines[y]) else "."
                        south_raw = ascii_lines[y + 1][x] if y + 1 < height and x < len(ascii_lines[y + 1]) else "."
                        west_raw = ascii_lines[y][x - 1] if x - 1 >= 0 else "."
                        direct_lake_special_tile = match_lake_shoreline_special_tile(
                            has_n=north_raw in ("L", "R"),
                            has_e=east_raw in ("L", "R"),
                            has_s=south_raw in ("L", "R"),
                            has_w=west_raw in ("L", "R"),
                            water_mask=eff_mask,
                            special_tiles=lake_special_tiles,
                            has_n_beach=north_raw == "B",
                            has_e_beach=east_raw == "B",
                            has_s_beach=south_raw == "B",
                            has_w_beach=west_raw == "B",
                        )
                    if direct_lake_special_tile is not None and grass_shoreline_lake:
                        if lakesrivers_sheet_path and lake_range_override[0] <= direct_lake_special_tile <= lake_range_override[1]:
                            idx = direct_lake_special_tile - lake_range_override[0]
                            if 0 <= idx < len(grass_shoreline_lake):
                                return grass_shoreline_lake[idx], True
                    # Special: south_of_n_edge (e.g. 49) for U inlet, single-edge caps, and diagonal corners
                    south_of_n_edge_tile = lake_special_tiles.get("south_of_n_edge") if lake_special_tiles else None
                    use_south_of_n_edge = False
                    if (
                        south_of_n_edge_tile is not None
                        and shore_ch == "L"
                        and grass_shoreline_lake
                        and lakesrivers_sheet_path
                        and lake_load_range[0] <= south_of_n_edge_tile <= lake_load_range[1]
                    ):
                        # Compute lake mask for this cell
                        lake_mask_check = get_water_adjacency_bitmask(
                            shore_ascii_lines, x, y, water_chars=LAKE_WATER_CHARS, border_width=0
                        )
                        if lake_mask_check == 0 and eff_mask != 0:
                            lake_mask_check = eff_mask
                        lake_mask_check = _lake_mask_with_diagonal_inference(
                            shore_ascii_lines, x, y, lake_mask_check, LAKE_WATER_CHARS
                        )
                        # Case 1: South neighbor is L with N edge only (U inlet)
                        if y + 1 < height:
                            sy, sx = y + 1, x
                            south_cell = shore_ascii_lines[sy][sx] if sy < len(shore_ascii_lines) and sx < len(shore_ascii_lines[sy]) else "."
                            if south_cell in ("L", "R"):
                                south_mask = get_water_adjacency_bitmask(
                                    shore_ascii_lines, sx, sy, water_chars=LAKE_WATER_CHARS, border_width=0
                                )
                                south_mask = _lake_mask_with_diagonal_inference(
                                    shore_ascii_lines, sx, sy, south_mask, LAKE_WATER_CHARS
                                )
                                south_tile = lake_map_override.get(south_mask, lake_range_override[0]) if lake_map_override else 6
                                if south_tile == 6:
                                    use_south_of_n_edge = True
                        # Case 2: Single-edge (1,2,4,8) - use tile 49 to avoid wrong orientation (grass facing water)
                        if not use_south_of_n_edge and lake_mask_check in (1, 2, 4, 8):
                            use_south_of_n_edge = True
                        # Case 3: Corner (3,6,9,12) with diagonal water - use tile 49 to avoid diagonal gap
                        if not use_south_of_n_edge and lake_mask_check in (3, 6, 9, 12):
                            diag_water = False
                            if lake_mask_check == 3:  # N+E corner -> NE diagonal
                                diag_water = _get_ascii_cell(x + 1, y - 1) in LAKE_WATER_CHARS
                            elif lake_mask_check == 6:  # S+E corner -> SE diagonal
                                diag_water = _get_ascii_cell(x + 1, y + 1) in LAKE_WATER_CHARS
                            elif lake_mask_check == 9:  # N+W corner -> NW diagonal
                                diag_water = _get_ascii_cell(x - 1, y - 1) in LAKE_WATER_CHARS
                            elif lake_mask_check == 12:  # S+W corner -> SW diagonal
                                diag_water = _get_ascii_cell(x - 1, y + 1) in LAKE_WATER_CHARS
                            if diag_water:
                                use_south_of_n_edge = True
                        if use_south_of_n_edge:
                            idx = south_of_n_edge_tile - lake_load_range[0]
                            if 0 <= idx < len(grass_shoreline_lake):
                                return grass_shoreline_lake[idx], True
                    special_inset_corner_tile = None
                    # Ocean inset is for B (continent) only; L/R use lake tiles (avoid wrong sheet for diagonal L)
                    if (inset_candidate or (explicit_shore and wmask == 0)) and shore_ch == "B":
                        special_inset_corner_tile = _get_ocean_inset_special_tile(
                            x,
                            y,
                            allow_shore_cell=explicit_shore and wmask == 0,
                        )
                    if (
                        special_inset_corner_tile is not None
                        and shoreline_sheet_path
                        and shoreline_sheet_path.exists()
                    ):
                        shore_start, shore_end = shoreline_range
                        if shore_start <= special_inset_corner_tile <= shore_end:
                            idx = special_inset_corner_tile - shore_start
                            if 0 <= idx < len(grass_shoreline):
                                return grass_shoreline[idx], True
                    if inset_candidate:
                        return _pick_interior_grass(), False
                    if eff_mask == 0 and (explicit_shore or inset_candidate):
                        eff_mask = 1
                    if eff_mask == 0:
                        return None, False
                    # L = lake shoreline: use lake tiles if available, else continent (inlets need shoreline too)
                    if (ch == "L" or (adj_lake and ch != "B")) and grass_shoreline_lake:
                        # Use lake water chars (L/R count as water) so straight edges get correct mask
                        lake_mask = get_water_adjacency_bitmask(
                            shore_ascii_lines, x, y, water_chars=LAKE_WATER_CHARS, border_width=0
                        )
                        if lake_mask != 0:
                            eff_mask = lake_mask
                        eff_mask = _lake_mask_with_diagonal_inference(
                            ascii_lines, x, y, eff_mask, LAKE_WATER_CHARS
                        )
                        # Explicit interior lake cases (neighbor-based)
                        if interior_lake_tiles and lake_map_override is not None:
                            n_ch = _get_ascii_cell(x, y - 1)
                            e_ch = _get_ascii_cell(x + 1, y)
                            s_ch = _get_ascii_cell(x, y + 1)
                            w_ch = _get_ascii_cell(x - 1, y)
                            n_is_lake = n_ch in ("L", "R")
                            e_is_lake = e_ch in ("L", "R")
                            s_is_lake = s_ch in ("L", "R")
                            w_is_lake = w_ch in ("L", "R")
                            n_is_water = n_ch in LAKE_WATER_CHARS
                            e_is_water = e_ch in LAKE_WATER_CHARS
                            s_is_water = s_ch in LAKE_WATER_CHARS
                            w_is_water = w_ch in LAKE_WATER_CHARS
                            e_is_shallow = e_ch == WATER_CHAR
                            n_is_shallow = n_ch == WATER_CHAR
                            s_is_shallow = s_ch == WATER_CHAR
                            w_is_shallow = w_ch == WATER_CHAR
                            lake_count = sum([n_is_lake, e_is_lake, s_is_lake, w_is_lake])
                            # Case 6: interior only - 3+ lake neighbors AND one neighbor is shallow water -> blank
                            # Exclude deep water (`): L next to deep water is the shallow border, needs a tile
                            if lake_count >= 3 and (n_is_shallow or e_is_shallow or s_is_shallow or w_is_shallow):
                                return None, False
                            # Cases 2-5: pick tile 49,50,51,52 from neighbor tile types (check before Case 1)
                            def _neighbor_tile(dx: int, dy: int) -> int:
                                nx, ny = x + dx, y + dy
                                if _get_ascii_cell(nx, ny) not in ("L", "R"):
                                    return -1
                                m = _lake_mask_at(nx, ny)
                                return lake_map_override.get(m, 0)
                            n_tile = _neighbor_tile(0, -1)
                            e_tile = _neighbor_tile(1, 0)
                            s_tile = _neighbor_tile(0, 1)
                            w_tile = _neighbor_tile(-1, 0)
                            # tile 3=mask6, tile 2=mask3, tile 5=mask12, tile 4=mask9
                            if n_tile == 3 and w_tile == 3:
                                tile_idx = interior_lake_tiles[0]  # 49
                            elif s_tile == 2 and w_tile == 2:
                                tile_idx = interior_lake_tiles[2]  # 51
                            elif n_tile == 5 and e_tile == 5:
                                tile_idx = interior_lake_tiles[1]  # 50
                            elif e_tile == 4 and s_tile == 4:
                                tile_idx = interior_lake_tiles[3]  # 52
                            else:
                                tile_idx = None
                            if tile_idx is not None and lake_load_range[0] <= tile_idx <= lake_load_range[1]:
                                idx = tile_idx - lake_load_range[0]
                                if 0 <= idx < len(grass_shoreline_lake):
                                    return grass_shoreline_lake[idx], True
                            # Case 1: NESW all water (L/R/~/`) -> blank (including N=lake, E=lake, S=deep, W=lake)
                            if n_is_water and e_is_water and s_is_water and w_is_water:
                                return None, False
                        if lakesrivers_sheet_path and lake_map_override is not None:
                            tile_idx = lake_map_override.get(eff_mask, lake_range_override[0])
                            lake_start, lake_end = lake_range_override[0], lake_range_override[1]
                        else:
                            tile_idx = lake_shoreline_map.get(eff_mask, 51)
                            lake_start = grass_shoreline_lake_range[0]
                            lake_end = grass_shoreline_lake_range[1]
                        if lake_start <= tile_idx <= lake_end:
                            idx = tile_idx - lake_start
                            if 0 <= idx < len(grass_shoreline_lake):
                                return grass_shoreline_lake[idx], True
                    # Fallthrough: L with no lake tiles -> use continent shoreline
                    # R = river bank: use river tiles (masks 5, 10)
                    if ch == "R" and grass_shoreline_river:
                        if eff_mask in river_masks:
                            if lakesrivers_sheet_path and river_map_override is not None:
                                tile_idx = river_map_override.get(eff_mask, river_range_override[0])
                                riv_idx = tile_idx - river_range_override[0]
                            else:
                                riv_idx = river_masks.index(eff_mask)
                            if 0 <= riv_idx < len(grass_shoreline_river):
                                return grass_shoreline_river[riv_idx], True
                        # Fallback: use first river tile
                        if grass_shoreline_river:
                            return grass_shoreline_river[0], True
                    # Extended: peninsula (7,11,13,14) or isolated island (15) - B uses shoreline.aseprite
                    if shore_ch != "B" and grass_shoreline_extended and eff_mask in extended_masks:
                        ext_idx = extended_masks.index(eff_mask)
                        if ext_idx < len(grass_shoreline_extended):
                            return grass_shoreline_extended[ext_idx], True
                    # River banks: water on opposite sides (5=N+S, 10=E+W) - R only, B uses shoreline.aseprite
                    if shore_ch != "B" and grass_shoreline_river and eff_mask in river_masks:
                        if lakesrivers_sheet_path and river_map_override is not None:
                            tile_idx = river_map_override.get(eff_mask, river_range_override[0])
                            riv_idx = tile_idx - river_range_override[0]
                        else:
                            riv_idx = river_masks.index(eff_mask)
                        if 0 <= riv_idx < len(grass_shoreline_river):
                            return grass_shoreline_river[riv_idx], True
                    # Interior shore corners (3,6,9,12): use 4,6,16,18 for lakes only (L or G/./P adjacent to lake)
                    # B = beach: always use shoreline.aseprite, never lakesrivers
                    if shore_ch != "B" and (ch == "L" or is_lake or (adj_lake and ch != "B")) and eff_mask in interior_corner_masks and grass_shoreline_lake:
                        if lakesrivers_sheet_path and lake_map_override is not None:
                            tile_idx = lake_map_override.get(eff_mask, lake_range_override[0])
                            lake_start, lake_end = lake_range_override[0], lake_range_override[1]
                        else:
                            tile_idx = lake_shoreline_map.get(eff_mask, 51)
                            lake_start, lake_end = grass_shoreline_lake_range[0], grass_shoreline_lake_range[1]
                        if lake_start <= tile_idx <= lake_end:
                            idx = tile_idx - lake_start
                            if 0 <= idx < len(grass_shoreline_lake):
                                return grass_shoreline_lake[idx], True
                    if shore_ch != "B" and (is_lake or (adj_lake and ch != "B")) and grass_shoreline_lake:
                        if lakesrivers_sheet_path and lake_map_override is not None:
                            tile_idx = lake_map_override.get(eff_mask, lake_range_override[0])
                            lake_start, lake_end = lake_range_override[0], lake_range_override[1]
                        else:
                            tile_idx = lake_shoreline_map.get(eff_mask, 51)
                            lake_start, lake_end = grass_shoreline_lake_range[0], grass_shoreline_lake_range[1]
                        if lake_start <= tile_idx <= lake_end:
                            idx = tile_idx - lake_start
                            if 0 <= idx < len(grass_shoreline_lake):
                                return grass_shoreline_lake[idx], True
                    # B = continent shoreline; also L/G/./P when lake tiles unavailable (inlets, water fingers)
                    if grass_shoreline:
                        shore_start = grass_shoreline_range[0]
                        shore_end = grass_shoreline_range[1]
                        if shoreline_sheet_path and shoreline_sheet_path.exists():
                            # Dedicated shoreline sheet: use shoreline_map if present, else convert grass_shoreline (98-118 -> 1-21)
                            if shoreline_map is not None:
                                tile_idx = shoreline_map.get(eff_mask, shoreline_range[0])
                                shore_start, shore_end = shoreline_range[0], shoreline_range[1]
                            else:
                                tile_idx = grass_shoreline_map.get(eff_mask, grass_shoreline_range[0])
                                tile_idx = (tile_idx - 97) if tile_idx >= 98 else tile_idx
                                shore_start, shore_end = shoreline_range[0], shoreline_range[1]
                        else:
                            tile_idx = grass_shoreline_map.get(eff_mask, grass_shoreline_range[0])
                        if shore_start <= tile_idx <= shore_end:
                            idx = tile_idx - shore_start
                            if grass_shoreline:
                                # Clamp idx if sheet has fewer tiles than range (avoids beige fallback)
                                idx = min(idx, len(grass_shoreline) - 1) if idx >= len(grass_shoreline) else idx
                                if 0 <= idx < len(grass_shoreline):
                                    return grass_shoreline[idx], True
                return _pick_interior_grass(), False

            # Terrain separated by layer: grass=interior only, shoreline=shoreline only (for verification)
            # I = hill: use shoreline when adjacent to water, else hill autotile by adjacency
            def _is_tile_visible(t: Any) -> bool:
                """True if tile has enough opaque pixels to be visible (not blank/transparent)."""
                if t is None:
                    return False
                try:
                    if hasattr(t, "mode") and "A" in getattr(t, "mode", ""):
                        if hasattr(t, "getchannel"):
                            a = t.getchannel("A")
                            return a.getextrema()[1] > 8
                except Exception:
                    pass
                return True

            def _paste_visible(
                layer: Any,
                tile: Any,
                fallback_rgb: tuple[int, int, int, int],
                color_tiles_ref: dict,
                *,
                use_tile_when_available: bool = False,
            ) -> None:
                """Paste tile to layer; use solid fallback if tile is transparent/blank."""
                if layer is None:
                    return
                use = tile
                if not use:
                    if fallback_rgb not in color_tiles_ref:
                        color_tiles_ref[fallback_rgb] = Image.new("RGBA", (tile_size, tile_size), fallback_rgb)
                    use = color_tiles_ref[fallback_rgb]
                elif not _is_tile_visible(use):
                    # Always use fallback when tile is blank/transparent (avoids gray/blank beach tiles)
                    if fallback_rgb not in color_tiles_ref:
                        color_tiles_ref[fallback_rgb] = Image.new("RGBA", (tile_size, tile_size), fallback_rgb)
                    use = color_tiles_ref[fallback_rgb]
                if use:
                    layer.paste(use, (dx, dy))

            def _paste_shore_tile(
                tile: Any,
                fallback_rgb: tuple[int, int, int, int],
                *,
                use_lakebank: bool | None = None,
            ) -> None:
                """Paste shoreline tile to Shoreline (ocean) or LakeBank (lake/river) layer.
                use_lakebank: True=lakebank, False=shoreline, None=infer from ch and is_lake."""
                if use_lakebank is None:
                    use_lakebank = (ch in ("L", "R")) or is_lake
                # Use correct fallback per layer: lakebank=L or R, shoreline=B (so inset tiles aren't beige)
                rgb = (
                    SOLID_TILE_COLORS["R"] if ch == "R" else
                    SOLID_TILE_COLORS["L"] if use_lakebank else
                    SOLID_TILE_COLORS["B"]
                )
                # Fallback to solid color when tile is blank/transparent (see _paste_visible)
                if use_lakebank and lakebank_layer:
                    _paste_visible(lakebank_layer, tile, rgb, color_tiles)
                elif shoreline_layer:
                    _paste_visible(shoreline_layer, tile, rgb, color_tiles)
                elif grass_layer:
                    # No shoreline output: use grass layer so B/L/R still render (fallback color)
                    _paste_visible(grass_layer, tile, fallback_rgb, color_tiles)

            if is_land_surrounded_by_water:
                # Water already pasted; skip grass/trees/dirt/POI (avoids grass painted over water)
                pass
            elif ch == "I" and grass_imgs:
                is_shore = False
                # Paint grass underneath so hiding hill layer shows grass
                grass_tile = _pick_interior_grass()
                if grass_tile:
                    _paste_visible(grass_layer, grass_tile, SOLID_TILE_COLORS["G"], color_tiles)
                if grass_hill:
                    hmask = get_hill_adjacency_bitmask(ascii_lines, x, y)
                    tile_id = hill_map.get(hmask, hill_map.get(0, 1))
                    hill_start = (grass_hill_range or (1, 37))[0]
                    idx = tile_id - hill_start
                    if 0 <= idx < len(grass_hill):
                        tile = grass_hill[idx]
                    else:
                        tile = grass_hill[0]
                else:
                    tile = _pick_interior_grass()
                if not tile or not _is_tile_visible(tile):
                    rgb = SOLID_TILE_COLORS.get("I", (90, 120, 70, 255))
                    if rgb not in color_tiles:
                        color_tiles[rgb] = Image.new("RGBA", (tile_size, tile_size), rgb)
                    tile = color_tiles[rgb]
                if tile:
                    if hill_layer:
                        _paste_visible(hill_layer, tile, SOLID_TILE_COLORS["I"], color_tiles)
                    else:
                        _paste_visible(grass_layer, tile, SOLID_TILE_COLORS["G"], color_tiles)
            elif ch == "I":
                # Fallback when grass_imgs empty: paint grass base, then hill
                grass_rgb = SOLID_TILE_COLORS.get("G", (104, 178, 76, 255))
                if grass_rgb not in color_tiles:
                    color_tiles[grass_rgb] = Image.new("RGBA", (tile_size, tile_size), grass_rgb)
                grass_layer.paste(color_tiles[grass_rgb], (dx, dy))
                rgb = SOLID_TILE_COLORS.get("I", (90, 120, 70, 255))
                if rgb not in color_tiles:
                    color_tiles[rgb] = Image.new("RGBA", (tile_size, tile_size), rgb)
                if hill_layer:
                    hill_layer.paste(color_tiles[rgb], (dx, dy))
                else:
                    grass_layer.paste(color_tiles[rgb], (dx, dy))
            elif display_ch in ("G", ".", "B", "L", "R") and grass_imgs:
                tile, is_shore = _pick_grass_tile()
                # Case 1/6: interior lake (NESW all water) returns (None, False) - paint as water (no shoreline tile)
                # Use shore_ch: promoted ~->L cells have ch=~ but shore_ch=L
                if tile is None and is_shore is False and shore_ch in ("L", "R"):
                    pass
                else:
                    tile = tile or (
                        grass_imgs[min(grass_default_idx, len(grass_imgs) - 1)]
                        if strict
                        else grass_imgs[rng.randint(0, len(grass_imgs) - 1)]
                    )
                    fallback = SOLID_TILE_COLORS.get(ch, SOLID_TILE_COLORS["G"])
                    adj_lake = _adjacent_to_lake_shoreline_cell(x, y)
                    use_shore_layer = shore_ch in ("B", "L", "R") or is_shore
                    if use_shore_layer and ch in ("G", "."):
                        fallback = SOLID_TILE_COLORS["L"] if adj_lake else SOLID_TILE_COLORS["B"]
                    if use_shore_layer:
                        _paste_shore_tile(
                            tile if is_shore else None,
                            fallback,
                            use_lakebank=adj_lake if ch in ("G", ".") else None,
                        )
                    elif is_shore:
                        _paste_shore_tile(tile, fallback)
                    else:
                        _paste_visible(grass_layer, tile, fallback, color_tiles)
            elif ch == "P" and grass_imgs:
                tile, is_shore = _pick_grass_tile()
                tile = tile or _pick_interior_grass()
                fallback = SOLID_TILE_COLORS["P"]
                if is_shore:
                    _paste_shore_tile(tile, fallback)
                else:
                    _paste_visible(grass_layer, tile, fallback, color_tiles)
            elif ch in POI_CHARS:
                # POI cells: draw base terrain (grass or path), then marker on poi_layer
                if ch in POI_GRASS_BASE and grass_imgs:
                    tile, is_shore = _pick_grass_tile()
                    tile = tile or _pick_interior_grass()
                    fallback = SOLID_TILE_COLORS["G"]
                    if is_shore:
                        _paste_shore_tile(tile, fallback)
                    else:
                        _paste_visible(grass_layer, tile, fallback, color_tiles)
                elif ch in POI_PATH_BASE and dirt_tiles and not skip_dirt:
                    bitmask = get_path_bitmask(ascii_lines, x, y)
                    idx = min(bitmask, len(dirt_tiles) - 1)
                    _paste_visible(dirt_layer, dirt_tiles[idx], SOLID_TILE_COLORS["P"], color_tiles)
                elif ch in POI_PATH_BASE and grass_imgs:
                    tile, is_shore = _pick_grass_tile()
                    tile = tile or _pick_interior_grass()
                    fallback = SOLID_TILE_COLORS["P"]
                    if is_shore:
                        _paste_shore_tile(tile, fallback)
                    else:
                        _paste_visible(grass_layer, tile, fallback, color_tiles)
                elif grass_imgs:
                    tile, is_shore = _pick_grass_tile()
                    tile = tile or _pick_interior_grass()
                    fallback = SOLID_TILE_COLORS["G"]
                    if is_shore:
                        _paste_shore_tile(tile, fallback)
                    else:
                        _paste_visible(grass_layer, tile, fallback, color_tiles)
                rgb = SOLID_TILE_COLORS.get(ch, DEFAULT_COLOR)
                if rgb not in color_tiles:
                    color_tiles[rgb] = Image.new("RGBA", (tile_size, tile_size), rgb)
                poi_layer.paste(color_tiles[rgb], (dx, dy))
                for layer_name, layer_ch in POI_LAYERS.items():
                    if ch == layer_ch and layer_name in poi_layers:
                        poi_layers[layer_name].paste(color_tiles[rgb], (dx, dy))
            elif is_pure_water:
                # Pure water: only paint water layer; never paint grass/trees on top
                pass
            else:
                rgb = SOLID_TILE_COLORS.get(display_ch, DEFAULT_COLOR)
                if rgb not in color_tiles:
                    color_tiles[rgb] = Image.new("RGBA", (tile_size, tile_size), rgb)
                grass_layer.paste(color_tiles[rgb], (dx, dy))

            # Dirt layer: P cells only, no dirt on ocean-adjacent tiles (reserve for shoreline)
            if not is_land_surrounded_by_water and ch == "P" and dirt_tiles and not skip_dirt:
                bitmask = get_path_bitmask(ascii_lines, x, y)
                idx = min(bitmask, len(dirt_tiles) - 1)
                _paste_visible(dirt_layer, dirt_tiles[idx], SOLID_TILE_COLORS["P"], color_tiles)

            # Trees layer: T, F cells (skip on water and shoreline B/L/R per terrain rules)
            if not is_land_surrounded_by_water and ch in ("T", "F") and not is_pure_water and shore_ch not in ("B", "L", "R"):
                tile_id = tile_rows[y][x] if y < len(tile_rows) and x < len(tile_rows[y]) else 0
                if tile_id and tile_id > 0:
                    idx = tile_id - 1
                    if idx < len(tree_tiles):
                        _paste_visible(trees_layer, tree_tiles[idx], SOLID_TILE_COLORS["T"], color_tiles)

    water_layer.save(water_out)
    if use_separate_water and water_shallow_layer is not None:
        water_shallow_layer.save(water_shallow_out)
        water_deep_layer.save(water_deep_out)
        water_lake_layer.save(water_lake_out)
        water_river_layer.save(water_river_out)
    grass_layer.save(grass_out)
    dirt_layer.save(dirt_out)
    trees_layer.save(trees_out)
    if shoreline_out and shoreline_layer:
        shoreline_layer.save(shoreline_out)
    if lakebank_out and lakebank_layer:
        lakebank_layer.save(lakebank_out)
    if hill_out and hill_layer:
        hill_layer.save(hill_out)
    if poi_out:
        poi_layer.save(poi_out)
    if poi_layers_out:
        for name, path in poi_layers_out.items():
            if name in poi_layers:
                poi_layers[name].save(path)
