"""Paint ASCII map to grass + trees PNGs using PIL (GotchiCraft-style pipeline)."""
from __future__ import annotations

import dataclasses
import json
import random
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

from tilemap_generator.tree_logic import to_tile_rows_with_trees


def load_bitmask_config(path: Path) -> dict[str, Any]:
    """Load grass bitmask config from JSON. Used for shoreline autotiling."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Bitmask config must be a JSON object")
    return data


def classify_hill_split_shape_key(
    *,
    raw_mask: int,
    autotile_mask: int,
) -> str:
    """Classify hill cell geometry for ``hill.maps_by_shape`` selection."""
    rm = int(raw_mask) & 15
    am = int(autotile_mask) & 15
    if rm == HILL_INTERIOR_MASK:
        return "cross"
    if rm in (1, 2, 4, 8):
        return "peninsula"
    if rm in (3, 6, 9, 12):
        return "corner"
    if am == 5:
        return "ridge_vertical"
    if am == 10:
        return "ridge_horizontal"
    if am in (7, 11, 13, 14):
        return "tee"
    return "default"


def resolve_hill_split_mask_tile_id(
    *,
    mask_for_lookup: int,
    raw_mask: int,
    autotile_mask: int,
    maps_by_shape: dict[str, dict[int, int]] | None = None,
    enabled_masks: frozenset[int] | None = None,
    default_shape: str = "default",
) -> int | None:
    """Resolve optional JSON split-mask tile id for a selected mask.

    Returns ``None`` when split-mask is disabled or no matching shape/map entry exists.
    """
    if not maps_by_shape:
        return None
    m = int(mask_for_lookup) & 15
    if enabled_masks and m not in enabled_masks:
        return None
    shape_key = classify_hill_split_shape_key(
        raw_mask=int(raw_mask) & 15,
        autotile_mask=int(autotile_mask) & 15,
    )
    by_shape = maps_by_shape.get(shape_key)
    if isinstance(by_shape, dict) and m in by_shape:
        return int(by_shape[m])
    fallback = maps_by_shape.get(default_shape)
    if isinstance(fallback, dict) and m in fallback:
        return int(fallback[m])
    return None


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

# Hill autotile: N=1,E=2,S=4,W=8. Maps mask to 1-based tile ID in hills.aseprite.
# Mask 15: four-way connector (tile 14) when not "deep interior"; deep interior = grass only (no hill layer).
HILL_INTERIOR_MASK = 15  # N+E+S+W all hills (raw adjacency)
# Raw two-edge outer corners: N+E=3, E+S=6, N+W=9, S+W=12. Keep these when interior-exclusion
# would drop both hill neighbors (both mesa interior), which wrongly yields peninsula/isolated art.
HILL_OUTER_CORNER_RAW_MASKS = frozenset({3, 6, 9, 12})
# Cardinals 1,2,4,8 = peninsula ends (one open side): N→12, E→11, S→10, W→13 per reference layout.
# Ridges: 5=N+S→9 (vertical spine default), 10=E+W→8. Three-open masks reuse cliff faces:
# 7→9, 13→7, 14→6, 11→8.
# (7/13 also pair as 2-column vertical strip → spine 9/7 via hill_two_wide_vertical_strip_spine_tile_id).
# (11/14 also pair as 2-row horizontal strip → spine 8/6 via hill_two_wide_horizontal_strip_spine_tile_id).
HILL_MAP: dict[int, int] = {
    0: 1,    # isolated
    1: 12,   # N only — north peninsula (grass to S)
    2: 11,   # E only — east peninsula
    3: 4,    # N+E outer corner
    4: 10,   # S only — south peninsula
    5: 9,    # N+S ridge (vertical spine); override hill_map[5] or ridge rules for alternates
    6: 2,    # E+S corner (NW corner piece)
    7: 9,    # N+E+S, W open — left cliff face
    8: 13,   # W only — west peninsula
    9: 5,    # N+W outer corner
    10: 8,  # E+W ridge (horizontal)
    11: 8,   # N+E+W, S open — south cliff face
    12: 3,   # S+W corner (NE corner piece)
    13: 7,   # N+S+W, E open — right cliff face
    14: 6,   # S+E+W, N open — north cliff face
    15: 14,  # mask 15: 4-way connector (not used for deep plateau interior — painter uses grass)
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


def load_water_tiles(water_path: Path, tile_size: int) -> list[Any]:
    """Load water tiles from a PNG sheet or single PNG."""
    return load_grass_from_sheet(water_path, tile_size)


def load_dirt_tiles(dirt_path: Path, tile_size: int) -> list[Any]:
    """Load path/dirt autotile tiles from a PNG sheet."""
    return load_grass_from_sheet(dirt_path, tile_size)


def get_path_bitmask(ascii_lines: list[str], x: int, y: int) -> int:
    """Return 4-bit NESW adjacency for path cells."""
    height = len(ascii_lines)
    width = max((len(row) for row in ascii_lines), default=0)

    def _is_path(px: int, py: int) -> bool:
        if not (0 <= px < width and 0 <= py < height):
            return False
        row = ascii_lines[py]
        ch = row[px] if px < len(row) else "."
        return ch in PATH_CHARS or ch in POI_PATH_BASE

    mask = 0
    if _is_path(x, y - 1):
        mask |= 1
    if _is_path(x + 1, y):
        mask |= 2
    if _is_path(x, y + 1):
        mask |= 4
    if _is_path(x - 1, y):
        mask |= 8
    return mask


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


def fill_bay_diagonal_shoreline(
    ascii_lines: list[str],
    ocean_connected: set[tuple[int, int]],
    width: int,
    height: int,
) -> list[str]:
    """Promote land to B/L when it has water on a diagonal but not NESW, and has shore NESW.
    Fills bay/inset corners to avoid diagonal land-water touch (1-tile perimeter)."""
    if width == 0 or height == 0:
        return ascii_lines

    land_chars = frozenset("G.PTF") | POI_CHARS
    diag_deltas = [(-1, -1), (1, -1), (1, 1), (-1, 1)]  # NW, NE, SE, SW
    nesw_deltas = [(0, -1), (1, 0), (0, 1), (-1, 0)]

    def _cell(px: int, py: int) -> str:
        if not (0 <= px < width and 0 <= py < height):
            return "."
        row = ascii_lines[py] if py < len(ascii_lines) else ""
        return row[px] if px < len(row) else "."

    def _has_water_nesw(px: int, py: int) -> bool:
        return any(
            0 <= px + dx < width and 0 <= py + dy < height
            and _cell(px + dx, py + dy) in WATER_CHARS
            for dx, dy in nesw_deltas
        )

    def _has_shore_nesw(px: int, py: int) -> bool:
        return any(
            0 <= px + dx < width and 0 <= py + dy < height
            and _cell(px + dx, py + dy) in ("B", "L", "R")
            for dx, dy in nesw_deltas
        )

    lines = [list(row.ljust(width, ".")) for row in ascii_lines]
    for y in range(height):
        for x in range(width):
            ch = lines[y][x]
            if ch not in land_chars:
                continue
            if _has_water_nesw(x, y):
                continue  # Already has water NESW, normal rules apply
            if not _has_shore_nesw(x, y):
                continue  # No adjacent shore, not filling a gap
            # Check diagonal water
            has_diag_water = False
            has_diag_ocean = False
            has_diag_lake = False
            for dx, dy in diag_deltas:
                nx, ny = x + dx, y + dy
                if not (0 <= nx < width and 0 <= ny < height):
                    continue
                if _cell(nx, ny) not in WATER_CHARS:
                    continue
                has_diag_water = True
                if (nx, ny) in ocean_connected:
                    has_diag_ocean = True
                else:
                    has_diag_lake = True
            if not has_diag_water:
                continue
            # Promote to B (ocean bay) or L (lake bay)
            lines[y][x] = "B" if has_diag_ocean else "L"
    return ["".join(row) for row in lines]


def demote_shoreline_without_water_neighbor(
    ascii_lines: list[str],
    ocean_connected: set[tuple[int, int]],
    width: int,
    height: int,
) -> list[str]:
    """Demote B/L to G when they have no water in NESW. Keep bay fill (water on diagonal)."""
    if width == 0 or height == 0:
        return ascii_lines

    diag_deltas = [(-1, -1), (1, -1), (1, 1), (-1, 1)]

    def _cell(px: int, py: int) -> str:
        if not (0 <= px < width and 0 <= py < height):
            return "."
        row = ascii_lines[py] if py < len(ascii_lines) else ""
        return row[px] if px < len(row) else "."

    def _has_water_diagonal(px: int, py: int) -> bool:
        return any(
            0 <= px + dx < width and 0 <= py + dy < height
            and _cell(px + dx, py + dy) in WATER_CHARS
            for dx, dy in diag_deltas
        )

    lines = [list(row.ljust(width, ".")) for row in ascii_lines]
    for y in range(height):
        for x in range(width):
            ch = lines[y][x]
            if ch == "B":
                has_ocean = any(
                    not (0 <= nx < width and 0 <= ny < height) or (nx, ny) in ocean_connected
                    for nx, ny in [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]
                )
                if not has_ocean and not _has_water_diagonal(x, y):
                    lines[y][x] = "G"
            elif ch == "L":
                has_lake = any(
                    0 <= nx < width and 0 <= ny < height
                    and _cell(nx, ny) in WATER_CHARS
                    and (nx, ny) not in ocean_connected
                    for nx, ny in [(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)]
                )
                if not has_lake and not _has_water_diagonal(x, y):
                    lines[y][x] = "G"
    return ["".join(row) for row in lines]


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


def is_hill_char(
    ascii_lines: list[str],
    x: int,
    y: int,
    hill_char: str = "I",
) -> bool:
    height = len(ascii_lines)
    width = max(len(row) for row in ascii_lines) if ascii_lines else 0
    if y < 0 or y >= height or x < 0 or x >= width:
        return False
    row = ascii_lines[y]
    ch = row.ljust(width, ".")[x]
    return ch == hill_char


def is_hill_interior_cell(
    ascii_lines: list[str],
    x: int,
    y: int,
    hill_char: str = "I",
) -> bool:
    """True if (x,y) is hill_char and all four cardinal neighbors are hill_char."""
    if not is_hill_char(ascii_lines, x, y, hill_char):
        return False
    for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
        if not is_hill_char(ascii_lines, x + dx, y + dy, hill_char):
            return False
    return True


def _hill_reachable_without_cell(
    ascii_lines: list[str],
    start: tuple[int, int],
    blocked: tuple[int, int],
    hill_char: str = "I",
) -> set[tuple[int, int]]:
    """4-connected flood fill over I cells from start, not stepping on blocked."""
    height = len(ascii_lines)
    width = max(len(row) for row in ascii_lines) if ascii_lines else 0
    bx, by = blocked
    seen: set[tuple[int, int]] = set()
    stack = [start]
    while stack:
        cx, cy = stack.pop()
        if (cx, cy) in seen:
            continue
        if cx == bx and cy == by:
            continue
        if not is_hill_char(ascii_lines, cx, cy, hill_char):
            continue
        seen.add((cx, cy))
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < width and 0 <= ny < height:
                stack.append((nx, ny))
    return seen


def is_hill_mask15_articulation_point(
    ascii_lines: list[str],
    x: int,
    y: int,
    hill_char: str = "I",
) -> bool:
    """True if (x,y) has mask 15 and removing it disconnects its four I neighbors.

    + cross center: articulation → 4-way connector (hill_map[15]). Solid plateau core: not → grass.
    """
    if get_hill_adjacency_bitmask(ascii_lines, x, y, hill_char, exclude_interior_hill_neighbors=False) != HILL_INTERIOR_MASK:
        return False
    neighbors = [(x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)]
    if not all(is_hill_char(ascii_lines, nx, ny, hill_char) for nx, ny in neighbors):
        return False
    reachable = _hill_reachable_without_cell(ascii_lines, neighbors[0], (x, y), hill_char)
    return not all(n in reachable for n in neighbors[1:])


def is_hill_deep_interior_cell(
    ascii_lines: list[str],
    x: int,
    y: int,
    hill_char: str = "I",
) -> bool:
    """Plateau interior (mask 15, not a cut vertex): grass only on hill feature, no hill sheet tile."""
    if get_hill_adjacency_bitmask(ascii_lines, x, y, hill_char, exclude_interior_hill_neighbors=False) != HILL_INTERIOR_MASK:
        return False
    return not is_hill_mask15_articulation_point(ascii_lines, x, y, hill_char)


def counts_as_hill_neighbor_for_autotile(
    ascii_lines: list[str],
    x: int,
    y: int,
    hill_char: str = "I",
) -> bool:
    """Hill tile that borders non-hill (exposed cliff). Interior I cells do not count as neighbors."""
    if not is_hill_char(ascii_lines, x, y, hill_char):
        return False
    return not is_hill_interior_cell(ascii_lines, x, y, hill_char)


def get_hill_adjacency_bitmask(
    ascii_lines: list[str],
    x: int,
    y: int,
    hill_char: str = "I",
    *,
    exclude_interior_hill_neighbors: bool = False,
) -> int:
    """Compute 4-bit hill adjacency. N=1, E=2, S=4, W=8. Tile IDs come from hill_map / resolve_hill_autotile_tile_id.

    When exclude_interior_hill_neighbors is True, a cardinal neighbor counts only if it is hill_char
    and not fully surrounded by hill_char (interior mesa). That keeps rim cliffs as ridges after
    fill_hill_interior closes grass holes with I — otherwise rim masks jump to tee (e.g. 10→14).
    """
    height = len(ascii_lines)
    width = max(len(row) for row in ascii_lines) if ascii_lines else 0

    def is_hill(px: int, py: int) -> bool:
        if py < 0 or py >= height or px < 0 or px >= width:
            return False
        row = ascii_lines[py]
        # Align with paint loop: enumerate rows, x in range(width), ch = row[x] if x < len(row) else "."
        # Pad so column x matches the same logical cell as ljust(width, ".")[x].
        ch = row.ljust(width, ".")[px]
        return ch == hill_char

    def neighbor_counts(px: int, py: int) -> bool:
        if exclude_interior_hill_neighbors:
            return counts_as_hill_neighbor_for_autotile(ascii_lines, px, py, hill_char)
        return is_hill(px, py)

    mask = 0
    if neighbor_counts(x, y - 1):
        mask |= 1  # North
    if neighbor_counts(x + 1, y):
        mask |= 2  # East
    if neighbor_counts(x, y + 1):
        mask |= 4  # South
    if neighbor_counts(x - 1, y):
        mask |= 8  # West
    return mask


def _hill_mask_with_diagonal_inference(
    ascii_lines: list[str],
    x: int,
    y: int,
    base_mask: int,
    hill_char: str = "I",
    *,
    is_hill_fn: Callable[[int, int], bool] | None = None,
) -> int:
    """Upgrade single-edge hill mask to a corner mask when the matching diagonal is hill.

    Same geometry as _lake_mask_with_diagonal_inference for water: treat the hill mass like
    lake water for bitmask purposes so shallow corners resolve to corner tiles instead of
    cardinals-only.

    is_hill_fn(px, py): if provided, used for diagonal checks (e.g. exposed-hill predicate for autotile).
    """
    if base_mask not in (1, 2, 4, 8):
        return base_mask
    height = len(ascii_lines)
    width = max((len(row) for row in ascii_lines), default=0)

    def _default_is_hill(px: int, py: int) -> bool:
        if not (0 <= px < width and 0 <= py < height):
            return False
        row = ascii_lines[py]
        ch = row.ljust(width, ".")[px]
        return ch == hill_char

    _is_hill = is_hill_fn if is_hill_fn is not None else _default_is_hill

    upgraded = base_mask
    if base_mask == 1:  # N
        if _is_hill(x + 1, y - 1):
            upgraded = 3  # N+E corner
        elif _is_hill(x - 1, y - 1):
            upgraded = 9  # N+W corner
    elif base_mask == 2:  # E
        if _is_hill(x + 1, y - 1):
            upgraded = 3  # N+E corner
        elif _is_hill(x + 1, y + 1):
            upgraded = 6  # S+E corner
    elif base_mask == 4:  # S
        if _is_hill(x + 1, y + 1):
            upgraded = 6  # S+E corner
        elif _is_hill(x - 1, y + 1):
            upgraded = 12  # S+W corner
    elif base_mask == 8:  # W
        if _is_hill(x - 1, y - 1):
            upgraded = 9  # N+W corner
        elif _is_hill(x - 1, y + 1):
            upgraded = 12  # S+W corner
    return upgraded


def hill_mask5_vertical_spine_open_diagonals_for_tile24(
    ascii_lines: list[str],
    x: int,
    y: int,
    *,
    hill_char: str = "I",
) -> bool:
    """True when vertical spine (mask 5) should use tile 24 instead of default 9.

    Requires **E and W** cardinals to be non-hill (so path ``P`` / dirt overlays do not read as
    hill). Requires **all four diagonals** (NW, NE, SW, SE — neighborhood positions 1,3,6,8 in a
    1–8 ring around the cell) to be open land: not ``I``, not water, and in the same grass-like
    set as rim refinement (``G.TFP.`` and POI chars).
    """
    height = len(ascii_lines)
    width = max((len(row) for row in ascii_lines), default=0)

    def ch_at(px: int, py: int) -> str:
        if not (0 <= px < width and 0 <= py < height):
            return "."
        row = ascii_lines[py]
        c = row[px] if px < len(row) else "."
        return c if c != "" else "."

    if ch_at(x - 1, y) == hill_char or ch_at(x + 1, y) == hill_char:
        return False

    open_land = frozenset("G.TFP.") | POI_CHARS
    for px, py in ((x - 1, y - 1), (x + 1, y - 1), (x - 1, y + 1), (x + 1, y + 1)):
        if not (0 <= px < width and 0 <= py < height):
            return False
        ch = ch_at(px, py)
        if ch == hill_char or ch in WATER_CHARS:
            return False
        if ch not in open_land:
            return False
    return True


def hill_mask5_vertical_ridge_tile_from_raw_cardinals(
    ascii_lines: list[str],
    x: int,
    y: int,
    *,
    hill_char: str = "I",
) -> int | None:
    """Resolve mask-5 rim cliff facing using **raw** NESW hills (not interior-stripped).

    Interior exclusion can shrink an east- or west-plateau face to autotile mask **5** (only N+S
    neighbors count). Those cells still have raw **W** hill and open **E** (tile **7**, east cliff)
    or the mirror (**9**). A true one-column spine has neither raw E nor raw W hill → ``None`` so
    the N/S neighbor ridge pass still picks 7 vs 9.
    """
    raw = get_hill_adjacency_bitmask(
        ascii_lines, x, y, hill_char=hill_char, exclude_interior_hill_neighbors=False
    )
    east_hill = bool(raw & 2)
    west_hill = bool(raw & 8)
    if west_hill and not east_hill:
        return 7
    if east_hill and not west_hill:
        return 9
    return None


def compute_hill_autotile_mask(
    ascii_lines: list[str],
    x: int,
    y: int,
    hill_char: str = "I",
) -> int:
    """Bitmask after interior-excluded cardinals + diagonal inference (same as resolve_hill_autotile_tile_id).

    When **raw** adjacency is an outer corner (masks 3/6/9/12), that mask is kept even if both hill
    cardinals are mesa-interior and would be stripped by ``exclude_interior_hill_neighbors`` — otherwise
    E+S (mask 6) collapses to 0 or a single cardinal and the wrong cliff tile is chosen (e.g. E-only
    instead of the E+S corner piece).
    """
    raw_mask = get_hill_adjacency_bitmask(
        ascii_lines, x, y, hill_char=hill_char, exclude_interior_hill_neighbors=False
    )
    if raw_mask == HILL_INTERIOR_MASK:
        return HILL_INTERIOR_MASK
    if raw_mask in HILL_OUTER_CORNER_RAW_MASKS:
        return _hill_mask_with_diagonal_inference(
            ascii_lines, x, y, raw_mask, hill_char=hill_char
        )
    excl_mask = get_hill_adjacency_bitmask(
        ascii_lines, x, y, hill_char=hill_char, exclude_interior_hill_neighbors=True
    )
    return _hill_mask_with_diagonal_inference(
        ascii_lines, x, y, excl_mask, hill_char=hill_char
    )


def _precompute_hill_paint_mask_grids(
    ascii_lines: list[str],
    width: int,
    height: int,
    *,
    hill_char: str = "I",
) -> tuple[list[list[int | None]], list[list[int | None]]]:
    """Per-cell raw cardinal mask and autotile mask for ``hill_char`` cells; ``None`` elsewhere.

    Used by :func:`paint_map_to_png` so painting and first-pass resolution read masks from grids
    instead of recomputing adjacency for every access.
    """
    raw_masks: list[list[int | None]] = [[None] * width for _ in range(height)]
    autotile_masks: list[list[int | None]] = [[None] * width for _ in range(height)]
    for hy in range(height):
        row = ascii_lines[hy] if hy < len(ascii_lines) else ""
        for hx in range(width):
            hc = row[hx] if hx < len(row) else "."
            if hc != hill_char:
                continue
            raw_masks[hy][hx] = get_hill_adjacency_bitmask(
                ascii_lines, hx, hy, hill_char=hill_char, exclude_interior_hill_neighbors=False
            )
            autotile_masks[hy][hx] = compute_hill_autotile_mask(
                ascii_lines, hx, hy, hill_char=hill_char
            )
    return raw_masks, autotile_masks


def hill_two_wide_vertical_strip_spine_tile_id(
    ascii_lines: list[str],
    x: int,
    y: int,
    hmask: int,
    hill_map: dict[int, int],
    hill_char: str = "I",
) -> int | None:
    """Left/right faces of a 2-column vertical hill strip: mask 7 + mask 13 pair → spine 9 / 7.

    A single-column spine uses mask 5 (N+S only). Two columns side-by-side yield mask 7 on the
    west face (W open, E+S+N hill) and mask 13 on the east (E open, W+S+N hill). The defaults now
    match the vertical cliff pair, while this rule preserves the same behavior for overridden maps.
    Wider strips (>2) have interior mask-15 cells, so 7+13 only occurs for exactly two columns.
    """
    width = max((len(row) for row in ascii_lines), default=0)
    ridge_default = hill_map.get(5, 9)
    if hmask == 7:
        if x + 1 >= width or not is_hill_char(ascii_lines, x + 1, y, hill_char):
            return None
        if compute_hill_autotile_mask(ascii_lines, x + 1, y, hill_char=hill_char) != 13:
            return None
        return ridge_default
    if hmask == 13:
        if x <= 0 or not is_hill_char(ascii_lines, x - 1, y, hill_char):
            return None
        if compute_hill_autotile_mask(ascii_lines, x - 1, y, hill_char=hill_char) != 7:
            return None
        return resolve_hill_vertical_ridge_tile_id(3, 5, ridge_default)
    return None


def hill_two_wide_horizontal_strip_spine_tile_id(
    ascii_lines: list[str],
    x: int,
    y: int,
    hmask: int,
    hill_map: dict[int, int],
    hill_char: str = "I",
) -> int | None:
    """Top/bottom faces of a 2-row horizontal hill strip: mask 14 + mask 11 pair → spine 6 / 8.

    A single-row spine uses mask 10 (E+W only). Two rows stacked yield mask 14 on the top face
    (N open, S+E+W hill) and mask 11 on the bottom (S open, N+E+W hill). The defaults now match the
    horizontal cliff pair, while this rule preserves the same behavior for overridden maps. Taller
    strips (>2) have interior mask-15 cells, so 14+11 only occurs for exactly two rows.
    """
    height = len(ascii_lines)
    ridge_h_default = hill_map.get(10, 8)
    if hmask == 14:
        if y + 1 >= height or not is_hill_char(ascii_lines, x, y + 1, hill_char):
            return None
        if compute_hill_autotile_mask(ascii_lines, x, y + 1, hill_char=hill_char) != 11:
            return None
        return resolve_hill_horizontal_ridge_tile_id(2, 3, False, False, ridge_h_default)
    if hmask == 11:
        if y <= 0 or not is_hill_char(ascii_lines, x, y - 1, hill_char):
            return None
        if compute_hill_autotile_mask(ascii_lines, x, y - 1, hill_char=hill_char) != 14:
            return None
        return resolve_hill_horizontal_ridge_tile_id(4, 5, False, False, ridge_h_default)
    return None


def resolve_hill_vertical_ridge_tile_id(
    tn: int | None,
    ts: int | None,
    default_tile: int,
) -> int:
    """Mask 5 (N+S spine): N/S neighbor pass-1 tile ids pick left cliff (9) vs right cliff (7).

    Tile 9 = left cliff, tile 7 = right cliff.
    Right: N-neighbor tile 3, or S-neighbor tile 5 (either alone), or (5,3), or (7,7) spine.
    Left: (2,4) or (4,2), or (9,9) spine middle, or (24,24) legacy pass-1.
    """
    if tn is None or ts is None:
        return default_tile
    if tn == 3 or ts == 5 or (tn == 5 and ts == 3) or (tn == 7 and ts == 7):
        return 7
    if (tn == 2 and ts == 4) or (tn == 4 and ts == 2) or (tn == 9 and ts == 9):
        return 9
    if tn == 24 and ts == 24:
        return 9
    return default_tile


def resolve_hill_horizontal_ridge_tile_id(
    tw: int | None,
    te: int | None,
    west_is_horizontal_ridge: bool,
    east_is_horizontal_ridge: bool,
    default_tile: int,
) -> int:
    """Mask 10 (E+W hill, N+S grass): north/south cliff faces from W/E pass-1 tiles.

    Tile 6: (E tile 3 or E is mask-10 continuation in {default,6}) and
             (W tile 2 or W is mask-10 continuation in {default,6}).
    Tile 8: (E tile 5 or E continuation in {default,8}) and
             (W tile 4 or W continuation in {default,8}).
    If both patterns match (typical spine middle while still default), keep default_tile.
    """
    if tw is None or te is None:
        return default_tile
    cont_e6 = east_is_horizontal_ridge and te in (default_tile, 6)
    cont_w6 = west_is_horizontal_ridge and tw in (default_tile, 6)
    east_ok_6 = (te == 3) or cont_e6
    west_ok_6 = (tw == 2) or cont_w6
    m6 = east_ok_6 and west_ok_6

    cont_e8 = east_is_horizontal_ridge and te in (default_tile, 8)
    cont_w8 = west_is_horizontal_ridge and tw in (default_tile, 8)
    east_ok_8 = (te == 5) or cont_e8
    west_ok_8 = (tw == 4) or cont_w8
    m8 = east_ok_8 and west_ok_8

    if m6 and m8:
        return default_tile
    if m6:
        return 6
    if m8:
        return 8
    return default_tile


def resolve_hill_mask11_corner_extension_connect_tile_id(
    tw: int | None,
    te: int | None,
    *,
    w_corner_tile: int = 4,
    e_extension_tile: int = 8,
    connect_tile: int = 8,
) -> int | None:
    """Mask 11 (N+E+W hill, S open): bridge W corner to E horizontal extension.

    When the west rim resolved to ``w_corner_tile`` (default 4 = N+E outer corner in the reference
    sheet) and the east rim to ``e_extension_tile`` (default 8 = horizontal spine / extension),
    return ``connect_tile`` (default 8) for the center cell so the bottom cliff line visually
    connects. Otherwise return None (keep first-pass ``hill_map[11]`` etc.).

    Tile ids are 1-based hills.aseprite indices; override via ``terrain.bitmask.json`` hill keys
    ``mask11_w_corner_tile_for_extension``, ``mask11_e_extension_neighbor_tile``,
    ``mask11_extension_connect_tile``.
    """
    if tw is None or te is None:
        return None
    if tw == w_corner_tile and te == e_extension_tile:
        return connect_tile
    return None


# Raw cardinal hill masks with exactly one hill neighbor (peninsula tips).
HILL_RAW_CARDINAL_PENINSULA_TIP_MASKS: frozenset[int] = frozenset({1, 2, 4, 8})


def resolve_hill_mask14_n_peninsula_connector_tile_id(
    n_open: bool,
    te: int | None,
    tw: int | None,
    ts: int | None,
    *,
    ew_ridge_tile: int = 8,
    south_tiles: frozenset[int] | None = None,
    south_raw_cardinal_mask: int | None = None,
    south_tip_raw_masks: frozenset[int] | None = None,
    out_tile: int = 21,
) -> int | None:
    """Mask **14** (N open, S+E+W hill): T-down connector when flanked by horizontal ridge tiles.

    When **north** is not hill (open), **east** and **west** resolved hill tiles equal
    ``ew_ridge_tile`` (default 8), and **south** matches either:

    - resolved tile id in ``south_tiles`` (default **10** and **24**), or
    - ``south_raw_cardinal_mask`` in ``south_tip_raw_masks`` (default raw masks **1, 2, 4, 8**).

    Otherwise None (keep ``hill_map[14]`` / strip spine / etc.).

    Override via ``terrain.bitmask.json`` hill keys ``mask14_ew_neighbor_tile``,
    ``mask14_south_neighbor_tiles``, ``mask14_south_neighbor_raw_tip_masks``,
    ``mask14_peninsula_n_tile``.
    """
    if not n_open:
        return None
    if te is None or tw is None:
        return None
    if te != ew_ridge_tile or tw != ew_ridge_tile:
        return None
    south_ok = south_tiles if south_tiles is not None else frozenset({10, 24})
    tips = south_tip_raw_masks if south_tip_raw_masks is not None else HILL_RAW_CARDINAL_PENINSULA_TIP_MASKS
    tile_ok = ts is not None and ts in south_ok
    geo_ok = (
        south_raw_cardinal_mask is not None and south_raw_cardinal_mask in tips
    )
    if not (tile_ok or geo_ok):
        return None
    return out_tile


def apply_hill_mask14_n_peninsula_connector_pass(
    ascii_lines: list[str],
    base_hill_tile_ids: list[list[int | None]],
    width: int,
    height: int,
    *,
    hill_char: str = "I",
    hill_cfg: dict[str, Any] | None = None,
) -> None:
    """Apply :func:`resolve_hill_mask14_n_peninsula_connector_tile_id` to mask-14 hill cells."""
    cfg = hill_cfg or {}
    if cfg.get("mask14_n_peninsula_connector", True) is False:
        return
    ew = int(cfg.get("mask14_ew_neighbor_tile", 8))
    out_t = int(cfg.get("mask14_peninsula_n_tile", 21))
    south_raw = cfg.get("mask14_south_neighbor_tiles")
    if south_raw is not None and isinstance(south_raw, list):
        south_fs: frozenset[int] = frozenset(int(x) for x in south_raw)
    else:
        south_fs = frozenset({10, 24})
    tips_raw = cfg.get("mask14_south_neighbor_raw_tip_masks")
    if tips_raw is not None and isinstance(tips_raw, list):
        tips: frozenset[int] = frozenset(int(x) for x in tips_raw)
    else:
        tips = HILL_RAW_CARDINAL_PENINSULA_TIP_MASKS
    for hy in range(height):
        for hx in range(width):
            if base_hill_tile_ids[hy][hx] is None:
                continue
            row = ascii_lines[hy]
            if (row[hx] if hx < len(row) else ".") != hill_char:
                continue
            amask = compute_hill_autotile_mask(ascii_lines, hx, hy, hill_char=hill_char)
            if amask != 14:
                continue
            n_open = hy == 0 or not is_hill_char(ascii_lines, hx, hy - 1, hill_char=hill_char)
            te = base_hill_tile_ids[hy][hx + 1] if hx + 1 < width else None
            tw = base_hill_tile_ids[hy][hx - 1] if hx > 0 else None
            ts = base_hill_tile_ids[hy + 1][hx] if hy + 1 < height else None
            south_raw_mask: int | None = None
            if hy + 1 < height:
                south_raw_mask = get_hill_adjacency_bitmask(
                    ascii_lines,
                    hx,
                    hy + 1,
                    hill_char=hill_char,
                    exclude_interior_hill_neighbors=False,
                )
            m = resolve_hill_mask14_n_peninsula_connector_tile_id(
                n_open,
                te,
                tw,
                ts,
                ew_ridge_tile=ew,
                south_tiles=south_fs,
                south_raw_cardinal_mask=south_raw_mask,
                south_tip_raw_masks=tips,
                out_tile=out_t,
            )
            if m is not None:
                base_hill_tile_ids[hy][hx] = m

# Mask 11 default tile (``hill_map[11]``): when projects override it to a tee, require a cardinal
# hill neighbor whose first-pass tile is in this set; otherwise replace it with ``hill_map[10]``.
# Override via
# ``terrain.bitmask.json`` hill key ``mask11_tee_neighbor_tile_ids``.
HILL_MASK11_TEE_NEIGHBOR_TILES: frozenset[int] = frozenset(range(10, 15)) | frozenset(range(23, 34))


def apply_hill_mask11_tee_neighbor_gate(
    ascii_lines: list[str],
    base_hill_tile_ids: list[list[int | None]],
    width: int,
    height: int,
    hill_map: dict[int, int],
    hill_char: str = "I",
    *,
    neighbor_tee_tile_ids: frozenset[int] | None = None,
) -> None:
    """After first-pass hill tiles: trim mask-11 tee usage to peninsula-adjacent cases.

    If a cell has autotile mask **11** and its stored tile equals ``hill_map[11]`` (the S-open tee),
    keep it only when **some** cardinal neighbor that is hill has a non-``None`` tile id in
    ``neighbor_tee_tile_ids`` (default **10–14** and **23–33**). Otherwise set
    ``hill_map[10]`` (horizontal ridge / extension). With the default map, ``hill_map[11]`` already
    equals that south cliff face, so this pass is effectively neutral. In-place.
    """
    allowed = (
        neighbor_tee_tile_ids
        if neighbor_tee_tile_ids is not None
        else HILL_MASK11_TEE_NEIGHBOR_TILES
    )
    tee_id = hill_map.get(11, 8)
    alt_id = hill_map.get(10, 8)
    for hy in range(height):
        for hx in range(width):
            if base_hill_tile_ids[hy][hx] is None:
                continue
            row = ascii_lines[hy] if hy < len(ascii_lines) else ""
            if (row[hx] if hx < len(row) else ".") != hill_char:
                continue
            if base_hill_tile_ids[hy][hx] != tee_id:
                continue
            if compute_hill_autotile_mask(ascii_lines, hx, hy, hill_char=hill_char) != 11:
                continue
            ok = False
            for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                nx, ny = hx + dx, hy + dy
                if not (0 <= ny < height and 0 <= nx < width):
                    continue
                nrow = ascii_lines[ny] if ny < len(ascii_lines) else ""
                if not is_hill_char(ascii_lines, nx, ny, hill_char):
                    continue
                tid = base_hill_tile_ids[ny][nx]
                if tid is not None and tid in allowed:
                    ok = True
                    break
            if not ok:
                base_hill_tile_ids[hy][hx] = alt_id


# Peninsula chain / cap: ends 10–13, 4-way 14, extension 22, inset-style 23–33 (1-based hill sheet).
HILL_PENINSULA_CHAIN_TILE_IDS: frozenset[int] = (
    frozenset(range(10, 15)) | frozenset(range(23, 34)) | frozenset({22})
)


def resolve_hill_peninsula_n_junction_tile_id(
    e_hill: bool,
    w_hill: bool,
    te: int | None,
    tw: int | None,
    *,
    bulk_e: bool,
    bulk_w: bool,
    side_cap_tile: int = 6,
    tee_both_sides: int = 16,
    tee_e_side: int = 15,
    tee_w_side: int = 17,
) -> int | None:
    """N-pointing spine junction (mask 5, N+S hill): T opens north when E/W attach bulk.

    Prefer cap match (``side_cap_tile``, default 6): both sides → ``tee_both_sides`` (16); E only →
    ``tee_e_side`` (15); W only → ``tee_w_side`` (17). If caps do not match, fall back using
    ``bulk_e`` / ``bulk_w`` (hill neighbor tile not in peninsula chain) the same way.
    """
    if not e_hill and not w_hill:
        return None
    e_cap = e_hill and te == side_cap_tile
    w_cap = w_hill and tw == side_cap_tile
    if e_cap and w_cap:
        return tee_both_sides
    if e_cap and not w_cap:
        return tee_e_side
    if w_cap and not e_cap:
        return tee_w_side
    if bulk_e and bulk_w:
        return tee_both_sides
    if bulk_e and not bulk_w:
        return tee_e_side
    if bulk_w and not bulk_e:
        return tee_w_side
    return None


def apply_hill_peninsula_vertical_spine_pass(
    ascii_lines: list[str],
    base_hill_tile_ids: list[list[int | None]],
    width: int,
    height: int,
    hill_map: dict[int, int],
    hill_char: str = "I",
    *,
    chain_tile_ids: frozenset[int] | None = None,
    extend_tile: int = 24,
    side_cap_tile: int = 6,
    tee_both_sides: int = 16,
    tee_e_side: int = 15,
    tee_w_side: int = 17,
) -> frozenset[tuple[int, int]]:
    """Walk from N-facing (mask 1) and S-facing (mask 4) tips along mask-5 spines.

    *Interior* steps: autotile mask **5** with E and W not hill → ``extend_tile`` (default 24).
    First cell north/south that is mask **7**, **13**, or **11** with a **bulk** cheek (E/W hill
    tile not in ``chain_tile_ids``): assign N-junction tee via
    :func:`resolve_hill_peninsula_n_junction_tile_id` (caps tile 6 → 16/15/17, else bulk-only).

    Runs after vertical ridge pass so extend / 15–17 override 9/7. Skips cells that use mask-5
    tile 24 (open diagonals). In-place.

    Returns coordinates ``(x, y)`` where this pass wrote a new tile id.
    """
    chain = chain_tile_ids if chain_tile_ids is not None else HILL_PENINSULA_CHAIN_TILE_IDS
    modified: set[tuple[int, int]] = set()

    def _bulk(tid: int | None) -> bool:
        return tid is not None and tid not in chain

    def _junction_tile(
        hx: int,
        cy: int,
        e_hill: bool,
        w_hill: bool,
    ) -> None:
        te = base_hill_tile_ids[cy][hx + 1] if e_hill else None
        tw = base_hill_tile_ids[cy][hx - 1] if w_hill else None
        bulk_e = e_hill and _bulk(te)
        bulk_w = w_hill and _bulk(tw)
        if not bulk_e and not bulk_w:
            return
        jt = resolve_hill_peninsula_n_junction_tile_id(
            e_hill,
            w_hill,
            te,
            tw,
            bulk_e=bulk_e,
            bulk_w=bulk_w,
            side_cap_tile=side_cap_tile,
            tee_both_sides=tee_both_sides,
            tee_e_side=tee_e_side,
            tee_w_side=tee_w_side,
        )
        if jt is not None:
            base_hill_tile_ids[cy][hx] = jt
            modified.add((hx, cy))

    def _walk_from_tip(hx: int, hy: int, step: int) -> None:
        """step -1 = walk north (from mask-1 tip); +1 = walk south (from mask-4 tip)."""
        cy = hy + step
        while 0 <= cy < height and is_hill_char(ascii_lines, hx, cy, hill_char):
            if base_hill_tile_ids[cy][hx] is None:
                break
            if hill_mask5_vertical_spine_open_diagonals_for_tile24(
                ascii_lines, hx, cy, hill_char=hill_char
            ):
                break
            amask = compute_hill_autotile_mask(ascii_lines, hx, cy, hill_char=hill_char)
            e_hill = is_hill_char(ascii_lines, hx + 1, cy, hill_char)
            w_hill = is_hill_char(ascii_lines, hx - 1, cy, hill_char)
            if amask == 5 and not e_hill and not w_hill:
                base_hill_tile_ids[cy][hx] = extend_tile
                modified.add((hx, cy))
                cy += step
                continue
            if amask in (7, 13, 11):
                _junction_tile(hx, cy, e_hill, w_hill)
            break

    for hy in range(height):
        for hx in range(width):
            if base_hill_tile_ids[hy][hx] is None:
                continue
            row = ascii_lines[hy] if hy < len(ascii_lines) else ""
            if (row[hx] if hx < len(row) else ".") != hill_char:
                continue
            am = compute_hill_autotile_mask(ascii_lines, hx, hy, hill_char=hill_char)
            if am == 1:
                _walk_from_tip(hx, hy, -1)
            elif am == 4:
                _walk_from_tip(hx, hy, 1)

    return frozenset(modified)


@dataclasses.dataclass(frozen=True)
class HillPeninsulaProtrusionTileIds:
    """First hill cell inward from cardinal tips (masks 1/2/4/8): tee vs extender by perpendicular hills."""

    # Mask 1 tip (hill N only, south peninsula end / tile 12): interior north; E/W both hill →
    # south-opening tee connector (default 21); E/W both grass → vertical extender 24.
    south_end_interior_n_tee: int = 21
    south_end_interior_n_extender: int = 24
    # Mask 4 tip (hill S only, “north” end): interior south; check interior E/W.
    north_end_interior_s_tee: int = 21
    north_end_interior_s_extender: int = 24
    # Mask 2 tip (hill E, “west” end): interior east; N/S both hill → east tee 18; both grass →
    # horizontal ridge ``hill_map[10]`` (default 8), not the narrow horizontal nib tile 23.
    west_end_interior_e_tee: int = 18
    west_end_interior_e_extender: int = 8
    # Mask 8 tip (hill W, “east” end): interior west; N/S both hill → west tee 19; both grass → 8.
    east_end_interior_w_tee: int = 19
    east_end_interior_w_extender: int = 8


@dataclasses.dataclass(frozen=True)
class HillPeninsulaConnectorTileIds:
    """Peninsula connector art selected from cardinal endpoint anchors and neighboring path tiles."""

    north_tip_both_sides: int = 16
    north_tip_left_open: int = 39
    north_tip_right_open: int = 41
    north_tip_extension: int = 24
    south_tip_both_sides: int = 21
    south_tip_left_open: int = 43
    south_tip_right_open: int = 45
    south_tip_extension: int = 24
    east_tip_both_sides: int = 18
    east_tip_top_open: int = 40
    east_tip_bottom_open: int = 44
    east_tip_extension: int = 23
    west_tip_both_sides: int = 19
    west_tip_top_open: int = 38
    west_tip_bottom_open: int = 42
    west_tip_extension: int = 23
    elbow_e_s: int = 25
    elbow_w_s: int = 27
    elbow_e_n: int = 31
    elbow_w_n: int = 33
    tee_w_n_e: int = 32
    tee_w_s_e: int = 26
    tee_s_e_n: int = 28
    tee_s_w_n: int = 30
    connector_4way: int = 29


DEFAULT_HILL_PENINSULA_PATH_TILE_IDS: frozenset[int] = frozenset(
    {
        10,
        11,
        12,
        13,
        16,
        18,
        19,
        21,
        23,
        24,
        25,
        26,
        27,
        28,
        29,
        30,
        31,
        32,
        33,
        38,
        39,
        40,
        41,
        42,
        43,
        44,
        45,
    }
)


def parse_hill_peninsula_connector_tile_ids(
    hill_cfg: dict[str, Any] | None,
) -> HillPeninsulaConnectorTileIds:
    """Parse optional ``hill.peninsula_connectors`` tile id overrides."""
    if not isinstance(hill_cfg, dict):
        return HillPeninsulaConnectorTileIds()
    raw = hill_cfg.get("peninsula_connectors")
    if not isinstance(raw, dict):
        return HillPeninsulaConnectorTileIds()
    defaults = dataclasses.asdict(HillPeninsulaConnectorTileIds())
    parsed: dict[str, int] = {}
    for key, default in defaults.items():
        value = raw.get(key, default)
        if isinstance(value, bool):
            parsed[key] = int(default)
            continue
        try:
            parsed[key] = int(value)
        except (TypeError, ValueError):
            parsed[key] = int(default)
    return HillPeninsulaConnectorTileIds(**parsed)


def parse_hill_peninsula_path_tile_ids(
    hill_cfg: dict[str, Any] | None,
    connector_tiles: HillPeninsulaConnectorTileIds | None = None,
) -> frozenset[int]:
    """Parse optional ``hill.peninsula_path_tile_ids`` used by elbow/tee/cross classification."""
    defaults = set(DEFAULT_HILL_PENINSULA_PATH_TILE_IDS)
    if connector_tiles is not None:
        defaults.update(int(v) for v in dataclasses.asdict(connector_tiles).values())
    if not isinstance(hill_cfg, dict):
        return frozenset(defaults)
    raw = hill_cfg.get("peninsula_path_tile_ids")
    if not isinstance(raw, (list, tuple, set)):
        return frozenset(defaults)
    out: set[int] = set()
    for value in raw:
        if isinstance(value, bool):
            continue
        try:
            out.add(int(value))
        except (TypeError, ValueError):
            continue
    return frozenset(out or defaults)


def resolve_hill_peninsula_connector_tile_id(
    neighbor_mask: int,
    tiles: HillPeninsulaConnectorTileIds | None = None,
) -> int | None:
    """Resolve peninsula connector tile from NESW neighbor mask of adjacent peninsula path tiles."""
    t = tiles if tiles is not None else HillPeninsulaConnectorTileIds()
    return {
        6: t.elbow_e_s,
        12: t.elbow_w_s,
        3: t.elbow_e_n,
        9: t.elbow_w_n,
        11: t.tee_w_n_e,
        14: t.tee_w_s_e,
        7: t.tee_s_e_n,
        13: t.tee_s_w_n,
        15: t.connector_4way,
    }.get(int(neighbor_mask) & 15)


def apply_hill_peninsula_connector_pass(
    ascii_lines: list[str],
    base_hill_tile_ids: list[list[int | None]],
    width: int,
    height: int,
    hill_char: str = "I",
    *,
    tiles: HillPeninsulaConnectorTileIds | None = None,
    path_tile_ids: frozenset[int] | None = None,
) -> frozenset[tuple[int, int]]:
    """Use cardinal endpoint tiles as anchors and rewrite the inward connector hill cell.

    Endpoint tiles 10–13 remain unchanged. The adjacent hill cell toward the hill mass becomes the
    straight extender, mixed elbow, or tee connector selected by the side cells at that inward step.
    A second classifier handles peninsula-path elbow / tee / cross cells from neighboring path tiles.
    """
    t = tiles if tiles is not None else HillPeninsulaConnectorTileIds()
    path_ids = path_tile_ids if path_tile_ids is not None else DEFAULT_HILL_PENINSULA_PATH_TILE_IDS
    touched: set[tuple[int, int]] = set()

    def _set_if_hill(px: int, py: int, tile_id: int) -> bool:
        if not (0 <= px < width and 0 <= py < height):
            return False
        if base_hill_tile_ids[py][px] is None:
            return False
        if not is_hill_char(ascii_lines, px, py, hill_char):
            return False
        base_hill_tile_ids[py][px] = tile_id
        touched.add((px, py))
        return True

    def _walk_from_anchor(
        ix: int,
        iy: int,
        step_x: int,
        step_y: int,
        side_a: tuple[int, int],
        side_b: tuple[int, int],
        both_sides_tile: int,
        side_a_open_tile: int,
        side_b_open_tile: int,
        extension_tile: int,
    ) -> None:
        cx, cy = ix, iy
        while 0 <= cx < width and 0 <= cy < height:
            if base_hill_tile_ids[cy][cx] is None:
                return
            if not is_hill_char(ascii_lines, cx, cy, hill_char):
                return
            side_a_hill = is_hill_char(ascii_lines, cx + side_a[0], cy + side_a[1], hill_char)
            side_b_hill = is_hill_char(ascii_lines, cx + side_b[0], cy + side_b[1], hill_char)
            if side_a_hill and side_b_hill:
                _set_if_hill(cx, cy, both_sides_tile)
                return
            if not side_a_hill and side_b_hill:
                _set_if_hill(cx, cy, side_a_open_tile)
                return
            if side_a_hill and not side_b_hill:
                _set_if_hill(cx, cy, side_b_open_tile)
                return
            if not _set_if_hill(cx, cy, extension_tile):
                return
            cx += step_x
            cy += step_y

    for hy in range(height):
        for hx in range(width):
            anchor = base_hill_tile_ids[hy][hx]
            if anchor not in (10, 11, 12, 13):
                continue
            if not is_hill_char(ascii_lines, hx, hy, hill_char):
                continue
            raw_tip = get_hill_adjacency_bitmask(
                ascii_lines,
                hx,
                hy,
                hill_char=hill_char,
                exclude_interior_hill_neighbors=False,
            )

            if raw_tip == 4 or (raw_tip not in HILL_RAW_CARDINAL_PENINSULA_TIP_MASKS and anchor == 10):
                _walk_from_anchor(
                    hx,
                    hy + 1,
                    0,
                    1,
                    (-1, 0),
                    (1, 0),
                    t.north_tip_both_sides,
                    t.north_tip_left_open,
                    t.north_tip_right_open,
                    t.north_tip_extension,
                )
            elif raw_tip == 1 or (raw_tip not in HILL_RAW_CARDINAL_PENINSULA_TIP_MASKS and anchor == 12):
                _walk_from_anchor(
                    hx,
                    hy - 1,
                    0,
                    -1,
                    (-1, 0),
                    (1, 0),
                    t.south_tip_both_sides,
                    t.south_tip_left_open,
                    t.south_tip_right_open,
                    t.south_tip_extension,
                )
            elif raw_tip == 8 or (raw_tip not in HILL_RAW_CARDINAL_PENINSULA_TIP_MASKS and anchor == 11):
                _walk_from_anchor(
                    hx - 1,
                    hy,
                    -1,
                    0,
                    (0, -1),
                    (0, 1),
                    t.east_tip_both_sides,
                    t.east_tip_top_open,
                    t.east_tip_bottom_open,
                    t.east_tip_extension,
                )
            elif raw_tip == 2 or (raw_tip not in HILL_RAW_CARDINAL_PENINSULA_TIP_MASKS and anchor == 13):
                _walk_from_anchor(
                    hx + 1,
                    hy,
                    1,
                    0,
                    (0, -1),
                    (0, 1),
                    t.west_tip_both_sides,
                    t.west_tip_top_open,
                    t.west_tip_bottom_open,
                    t.west_tip_extension,
                )

    for hy in range(height):
        for hx in range(width):
            current_tile = base_hill_tile_ids[hy][hx]
            if current_tile is None:
                continue
            promotable_touched_tiles = frozenset(
                {
                    16,
                    18,
                    19,
                    21,
                    23,
                    24,
                    38,
                    39,
                    40,
                    41,
                    42,
                    43,
                    44,
                    45,
                }
            )
            if (hx, hy) in touched and current_tile not in promotable_touched_tiles:
                continue
            if current_tile in (10, 11, 12, 13):
                continue
            if not is_hill_char(ascii_lines, hx, hy, hill_char):
                continue
            neighbor_mask = 0
            for bit, nx, ny in (
                (1, hx, hy - 1),
                (2, hx + 1, hy),
                (4, hx, hy + 1),
                (8, hx - 1, hy),
            ):
                if 0 <= nx < width and 0 <= ny < height:
                    nt = base_hill_tile_ids[ny][nx]
                    if nt is not None and nt in path_ids:
                        neighbor_mask |= bit
            connector = resolve_hill_peninsula_connector_tile_id(neighbor_mask, t)
            if connector is not None:
                base_hill_tile_ids[hy][hx] = connector
                touched.add((hx, hy))

    return frozenset(touched)


@dataclasses.dataclass(frozen=True)
class HillInset2x2Rule:
    """Tile-id rule for one 2x2 hill inset shape."""

    edge_a: frozenset[int]
    edge_b: frozenset[int]
    out_tile: int


@dataclasses.dataclass(frozen=True)
class HillInset2x2Rules:
    """NW/NE/SE/SW 2x2 hill inset rules."""

    nw: HillInset2x2Rule = dataclasses.field(
        default_factory=lambda: HillInset2x2Rule(frozenset({39, 2, 9}), frozenset({38, 2, 8}), 34)
    )
    ne: HillInset2x2Rule = dataclasses.field(
        default_factory=lambda: HillInset2x2Rule(frozenset({41, 3, 7}), frozenset({40, 3, 6}), 35)
    )
    se: HillInset2x2Rule = dataclasses.field(
        default_factory=lambda: HillInset2x2Rule(frozenset({44, 5, 8}), frozenset({45, 5, 7}), 37)
    )
    sw: HillInset2x2Rule = dataclasses.field(
        default_factory=lambda: HillInset2x2Rule(frozenset({42, 4, 8}), frozenset({43, 4, 9}), 36)
    )


def parse_hill_inset_2x2_rules(hill_cfg: dict[str, Any] | None) -> HillInset2x2Rules:
    """Parse optional ``hill.inset_2x2_rules`` overrides."""
    defaults = HillInset2x2Rules()
    if not isinstance(hill_cfg, dict):
        return defaults
    raw = hill_cfg.get("inset_2x2_rules")
    if not isinstance(raw, dict):
        return defaults

    def _parse_rule(key: str, default: HillInset2x2Rule) -> HillInset2x2Rule:
        item = raw.get(key)
        if not isinstance(item, dict):
            return default

        def _int_set(name: str, fallback: frozenset[int]) -> frozenset[int]:
            value = item.get(name)
            if not isinstance(value, (list, tuple, set)):
                return fallback
            out: set[int] = set()
            for v in value:
                if isinstance(v, bool):
                    continue
                try:
                    out.add(int(v))
                except (TypeError, ValueError):
                    continue
            return frozenset(out or fallback)

        out_raw = item.get("out_tile", default.out_tile)
        try:
            out_tile = int(out_raw)
        except (TypeError, ValueError):
            out_tile = default.out_tile
        return HillInset2x2Rule(
            edge_a=_int_set("edge_a", default.edge_a),
            edge_b=_int_set("edge_b", default.edge_b),
            out_tile=out_tile,
        )

    return HillInset2x2Rules(
        nw=_parse_rule("nw", defaults.nw),
        ne=_parse_rule("ne", defaults.ne),
        se=_parse_rule("se", defaults.se),
        sw=_parse_rule("sw", defaults.sw),
    )


def apply_hill_inset_2x2_pass(
    ascii_lines: list[str],
    base_hill_tile_ids: list[list[int | None]],
    width: int,
    height: int,
    *,
    rules: HillInset2x2Rules | None = None,
    hill_char: str = "I",
) -> frozenset[tuple[int, int]]:
    """Apply 2x2 hill inset rules to the resolved hill grid."""
    r = rules if rules is not None else HillInset2x2Rules()
    source = [row[:] for row in base_hill_tile_ids]
    touched: set[tuple[int, int]] = set()

    def _tile(px: int, py: int) -> int | None:
        if not (0 <= px < width and 0 <= py < height):
            return None
        return source[py][px]

    def _is_grass(px: int, py: int) -> bool:
        if not (0 <= px < width and 0 <= py < height):
            return True
        if not is_hill_char(ascii_lines, px, py, hill_char):
            return True
        return source[py][px] is None

    def _is_target_hill(px: int, py: int) -> bool:
        if not (0 <= px < width and 0 <= py < height):
            return False
        return is_hill_char(ascii_lines, px, py, hill_char)

    def _set(px: int, py: int, tile_id: int) -> None:
        if _is_target_hill(px, py):
            base_hill_tile_ids[py][px] = tile_id
            touched.add((px, py))

    for y in range(max(0, height - 1)):
        for x in range(max(0, width - 1)):
            tl = (x, y)
            tr = (x + 1, y)
            bl = (x, y + 1)
            br = (x + 1, y + 1)

            if (
                _is_grass(*tl)
                and _tile(*tr) in r.nw.edge_a
                and _tile(*bl) in r.nw.edge_b
            ):
                _set(*br, r.nw.out_tile)
            if (
                _is_grass(*tr)
                and _tile(*tl) in r.ne.edge_a
                and _tile(*br) in r.ne.edge_b
            ):
                _set(*bl, r.ne.out_tile)
            if (
                _is_grass(*br)
                and _tile(*tr) in r.se.edge_a
                and _tile(*bl) in r.se.edge_b
            ):
                _set(*tl, r.se.out_tile)
            if (
                _is_grass(*bl)
                and _tile(*tl) in r.sw.edge_a
                and _tile(*br) in r.sw.edge_b
            ):
                _set(*tr, r.sw.out_tile)

    return frozenset(touched)


@dataclasses.dataclass(frozen=True)
class HillFourWayConnectorTileIds:
    """Final raw mask-15 connector art selected from resolved N/E/S/W neighbor tiles."""

    n7_e6_s9_w8: int = 47
    n9_e8_s7_w6: int = 46
    peninsula_4way: int = 29
    n_pen_e_hill_s_hill_w_pen: int = 15
    n_pen_e_pen_s_hill_w_hill: int = 17
    n_hill_e_hill_s_pen_w_pen: int = 20
    n_hill_e_pen_s_pen_w_hill: int = 22


def parse_hill_four_way_connector_tile_ids(
    hill_cfg: dict[str, Any] | None,
) -> HillFourWayConnectorTileIds:
    """Parse optional ``hill.four_way_connectors`` tile id overrides."""
    defaults = dataclasses.asdict(HillFourWayConnectorTileIds())
    if not isinstance(hill_cfg, dict):
        return HillFourWayConnectorTileIds()
    raw = hill_cfg.get("four_way_connectors")
    if not isinstance(raw, dict):
        return HillFourWayConnectorTileIds()
    parsed: dict[str, int] = {}
    for key, default in defaults.items():
        value = raw.get(key, default)
        if isinstance(value, bool):
            parsed[key] = int(default)
            continue
        try:
            parsed[key] = int(value)
        except (TypeError, ValueError):
            parsed[key] = int(default)
    return HillFourWayConnectorTileIds(**parsed)


def apply_hill_four_way_connector_pass(
    ascii_lines: list[str],
    base_hill_tile_ids: list[list[int | None]],
    width: int,
    height: int,
    *,
    tiles: HillFourWayConnectorTileIds | None = None,
    peninsula_tile_ids: frozenset[int] | None = None,
    hill_map: dict[int, int] | None = None,
    hill_char: str = "I",
) -> frozenset[tuple[int, int]]:
    """Apply final 4-way connector rules to raw NEWS hill cells."""
    t = tiles if tiles is not None else HillFourWayConnectorTileIds()
    peninsula_ids = peninsula_tile_ids if peninsula_tile_ids is not None else DEFAULT_HILL_PENINSULA_PATH_TILE_IDS
    hm = hill_map if hill_map is not None else HILL_MAP
    source = [row[:] for row in base_hill_tile_ids]
    touched: set[tuple[int, int]] = set()

    def _tile(px: int, py: int) -> int | None:
        if not (0 <= px < width and 0 <= py < height):
            return None
        return source[py][px]

    def _raw_mask(px: int, py: int) -> int | None:
        if not is_hill_char(ascii_lines, px, py, hill_char):
            return None
        return get_hill_adjacency_bitmask(
            ascii_lines,
            px,
            py,
            hill_char=hill_char,
            exclude_interior_hill_neighbors=False,
        )

    def _peninsula_tile_for_geometry(px: int, py: int, tid: int | None) -> int | None:
        if not is_hill_char(ascii_lines, px, py, hill_char):
            return None
        if tid in peninsula_ids:
            return tid
        rm = _raw_mask(px, py)
        if rm in HILL_RAW_CARDINAL_PENINSULA_TIP_MASKS and (tid is None or tid in (34, 35, 36, 37)):
            return hm.get(int(rm), HILL_MAP.get(int(rm)))
        if (
            rm == 10
            and not is_hill_char(ascii_lines, px, py - 1, hill_char)
            and not is_hill_char(ascii_lines, px, py + 1, hill_char)
        ):
            return 23
        if (
            rm == 5
            and not is_hill_char(ascii_lines, px - 1, py, hill_char)
            and not is_hill_char(ascii_lines, px + 1, py, hill_char)
        ):
            return 24
        return None

    def _is_peninsula_at(px: int, py: int, tid: int | None) -> bool:
        return _peninsula_tile_for_geometry(px, py, tid) is not None

    def _is_non_peninsula_hill(px: int, py: int, tid: int | None) -> bool:
        return is_hill_char(ascii_lines, px, py, hill_char) and not _is_peninsula_at(px, py, tid)

    def _normalize_peninsula_neighbors(coords: tuple[tuple[int, int, int | None], ...]) -> None:
        for px, py, tid in coords:
            pt = _peninsula_tile_for_geometry(px, py, tid)
            if pt is not None and (0 <= px < width and 0 <= py < height):
                base_hill_tile_ids[py][px] = pt
                touched.add((px, py))

    for hy in range(height):
        for hx in range(width):
            if not is_hill_char(ascii_lines, hx, hy, hill_char):
                continue
            raw_mask = get_hill_adjacency_bitmask(
                ascii_lines,
                hx,
                hy,
                hill_char=hill_char,
                exclude_interior_hill_neighbors=False,
            )
            if raw_mask != HILL_INTERIOR_MASK:
                continue
            tn = _tile(hx, hy - 1)
            te = _tile(hx + 1, hy)
            ts = _tile(hx, hy + 1)
            tw = _tile(hx - 1, hy)
            out_tile: int | None = None
            if (tn, te, ts, tw) == (7, 6, 9, 8):
                out_tile = t.n7_e6_s9_w8
            elif (tn, te, ts, tw) == (9, 8, 7, 6):
                out_tile = t.n9_e8_s7_w6
            elif (
                _is_peninsula_at(hx, hy - 1, tn)
                and _is_peninsula_at(hx + 1, hy, te)
                and _is_peninsula_at(hx, hy + 1, ts)
                and _is_peninsula_at(hx - 1, hy, tw)
            ):
                out_tile = t.peninsula_4way
                _normalize_peninsula_neighbors(
                    ((hx, hy - 1, tn), (hx + 1, hy, te), (hx, hy + 1, ts), (hx - 1, hy, tw))
                )
            elif (
                _is_peninsula_at(hx, hy - 1, tn)
                and _is_non_peninsula_hill(hx + 1, hy, te)
                and _is_non_peninsula_hill(hx, hy + 1, ts)
                and _is_peninsula_at(hx - 1, hy, tw)
            ):
                out_tile = t.n_pen_e_hill_s_hill_w_pen
                _normalize_peninsula_neighbors(((hx, hy - 1, tn), (hx - 1, hy, tw)))
            elif (
                _is_peninsula_at(hx, hy - 1, tn)
                and _is_peninsula_at(hx + 1, hy, te)
                and _is_non_peninsula_hill(hx, hy + 1, ts)
                and _is_non_peninsula_hill(hx - 1, hy, tw)
            ):
                out_tile = t.n_pen_e_pen_s_hill_w_hill
                _normalize_peninsula_neighbors(((hx, hy - 1, tn), (hx + 1, hy, te)))
            elif (
                _is_non_peninsula_hill(hx, hy - 1, tn)
                and _is_non_peninsula_hill(hx + 1, hy, te)
                and _is_peninsula_at(hx, hy + 1, ts)
                and _is_peninsula_at(hx - 1, hy, tw)
            ):
                out_tile = t.n_hill_e_hill_s_pen_w_pen
                _normalize_peninsula_neighbors(((hx, hy + 1, ts), (hx - 1, hy, tw)))
            elif (
                _is_non_peninsula_hill(hx, hy - 1, tn)
                and _is_peninsula_at(hx + 1, hy, te)
                and _is_peninsula_at(hx, hy + 1, ts)
                and _is_non_peninsula_hill(hx - 1, hy, tw)
            ):
                out_tile = t.n_hill_e_pen_s_pen_w_hill
                _normalize_peninsula_neighbors(((hx + 1, hy, te), (hx, hy + 1, ts)))
            if out_tile is not None:
                base_hill_tile_ids[hy][hx] = out_tile
                touched.add((hx, hy))

    return frozenset(touched)


def apply_hill_peninsula_protrusion_adjacent_pass(
    ascii_lines: list[str],
    base_hill_tile_ids: list[list[int | None]],
    width: int,
    height: int,
    hill_map: dict[int, int],
    hill_char: str = "I",
    *,
    tiles: HillPeninsulaProtrusionTileIds | None = None,
) -> frozenset[tuple[int, int]]:
    """Fix the single spine cell adjacent to each cardinal peninsula tip (masks 1, 2, 4, 8).

    * **Mask 1** (hill to N only, south peninsula end / ``hill_map[1]`` e.g. tile 12): first hill
      **north** of tip; if interior E and W are hill (mask **15**), use ``south_end_interior_n_tee``
      (default **21**, south tee connector); if both non-hill (mask **5**), use **24**.
    * **Mask 4** (hill to S only): first hill **south** of tip; E/W both hill → 21 (interior mask
      **15**); both non-hill → 24 (mask **5**).
    * **Mask 2** (hill to E): first hill **east** of tip; N/S both hill → 18 (mask **15**); both
      non-hill → ``west_end_interior_e_extender`` (default **8**, horizontal ridge for mask **10**).
    * **Mask 8** (hill to W): first hill **west** of tip; N/S both hill → 19; both non-hill → **8**.

    If perpendicular neighbors are mixed (one hill, one not), leave the tile unchanged. Tips are
    detected with **raw** cardinal adjacency (not interior-stripped) so rim cells next to mesa
    interiors still read as masks 1/2/4/8. Interior masks for tee vs extender still use
    :func:`compute_hill_autotile_mask`. Runs after ridge / spine passes. In-place.

    Returns ``(x, y)`` for each hill cell this pass assigned (for post-inset restore merging).
    """
    t = tiles if tiles is not None else HillPeninsulaProtrusionTileIds()
    hm = hill_char

    def _tiles_for_tip(am: int) -> tuple[int, int]:
        if am == 1:
            return (t.south_end_interior_n_tee, t.south_end_interior_n_extender)
        if am == 4:
            return (t.north_end_interior_s_tee, t.north_end_interior_s_extender)
        if am == 2:
            return (t.west_end_interior_e_tee, t.west_end_interior_e_extender)
        if am == 8:
            return (t.east_end_interior_w_tee, t.east_end_interior_w_extender)
        return (0, 0)

    touched: set[tuple[int, int]] = set()
    # Vertical tips (1 / 4) before horizontal (2 / 8) so a T spine cell is claimed by the
    # north–south peninsula, not by the E/W bar end caps.
    for raw_allowed in ((1, 4), (2, 8)):
        for hy in range(height):
            for hx in range(width):
                if base_hill_tile_ids[hy][hx] is None:
                    continue
                row = ascii_lines[hy] if hy < len(ascii_lines) else ""
                if (row[hx] if hx < len(row) else ".") != hm:
                    continue
                raw_tip = get_hill_adjacency_bitmask(
                    ascii_lines, hx, hy, hill_char=hm, exclude_interior_hill_neighbors=False
                )
                if raw_tip not in raw_allowed:
                    continue
                am = raw_tip
                if am == 1:
                    ddx, ddy = 0, -1
                    p1, p2 = (1, 0), (-1, 0)
                elif am == 4:
                    ddx, ddy = 0, 1
                    p1, p2 = (1, 0), (-1, 0)
                elif am == 2:
                    ddx, ddy = 1, 0
                    p1, p2 = (0, -1), (0, 1)
                elif am == 8:
                    ddx, ddy = -1, 0
                    p1, p2 = (0, -1), (0, 1)
                else:
                    continue
                ix, iy = hx + ddx, hy + ddy
                if not (0 <= ix < width and 0 <= iy < height):
                    continue
                if not is_hill_char(ascii_lines, ix, iy, hm):
                    continue
                px1, py1 = ix + p1[0], iy + p1[1]
                px2, py2 = ix + p2[0], iy + p2[1]
                h1 = is_hill_char(ascii_lines, px1, py1, hm)
                h2 = is_hill_char(ascii_lines, px2, py2, hm)
                tee_id, ext_id = _tiles_for_tip(am)
                new_tile: int | None = None
                need_mask: int | None = None
                if h1 and h2:
                    new_tile = tee_id
                    need_mask = 15
                elif not h1 and not h2:
                    new_tile = ext_id
                    need_mask = 5 if am in (1, 4) else 10
                if new_tile is None or need_mask is None:
                    continue
                if compute_hill_autotile_mask(ascii_lines, ix, iy, hill_char=hm) != need_mask:
                    continue
                if (ix, iy) in touched:
                    continue
                base_hill_tile_ids[iy][ix] = new_tile
                touched.add((ix, iy))

    return frozenset(touched)



def apply_hill_vertical_spine_tile_fix(
    ascii_lines: list[str],
    base_hill_tile_ids: list[list[int | None]],
    width: int,
    height: int,
    hill_map: dict[int, int],
    *,
    hill_char: str = "I",
    skip_coords: frozenset[tuple[int, int]] | None = None,
) -> None:
    """Fix wrong E peninsula (11) on vertical spine; keep left (9) vs right (7) cliffs.

    Uses ``resolve_hill_vertical_ridge_tile_id`` from N/S neighbor tile ids so we do not overwrite
    tile 7 with 9. Interior stripping can still yield mask 2 → tile 11 when both N and S are hill.

    ``skip_coords``: hill cells that must not be rewritten by this late spine fix.
    """
    ridge_default = hill_map.get(5, 9)
    e_only_tile = hill_map.get(2, 11)
    for hy in range(height):
        for hx in range(width):
            tid = base_hill_tile_ids[hy][hx]
            if tid is None:
                continue
            if skip_coords is not None and (hx, hy) in skip_coords:
                continue
            rc = get_hill_adjacency_bitmask(
                ascii_lines, hx, hy, hill_char=hill_char, exclude_interior_hill_neighbors=False
            )
            if rc == HILL_INTERIOR_MASK:
                continue
            # Both N and S are hill (bits 1 and 4).
            if (rc & 5) != 5:
                continue
            if rc == 5 and hill_mask5_vertical_spine_open_diagonals_for_tile24(
                ascii_lines, hx, hy, hill_char=hill_char
            ):
                base_hill_tile_ids[hy][hx] = hill_map.get(24, 24)
                continue
            rim_ridge = hill_mask5_vertical_ridge_tile_from_raw_cardinals(
                ascii_lines, hx, hy, hill_char=hill_char
            )
            if rim_ridge is not None:
                base_hill_tile_ids[hy][hx] = rim_ridge
                continue
            tn = base_hill_tile_ids[hy - 1][hx] if hy > 0 else None
            ts = base_hill_tile_ids[hy + 1][hx] if hy + 1 < height else None
            fixed = resolve_hill_vertical_ridge_tile_id(tn, ts, ridge_default)
            am5 = compute_hill_autotile_mask(ascii_lines, hx, hy, hill_char=hill_char) == 5
            if rc == 5 or am5:
                base_hill_tile_ids[hy][hx] = fixed
            elif tid == e_only_tile or tid == 11:
                base_hill_tile_ids[hy][hx] = fixed


def _resolve_hill_autotile_tile_id_for_autotile_hmask(
    ascii_lines: list[str],
    x: int,
    y: int,
    hill_map: dict[int, int],
    hmask: int,
    *,
    raw_mask: int,
    split_maps_by_shape: dict[str, dict[int, int]] | None = None,
    split_enabled_masks: frozenset[int] | None = None,
    split_default_shape: str = "default",
    hill_char: str = "I",
) -> int:
    """Map inferred autotile mask (not raw 15) to first-pass hill tile id; see :func:`resolve_hill_autotile_tile_id`."""
    split_tid = resolve_hill_split_mask_tile_id(
        mask_for_lookup=hmask,
        raw_mask=raw_mask,
        autotile_mask=hmask,
        maps_by_shape=split_maps_by_shape,
        enabled_masks=split_enabled_masks,
        default_shape=split_default_shape,
    )
    if split_tid is not None:
        return split_tid
    tw = hill_two_wide_vertical_strip_spine_tile_id(
        ascii_lines, x, y, hmask, hill_map, hill_char=hill_char
    )
    if tw is not None:
        return tw
    th = hill_two_wide_horizontal_strip_spine_tile_id(
        ascii_lines, x, y, hmask, hill_map, hill_char=hill_char
    )
    if th is not None:
        return th
    if hmask == 5:
        if hill_mask5_vertical_spine_open_diagonals_for_tile24(
            ascii_lines, x, y, hill_char=hill_char
        ):
            return hill_map.get(24, 24)
        rim_ridge = hill_mask5_vertical_ridge_tile_from_raw_cardinals(
            ascii_lines, x, y, hill_char=hill_char
        )
        if rim_ridge is not None:
            return rim_ridge
        return hill_map.get(5, 9)
    if hmask == 6:
        return hill_map.get(6, 2)
    if hmask == 12:
        return hill_map.get(12, 3)
    if hmask == 11:
        return hill_map.get(11, 8)
    if hmask == 14:
        return hill_map.get(14, 6)
    return hill_map.get(hmask, hill_map.get(0, 1))


def resolve_hill_autotile_tile_id(
    ascii_lines: list[str],
    x: int,
    y: int,
    hill_map: dict[int, int],
    hill_char: str = "I",
    *,
    cached_raw_mask: int | None = None,
    cached_autotile_mask: int | None = None,
    split_maps_by_shape: dict[str, dict[int, int]] | None = None,
    split_enabled_masks: frozenset[int] | None = None,
    split_default_shape: str = "default",
) -> int:
    """Map hill adjacency mask to 1-based hills.aseprite tile id.

    Applies the same diagonal corner upgrade as lake shorelines (see `_hill_mask_with_diagonal_inference`).
    Corners: 6→2, 12→3; three-open sides: 7,11,13,14 from hill_map (defaults 9,8,7,6).

    Interior cells (raw mask 15: all four cardinals are I) use mesa from hill_map[15]. Non-interior
    cells use cardinal neighbors with interior I excluded (so rim stays ridge/edge after fill), except
    raw outer corners (3/6/9/12) which keep full raw cardinals — see :func:`compute_hill_autotile_mask`.
    Diagonal inference still uses raw I on diagonals so outer corners of thick blobs upgrade correctly.

    Mask 5 / 10 ridge tiles use a second pass in paint_map_to_png: vertical (5) picks 7/9 from N/S
    neighbors; horizontal (10) picks 6/8 from W/E neighbors (see
    ``resolve_hill_vertical_ridge_tile_id`` / ``resolve_hill_horizontal_ridge_tile_id``).
    When mask **5** comes from excluding an interior **W** or **E** neighbor, raw cardinals still
    show plateau bulk on one side — use ``hill_mask5_vertical_ridge_tile_from_raw_cardinals`` so
    the east vs west cliff is stable (avoids 7/9 flicker from N/S first-pass neighbors).
    Mask 5 with E/W not hill and all four diagonals open grass-like land uses ``hill_map[24]``
    (default 24) instead of ``hill_map[5]`` / ridge 9 (see
    ``hill_mask5_vertical_spine_open_diagonals_for_tile24``).

    Two-column vertical strips use mask 7 / 13 on the outer faces; those pair as left/right spine
    cliffs (``hill_map[5]`` and the paired right cliff from ``resolve_hill_vertical_ridge_tile_id``)
    — see :func:`hill_two_wide_vertical_strip_spine_tile_id`.

    Two-row horizontal strips use mask 14 / 11 on the outer faces; those pair as top/bottom spine
    ridges (tile 6 / 8 from ``resolve_hill_horizontal_ridge_tile_id``)
    — see :func:`hill_two_wide_horizontal_strip_spine_tile_id`.

    Mask **11** (N+E+W, S open): default ``hill_map[11]`` is the south cliff face. If a project
    overrides it to a tee, the PNG painter then runs :func:`apply_hill_mask11_tee_neighbor_gate` so
    the tee is kept only when a cardinal hill neighbor's first-pass tile is in the configured
    peninsula/tee-adjacent id set (default 10–14, 23–33); otherwise ``hill_map[10]``. Ridge second
    pass may still set
    :func:`resolve_hill_mask11_corner_extension_connect_tile_id` (default W=4, E=8 → center 8).

    After ridge passes, :func:`apply_hill_peninsula_vertical_spine_pass` walks from mask **1** / **4**
    tips along vertical spines (mask **5** → extend tile, default 24; mask **7** / **13** / **11**
    junctions with bulk E/W → tees 15–17 / 16). Then :func:`apply_hill_peninsula_protrusion_adjacent_pass`
    sets the first hill inward from **raw** tips 1/2/4/8 (21/24 for vertical S-tip + N-tip tees,
    18/8 and 19/8 for horizontal mask-10 ridge after W/E tips). Mask **14** (N open):
    :func:`apply_hill_mask14_n_peninsula_connector_pass` runs **after** inset + spine fix and sets
    :func:`resolve_hill_mask14_n_peninsula_connector_tile_id` (default **21**) when E/W are
    ``mask14_ew_neighbor_tile`` (8) and S matches ``mask14_south_neighbor_tiles`` **or** S's raw
    cardinal mask is in ``mask14_south_neighbor_raw_tip_masks`` (default **1, 2, 4, 8**). The active
    painter then runs :func:`apply_hill_inset_2x2_pass` on the resolved hill grid.

    Pass ``cached_raw_mask`` / ``cached_autotile_mask`` from :func:`_precompute_hill_paint_mask_grids`
    to avoid duplicate bitmask work when painting.
    """
    raw_mask = (
        cached_raw_mask
        if cached_raw_mask is not None
        else get_hill_adjacency_bitmask(
            ascii_lines, x, y, hill_char=hill_char, exclude_interior_hill_neighbors=False
        )
    )
    if raw_mask == HILL_INTERIOR_MASK:
        split_tid = resolve_hill_split_mask_tile_id(
            mask_for_lookup=HILL_INTERIOR_MASK,
            raw_mask=raw_mask,
            autotile_mask=HILL_INTERIOR_MASK,
            maps_by_shape=split_maps_by_shape,
            enabled_masks=split_enabled_masks,
            default_shape=split_default_shape,
        )
        if split_tid is not None:
            return split_tid
        return hill_map.get(15, hill_map.get(0, 1))

    hmask = (
        cached_autotile_mask
        if cached_autotile_mask is not None
        else compute_hill_autotile_mask(ascii_lines, x, y, hill_char=hill_char)
    )
    return _resolve_hill_autotile_tile_id_for_autotile_hmask(
        ascii_lines,
        x,
        y,
        hill_map,
        hmask,
        raw_mask=raw_mask,
        split_maps_by_shape=split_maps_by_shape,
        split_enabled_masks=split_enabled_masks,
        split_default_shape=split_default_shape,
        hill_char=hill_char,
    )


def resolve_hill_paint_layer_tile_id(
    ascii_lines: list[str],
    x: int,
    y: int,
    *,
    raw_cardinal_mask: int,
    autotile_mask: int,
    base_hill_tile_ids: list[list[int | None]] | None,
    hill_map: dict[int, int],
    post_first_pass: bool,
    width: int,
    height: int,
    split_maps_by_shape: dict[str, dict[int, int]] | None = None,
    split_enabled_masks: frozenset[int] | None = None,
    split_default_shape: str = "default",
    hill_char: str = "I",
) -> int | None:
    """Hills-layer tile id for (x, y), or ``None`` when only grass should show (deep plateau core).

    Decisions are driven by precomputed **raw** cardinal mask (``raw_cardinal_mask``) and
    ``base_hill_tile_ids`` after optional post-passes; rim fallback uses ``autotile_mask`` with
    :func:`resolve_hill_autotile_tile_id` cache parameters.
    """
    if base_hill_tile_ids is not None and base_hill_tile_ids[y][x] is not None:
        return base_hill_tile_ids[y][x]
    if is_hill_deep_interior_cell(ascii_lines, x, y, hill_char=hill_char):
        return None
    if raw_cardinal_mask != HILL_INTERIOR_MASK:
        return resolve_hill_autotile_tile_id(
            ascii_lines,
            x,
            y,
            hill_map,
            hill_char,
            cached_raw_mask=raw_cardinal_mask,
            cached_autotile_mask=autotile_mask,
            split_maps_by_shape=split_maps_by_shape,
            split_enabled_masks=split_enabled_masks,
            split_default_shape=split_default_shape,
        )
    if base_hill_tile_ids is not None:
        if post_first_pass:
            return resolve_hill_mask15_protrusion_tile_id(
                x,
                y,
                base_hill_tile_ids,
                width,
                height,
                default_tile=hill_map.get(15, 14),
            )
        tid = base_hill_tile_ids[y][x]
        return tid if tid is not None else hill_map.get(15, 14)
    return resolve_hill_autotile_tile_id(
        ascii_lines,
        x,
        y,
        hill_map,
        hill_char,
        cached_raw_mask=raw_cardinal_mask,
        cached_autotile_mask=autotile_mask,
        split_maps_by_shape=split_maps_by_shape,
        split_enabled_masks=split_enabled_masks,
        split_default_shape=split_default_shape,
    )


def resolve_hill_basic_mask_paint_tile_id(
    ascii_lines: list[str],
    x: int,
    y: int,
    *,
    raw_cardinal_mask: int,
    hill_map: dict[int, int],
    split_maps_by_shape: dict[str, dict[int, int]] | None = None,
    split_enabled_masks: frozenset[int] | None = None,
    split_default_shape: str = "default",
    hill_char: str = "I",
) -> int | None:
    """Hill PNG paint: strict cardinal mask 0–15 → ``hill_map``.

    Uses the same 4-bit NESW adjacency as :func:`get_hill_adjacency_bitmask` with
    ``exclude_interior_hill_neighbors=False`` (no autotile diagonal inference or interior stripping).

    Returns ``None`` for deep plateau cores so only the grass under-layer shows.
    """
    if is_hill_deep_interior_cell(ascii_lines, x, y, hill_char=hill_char):
        return None
    m = int(raw_cardinal_mask) & 15
    split_tid = resolve_hill_split_mask_tile_id(
        mask_for_lookup=m,
        raw_mask=m,
        autotile_mask=m,
        maps_by_shape=split_maps_by_shape,
        enabled_masks=split_enabled_masks,
        default_shape=split_default_shape,
    )
    if split_tid is not None:
        return split_tid
    return hill_map.get(m, hill_map.get(0, 1))


def resolve_hill_mask15_protrusion_tile_id(
    x: int,
    y: int,
    base_tile_ids: list[list[int | None]],
    width: int,
    height: int,
    *,
    default_tile: int = 14,
) -> int:
    """Second pass for interior hills (all four cardinals are hill): two protrusions at a corner.

    Uses *first-pass* resolved tile IDs of N/E/S/W neighbors (hills.aseprite 1-based indices).
    If both neighbors for a diagonal pair are in the given sets, use the corner-alternative tile.
    Priority: NW, NE, SW, SE (first match wins).
    """
    def base_at(px: int, py: int) -> int | None:
        if not (0 <= py < height and 0 <= px < width):
            return None
        return base_tile_ids[py][px]

    tn = base_at(x, y - 1)
    ts = base_at(x, y + 1)
    te = base_at(x + 1, y)
    tw = base_at(x - 1, y)

    nw_set = frozenset({8, 12, 13, 23, 24})
    ne_set = frozenset({8, 11, 12, 23, 24})
    sw_set = frozenset({8, 10, 13, 23, 24})
    se_set = frozenset({8, 10, 11, 23, 24})

    if tn is not None and tw is not None and tn in nw_set and tw in nw_set:
        return 15
    if tn is not None and te is not None and tn in ne_set and te in ne_set:
        return 16
    if ts is not None and tw is not None and ts in sw_set and tw in sw_set:
        return 17
    if ts is not None and te is not None and ts in se_set and te in se_set:
        return 18
    return default_tile



def export_treeset_to_png(
    aseprite_path: Path,
    out_png: Path,
    aseprite_bin: Path,
    *,
    sheet_columns: int | None = None,
    out_json: Path | None = None,
) -> None:
    """Export an Aseprite tileset or sprite sheet to a PNG sheet."""
    out_png.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(aseprite_bin), "-b", str(aseprite_path), "--sheet", str(out_png)]
    if sheet_columns is not None:
        cmd.extend(["--sheet-columns", str(sheet_columns)])
    if out_json is not None:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        cmd.extend(["--data", str(out_json), "--format", "json-array"])
    subprocess.run(cmd, check=True)


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
    hill_json_out: Path | None = None,
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
            for key in ("lake_east", "tee_west", "tee_east", "south_cap_north_vertical", "diagonal_water_1", "diagonal_water_3", "diagonal_water_6", "diagonal_water_8", "junction_n3_w5_e8_s_water", "junction_n_water_s13_w16_e2", "junction_n16_or_17_w_water", "junction_n_water_w2_e8_s3", "junction_n2_w13_s9_e_grass", "junction_n10_w10_s_has_37_pattern_e_grass", "junction_n3_e4_s_grass_w_grass", "junction_nw_n_w_b_e_s_water", "junction_n9_e5_s_water_w16_or_17", "junction_n3_e_water_s3_w_lake9", "junction_n26_e7_s_water_w13", "junction_n_grass_e_grass_s5_w_corner", "junction_n3_e_water_s3_w_grass", "junction_n10_e5_s6_w_water_se_water"):
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
    split_maps_by_shape: dict[str, dict[int, int]] | None = None
    split_enabled_masks: frozenset[int] = frozenset()
    split_default_shape = "default"
    _hill_cfg = cfg.get("hill") if isinstance(cfg.get("hill"), dict) else {}
    hill_peninsula_connector_tiles = parse_hill_peninsula_connector_tile_ids(_hill_cfg)
    hill_peninsula_path_tile_ids = parse_hill_peninsula_path_tile_ids(
        _hill_cfg, hill_peninsula_connector_tiles
    )
    hill_inset_2x2_rules = parse_hill_inset_2x2_rules(_hill_cfg)
    hill_four_way_connector_tiles = parse_hill_four_way_connector_tile_ids(_hill_cfg)
    if _hill_cfg:
        raw_split = _hill_cfg.get("maps_by_shape")
        if isinstance(raw_split, dict):
            parsed_split: dict[str, dict[int, int]] = {}
            for shape_key, mapping in raw_split.items():
                if not isinstance(shape_key, str) or not isinstance(mapping, dict):
                    continue
                int_map: dict[int, int] = {}
                for mk, mv in mapping.items():
                    try:
                        if isinstance(mv, bool):
                            continue
                        int_map[int(mk)] = int(mv)
                    except (TypeError, ValueError):
                        continue
                if int_map:
                    parsed_split[shape_key.strip()] = int_map
            if parsed_split:
                split_maps_by_shape = parsed_split
        raw_enabled = _hill_cfg.get("split_mask_enabled_masks")
        if isinstance(raw_enabled, (list, tuple, set)):
            enabled: set[int] = set()
            for item in raw_enabled:
                try:
                    if isinstance(item, bool):
                        continue
                    m = int(item)
                    if 0 <= m <= 15:
                        enabled.add(m)
                except (TypeError, ValueError):
                    continue
            split_enabled_masks = frozenset(enabled)
        raw_default_shape = _hill_cfg.get("split_mask_default_shape")
        if isinstance(raw_default_shape, str) and raw_default_shape.strip():
            split_default_shape = raw_default_shape.strip()
    extended_masks = tuple(cfg.get("extended_shoreline_masks") or EXTENDED_SHORELINE_MASKS)
    river_masks = tuple(cfg.get("river_masks") or RIVER_MASKS)
    interior_corner_masks = tuple(cfg.get("interior_corner_masks") or INTERIOR_CORNER_MASKS)

    width = max(len(row) for row in ascii_lines) if ascii_lines else 0
    height = len(ascii_lines)
    if width == 0 or height == 0:
        raise ValueError("ASCII map is empty")

    # If ASCII already has water border (first row all water: ~ or `), don't add another
    first_row = ascii_lines[0] if ascii_lines else ""
    ascii_has_border = len(first_row) >= 2 and all(c in WATER_CHARS for c in first_row)
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
    shore_ascii_lines = fill_bay_diagonal_shoreline(
        shore_ascii_lines, ocean_connected, width, height
    )
    shore_ascii_lines = demote_shoreline_without_water_neighbor(
        shore_ascii_lines, ocean_connected, width, height
    )
    shore_ascii_lines = filter_isolated_lake_shoreline(shore_ascii_lines)
    shore_mask_grid = propagate_shore_masks(shore_ascii_lines, water_mask_grid)

    def _has_water_in_neighborhood(ax: int, ay: int) -> bool:
        """True if (ax,ay) or any of 8 neighbors has an actual water tile (~ or `). Avoids shoreline on land."""
        for dx, dy in [(0, 0), (0, -1), (1, 0), (0, 1), (-1, 0), (-1, -1), (1, -1), (1, 1), (-1, 1)]:
            nx, ny = ax + dx, ay + dy
            if not (0 <= ny < height and 0 <= nx < width):
                return True  # Out of bounds = ocean
            row = ascii_lines[ny] if ny < len(ascii_lines) else ""
            ch = row[nx] if nx < len(row) else "."
            if ch in WATER_CHARS:
                return True
        return False

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

    def _adjacent_to_shoreline_with_water(ax: int, ay: int) -> bool:
        """True if any of 8 neighbors is B/L/R and has actual water in its neighborhood. Inland connectors need this."""
        for ddx, ddy in [(0, -1), (1, 0), (0, 1), (-1, 0), (-1, -1), (1, -1), (1, 1), (-1, 1)]:
            nx, ny = ax + ddx, ay + ddy
            if 0 <= ny < height and 0 <= nx < width:
                nch = _get_ascii_cell(nx, ny)
                if nch in ("B", "L", "R") and _has_water_in_neighborhood(nx, ny):
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

    def _get_lake_shoreline_tile_index(ax: int, ay: int) -> int | None:
        """Return lake tile index (1-9) for L/R cells, or None for non-lake-shoreline."""
        wch = _get_ascii_cell(ax, ay)
        if wch not in ("L", "R"):
            return None
        if not (0 <= ay < height and 0 <= ax < width):
            return None
        lake_mask = get_water_adjacency_bitmask(
            shore_ascii_lines, ax, ay, water_chars=LAKE_WATER_CHARS, border_width=0
        )
        if lake_mask == 0:
            return None
        lake_mask = _lake_mask_with_diagonal_inference(
            shore_ascii_lines, ax, ay, lake_mask, LAKE_WATER_CHARS
        )
        if lakesrivers_sheet_path and lake_map_override is not None:
            return lake_map_override.get(lake_mask, lake_range_override[0])
        return lake_shoreline_map.get(lake_mask, 51)

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

    # Fill water border (2 tiles wide around map) - outermost = deep, inner = shallow (match map_gen wrap)
    if border > 0 and water_shallow is not None:
        out_tiles_w = out_w // tile_size
        out_tiles_h = out_h // tile_size
        for by in range(out_tiles_h):
            for bx in range(out_tiles_w):
                if bx < border or bx >= width + border or by < border or by >= height + border:
                    dist_from_edge = min(bx, by, out_tiles_w - 1 - bx, out_tiles_h - 1 - by)
                    wt = water_deep if dist_from_edge == 0 else water_shallow
                    _paste_water(water_layer, wt, bx * tile_size, by * tile_size)
                    if use_separate_water:
                        _paste_water(
                            water_deep_layer if dist_from_edge == 0 else water_shallow_layer,
                            wt, bx * tile_size, by * tile_size
                        )
                    elif water_shallow_layer is not None:
                        _paste_water(water_shallow_layer, wt, bx * tile_size, by * tile_size)

    resolved_shore_tiles: dict[tuple[int, int], int] = {}
    # Hill layer: strict cardinal mask 0–15 → ``hill_map`` only (see :func:`resolve_hill_basic_mask_paint_tile_id`).
    base_hill_tile_ids: list[list[int | None]] | None = None
    hill_raw_masks: list[list[int | None]] | None = None
    hill_autotile_masks: list[list[int | None]] | None = None
    hill_paint_tile_ids: list[list[int | None]] | None = None
    if grass_hill and hill_map:
        hill_paint_tile_ids = [[None] * width for _ in range(height)]
        hill_raw_masks, hill_autotile_masks = _precompute_hill_paint_mask_grids(
            ascii_lines, width, height, hill_char="I"
        )
        base_hill_tile_ids = [[None] * width for _ in range(height)]
        for hy in range(height):
            for hx in range(width):
                r = ascii_lines[hy]
                hc = r[hx] if hx < len(r) else "."
                if hc != "I":
                    continue
                if is_hill_deep_interior_cell(ascii_lines, hx, hy, hill_char="I"):
                    base_hill_tile_ids[hy][hx] = None
                else:
                    rm = hill_raw_masks[hy][hx]
                    if rm is None:
                        rm = get_hill_adjacency_bitmask(
                            ascii_lines, hx, hy, hill_char="I", exclude_interior_hill_neighbors=False
                        )
                    tid = resolve_hill_basic_mask_paint_tile_id(
                        ascii_lines,
                        hx,
                        hy,
                        raw_cardinal_mask=int(rm),
                        hill_map=hill_map,
                        split_maps_by_shape=split_maps_by_shape,
                        split_enabled_masks=split_enabled_masks,
                        split_default_shape=split_default_shape,
                        hill_char="I",
                    )
                    base_hill_tile_ids[hy][hx] = tid
        apply_hill_peninsula_connector_pass(
            ascii_lines,
            base_hill_tile_ids,
            width,
            height,
            hill_char="I",
            tiles=hill_peninsula_connector_tiles,
            path_tile_ids=hill_peninsula_path_tile_ids,
        )
        apply_hill_inset_2x2_pass(
            ascii_lines,
            base_hill_tile_ids,
            width,
            height,
            rules=hill_inset_2x2_rules,
            hill_char="I",
        )
        apply_hill_four_way_connector_pass(
            ascii_lines,
            base_hill_tile_ids,
            width,
            height,
            tiles=hill_four_way_connector_tiles,
            peninsula_tile_ids=hill_peninsula_path_tile_ids,
            hill_map=hill_map,
            hill_char="I",
        )

    for y, row in enumerate(ascii_lines):
        for x in range(width):
            ch = row[x] if x < len(row) else "."
            if ch == "":
                ch = "."
            shore_row = shore_ascii_lines[y] if y < len(shore_ascii_lines) else ""
            shore_ch = shore_row[x] if x < len(shore_row) else ch
            # Use shore_ch for B/L/R (promoted water->L); never paint grass/trees on pure water
            display_ch = shore_ch if shore_ch in ("B", "L", "R") else ("G" if ch in ("T", "F") else ch)
            # Hill on shoreline: I with 2+ B neighbors - render as shoreline or grass, not hill
            if ch == "I":
                b_neighbors = sum(
                    1
                    for dx, dy in [(0, -1), (1, 0), (0, 1), (-1, 0)]
                    if 0 <= x + dx < width and 0 <= y + dy < height
                    and _get_ascii_cell(x + dx, y + dy) == "B"
                )
                grass_neighbors = sum(
                    1
                    for dx, dy in [(0, -1), (1, 0), (0, 1), (-1, 0)]
                    if 0 <= x + dx < width and 0 <= y + dy < height
                    and _get_ascii_cell(x + dx, y + dy) in frozenset("G.PITF") | POI_CHARS
                )
                if b_neighbors >= 2:
                    if grass_neighbors >= 1:
                        ch, shore_ch, display_ch = "G", "G", "G"  # Inland connector: grass
                    else:
                        ch, shore_ch, display_ch = "B", "B", "B"  # Water-edge connector: shoreline
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

            # Track if this cell has water (never paint grass over water)
            cell_has_water = False

            if water_shallow is not None:
                if ch in WATER_CHARS:
                    cell_has_water = True
                    wt = water_deep if ch == DEEP_WATER_CHAR else water_shallow
                    water_layer.paste(wt, (dx, dy))
                    if use_separate_water:
                        if (x, y) in river_cells:
                            _paste_water(water_river_layer, water_shallow, dx, dy)
                        elif (x, y) in ocean_connected:
                            _paste_water(water_deep_layer if ch == DEEP_WATER_CHAR else water_shallow_layer, wt, dx, dy)
                        else:
                            _paste_water(water_lake_layer, wt, dx, dy)
                elif (
                    wmask != 0
                    and shore_ch in ("B", "L", "R")
                    and (ch in ("G", ".", "B", "L", "R", "P", "T", "F") or ch in POI_CHARS)
                ):
                    # Only paste water under actual shoreline cells (B/L/R).
                    # Avoids water in demoted cells (e.g. diagonal-only) so painted map matches ASCII.
                    cell_has_water = True
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
                elif shore_ch in ("B", "L", "R"):
                    # Bay/inset special case: shoreline with water only on diagonal (wmask=0)
                    # Still need shallow water underneath
                    cell_has_water = True
                    water_layer.paste(water_shallow, (dx, dy))
                    if use_separate_water:
                        adj_ocean = any(
                            (x + ddx, y + ddy) in ocean_connected
                            for ddx, ddy in [(0, -1), (1, 0), (0, 1), (-1, 0)]
                            if 0 <= x + ddx < width and 0 <= y + ddy < height
                        )
                        diag_water_ocean = any(
                            0 <= x + ddx < width and 0 <= y + ddy < height
                            and (x + ddx, y + ddy) in ocean_connected
                            for ddx, ddy in [(-1, -1), (1, -1), (1, 1), (-1, 1)]
                        )
                        if adj_ocean or diag_water_ocean:
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
            def _get_resolved_shore_tile_index(ax: int, ay: int) -> int | None:
                """Return cached junction tile, inset tile, or mask-based tile for B/inland cells."""
                if (ax, ay) in resolved_shore_tiles:
                    return resolved_shore_tiles[(ax, ay)]
                t = _get_ocean_shoreline_tile_index(ax, ay)
                if t is not None:
                    return t
                return _get_ocean_inset_special_tile(ax, ay, allow_shore_cell=True)

            def _pick_grass_tile() -> tuple[Any, bool]:
                """Returns (tile, is_shoreline). is_shoreline=True when tile is from shoreline set.
                Map-building rules (1-wide shore, water-adjacency, NESW connectivity) are enforced
                in map_gen_cli; painter trusts the ASCII and selects tiles."""
                if not grass_imgs:
                    return None, False
                land_chars = frozenset("G.P") | POI_CHARS | frozenset("ITF")
                adj_lake = _adjacent_to_lake_shoreline_cell(x, y)
                explicit_shore = shore_ch in ("B", "L", "R")
                inset_candidate = (
                    (ch in land_chars)
                    and wmask == 0
                    and _adjacent_to_shoreline_cell(x, y)
                    and _adjacent_to_shoreline_with_water(x, y)
                )
                # G/./P with direct water adjacency (wmask != 0): outer corners, edges—treat as shoreline
                direct_water_shore = (ch in land_chars) and wmask != 0
                use_shoreline = explicit_shore or inset_candidate or direct_water_shore
                if (grass_shoreline or grass_shoreline_lake or grass_shoreline_river or grass_shoreline_extended) and use_shoreline:
                    # Direct coastlines use water adjacency; inland connectors infer from nearby shore cells.
                    eff_mask = (
                        water_mask_grid[y][x]
                        if (explicit_shore or direct_water_shore) and wmask != 0 and y < len(water_mask_grid) and x < len(water_mask_grid[y])
                        else shore_mask_grid[y][x]
                        if explicit_shore and y < len(shore_mask_grid) and x < len(shore_mask_grid[y])
                        else _propagated_shore_mask(x, y, wmask)
                    )
                    # N=tile 10, E=tile 5, S=tile 6, W=water, SE(spot 8)=water -> tile 32 (before tee_west)
                    junction_tile_n10_e5_s6 = shoreline_special_tiles.get("junction_n10_e5_s6_w_water_se_water")
                    if (
                        junction_tile_n10_e5_s6 is not None
                        and shore_ch == "B"
                        and shoreline_sheet_path
                        and shoreline_sheet_path.exists()
                        and y > 0
                        and y + 1 < height
                        and x > 0
                        and x + 1 < width
                    ):
                        north_t_j = _get_resolved_shore_tile_index(x, y - 1)
                        east_t_j = _get_ocean_shoreline_tile_index(x + 1, y)
                        south_t_j = _get_ocean_shoreline_tile_index(x, y + 1)
                        west_ch_j = _get_ascii_cell(x - 1, y)
                        se_ch_j = _get_ascii_cell(x + 1, y + 1)
                        east_ok = east_t_j == 5 or (east_t_j is None and _get_ascii_cell(x + 1, y) in frozenset("G.PITF") | POI_CHARS)
                        if (
                            north_t_j == 10
                            and east_ok
                            and south_t_j == 6
                            and west_ch_j in WATER_CHARS
                            and se_ch_j in WATER_CHARS
                        ):
                            shore_start, shore_end = shoreline_range
                            if shore_start <= junction_tile_n10_e5_s6 <= shore_end:
                                idx = junction_tile_n10_e5_s6 - shore_start
                                if 0 <= idx < len(grass_shoreline):
                                    return grass_shoreline[idx], True
                    # N=tile 16 or 17, W=water -> tile 10 (check before tee_west)
                    tee_west_tile = shoreline_special_tiles.get("tee_west")
                    junction_n16_w = shoreline_special_tiles.get("junction_n16_or_17_w_water")
                    if (
                        junction_n16_w is not None
                        and shore_ch == "B"
                        and y > 0
                        and x > 0
                        and shoreline_sheet_path
                        and shoreline_sheet_path.exists()
                    ):
                        north_t_pre = _get_ocean_shoreline_tile_index(x, y - 1)
                        west_ch_pre = _get_ascii_cell(x - 1, y)
                        if north_t_pre in (16, 17) and west_ch_pre in WATER_CHARS:
                            shore_start, shore_end = shoreline_range
                            if shore_start <= junction_n16_w <= shore_end:
                                idx = junction_n16_w - shore_start
                                if 0 <= idx < len(grass_shoreline):
                                    return grass_shoreline[idx], True
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
                        # tee_west (32) only when N is peninsula (tile 12 or 15)
                        if direct_shore_special_tile == tee_west_tile and tee_west_tile is not None:
                            north_t_for_tee = _get_ocean_shoreline_tile_index(x, y - 1) if y > 0 else None
                            if north_t_for_tee not in (12, 15):
                                direct_shore_special_tile = None
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
                    # Beach inlet inner corners: ocean (B) only, not lake (L). Water only on one diagonal (1=NW,3=NE,6=SW,8=SE).
                    if shore_ch == "B" and wmask == 0 and shoreline_special_tiles and shoreline_sheet_path and shoreline_sheet_path.exists():
                        def _is_water_at(dx: int, dy: int) -> bool:
                            nx, ny = x + dx, y + dy
                            if not (0 <= ny < height and 0 <= nx < width):
                                return False
                            row = ascii_lines[ny] if ny < len(ascii_lines) else ""
                            return row[nx] in WATER_CHARS if nx < len(row) else False

                        others_1 = [(0, -1), (1, 0), (0, 1), (-1, 0), (1, -1), (-1, 1), (1, 1)]  # exclude NW
                        others_3 = [(0, -1), (1, 0), (0, 1), (-1, 0), (-1, -1), (-1, 1), (1, 1)]  # exclude NE
                        others_6 = [(0, -1), (1, 0), (0, 1), (-1, 0), (-1, -1), (1, -1), (1, 1)]  # exclude SW
                        others_8 = [(0, -1), (1, 0), (0, 1), (-1, 0), (-1, -1), (1, -1), (-1, 1)]  # exclude SE
                        diag_tile = None
                        if _is_water_at(-1, -1) and not any(_is_water_at(dx, dy) for dx, dy in others_1):
                            diag_tile = shoreline_special_tiles.get("diagonal_water_1")
                        elif _is_water_at(1, -1) and not any(_is_water_at(dx, dy) for dx, dy in others_3):
                            diag_tile = shoreline_special_tiles.get("diagonal_water_3")
                        elif _is_water_at(-1, 1) and not any(_is_water_at(dx, dy) for dx, dy in others_6):
                            diag_tile = shoreline_special_tiles.get("diagonal_water_6")
                        elif _is_water_at(1, 1) and not any(_is_water_at(dx, dy) for dx, dy in others_8):
                            diag_tile = shoreline_special_tiles.get("diagonal_water_8")
                        if diag_tile is not None:
                            shore_start, shore_end = shoreline_range
                            if shore_start <= diag_tile <= shore_end:
                                idx = diag_tile - shore_start
                                if 0 <= idx < len(grass_shoreline):
                                    return grass_shoreline[idx], True
                    # South cap when N=beach tile 6 (vertical strip), E/S/W=water or 16/17: use tile 15
                    # eff_mask 14 = S+E+W (all water), 6 = S+E (W can be tile 16/17)
                    south_cap_tile = shoreline_special_tiles.get("south_cap_north_vertical")
                    if (
                        south_cap_tile is not None
                        and shore_ch == "B"
                        and eff_mask in (6, 14)
                        and shoreline_sheet_path
                        and shoreline_sheet_path.exists()
                        and y > 0
                    ):
                        north_tile_idx = _get_ocean_shoreline_tile_index(x, y - 1)
                        if north_tile_idx == 6:
                            shore_start, shore_end = shoreline_range
                            if shore_start <= south_cap_tile <= shore_end:
                                idx = south_cap_tile - shore_start
                                if 0 <= idx < len(grass_shoreline):
                                    return grass_shoreline[idx], True
                    # Junction: N=tile 3, W=tile 5, E=tile 8, S=water -> use tile 35
                    junction_tile = shoreline_special_tiles.get("junction_n3_w5_e8_s_water")
                    if (
                        junction_tile is not None
                        and shore_ch == "B"
                        and shoreline_sheet_path
                        and shoreline_sheet_path.exists()
                        and y > 0
                        and y + 1 < height
                    ):
                        north_t = _get_ocean_shoreline_tile_index(x, y - 1)
                        west_t = _get_ocean_shoreline_tile_index(x - 1, y) if x > 0 else None
                        east_t = _get_ocean_shoreline_tile_index(x + 1, y)
                        south_ch = _get_ascii_cell(x, y + 1)
                        south_is_water = south_ch in WATER_CHARS
                        if north_t == 3 and west_t == 5 and east_t == 8 and south_is_water:
                            shore_start, shore_end = shoreline_range
                            if shore_start <= junction_tile <= shore_end:
                                idx = junction_tile - shore_start
                                if 0 <= idx < len(grass_shoreline):
                                    return grass_shoreline[idx], True
                    # Junction: N=water, S=tile 13, W=tile 16, E=tile 2 -> use tile 10
                    junction_tile_10 = shoreline_special_tiles.get("junction_n_water_s13_w16_e2")
                    if (
                        junction_tile_10 is not None
                        and shore_ch == "B"
                        and shoreline_sheet_path
                        and shoreline_sheet_path.exists()
                        and y > 0
                        and y + 1 < height
                    ):
                        north_ch = _get_ascii_cell(x, y - 1)
                        north_is_water = north_ch in WATER_CHARS
                        south_t = _get_ocean_shoreline_tile_index(x, y + 1)
                        west_t_10 = _get_ocean_shoreline_tile_index(x - 1, y) if x > 0 else None
                        east_t_10 = _get_ocean_shoreline_tile_index(x + 1, y)
                        if north_is_water and south_t == 13 and west_t_10 == 16 and east_t_10 == 2:
                            shore_start, shore_end = shoreline_range
                            if shore_start <= junction_tile_10 <= shore_end:
                                idx = junction_tile_10 - shore_start
                                if 0 <= idx < len(grass_shoreline):
                                    return grass_shoreline[idx], True
                    # Junction: N=water, W=tile 2, E=tile 8, S=tile 3 -> use tile 50
                    junction_tile_50 = shoreline_special_tiles.get("junction_n_water_w2_e8_s3")
                    if (
                        junction_tile_50 is not None
                        and shore_ch == "B"
                        and shoreline_sheet_path
                        and shoreline_sheet_path.exists()
                        and y > 0
                        and y + 1 < height
                    ):
                        north_ch_50 = _get_ascii_cell(x, y - 1)
                        north_is_water_50 = north_ch_50 in WATER_CHARS
                        south_t_50 = _get_ocean_shoreline_tile_index(x, y + 1)
                        west_t_50 = _get_ocean_shoreline_tile_index(x - 1, y) if x > 0 else None
                        east_t_50 = _get_ocean_shoreline_tile_index(x + 1, y)
                        if north_is_water_50 and west_t_50 == 2 and east_t_50 == 8 and south_t_50 == 3:
                            shore_start, shore_end = shoreline_range
                            if shore_start <= junction_tile_50 <= shore_end:
                                idx = junction_tile_50 - shore_start
                                if 0 <= idx < len(grass_shoreline):
                                    return grass_shoreline[idx], True
                    # Junction: N=tile 10, W=tile 10, E=grass, S has 37-pattern (W=13,S=9,E=grass) -> use tile 41
                    # Check before 37 so upper cell gets 41 first (top-to-bottom processing)
                    junction_tile_41 = shoreline_special_tiles.get("junction_n10_w10_s_has_37_pattern_e_grass")
                    if (
                        junction_tile_41 is not None
                        and shore_ch == "B"
                        and shoreline_sheet_path
                        and shoreline_sheet_path.exists()
                        and y > 0
                        and y + 2 < height
                    ):
                        north_t_41 = _get_ocean_shoreline_tile_index(x, y - 1)
                        west_t_41 = _get_ocean_shoreline_tile_index(x - 1, y) if x > 0 else None
                        east_ch_41 = _get_ascii_cell(x + 1, y)
                        east_is_grass_41 = east_ch_41 in frozenset("G.PITF") | POI_CHARS
                        south_ch_41 = _get_ascii_cell(x, y + 1)
                        south_is_b = south_ch_41 == "B"
                        south_w = _get_ocean_shoreline_tile_index(x - 1, y + 1) if x > 0 else None
                        south_s = _get_ocean_shoreline_tile_index(x, y + 2)
                        south_e_ch = _get_ascii_cell(x + 1, y + 1)
                        south_e_grass = south_e_ch in frozenset("G.PITF") | POI_CHARS
                        south_has_37_pattern = south_is_b and south_w == 13 and south_s == 9 and south_e_grass
                        if north_t_41 == 10 and west_t_41 == 10 and east_is_grass_41 and south_has_37_pattern:
                            shore_start, shore_end = shoreline_range
                            if shore_start <= junction_tile_41 <= shore_end:
                                idx = junction_tile_41 - shore_start
                                if 0 <= idx < len(grass_shoreline):
                                    resolved_shore_tiles[(x, y)] = junction_tile_41
                                    return grass_shoreline[idx], True
                    # Junction: N=tile 2 or 41, W=tile 13, S=tile 9, E=grass -> use tile 37
                    # Use resolved north (can be 41 from upper cell in 41/37 pair)
                    junction_tile_37 = shoreline_special_tiles.get("junction_n2_w13_s9_e_grass")
                    if (
                        junction_tile_37 is not None
                        and shore_ch == "B"
                        and shoreline_sheet_path
                        and shoreline_sheet_path.exists()
                        and y > 0
                        and y + 1 < height
                    ):
                        north_t_37 = _get_resolved_shore_tile_index(x, y - 1)
                        west_t_37 = _get_ocean_shoreline_tile_index(x - 1, y) if x > 0 else None
                        south_t_37 = _get_ocean_shoreline_tile_index(x, y + 1)
                        east_ch_37 = _get_ascii_cell(x + 1, y)
                        east_is_grass = east_ch_37 in frozenset("G.PITF") | POI_CHARS
                        if north_t_37 in (2, 41) and west_t_37 == 13 and south_t_37 == 9 and east_is_grass:
                            shore_start, shore_end = shoreline_range
                            if shore_start <= junction_tile_37 <= shore_end:
                                idx = junction_tile_37 - shore_start
                                if 0 <= idx < len(grass_shoreline):
                                    resolved_shore_tiles[(x, y)] = junction_tile_37
                                    return grass_shoreline[idx], True
                    # Junction: N=tile 3, E=tile 4, S=grass, W=grass -> use tile 40
                    junction_tile_40 = shoreline_special_tiles.get("junction_n3_e4_s_grass_w_grass")
                    if (
                        junction_tile_40 is not None
                        and shore_ch == "B"
                        and shoreline_sheet_path
                        and shoreline_sheet_path.exists()
                        and y > 0
                        and y + 1 < height
                    ):
                        north_t_40 = _get_ocean_shoreline_tile_index(x, y - 1)
                        east_t_40 = _get_ocean_shoreline_tile_index(x + 1, y)
                        south_ch_40 = _get_ascii_cell(x, y + 1)
                        west_ch_40 = _get_ascii_cell(x - 1, y)
                        south_grass = south_ch_40 in frozenset("G.PITF") | POI_CHARS
                        west_grass = west_ch_40 in frozenset("G.PITF") | POI_CHARS
                        if north_t_40 == 3 and east_t_40 in (3, 4) and south_grass and west_grass:
                            shore_start, shore_end = shoreline_range
                            if shore_start <= junction_tile_40 <= shore_end:
                                idx = junction_tile_40 - shore_start
                                if 0 <= idx < len(grass_shoreline):
                                    return grass_shoreline[idx], True
                    # Junction: 1(NW),2(N),4(W)=shoreline B, 5(E),6(SW),7(S),8(SE)=ocean water -> tile 55 (vertical inlet)
                    junction_tile_55 = shoreline_special_tiles.get("junction_nw_n_w_b_e_s_water")
                    if (
                        junction_tile_55 is not None
                        and shore_ch == "B"
                        and shoreline_sheet_path
                        and shoreline_sheet_path.exists()
                    ):
                        nw_ch = _get_ascii_cell(x - 1, y - 1)
                        n_ch = _get_ascii_cell(x, y - 1)
                        w_ch = _get_ascii_cell(x - 1, y)
                        e_ch = _get_ascii_cell(x + 1, y)
                        s_ch = _get_ascii_cell(x, y + 1)
                        ne_ch = _get_ascii_cell(x + 1, y - 1)
                        sw_ch = _get_ascii_cell(x - 1, y + 1)
                        se_ch = _get_ascii_cell(x + 1, y + 1)
                        nw_n_w_b = nw_ch == "B" and n_ch == "B" and w_ch == "B"
                        e_s_water = e_ch in WATER_CHARS and s_ch in WATER_CHARS
                        ne_sw_se_water = ne_ch in WATER_CHARS and sw_ch in WATER_CHARS and se_ch in WATER_CHARS
                        if nw_n_w_b and e_s_water and ne_sw_se_water:
                            shore_start, shore_end = shoreline_range
                            if shore_start <= junction_tile_55 <= shore_end:
                                idx = junction_tile_55 - shore_start
                                if 0 <= idx < len(grass_shoreline):
                                    return grass_shoreline[idx], True
                    # Junction: N=tile 9, E=tile 5, S=water, W=tile 16 or 17 -> use tile 13
                    junction_tile_13 = shoreline_special_tiles.get("junction_n9_e5_s_water_w16_or_17")
                    if (
                        junction_tile_13 is not None
                        and shore_ch == "B"
                        and shoreline_sheet_path
                        and shoreline_sheet_path.exists()
                        and y > 0
                        and y + 1 < height
                    ):
                        north_t_13 = _get_ocean_shoreline_tile_index(x, y - 1)
                        east_t_13 = _get_ocean_shoreline_tile_index(x + 1, y)
                        south_ch_13 = _get_ascii_cell(x, y + 1)
                        south_is_water_13 = south_ch_13 in WATER_CHARS
                        west_t_13 = _get_ocean_shoreline_tile_index(x - 1, y) if x > 0 else None
                        if north_t_13 == 9 and east_t_13 == 5 and south_is_water_13 and west_t_13 in (16, 17):
                            shore_start, shore_end = shoreline_range
                            if shore_start <= junction_tile_13 <= shore_end:
                                idx = junction_tile_13 - shore_start
                                if 0 <= idx < len(grass_shoreline):
                                    return grass_shoreline[idx], True
                    # Junction: N=beach tile 3, E=water, S=beach (B), W=lake tile 9 -> use shoreline tile 3
                    # Use resolved north so south cell can also get tile 3 when its N is 3 (continues vertical strip)
                    junction_tile_3 = shoreline_special_tiles.get("junction_n3_e_water_s3_w_lake9")
                    if (
                        junction_tile_3 is not None
                        and shore_ch == "B"
                        and shoreline_sheet_path
                        and shoreline_sheet_path.exists()
                        and y > 0
                        and y + 1 < height
                    ):
                        north_t_3 = _get_resolved_shore_tile_index(x, y - 1)
                        east_ch_3 = _get_ascii_cell(x + 1, y)
                        east_is_water_3 = east_ch_3 in WATER_CHARS
                        south_ch_3 = _get_ascii_cell(x, y + 1)
                        south_is_beach_3 = south_ch_3 == "B"
                        west_lake_t_3 = _get_lake_shoreline_tile_index(x - 1, y) if x > 0 else None
                        if north_t_3 == 3 and east_is_water_3 and south_is_beach_3 and west_lake_t_3 == 9:
                            shore_start, shore_end = shoreline_range
                            if shore_start <= junction_tile_3 <= shore_end:
                                idx = junction_tile_3 - shore_start
                                if 0 <= idx < len(grass_shoreline):
                                    resolved_shore_tiles[(x, y)] = junction_tile_3
                                    return grass_shoreline[idx], True
                    # Junction: N=tile 26, E=tile 7, S=water, W=tile 13 -> use tile 52
                    junction_tile_52 = shoreline_special_tiles.get("junction_n26_e7_s_water_w13")
                    if (
                        junction_tile_52 is not None
                        and shore_ch == "B"
                        and shoreline_sheet_path
                        and shoreline_sheet_path.exists()
                        and y > 0
                        and y + 1 < height
                    ):
                        north_t_52 = _get_resolved_shore_tile_index(x, y - 1)
                        east_t_52 = _get_ocean_shoreline_tile_index(x + 1, y)
                        south_ch_52 = _get_ascii_cell(x, y + 1)
                        south_is_water_52 = south_ch_52 in WATER_CHARS
                        west_t_52 = _get_ocean_shoreline_tile_index(x - 1, y) if x > 0 else None
                        if north_t_52 == 26 and east_t_52 == 7 and south_is_water_52 and west_t_52 == 13:
                            shore_start, shore_end = shoreline_range
                            if shore_start <= junction_tile_52 <= shore_end:
                                idx = junction_tile_52 - shore_start
                                if 0 <= idx < len(grass_shoreline):
                                    return grass_shoreline[idx], True
                    # Junction: N=grass, E=grass, S=tile 5, W=shoreline corner (9,10,12,13) -> use tile 54
                    junction_tile_54 = shoreline_special_tiles.get("junction_n_grass_e_grass_s5_w_corner")
                    if (
                        junction_tile_54 is not None
                        and shore_ch == "B"
                        and shoreline_sheet_path
                        and shoreline_sheet_path.exists()
                        and y > 0
                        and y + 1 < height
                    ):
                        north_ch_54 = _get_ascii_cell(x, y - 1)
                        east_ch_54 = _get_ascii_cell(x + 1, y)
                        north_grass_54 = north_ch_54 in frozenset("G.PITF") | POI_CHARS
                        east_grass_54 = east_ch_54 in frozenset("G.PITF") | POI_CHARS
                        south_t_54 = _get_ocean_shoreline_tile_index(x, y + 1)
                        west_t_54 = _get_ocean_shoreline_tile_index(x - 1, y) if x > 0 else None
                        w_is_corner = west_t_54 in (9, 10, 12, 13) if west_t_54 is not None else False
                        if north_grass_54 and east_grass_54 and south_t_54 == 5 and w_is_corner:
                            shore_start, shore_end = shoreline_range
                            if shore_start <= junction_tile_54 <= shore_end:
                                idx = junction_tile_54 - shore_start
                                if 0 <= idx < len(grass_shoreline):
                                    return grass_shoreline[idx], True
                    # Junction: N=tile 3, E=water, S=tile 3, W=grass -> use tile 3 (vertical strip)
                    junction_tile_3_v = shoreline_special_tiles.get("junction_n3_e_water_s3_w_grass")
                    if (
                        junction_tile_3_v is not None
                        and shore_ch == "B"
                        and shoreline_sheet_path
                        and shoreline_sheet_path.exists()
                        and y > 0
                        and y + 1 < height
                    ):
                        north_t_3v = _get_resolved_shore_tile_index(x, y - 1)
                        east_ch_3v = _get_ascii_cell(x + 1, y)
                        east_water_3v = east_ch_3v in WATER_CHARS
                        south_t_3v = _get_resolved_shore_tile_index(x, y + 1)
                        west_ch_3v = _get_ascii_cell(x - 1, y)
                        west_grass_3v = west_ch_3v in frozenset("G.PITF") | POI_CHARS
                        if north_t_3v == 3 and east_water_3v and south_t_3v == 3 and west_grass_3v:
                            shore_start, shore_end = shoreline_range
                            if shore_start <= junction_tile_3_v <= shore_end:
                                idx = junction_tile_3_v - shore_start
                                if 0 <= idx < len(grass_shoreline):
                                    resolved_shore_tiles[(x, y)] = junction_tile_3_v
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

            def _visible_grass_or_default(t: Any) -> Any:
                """Return tile if visible; else try default grass to avoid solid-green fallback."""
                if t and _is_tile_visible(t):
                    return t
                if grass_imgs:
                    default_tile = grass_imgs[min(grass_default_idx, len(grass_imgs) - 1)]
                    if _is_tile_visible(default_tile):
                        return default_tile
                return t  # keep original so _paste_visible can use solid fallback if needed

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
                elif not use_tile_when_available and not _is_tile_visible(use):
                    # Shoreline/grass: fallback when blank. Hill corners often sparse — use use_tile_when_available.
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
                skip_grass_over_water: bool = False,
            ) -> None:
                """Paste shoreline tile to Shoreline (ocean) or LakeBank (lake/river) layer.
                use_lakebank: True=lakebank, False=shoreline, None=infer from ch and is_lake.
                skip_grass_over_water: when True, never paste to grass layer (rule: no grass over water)."""
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
                elif grass_layer and not skip_grass_over_water:
                    # No shoreline output: use grass layer so B/L/R still render (fallback color)
                    _paste_visible(grass_layer, tile, fallback_rgb, color_tiles)

            if is_land_surrounded_by_water:
                # Water already pasted; skip grass/trees/dirt/POI (avoids grass painted over water)
                pass
            elif ch == "I" and grass_imgs:
                is_shore = False
                # Paint grass underneath so hiding hill layer shows grass
                grass_tile = _visible_grass_or_default(_pick_interior_grass())
                if grass_tile and not cell_has_water:
                    _paste_visible(grass_layer, grass_tile, SOLID_TILE_COLORS["G"], color_tiles)
                raw_card = (
                    hill_raw_masks[y][x]
                    if hill_raw_masks is not None
                    else get_hill_adjacency_bitmask(
                        ascii_lines, x, y, hill_char="I", exclude_interior_hill_neighbors=False
                    )
                )
                if raw_card is None:
                    raw_card = get_hill_adjacency_bitmask(
                        ascii_lines, x, y, hill_char="I", exclude_interior_hill_neighbors=False
                    )
                autotile_mask = (
                    hill_autotile_masks[y][x]
                    if hill_autotile_masks is not None
                    else compute_hill_autotile_mask(ascii_lines, x, y, hill_char="I")
                )
                if autotile_mask is None:
                    autotile_mask = compute_hill_autotile_mask(ascii_lines, x, y, hill_char="I")
                is_hill_interior = raw_card == HILL_INTERIOR_MASK
                if grass_hill:
                    tile_id = resolve_hill_paint_layer_tile_id(
                        ascii_lines,
                        x,
                        y,
                        raw_cardinal_mask=int(raw_card),
                        autotile_mask=int(autotile_mask),
                        base_hill_tile_ids=base_hill_tile_ids,
                        hill_map=hill_map,
                        post_first_pass=False,
                        width=width,
                        height=height,
                        hill_char="I",
                    )
                    if tile_id is None:
                        tile = None
                    else:
                        if hill_paint_tile_ids is not None:
                            hill_paint_tile_ids[y][x] = int(tile_id)
                        hill_start = (grass_hill_range or (1, 37))[0]
                        idx = tile_id - hill_start
                        if 0 <= idx < len(grass_hill):
                            tile = grass_hill[idx]
                        else:
                            tile = grass_hill[0]
                elif not is_hill_interior:
                    tile = _pick_interior_grass()
                else:
                    tile = None  # Interior mesa: no hill sheet — grass base only
                # Solid fallback only when no tile; hill corners are often sparse — do not use _is_tile_visible here.
                if not tile and not is_hill_interior:
                    rgb = SOLID_TILE_COLORS.get("I", (90, 120, 70, 255))
                    if rgb not in color_tiles:
                        color_tiles[rgb] = Image.new("RGBA", (tile_size, tile_size), rgb)
                    tile = color_tiles[rgb]
                if tile:
                    if hill_layer:
                        _paste_visible(
                            hill_layer,
                            tile,
                            SOLID_TILE_COLORS["I"],
                            color_tiles,
                            use_tile_when_available=bool(grass_hill),
                        )
                    elif not cell_has_water:
                        _paste_visible(grass_layer, tile, SOLID_TILE_COLORS["G"], color_tiles)
            elif ch == "I":
                # Fallback when grass_imgs empty: paint grass base, hill cliff only on perimeter
                if not cell_has_water:
                    grass_rgb = SOLID_TILE_COLORS.get("G", (104, 178, 76, 255))
                    if grass_rgb not in color_tiles:
                        color_tiles[grass_rgb] = Image.new("RGBA", (tile_size, tile_size), grass_rgb)
                    grass_layer.paste(color_tiles[grass_rgb], (dx, dy))
                raw_fb = (
                    hill_raw_masks[y][x]
                    if hill_raw_masks is not None
                    else get_hill_adjacency_bitmask(ascii_lines, x, y, hill_char="I", exclude_interior_hill_neighbors=False)
                )
                if raw_fb is None:
                    raw_fb = get_hill_adjacency_bitmask(
                        ascii_lines, x, y, hill_char="I", exclude_interior_hill_neighbors=False
                    )
                if raw_fb != HILL_INTERIOR_MASK:
                    rgb = SOLID_TILE_COLORS.get("I", (90, 120, 70, 255))
                    if rgb not in color_tiles:
                        color_tiles[rgb] = Image.new("RGBA", (tile_size, tile_size), rgb)
                    if hill_layer:
                        hill_layer.paste(color_tiles[rgb], (dx, dy))
                    elif not cell_has_water:
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
                    tile = _visible_grass_or_default(tile)
                    fallback = SOLID_TILE_COLORS.get(ch, SOLID_TILE_COLORS["G"])
                    adj_lake = _adjacent_to_lake_shoreline_cell(x, y)
                    use_shore_layer = shore_ch in ("B", "L", "R") or is_shore
                    if use_shore_layer and ch in ("G", "."):
                        fallback = SOLID_TILE_COLORS["L"] if adj_lake else SOLID_TILE_COLORS["B"]
                    if use_shore_layer:
                        # When is_shore is False (demoted: no water in neighborhood), paste grass tile, not beige fallback
                        _paste_shore_tile(
                            tile,
                            fallback if is_shore else SOLID_TILE_COLORS["G"],
                            use_lakebank=adj_lake if ch in ("G", ".") else None,
                            skip_grass_over_water=cell_has_water,
                        )
                    elif is_shore:
                        _paste_shore_tile(tile, fallback, skip_grass_over_water=cell_has_water)
                    else:
                        if not cell_has_water:
                            _paste_visible(grass_layer, tile, fallback, color_tiles)
            elif ch == "P" and grass_imgs:
                tile, is_shore = _pick_grass_tile()
                tile = _visible_grass_or_default(tile or _pick_interior_grass())
                fallback = SOLID_TILE_COLORS["P"]
                if is_shore:
                    _paste_shore_tile(tile, fallback, skip_grass_over_water=cell_has_water)
                else:
                    if not cell_has_water:
                        _paste_visible(grass_layer, tile, fallback, color_tiles)
            elif ch in POI_CHARS:
                # POI cells: draw base terrain (grass or path), then marker on poi_layer
                if ch in POI_GRASS_BASE and grass_imgs:
                    tile, is_shore = _pick_grass_tile()
                    tile = _visible_grass_or_default(tile or _pick_interior_grass())
                    fallback = SOLID_TILE_COLORS["G"]
                    if is_shore:
                        _paste_shore_tile(tile, fallback, skip_grass_over_water=cell_has_water)
                    else:
                        if not cell_has_water:
                            _paste_visible(grass_layer, tile, fallback, color_tiles)
                elif ch in POI_PATH_BASE and dirt_tiles and not skip_dirt and not cell_has_water:
                    bitmask = get_path_bitmask(ascii_lines, x, y)
                    idx = min(bitmask, len(dirt_tiles) - 1)
                    _paste_visible(dirt_layer, dirt_tiles[idx], SOLID_TILE_COLORS["P"], color_tiles)
                elif ch in POI_PATH_BASE and grass_imgs:
                    tile, is_shore = _pick_grass_tile()
                    tile = _visible_grass_or_default(tile or _pick_interior_grass())
                    fallback = SOLID_TILE_COLORS["P"]
                    if is_shore:
                        _paste_shore_tile(tile, fallback, skip_grass_over_water=cell_has_water)
                    else:
                        if not cell_has_water:
                            _paste_visible(grass_layer, tile, fallback, color_tiles)
                elif grass_imgs:
                    tile, is_shore = _pick_grass_tile()
                    tile = _visible_grass_or_default(tile or _pick_interior_grass())
                    fallback = SOLID_TILE_COLORS["G"]
                    if is_shore:
                        _paste_shore_tile(tile, fallback, skip_grass_over_water=cell_has_water)
                    else:
                        if not cell_has_water:
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
                if not cell_has_water:
                    rgb = SOLID_TILE_COLORS.get(display_ch, DEFAULT_COLOR)
                    if rgb not in color_tiles:
                        color_tiles[rgb] = Image.new("RGBA", (tile_size, tile_size), rgb)
                    grass_layer.paste(color_tiles[rgb], (dx, dy))

            # Dirt layer: P cells only, no dirt on ocean-adjacent tiles (reserve for shoreline)
            if not is_land_surrounded_by_water and not cell_has_water and ch == "P" and dirt_tiles and not skip_dirt:
                bitmask = get_path_bitmask(ascii_lines, x, y)
                idx = min(bitmask, len(dirt_tiles) - 1)
                _paste_visible(dirt_layer, dirt_tiles[idx], SOLID_TILE_COLORS["P"], color_tiles)

            # Trees layer: T, F cells (skip on water and shoreline B/L/R per terrain rules)
            if not is_land_surrounded_by_water and not cell_has_water and ch in ("T", "F") and not is_pure_water and shore_ch not in ("B", "L", "R"):
                tile_id = tile_rows[y][x] if y < len(tile_rows) and x < len(tile_rows[y]) else 0
                if tile_id and tile_id > 0:
                    idx = tile_id - 1
                    if idx < len(tree_tiles):
                        _paste_visible(trees_layer, tree_tiles[idx], SOLID_TILE_COLORS["T"], color_tiles)

    if hill_json_out and base_hill_tile_ids is not None:
        hill_json_out.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "version": 3,
            "width": width,
            "height": height,
            "tiles": base_hill_tile_ids,
            "paint_tile_ids": hill_paint_tile_ids,
            "grass_inset": None,
            "raw_cardinal_mask": hill_raw_masks,
            "autotile_mask": hill_autotile_masks,
        }
        hill_json_out.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")

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
