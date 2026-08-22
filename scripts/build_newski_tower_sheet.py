"""Build a newski tower spritesheet SLICED into native-res 64x64 tiles, and overlay
the multi-tile pieces onto the 2x2 chunk of district 43 at tower1 positions.

Each newski piece is sliced into ceil(w/64) x ceil(h/64) tiles at native 64px
resolution (NO downscaling). The sheet stacks each piece as a tile-block column.
The overlay stamps the full multi-tile piece centered on each tower1 cell.

Outputs:
  build/towers_newski_sliced.png       - native-res 64x64 tile grid
  build/towers_newski_sliced.json       - metadata: piece -> {col, row, cols, rows, w, h}
  build/district_43_2x2_newski_towers_preview.png - chunk + new towers overlaid
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path("/Users/juliuswong/Dev/Aseprite-Mappie")
MAPS_ROOT = Path("/Users/juliuswong/Dev/gotchiverse-2d/public/maps")
NEWski_LAYERS = Path("/tmp/newski_layers")
BUILD = REPO / "build"
BUILD.mkdir(exist_ok=True)

TILE = 64
TOWER1_FIRSTGID = 50
TOWER1_COUNT = 140

PIECES = [
    "leftmidtowerlarge", "leftmidtowermed", "leftmidtowersmall",
    "rightmidtowerlarge", "rightmidtowermed", "rightmidtowersmall",
    "northsouthconnector", "westeastconnector",
]
# role -> piece index
ROLE_PIECE = {"tower_left": 1, "tower_right": 4, "ns": 6, "we": 7}


def content_bbox(img: Image.Image):
    arr = np.array(img.convert("RGBA"))
    a = arr[:, :, 3]
    ys, xs = np.where(a > 0)
    if len(xs) == 0:
        return None
    return xs.min(), ys.min(), xs.max(), ys.max()


def classify_orientation(tile_img: Image.Image) -> str:
    bbox = content_bbox(tile_img)
    if bbox is None:
        return "square"
    x0, y0, x1, y1 = bbox
    w, h = (x1 - x0 + 1), (y1 - y0 + 1)
    if w > h * 1.4:
        return "horizontal"
    if h > w * 1.4:
        return "vertical"
    return "square"


# --- Load + slice each newski piece into 64x64 tiles (native res) ---
piece_tiles: list[list[list[Image.Image]]] = []  # [piece][row][col] -> 64x64 tile
piece_dims: list[dict] = []
for name in PIECES:
    src = Image.open(NEWski_LAYERS / f"{name}.png").convert("RGBA")
    bbox = content_bbox(src)
    if bbox is None:
        piece_tiles.append([[Image.new("RGBA", (TILE, TILE), (0, 0, 0, 0))]])
        piece_dims.append({"name": name, "w": 0, "h": 0, "cols": 1, "rows": 1})
        continue
    x0, y0, x1, y1 = bbox
    cropped = src.crop((x0, y0, x1 + 1, y1 + 1))
    w, h = cropped.size
    cols = (w + TILE - 1) // TILE
    rows = (h + TILE - 1) // TILE
    # pad cropped to a multiple of 64, then slice
    padded = Image.new("RGBA", (cols * TILE, rows * TILE), (0, 0, 0, 0))
    padded.alpha_composite(cropped, (0, 0))
    tiles: list[list[Image.Image]] = []
    for r in range(rows):
        row_tiles: list[Image.Image] = []
        for c in range(cols):
            row_tiles.append(padded.crop((c * TILE, r * TILE, (c + 1) * TILE, (r + 1) * TILE)))
        tiles.append(row_tiles)
    piece_tiles.append(tiles)
    piece_dims.append({"name": name, "w": w, "h": h, "cols": cols, "rows": rows})

# --- Build spritesheet: each piece as a tile-block column ---
total_cols = sum(d["cols"] for d in piece_dims)
total_rows = max(d["rows"] for d in piece_dims)
sheet = Image.new("RGBA", (total_cols * TILE, total_rows * TILE), (0, 0, 0, 0))
meta = {"tile_size": TILE, "pieces": []}
col_cursor = 0
for pi, d in enumerate(piece_dims):
    tiles = piece_tiles[pi]
    for r in range(d["rows"]):
        for c in range(d["cols"]):
            sheet.paste(tiles[r][c], ((col_cursor + c) * TILE, r * TILE))
    meta["pieces"].append({
        "name": d["name"], "index": pi,
        "col": col_cursor, "row": 0,
        "cols": d["cols"], "rows": d["rows"],
        "w": d["w"], "h": d["h"],
    })
    col_cursor += d["cols"]

sheet_path = BUILD / "towers_newski_sliced.png"
sheet.save(sheet_path)
(BUILD / "towers_newski_sliced.json").write_text(json.dumps(meta, indent=2))
print(f"Wrote sliced sheet: {sheet_path} ({sheet.size})")
for d in piece_dims:
    print(f"  {d['name']:24s} {d['w']}x{d['h']} -> {d['cols']}x{d['rows']} tiles")

# --- Classify used tower1 tiles by orientation ---
tower1_src = Image.open(MAPS_ROOT / "sprites" / "tower1.png").convert("RGBA")
COLS = 14


def tower1_tile(local_id: int) -> Image.Image:
    idx = local_id - 1
    return tower1_src.crop(((idx % COLS) * TILE, (idx // COLS) * TILE,
                             (idx % COLS) * TILE + TILE, (idx // COLS) * TILE + TILE))


master = json.load(open(MAPS_ROOT / "chunks" / "master.json"))
CH = master["chunksHorizontal"]
chunk_ids = [0, 1, CH, CH + 1]
CHUNK_W = master["chunkWidth"]

used_locals: set[int] = set()
for cid in chunk_ids:
    c = json.load(open(MAPS_ROOT / "chunks" / f"chunk{cid}.json"))
    for layer in c["layers"]:
        if layer.get("name") not in ("tower_bottom", "tower_top"):
            continue
        for g in layer["data"]:
            if TOWER1_FIRSTGID <= g <= TOWER1_FIRSTGID + TOWER1_COUNT - 1:
                used_locals.add(g - TOWER1_FIRSTGID + 1)

local_orientation = {L: classify_orientation(tower1_tile(L)) for L in used_locals}

# --- Overlay: stamp full multi-tile piece centered on each tower1 cell ---
canvas = Image.open("/tmp/d43_2x2_flat.png").convert("RGBA").copy()
stamped = 0
for cid_idx, cid in enumerate(chunk_ids):
    cx = cid_idx % 2
    cy = cid_idx // 2
    c = json.load(open(MAPS_ROOT / "chunks" / f"chunk{cid}.json"))
    for layer in c["layers"]:
        if layer.get("name") not in ("tower_bottom", "tower_top"):
            continue
        data = layer["data"]
        lw = layer["width"]
        for idx, g in enumerate(data):
            if not (TOWER1_FIRSTGID <= g <= TOWER1_FIRSTGID + TOWER1_COUNT - 1):
                continue
            local = g - TOWER1_FIRSTGID + 1
            orient = local_orientation[local]
            tx = idx % lw
            ty = idx // lw
            gx = cx * CHUNK_W + tx
            gy = cy * CHUNK_W + ty
            if orient == "horizontal":
                pi = ROLE_PIECE["we"]
            elif orient == "vertical":
                pi = ROLE_PIECE["ns"]
            else:
                pi = ROLE_PIECE["tower_left"] if gx < CHUNK_W else ROLE_PIECE["tower_right"]
            d = piece_dims[pi]
            tiles = piece_tiles[pi]
            # center the piece's tile-block on the tower1 cell
            origin_c = gx - d["cols"] // 2
            origin_r = gy - d["rows"] // 2
            for r in range(d["rows"]):
                for cc in range(d["cols"]):
                    px = (origin_c + cc) * TILE
                    py = (origin_r + r) * TILE
                    if px < 0 or py < 0:
                        continue
                    canvas.alpha_composite(tiles[r][cc], (px, py))
            stamped += 1

preview_path = BUILD / "district_43_2x2_newski_towers_preview.png"
canvas.save(preview_path)
print(f"Stamped {stamped} tower1 cells with sliced multi-tile pieces")
print(f"Wrote preview: {preview_path} ({canvas.size})")
