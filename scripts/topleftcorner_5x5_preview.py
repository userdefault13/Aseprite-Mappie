"""Reprint the topleftcorner preview over the d43 2x2 chunk, but with 3 extra
chunks of context to the LEFT and TOP.

After center_map_margin.py, the d43 2x2 sits at rows 10-11, cols 10-11 in the
148-wide grid. We stitch a 5x5 bbox (cols 7-11, rows 7-11) so the d43 2x2 is the
bottom-right 2x2, with 3 empty margin chunks on its left and top.

The topleftcorner art is overlaid at the same anchor used previously
((-4,-13) tiles relative to the d43 2x2 origin). In the 5x5 preview the d43 2x2
origin is at tile (3*66, 3*66) = (198,198), so the art anchor is (194,185).

Outputs:
  build/d43_5x5_topleftcorner.png
  /tmp/tlc5_overview.png
  /tmp/tlc5_zoom.png
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

# 5x5 bbox: d43 2x2 at cols 10-11, rows 10-11; +3 left (cols 7-9), +3 top (rows 7-9)
X0, X1, Y0, Y1 = 7, 11, 7, 11
D43_ORIGIN_CHUNKS = (3, 3)  # d43 2x2 top-left is 3 chunks in from preview origin
ART_ANCHOR_REL = (-86, -27)  # tiles relative to d43 2x2 origin (left 82, up 27 total)


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

    # citadel wall bounds in GLOBAL tile coords (original 38/50/7082/8398 shifted by +660)
    SHIFT = 660
    bL, bT, bR, bB = 38 + SHIFT, 50 + SHIFT, 7082 + SHIFT, 8398 + SHIFT
    margin = 2
    # preview global origin (cols/rows 7..11, 66 tiles each)
    gx0 = X0 * int(master["chunkWidth"])
    gy0 = Y0 * int(master["chunkHeight"])
    pw, ph = tiles_w, tiles_h  # preview size in tiles

    def in_preview(sx, sy, sw, sh):
        """clip a global-tile rect to the preview; return local (x,y,w,h) or None"""
        ix = max(sx, gx0); iy = max(sy, gy0)
        ir = min(sx + sw, gx0 + pw); ib = min(sy + sh, gy0 + ph)
        if ir <= ix or ib <= iy:
            return None
        return ix - gx0, iy - gy0, ir - ix, ib - iy

    canvas = Image.new("RGBA", (pw * TILE, ph * TILE), (0, 0, 0, 0))

    # dirt base (whole preview)
    for yy in range(ph):
        for xx in range(pw):
            canvas.alpha_composite(dirt_tx, (xx * TILE, yy * TILE))

    # water strips (outside walls, with 2-tile dirt gap)
    water_strips = [
        (0, 0, 9768, bT - margin),                       # north
        (0, bB + margin, 9768, 9768 - bB - margin),       # south
        (0, bT - margin, bL - margin, bB - bT + margin),  # west
        (bR + margin, bT - margin, 9768 - bR - margin, bB - bT + margin),  # east
    ]
    for sx, sy, sw, sh in water_strips:
        c = in_preview(sx, sy, sw, sh)
        if not c:
            continue
        lx, ly, lw, lh = c
        for yy in range(lh):
            for xx in range(lw):
                canvas.alpha_composite(water_tx, ((lx + xx) * TILE, (ly + yy) * TILE))

    # grass strips (wall-adjacent half of the water area)
    # grass strips (wall-adjacent quarter of the water area — contracted by half)
    northH = bT - margin
    southH = 9768 - bB - margin
    westW = bL - margin
    eastW = 9768 - bR - margin
    sideH = bB - bT + margin
    grass_w = westW // 4
    west_grass_x = westW - grass_w
    citadel_w = bR - bL
    grass_strips = [
        (west_grass_x, northH - northH // 4, citadel_w + 2 * grass_w, northH // 4),        # north: width = citadel + 2*grass, x == west grass x
        (0, bB + margin, 9768, southH // 4),                                              # south: outer quarter
        (west_grass_x, bT - margin, grass_w, sideH),                                     # west: right quarter
        (bR + margin + eastW - eastW // 4, bT - margin, eastW // 4, sideH),              # east: left quarter
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

    cw = int(master["chunkWidth"])
    ax = D43_ORIGIN_CHUNKS[0] * cw + ART_ANCHOR_REL[0]
    ay = D43_ORIGIN_CHUNKS[1] * cw + ART_ANCHOR_REL[1]
    art = Image.open(BUILD / "newski_topleftcorner_64.png").convert("RGBA")
    atw, ath = art.size[0] // TILE, art.size[1] // TILE
    print(f"topleftcorner art {atw}x{ath} tiles, anchor in preview ({ax},{ay})")
    canvas.alpha_composite(art, (ax * TILE, ay * TILE))

    # west-wall small tower (leftmidtowersmall) centered on the ORIGINAL small tower's center.
    # Original west small tower: bbox x33..39 y117..122, size 7x6, center (36,120) in d43 2x2.
    # New art is 32x35; anchor = center - (16,17) = (20,103) in d43-local -> preview (218,301).
    west = Image.open(BUILD / "newski_leftmidtowersmall_64.png").convert("RGBA")
    ww, wh = west.size[0] // TILE, west.size[1] // TILE
    wx = 209  # left path connecting point (15 tiles from left) aligns with northsouth path left edge (x=224)
    wy = D43_ORIGIN_CHUNKS[1] * cw + 120 - wh // 2
    print(f"leftmidtowersmall {ww}x{wh} tiles, anchor in preview ({wx},{wy}) [center on original (36,120)]")
    canvas.alpha_composite(west, (wx * TILE, wy * TILE))

    # northsouthconnector stacked vertically to bridge the northsouth path (y=200-277)
    # down to the left mid small tower top (y=301). Stack from y=277 to y=300.
    ns = Image.open(BUILD / "newski_northsouthconnector_64.png").convert("RGBA")
    nsw, nsh = ns.size[0] // TILE, ns.size[1] // TILE
    nsx = 224  # aligned with northsouth path left edge
    nsy_start = 277  # path south end (bottom)
    nsy_end = 300  # just above small tower top (y=301)
    for nsy in range(nsy_start, nsy_end + 1):
        canvas.alpha_composite(ns, (nsx * TILE, nsy * TILE))
    print(f"northsouthconnector {nsw}x{nsh} tiles stacked x={nsx} y={nsy_start}..{nsy_end}")

    out = BUILD / "d43_5x5_topleftcorner.png"
    canvas.save(out)
    print(f"wrote {out}")

    canvas.resize((1600, 1600), Image.LANCZOS).save("/tmp/tlc5_overview.png")
    z = canvas.crop((ax * TILE, ay * TILE,
                     min(canvas.size[0], (ax + atw + 6) * TILE),
                     min(canvas.size[1], (ay + ath + 6) * TILE)))
    z.resize((1600, 1600), Image.LANCZOS).save("/tmp/tlc5_zoom.png")
    print("previews: /tmp/tlc5_overview.png /tmp/tlc5_zoom.png")


if __name__ == "__main__":
    main()
