"""Count towers along the west wall between the NW corner (d43) and SW corner.

The west wall is at global tile x ≈ 698 (col 10). After center_map_margin.py,
the NW corner (topleftcorner) is at rows 10-11, cols 10-11.
The SW corner is at the south end of the west wall: global (698, 9058) ≈ row 137.

We scan chunks along col 10 (and col 9 for context) from row 10 to row 137,
load the tower_top layer, collect non-zero tile positions, and count distinct
tower blobs via connected components.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

REPO = Path("/Users/juliuswong/Dev/Aseprite-Mappie")
MAPS_ROOT = Path("/Users/juliuswong/Dev/gotchiverse-2d/public/maps/chunks")
TILE = 64
CHUNK_W = 66
CHUNK_H = 66


def load_chunk(cid: int) -> dict | None:
    p = MAPS_ROOT / f"chunk{cid}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text())


def main():
    sys.path.insert(0, str(REPO / "src" / "tilemap_generator"))
    from district_cli import load_master

    master = load_master(MAPS_ROOT)
    W = int(master["chunksHorizontal"])
    cw = int(master["chunkWidth"])
    ch = int(master["chunkHeight"])

    # Citadel west wall at global tile x = 698 (bL = 38 + 660).
    # Scan cols 9-11 (to catch towers that may straddle the wall).
    # NW corner at row 10, SW corner at row ~137.
    col_start, col_end = 9, 11
    row_start, row_end = 10, 137

    # Build a mask of non-zero tower_top tiles across the scan region.
    mask_w = (col_end - col_start + 1) * cw
    mask_h = (row_end - row_start + 1) * ch
    mask = np.zeros((mask_h, mask_w), dtype=bool)

    for row in range(row_start, row_end + 1):
        for col in range(col_start, col_end + 1):
            cid = row * W + col
            chunk = load_chunk(cid)
            if chunk is None:
                continue
            layers = chunk.get("layers", [])
            for layer in layers:
                if layer.get("name") != "tower_top":
                    continue
                data = layer.get("data", [])
                lw = layer.get("width", cw)
                lh = layer.get("height", ch)
                arr = np.array(data, dtype=np.int64).reshape(lh, lw)
                nz = arr > 0
                ly = (row - row_start) * ch
                lx = (col - col_start) * cw
                mask[ly:ly + lh, lx:lx + lw] |= nz

    print(f"scan region: cols {col_start}-{col_end}, rows {row_start}-{row_end}")
    print(f"mask size: {mask_w}x{mask_h} tiles, non-zero tiles: {mask.sum()}")

    if mask.sum() == 0:
        print("no tower_top tiles found")
        return

    # Connected components (towers are contiguous blobs)
    labeled, num = ndimage.label(mask)
    print(f"raw connected components: {num}")

    # Filter by size: towers are at least ~3x3 tiles
    sizes = ndimage.sum(mask, labeled, range(1, num + 1))
    min_tiles = 9  # minimum 3x3
    tower_blobs = [i for i, s in enumerate(sizes, 1) if s >= min_tiles]
    print(f"towers (>= {min_tiles} tiles): {len(tower_blobs)}")

    # Print each tower's centroid (in scan-local tiles) and global position
    for i in tower_blobs:
        ys, xs = np.where(labeled == i)
        cy, cx = ys.mean(), xs.mean()
        gx = (col_start * cw) + cx
        gy = (row_start * ch) + cy
        bbox = (xs.min(), ys.min(), xs.max(), ys.max())
        gbbox = (col_start * cw + bbox[0], row_start * ch + bbox[1],
                 col_start * cw + bbox[2], row_start * ch + bbox[3])
        print(f"  tower #{i}: size={int(sizes[i-1])} tiles, "
              f"global center=({gx:.0f},{gy:.0f}), bbox={gbbox}")


if __name__ == "__main__":
    main()
