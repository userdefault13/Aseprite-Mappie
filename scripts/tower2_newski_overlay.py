"""Stitch a 2x2 chunk block that uses tower2 (chunks 70,71,198,199) into a flat
PNG, then overlay the 8x-scaled newski leftmidsmalltower onto the tower2 cells.

Outputs:
  build/tower2_2x2_flat.png                 - flat stitched chunk (no overlay)
  build/tower2_2x2_newski_overlay.png       - chunk with newski tower on tower2 cells
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image
import numpy as np

from district_cli import (
    stitch_layers,
    load_master,
    resolve_tileset_image,
)

REPO = Path("/Users/juliuswong/Dev/Aseprite-Mappie")
MAPS_ROOT = Path("/Users/juliuswong/Dev/gotchiverse-2d/public/maps/chunks")
BUILD = REPO / "build"
BUILD.mkdir(exist_ok=True)

TILE = 64
T2_FIRST = 190
T2_LAST = 190 + 216 - 1  # 405

# 2x2 block: chunks 70,71 (row0 col70,71) + 198,199 (row1 col70,71)
X0, X1, Y0, Y1 = 70, 71, 0, 1


def slice_tileset(ts: dict) -> dict[int, Image.Image]:
    """Slice a tileset PNG (with margin/spacing) into {gid: Image}."""
    firstgid = int(ts.get("firstgid", 1))
    tw = int(ts.get("tilewidth", TILE))
    th = int(ts.get("tileheight", TILE))
    margin = int(ts.get("margin", 0) or 0)
    spacing = int(ts.get("spacing", 0) or 0)
    cols = int(ts.get("columns", 0) or 0)
    count = int(ts.get("tilecount", 0) or 0)
    img_path = resolve_tileset_image(ts, MAPS_ROOT)
    if img_path is None:
        return {}
    src = Image.open(img_path).convert("RGBA")
    tiles: dict[int, Image.Image] = {}
    for i in range(count):
        c = i % cols
        r = i // cols
        x = margin + c * (tw + spacing)
        y = margin + r * (th + spacing)
        t = src.crop((x, y, x + tw, y + th))
        tiles[firstgid + i] = t
    return tiles


def main():
    import sys
    sys.path.insert(0, str(REPO / "src" / "tilemap_generator"))

    master = load_master(MAPS_ROOT)
    tiled_layers, tilesets_by_name = stitch_layers(MAPS_ROOT, master, X0, X1, Y0, Y1)
    tiles_w = tiled_layers[next(iter(tiled_layers))]["width"]
    tiles_h = tiled_layers[next(iter(tiled_layers))]["height"]
    print(f"stitched {tiles_w}x{tiles_h} tiles, layers: {list(tiled_layers)}")

    # slice all tilesets into one gid->image map
    gid_img: dict[int, Image.Image] = {}
    for name, ts in tilesets_by_name.items():
        gid_img.update(slice_tileset(ts))

    # composite layers in their natural order (alchemica bottom, tower_bottom, tower_top)
    canvas = Image.new("RGBA", (tiles_w * TILE, tiles_h * TILE), (0, 0, 0, 0))
    for name, layer in tiled_layers.items():
        data = layer["data"]
        w = layer["width"]
        for i, gid in enumerate(data):
            if gid == 0:
                continue
            t = gid_img.get(gid)
            if t is None:
                continue
            x = (i % w) * TILE
            y = (i // w) * TILE
            canvas.alpha_composite(t, (x, y))
    flat_path = BUILD / "tower2_2x2_flat.png"
    canvas.save(flat_path)
    print(f"wrote flat: {flat_path} ({canvas.size})")

    # find tower2 cells (union of tower_bottom + tower_top)
    t2_cells = []
    for name, layer in tiled_layers.items():
        data = layer["data"]
        w = layer["width"]
        for i, gid in enumerate(data):
            if T2_FIRST <= gid <= T2_LAST:
                t2_cells.append((i % w, i // w))
    print(f"tower2 cells: {len(t2_cells)}")
    if not t2_cells:
        print("no tower2 cells in this block!")
        return
    xs = [c[0] for c in t2_cells]
    ys = [c[1] for c in t2_cells]
    print(f"tower2 bbox: x[{min(xs)}..{max(xs)}] y[{min(ys)}..{max(ys)}]  (w={max(xs)-min(xs)+1} h={max(ys)-min(ys)+1})")

    # overlay the 8x-scaled newski tower, centered on the tower2 bbox
    tower = Image.open(BUILD / "newski_leftmidsmall_64.png").convert("RGBA")
    tw_tiles = tower.size[0] // TILE
    th_tiles = tower.size[1] // TILE
    cx = (min(xs) + max(xs)) // 2
    cy = (min(ys) + max(ys)) // 2
    ax = cx - tw_tiles // 2
    ay = cy - th_tiles // 2
    print(f"newski tower {tw_tiles}x{th_tiles} tiles, centered at ({cx},{cy}) -> anchor ({ax},{ay})")
    overlay = canvas.copy()
    overlay.alpha_composite(tower, (ax * TILE, ay * TILE))
    out_path = BUILD / "tower2_2x2_newski_overlay.png"
    overlay.save(out_path)
    print(f"wrote overlay: {out_path}")

    # previews
    overlay.resize((1408, 1408), Image.LANCZOS).save("/tmp/t2_overlay_overview.png")
    pad = 6
    z = overlay.crop(
        (
            max(0, (ax - pad) * TILE),
            max(0, (ay - pad) * TILE),
            min(overlay.size[0], (ax + tw_tiles + pad) * TILE),
            min(overlay.size[1], (ay + th_tiles + pad) * TILE),
        )
    )
    z.save("/tmp/t2_overlay_zoom.png")
    print("previews: /tmp/t2_overlay_overview.png /tmp/t2_overlay_zoom.png")


if __name__ == "__main__":
    main()
