"""Render west wall with cycled tower art: small, large, med, repeat.

Scans col 10 (rows 10-137) for tower_top blobs, excludes the NW corner,
cycles [leftmidtowersmall, leftmidtowerlarge, leftmidtowermed], centers
each on its original position. Outputs a scaled strip + zoomed sections.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage

REPO = Path("/Users/juliuswong/Dev/Aseprite-Mappie")
MAPS_ROOT = Path("/Users/juliuswong/Dev/gotchiverse-2d/public/maps/chunks")
BUILD = REPO / "build"
TILE = 64
TOWER_LAYERS = ["leftmidtowersmall", "leftmidtowerlarge", "leftmidtowermed"]


def load_chunk(cid):
    p = MAPS_ROOT / f"chunk{cid}.json"
    return json.loads(p.read_text()) if p.exists() else None


def get_wall_towers():
    sys.path.insert(0, str(REPO / "src" / "tilemap_generator"))
    from district_cli import load_master
    master = load_master(MAPS_ROOT)
    W = int(master["chunksHorizontal"]); cw = int(master["chunkWidth"])
    cs, ce = 9, 11; rs, re = 10, 137
    mw = (ce - cs + 1) * cw; mh = (re - rs + 1) * cw
    mask = np.zeros((mh, mw), dtype=bool)
    for row in range(rs, re + 1):
        for col in range(cs, ce + 1):
            chunk = load_chunk(row * W + col)
            if not chunk: continue
            for layer in chunk.get("layers", []):
                if layer.get("name") != "tower_top": continue
                d = layer.get("data", []); lw = layer.get("width", cw); lh = layer.get("height", cw)
                arr = np.array(d, dtype=np.int64).reshape(lh, lw)
                ly = (row - rs) * cw; lx = (col - cs) * cw
                mask[ly:ly+lh, lx:lx+lw] |= arr > 0
    labeled, num = ndimage.label(mask)
    sizes = ndimage.sum(mask, labeled, range(1, num + 1))
    towers = []
    for i in range(1, num + 1):
        if sizes[i-1] < 9: continue
        ys, xs = np.where(labeled == i)
        cx = cs * cw + xs.mean(); cy = rs * cw + ys.mean()
        if 690 <= cx <= 700:  # wall towers only
            towers.append((cx, cy, int(sizes[i-1])))
    towers.sort(key=lambda t: t[1])
    return towers


def main():
    towers = get_wall_towers()
    print(f"wall towers: {len(towers)}")
    # Exclude NW corner (first tower)
    nw = towers[0]
    rest = towers[1:]
    print(f"NW corner: center=({nw[0]:.0f},{nw[1]:.0f})")
    print(f"towers to cycle: {len(rest)}")

    # Load tower art
    arts = {}
    for name in TOWER_LAYERS:
        p = BUILD / f"newski_{name}_64.png"
        arts[name] = Image.open(p).convert("RGBA") if p.exists() else None
        if arts[name]:
            w, h = arts[name].size
            print(f"  {name}: {w//TILE}x{h//TILE} tiles")

    # Load topleftcorner
    tlc = Image.open(BUILD / "newski_topleftcorner_64.png").convert("RGBA")

    # Determine render bounds: col 9-11, from row 10 to bottomleftcorner bottom
    cs, ce = 9, 12  # 4 chunks wide for context
    cw = 66
    y_start = 10 * cw
    # Compute bottomleftcorner bottom to set canvas height
    prev = rest[-2]
    prev_art = arts[TOWER_LAYERS[0]]
    prev_h = prev_art.size[1] // TILE if prev_art else 35
    prev_bottom = int(prev[1]) + prev_h // 2
    blc_path = BUILD / "newski_bottomleftcorner_64.png"
    blc_h = Image.open(blc_path).size[1] // TILE if blc_path.exists() else 112
    blc_bottom = prev_bottom + 7 + blc_h
    y_end = blc_bottom + 1  # +1 tile so last row is empty
    x_start = cs * cw
    x_end = ce * cw + cw
    rw = x_end - x_start; rh = y_end - y_start
    print(f"render bounds: global x[{x_start},{x_end}] y[{y_start},{y_end}] = {rw}x{rh} tiles")

    # Scale: 4px per tile for overview
    S = 4
    canvas = Image.new("RGBA", (rw * S, rh * S), (20, 20, 30, 255))

    # Place topleftcorner at NW corner
    tlc_w, tlc_h = tlc.size[0] // TILE, tlc.size[1] // TILE
    tlc_x = int(nw[0]) - tlc_w // 2 - x_start
    tlc_y = int(nw[1]) - tlc_h // 2 - y_start
    tlc_small = tlc.resize((tlc_w * S, tlc_h * S), Image.NEAREST)
    canvas.alpha_composite(tlc_small, (tlc_x * S, tlc_y * S))
    print(f"topleftcorner at ({tlc_x},{tlc_y}) tiles, {tlc_w}x{tlc_h}")

    # Place bottomleftcorner at SW corner: 7 tiles below the last tower before it
    sw = rest[-1]
    prev = rest[-2]  # last tower before the corner
    blc_path = BUILD / "newski_bottomleftcorner_64.png"
    if blc_path.exists():
        blc = Image.open(blc_path).convert("RGBA")
        blc_w, blc_h = blc.size[0] // TILE, blc.size[1] // TILE
        # last tower bottom edge + 7 tiles = blc top edge
        prev_name = TOWER_LAYERS[(len(rest) - 2 - 1) % 3]
        prev_art = arts[prev_name]
        prev_h = prev_art.size[1] // TILE if prev_art else 35
        prev_bottom = int(prev[1]) + prev_h // 2
        blc_top = prev_bottom + 7
        blc_x = int(sw[0]) - blc_w // 2 - x_start
        blc_y = blc_top - y_start
        blc_small = blc.resize((blc_w * S, blc_h * S), Image.NEAREST)
        canvas.alpha_composite(blc_small, (blc_x * S, blc_y * S))
        print(f"bottomleftcorner at ({blc_x},{blc_y}) tiles, {blc_w}x{blc_h}, top={blc_top} (7 below last tower bottom={prev_bottom})")

    # Cycle towers: skip first and last (leave as original), middle cycles [small, large, med]
    # Track all placed pieces for connector gaps: (top_y, bottom_y) in global coords
    placed = []
    placed.append((tlc_y + y_start, tlc_y + y_start + tlc_h))  # topleftcorner

    n = len(rest)
    for i, (cx, cy, sz) in enumerate(rest):
        if i == 0 or i == n - 1:
            continue  # skip first and last tower
        name = TOWER_LAYERS[(i - 1) % 3]  # cycle from tower #2
        art = arts[name]
        if not art: continue
        aw, ah = art.size[0] // TILE, art.size[1] // TILE

        # Downsize to small if the cycled type would overlap the previous piece
        prev_bot = placed[-1][1]
        top = int(cy) - ah // 2
        if top < prev_bot and name != "leftmidtowersmall":
            name = "leftmidtowersmall"
            art = arts[name]
            aw, ah = art.size[0] // TILE, art.size[1] // TILE
            top = int(cy) - ah // 2

        # Skip if even the small tower would overlap
        if top < prev_bot:
            continue

        if name == "leftmidtowersmall":
            px = int(cx) - aw // 2 - x_start + 33
        elif name == "leftmidtowermed":
            px = int(cx) - aw // 2 - x_start + 14
        else:
            px = int(cx) - aw // 2 - x_start + 14  # large
        py = int(cy) - ah // 2 - y_start
        art_small = art.resize((aw * S, ah * S), Image.NEAREST)
        canvas.alpha_composite(art_small, (px * S, py * S))
        placed.append((py + y_start, py + y_start + ah))
        if i < 6 or i >= len(rest) - 3 or name != TOWER_LAYERS[(i - 1) % 3]:
            print(f"  tower #{i+1}: {name} at global ({cx:.0f},{cy:.0f}) -> render ({px},{py})")

    # Add bottomleftcorner to placed list
    if blc_path.exists():
        placed.append((blc_top, blc_top + blc_h))

    # Fill gaps between consecutive placed pieces with northsouthconnector
    ns_path = BUILD / "newski_northsouthconnector_64.png"
    if ns_path.exists():
        ns = Image.open(ns_path).convert("RGBA")
        nsw, nsh = ns.size[0] // TILE, ns.size[1] // TILE
        ns_small = ns.resize((nsw * S, nsh * S), Image.NEAREST)
        ns_x_global = 727  # shifted left by 1 tile
        ns_x = ns_x_global - x_start
        placed.sort(key=lambda p: p[0])
        gap_count = 0
        for j in range(len(placed) - 1):
            gap_top = placed[j][1]  # bottom of upper piece
            gap_bottom = placed[j + 1][0]  # top of lower piece
            gap = int(gap_bottom - gap_top)
            if gap > 0:
                for gy in range(gap):
                    nsy = int(gap_top) + gy - y_start
                    if 0 <= nsy < rh:
                        canvas.alpha_composite(ns_small, (ns_x * S, nsy * S))
                gap_count += 1
        print(f"northsouthconnector: filled {gap_count} gaps, x={ns_x_global}")

    out = BUILD / "west_wall_cycled.png"
    canvas.save(out)
    print(f"wrote {out} ({canvas.size})")

    # Also save a 1px/tile ultra-compact strip
    strip = canvas.resize((rw, rh), Image.LANCZOS)
    strip.save(BUILD / "west_wall_cycled_strip.png")
    print(f"wrote strip {strip.size}")

    # Zoomed sections: first 3 towers and last 3 towers at 16px/tile
    Z = 16
    for label, tidx in [("first3", 0), ("last3", len(rest) - 3)]:
        cx, cy, _ = rest[tidx]
        zx = int(cx) - x_start - 20; zy = int(cy) - y_start - 20
        zw, zh = 80, 80
        crop = canvas.crop((zx * S, zy * S, (zx + zw) * S, (zy + zh) * S))
        crop = crop.resize((zw * Z, zh * Z), Image.NEAREST)
        crop.save(f"/tmp/west_{label}.png")
        print(f"zoom {label}: /tmp/west_{label}.png")


if __name__ == "__main__":
    main()
