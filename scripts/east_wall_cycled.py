"""Render east wall with cycled tower art: small, large, med, repeat.
Mirrors the west wall logic but uses right-side art and mirrored x-offsets.
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
    """Mirror west wall tower positions to east wall (same y, x=7744)."""
    sys.path.insert(0, str(REPO / "src" / "tilemap_generator"))
    from district_cli import load_master
    master = load_master(MAPS_ROOT)
    W = int(master["chunksHorizontal"]); cw = int(master["chunkWidth"])
    # Scan WEST wall (cols 9-11) to get the 79 tower positions
    cs, ce = 9, 11; rs, re = 10, 137
    mw = (ce - cs + 1) * cw; mh = (re - rs + 1) * cw
    mask = np.zeros((mh, mw), dtype=bool)
    for row in range(rs, re + 1):
        for col in range(cs, ce + 1):
            cid = row * W + col
            p = MAPS_ROOT / f"chunk{cid}.json"
            if not p.exists(): continue
            chunk = json.loads(p.read_text())
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
        if 690 <= cx <= 700:  # west wall towers only
            # Mirror to east wall: x=7744, same y
            towers.append((7744.0, cy, int(sizes[i-1])))
    towers.sort(key=lambda t: t[1])
    return towers


def main():
    towers = get_wall_towers()
    print(f"wall towers: {len(towers)}")
    ne = towers[0]
    rest = towers[1:]
    print(f"NE corner: center=({ne[0]:.0f},{ne[1]:.0f})")
    print(f"towers to cycle: {len(rest)}")

    arts = {}
    for name in TOWER_LAYERS:
        p = BUILD / f"newski_{name}_64.png"
        arts[name] = Image.open(p).convert("RGBA") if p.exists() else None
        if arts[name]:
            w, h = arts[name].size
            print(f"  {name}: {w//TILE}x{h//TILE} tiles")

    trc = Image.open(BUILD / "newski_topleftcorner_64.png").convert("RGBA").transpose(Image.FLIP_LEFT_RIGHT)

    cs, ce = 116, 119
    cw = 66
    y_start = 10 * cw
    # Compute bottomrightcorner bottom for canvas height
    prev = rest[-2]
    prev_art = arts[TOWER_LAYERS[0]]
    prev_h = prev_art.size[1] // TILE if prev_art else 35
    prev_bottom = int(prev[1]) + prev_h // 2
    brc_path = BUILD / "newski_bottomleftcorner_64.png"
    brc_h = Image.open(brc_path).size[1] // TILE if brc_path.exists() else 112
    brc_bottom = prev_bottom + 7 + brc_h
    y_end = brc_bottom + 1
    x_start = cs * cw
    x_end = ce * cw + cw
    rw = x_end - x_start; rh = y_end - y_start
    print(f"render bounds: global x[{x_start},{x_end}] y[{y_start},{y_end}] = {rw}x{rh} tiles")

    S = 4
    canvas = Image.new("RGBA", (rw * S, rh * S), (20, 20, 30, 255))

    # Place toprightcorner at NE corner
    trc_w, trc_h = trc.size[0] // TILE, trc.size[1] // TILE
    trc_x = int(ne[0]) - trc_w // 2 - x_start
    trc_y = int(ne[1]) - trc_h // 2 - y_start
    trc_small = trc.resize((trc_w * S, trc_h * S), Image.NEAREST)
    canvas.alpha_composite(trc_small, (trc_x * S, trc_y * S))
    print(f"toprightcorner at ({trc_x},{trc_y}) tiles, {trc_w}x{trc_h}")

    # Place bottomrightcorner at SE corner: 7 tiles below the last tower before it
    se = rest[-1]
    prev = rest[-2]
    if brc_path.exists():
        brc = Image.open(brc_path).convert("RGBA").transpose(Image.FLIP_LEFT_RIGHT)
        brc_w, brc_h = brc.size[0] // TILE, brc.size[1] // TILE
        prev_name = TOWER_LAYERS[(len(rest) - 2 - 1) % 3]
        prev_art = arts[prev_name]
        prev_h = prev_art.size[1] // TILE if prev_art else 35
        prev_bottom = int(prev[1]) + prev_h // 2
        brc_top = prev_bottom + 7
        brc_x = int(se[0]) - brc_w // 2 - x_start
        brc_y = brc_top - y_start
        brc_small = brc.resize((brc_w * S, brc_h * S), Image.NEAREST)
        canvas.alpha_composite(brc_small, (brc_x * S, brc_y * S))
        print(f"bottomrightcorner at ({brc_x},{brc_y}) tiles, {brc_w}x{brc_h}, top={brc_top} (7 below last tower bottom={prev_bottom})")

    # Cycle towers: skip first and last, middle cycles [small, large, med]
    # Mirror x-offsets: west used +33/+14, east uses -33/-14
    placed = []
    placed.append((trc_y + y_start, trc_y + y_start + trc_h))

    n = len(rest)
    for i, (cx, cy, sz) in enumerate(rest):
        if i == 0 or i == n - 1:
            continue
        name = TOWER_LAYERS[(i - 1) % 3]
        art = arts[name]
        if not art: continue
        aw, ah = art.size[0] // TILE, art.size[1] // TILE

        # Downsize to small if the cycled type would overlap the previous piece
        # but still place it (no skip)
        prev_bot = placed[-1][1]
        top = int(cy) - ah // 2
        if top < prev_bot and name != "leftmidtowersmall":
            name = "leftmidtowersmall"
            art = arts[name]
            aw, ah = art.size[0] // TILE, art.size[1] // TILE
            top = int(cy) - ah // 2

        if name == "leftmidtowersmall":
            px = int(cx) - aw // 2 - x_start - 33  # mirrored: shift left
        elif name == "leftmidtowermed":
            px = int(cx) - aw // 2 - x_start - 14
        else:
            px = int(cx) - aw // 2 - x_start - 14  # large
        py = int(cy) - ah // 2 - y_start
        art_flipped = art.transpose(Image.FLIP_LEFT_RIGHT)
        art_small = art_flipped.resize((aw * S, ah * S), Image.NEAREST)
        canvas.alpha_composite(art_small, (px * S, py * S))
        placed.append((py + y_start, py + y_start + ah))
        if i < 6 or i >= len(rest) - 3 or name != TOWER_LAYERS[(i - 1) % 3]:
            print(f"  tower #{i+1}: {name} at global ({cx:.0f},{cy:.0f}) -> render ({px},{py})")

    if brc_path.exists():
        placed.append((brc_top, brc_top + brc_h))

    # Fill gaps with northsouthconnector (mirrored x)
    ns_path = BUILD / "newski_northsouthconnector_64.png"
    if ns_path.exists():
        ns = Image.open(ns_path).convert("RGBA").transpose(Image.FLIP_LEFT_RIGHT)
        nsw, nsh = ns.size[0] // TILE, ns.size[1] // TILE
        ns_small = ns.resize((nsw * S, nsh * S), Image.NEAREST)
        # West connector at wall_x + 31 = 696 + 31 = 727
        # East connector mirrored: wall_x - 31 = 7744 - 31 = 7713
        ns_x_global = 7698  # 7697 + 1, shifted right 1 tile
        ns_x = ns_x_global - x_start
        placed.sort(key=lambda p: p[0])
        gap_count = 0
        for j in range(len(placed) - 1):
            gap_top = placed[j][1]
            gap_bottom = placed[j + 1][0]
            gap = int(gap_bottom - gap_top)
            if gap > 0:
                for gy in range(gap):
                    nsy = int(gap_top) + gy - y_start
                    if 0 <= nsy < rh:
                        canvas.alpha_composite(ns_small, (ns_x * S, nsy * S))
                gap_count += 1
        print(f"northsouthconnector: filled {gap_count} gaps, x={ns_x_global}")

    out = BUILD / "east_wall_cycled.png"
    canvas.save(out)
    print(f"wrote {out} ({canvas.size})")

    strip = canvas.resize((rw, rh), Image.LANCZOS)
    strip.save(BUILD / "east_wall_cycled_strip.png")
    print(f"wrote strip {strip.size}")

    Z = 16
    for label, tidx in [("first3", 0), ("last3", len(rest) - 3)]:
        cx, cy, _ = rest[tidx]
        zx = int(cx) - x_start - 20; zy = int(cy) - y_start - 20
        zw, zh = 80, 80
        crop = canvas.crop((zx * S, zy * S, (zx + zw) * S, (zy + zh) * S))
        crop = crop.resize((zw * Z, zh * Z), Image.NEAREST)
        crop.save(f"/tmp/east_{label}.png")
        print(f"zoom {label}: /tmp/east_{label}.png")


if __name__ == "__main__":
    main()
