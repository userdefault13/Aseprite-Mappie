"""Paint ASCII map to grass + trees PNGs using PIL (GotchiCraft-style pipeline)."""
from __future__ import annotations

import random
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from tilemap_generator.tree_logic import to_tile_rows_with_trees

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
PATH_CHARS = frozenset("P")


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
) -> list[Any]:
    """Load grass tiles from a PNG sheet (grid of tiles). Returns list of RGBA images.
    tile_range: optional (start, end) 1-based inclusive, e.g. (19, 30) for tiles 19-30 only."""
    Image = _ensure_pillow()
    img = Image.open(sheet_path)
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    w, h = img.size
    cols = max(1, w // tile_size)
    rows = max(1, h // tile_size)
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


def export_treeset_to_png(treeset_path: Path, out_png: Path, aseprite_bin: Path) -> None:
    """Export treeset .aseprite to PNG sheet via Aseprite CLI."""
    cmd = [
        str(aseprite_bin),
        "-b",
        str(treeset_path),
        "--sheet",
        str(out_png),
        "--sheet-type",
        "horizontal",
    ]
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
    dirt_out: Path,
    trees_out: Path,
    grass_dir: Path | None = None,
    grass_sheet_path: Path | None = None,
    grass_tile_range: tuple[int, int] | None = (19, 30),
    water_path: Path | None = None,
    dirt_path: Path | None = None,
    grass_tile_names: list[str] | None = None,
    seed: int = 42,
) -> None:
    """Composite grass and trees layers to PNGs using PIL."""
    Image = _ensure_pillow()
    rng = random.Random(seed)

    width = max(len(row) for row in ascii_lines) if ascii_lines else 0
    height = len(ascii_lines)
    if width == 0 or height == 0:
        raise ValueError("ASCII map is empty")

    out_w = width * tile_size
    out_h = height * tile_size

    # Load grass tiles: from sheet (PNG) or from directory
    grass_imgs: list[Any] = []
    if grass_sheet_path and grass_sheet_path.exists():
        grass_imgs = load_grass_from_sheet(
            grass_sheet_path, tile_size, tile_range=grass_tile_range
        )
    elif grass_dir and grass_dir.exists() and grass_dir.is_dir():
        grass_imgs = load_grass_tiles(grass_dir, tile_size, grass_tile_names)

    # Load water tile (optional)
    water_tile: Any = None
    if water_path and water_path.exists():
        water_tile = Image.open(water_path)
        if water_tile.mode != "RGBA":
            water_tile = water_tile.convert("RGBA")
        if water_tile.width != tile_size or water_tile.height != tile_size:
            water_tile = water_tile.resize(
                (tile_size, tile_size), Image.Resampling.NEAREST
            )

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

    water_layer = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
    grass_layer = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
    dirt_layer = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
    trees_layer = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))

    for y, row in enumerate(ascii_lines):
        for x in range(width):
            ch = row[x] if x < len(row) else "."
            if ch == "":
                ch = "."
            display_ch = "G" if ch in ("T", "F") else ch
            dx, dy = x * tile_size, y * tile_size

            # Water layer: ~ cells only
            if ch == "~" and water_tile is not None:
                water_layer.paste(water_tile, (dx, dy))

            # Grass layer: G, ., T, F, P (base), ~ (under water), and other terrain
            if display_ch in ("G", ".") and grass_imgs:
                tile = grass_imgs[rng.randint(0, len(grass_imgs) - 1)]
                grass_layer.paste(tile, (dx, dy))
            elif ch == "~" and grass_imgs:
                grass_layer.paste(grass_imgs[rng.randint(0, len(grass_imgs) - 1)], (dx, dy))
            elif ch == "P" and grass_imgs:
                grass_layer.paste(grass_imgs[rng.randint(0, len(grass_imgs) - 1)], (dx, dy))
            elif ch == "~":
                rgb = SOLID_TILE_COLORS.get("~", DEFAULT_COLOR)
                if rgb not in color_tiles:
                    color_tiles[rgb] = Image.new("RGBA", (tile_size, tile_size), rgb)
                grass_layer.paste(color_tiles[rgb], (dx, dy))
            else:
                rgb = SOLID_TILE_COLORS.get(display_ch, DEFAULT_COLOR)
                if rgb not in color_tiles:
                    color_tiles[rgb] = Image.new("RGBA", (tile_size, tile_size), rgb)
                grass_layer.paste(color_tiles[rgb], (dx, dy))

            # Dirt layer: P cells only, tile selected by path connectivity
            if ch == "P" and dirt_tiles:
                bitmask = get_path_bitmask(ascii_lines, x, y)
                idx = min(bitmask, len(dirt_tiles) - 1)
                dirt_layer.paste(dirt_tiles[idx], (dx, dy))

            # Trees layer: T, F cells
            if ch in ("T", "F"):
                tile_id = tile_rows[y][x] if y < len(tile_rows) and x < len(tile_rows[y]) else 0
                if tile_id and tile_id > 0:
                    idx = tile_id - 1
                    if idx < len(tree_tiles):
                        trees_layer.paste(tree_tiles[idx], (dx, dy))

    water_layer.save(water_out)
    grass_layer.save(grass_out)
    dirt_layer.save(dirt_out)
    trees_layer.save(trees_out)
