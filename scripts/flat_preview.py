"""Flat render of an arbitrary bbox of chunks with ground layers.

Usage: python scripts/flat_preview.py X0 X1 Y0 Y1 [label]
  X0,X1 = col range (inclusive)
  Y0,Y1 = row range (inclusive)
  label = output filename label (default: x{X0}_y{Y0})

Outputs:
  build/<label>_flat.png
  /tmp/<label>_overview.png
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

REPO = Path("/Users/juliuswong/Dev/Aseprite-Mappie")
MAPS_ROOT = Path("/Users/juliuswong/Dev/gotchiverse-2d/public/maps/chunks")
BUILD = REPO / "build"
BUILD.mkdir(exist_ok=True)

TILE = 64


def slice_tileset(ts: dict) -> dict[int, Image.Image]:
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
        tiles[firstgid + i] = src.crop((x, y, x + tw, y + th))
    return tiles


def resolve_tileset_image(ts: dict, maps_root: Path):
    name = ts.get("name", "tileset")
    image_rel = ts.get("image") or ""
    candidates = []
    if image_rel:
        candidates.append(maps_root / image_rel)
        candidates.append(maps_root.parent / image_rel)
    candidates.append(maps_root / "sprites" / f"{name}.png")
    candidates.append(maps_root.parent / "sprites" / f"{name}.png")
    seen = set()
    for p in candidates:
        k = str(p)
        if k in seen:
            continue
        seen.add(k)
        if p.exists():
            return p
    return None


def main():
    if len(sys.argv) < 5:
        print("Usage: python scripts/flat_preview.py X0 X1 Y0 Y1 [label]", file=sys.stderr)
        sys.exit(2)
    X0, X1, Y0, Y1 = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    label = sys.argv[5] if len(sys.argv) > 5 else f"x{X0}_y{Y0}"

    sys.path.insert(0, str(REPO / "src" / "tilemap_generator"))
    from district_cli import stitch_layers, load_master

    master = load_master(MAPS_ROOT)
    tiled_layers, tilesets_by_name = stitch_layers(MAPS_ROOT, master, X0, X1, Y0, Y1)
    tiles_w = tiled_layers[next(iter(tiled_layers))]["width"]
    tiles_h = tiled_layers[next(iter(tiled_layers))]["height"]
    print(f"stitched {tiles_w}x{tiles_h} tiles, layers: {list(tiled_layers)}")

    gid_img: dict[int, Image.Image] = {}
    for name, ts in tilesets_by_name.items():
        gid_img.update(slice_tileset(ts))

    SPRITES = MAPS_ROOT.parent / "sprites"
    dirt_tx = Image.open(SPRITES / "dirt.png").convert("RGBA").resize((TILE, TILE), Image.NEAREST)
    water_tx = Image.open(SPRITES / "water_tile.png").convert("RGBA").resize((TILE, TILE), Image.NEAREST)
    grass_tx = Image.open(SPRITES / "grass1.png").convert("RGBA").resize((TILE, TILE), Image.NEAREST)

    SHIFT = 660
    bL, bT, bR, bB = 38 + SHIFT, 50 + SHIFT, 7082 + SHIFT, 8398 + SHIFT
    margin = 2
    gx0 = X0 * int(master["chunkWidth"])
    gy0 = Y0 * int(master["chunkHeight"])
    pw, ph = tiles_w, tiles_h

    def in_preview(sx, sy, sw, sh):
        ix = max(sx, gx0); iy = max(sy, gy0)
        ir = min(sx + sw, gx0 + pw); ib = min(sy + sh, gy0 + ph)
        if ir <= ix or ib <= iy:
            return None
        return ix - gx0, iy - gy0, ir - ix, ib - iy

    canvas = Image.new("RGBA", (pw * TILE, ph * TILE), (0, 0, 0, 0))

    for yy in range(ph):
        for xx in range(pw):
            canvas.alpha_composite(dirt_tx, (xx * TILE, yy * TILE))

    water_strips = [
        (0, 0, 9768, bT - margin),
        (0, bB + margin, 9768, 9768 - bB - margin),
        (0, bT - margin, bL - margin, bB - bT + margin),
        (bR + margin, bT - margin, 9768 - bR - margin, bB - bT + margin),
    ]
    for sx, sy, sw, sh in water_strips:
        c = in_preview(sx, sy, sw, sh)
        if not c:
            continue
        lx, ly, lw, lh = c
        for yy in range(lh):
            for xx in range(lw):
                canvas.alpha_composite(water_tx, ((lx + xx) * TILE, (ly + yy) * TILE))

    northH = bT - margin
    southH = 9768 - bB - margin
    westW = bL - margin
    eastW = 9768 - bR - margin
    sideH = bB - bT + margin
    grass_w = westW // 4
    west_grass_x = westW - grass_w
    citadel_w = bR - bL
    grass_strips = [
        (west_grass_x, northH - northH // 4, citadel_w + 2 * grass_w, northH // 4),
        (0, bB + margin, 9768, southH // 4),
        (west_grass_x, bT - margin, grass_w, sideH),
        (bR + margin + eastW - eastW // 4, bT - margin, eastW // 4, sideH),
    ]
    for sx, sy, sw, sh in grass_strips:
        c = in_preview(sx, sy, sw, sh)
        if not c:
            continue
        lx, ly, lw, lh = c
        for yy in range(lh):
            for xx in range(lw):
                canvas.alpha_composite(grass_tx, ((lx + xx) * TILE, (ly + yy) * TILE))
    print("ground layers: dirt base + water/grass strips composited")

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
    print(f"composited flat canvas: {canvas.size}")

    out = BUILD / f"{label}_flat.png"
    canvas.save(out)
    print(f"wrote {out}")

    canvas.resize((1600, 1600), Image.LANCZOS).save(f"/tmp/{label}_overview.png")
    print(f"previews: /tmp/{label}_overview.png")


if __name__ == "__main__":
    main()
