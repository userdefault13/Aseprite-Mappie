"""Use a newski layer as a legend: slice it into 8x8 tiles, dedupe to a unique
legend, scale each unique tile 8x -> 64x64 (nearest-neighbor), emit a JSON
tilemap, and render the layer at 64px from the JSON.

Usage:
  python scripts/newski_legend_pipeline.py <layer_name>

Example:
  python scripts/newski_legend_pipeline.py leftmidtowersmall
  python scripts/newski_legend_pipeline.py topleftcorner

Pipeline:
  1. Slice <layer> content into 8x8 tiles.
  2. Dedupe -> unique tiles (the legend).
  3. Scale each unique 8x8 -> 64x64 (NEAREST) -> legend spritesheet.
  4. JSON: {tile_size, legend_cols, legend_count, tilemap: [[idx,...]]}
  5. Render the layer at 64px by placing legend tiles per the JSON.

Outputs (per layer):
  build/newski_legend_<layer>.png   - legend spritesheet (unique 64x64 tiles)
  build/newski_legend_<layer>.json - legend metadata + tilemap
  build/newski_<layer>_64.png       - the layer rendered at 64px (standalone)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path("/Users/juliuswong/Dev/Aseprite-Mappie")
NEWski_LAYERS = REPO / "assets" / "newski" / "source"
BUILD = REPO / "build"
BUILD.mkdir(exist_ok=True)

SMALL = 8          # native tile size in newski
TILE = 64           # target gotchiverse tile size
SCALE = TILE // SMALL  # 8x


def content_bbox(img: Image.Image):
    arr = np.array(img.convert("RGBA"))
    a = arr[:, :, 3]
    ys, xs = np.where(a > 0)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def run(layer: str) -> None:
    src_path = NEWski_LAYERS / f"{layer}.png"
    if not src_path.exists():
        raise FileNotFoundError(f"Layer PNG not found: {src_path}")

    # --- Step 1: slice content into 8x8 tiles ---
    src = Image.open(src_path).convert("RGBA")
    bbox = content_bbox(src)
    if bbox is None:
        raise ValueError(f"Layer {layer!r} has no content")
    x0, y0, x1, y1 = bbox
    content = src.crop((x0, y0, x1 + 1, y1 + 1))
    cw, ch = content.size
    tcols, trows = cw // SMALL, ch // SMALL
    print(f"[{layer}] content {cw}x{ch} = {tcols}x{trows} tiles at {SMALL}px")

    tiles_8: list[Image.Image] = []
    for r in range(trows):
        for c in range(tcols):
            t = content.crop((c * SMALL, r * SMALL, (c + 1) * SMALL, (r + 1) * SMALL))
            tiles_8.append(t)

    # --- Step 2: dedupe -> legend ---
    def tile_key(t: Image.Image) -> bytes:
        return t.tobytes()

    seen: dict[bytes, int] = {}
    legend_idx: list[int] = []
    for t in tiles_8:
        k = tile_key(t)
        if k not in seen:
            seen[k] = len(seen)
        legend_idx.append(seen[k])
    legend_count = len(seen)
    print(f"[{layer}] unique tiles (legend size): {legend_count} (of {len(tiles_8)} cells)")

    # --- Step 3: scale each unique 8x8 -> 64x64 -> legend spritesheet ---
    LEGEND_COLS = min(16, legend_count)
    LEGEND_ROWS = (legend_count + LEGEND_COLS - 1) // LEGEND_COLS
    legend_sheet = Image.new("RGBA", (LEGEND_COLS * TILE, LEGEND_ROWS * TILE), (0, 0, 0, 0))
    legend_tiles: list[Image.Image] = [None] * legend_count
    for cell_i, li in enumerate(legend_idx):
        if legend_tiles[li] is None:
            legend_tiles[li] = tiles_8[cell_i]
    for li, t8 in enumerate(legend_tiles):
        t64 = t8.resize((TILE, TILE), Image.NEAREST)
        c = li % LEGEND_COLS
        r = li // LEGEND_COLS
        legend_sheet.paste(t64, (c * TILE, r * TILE))
    legend_path = BUILD / f"newski_legend_{layer}.png"
    legend_sheet.save(legend_path)
    print(f"[{layer}] wrote legend spritesheet: {legend_path} ({legend_sheet.size})")

    # --- Step 4: JSON tilemap ---
    meta = {
        "source_layer": layer,
        "native_tile_size": SMALL,
        "tile_size": TILE,
        "scale": SCALE,
        "tilemap_cols": tcols,
        "tilemap_rows": trows,
        "legend_cols": LEGEND_COLS,
        "legend_count": legend_count,
        "tilemap": [
            [legend_idx[r * tcols + c] for c in range(tcols)] for r in range(trows)
        ],
    }
    json_path = BUILD / f"newski_legend_{layer}.json"
    json_path.write_text(json.dumps(meta, indent=2))
    print(f"[{layer}] wrote JSON tilemap: {json_path}")

    # --- Step 5: render the layer at 64px from the JSON ---
    render = Image.new("RGBA", (tcols * TILE, trows * TILE), (0, 0, 0, 0))
    for r in range(trows):
        for c in range(tcols):
            li = legend_idx[r * tcols + c]
            lt = legend_tiles[li].resize((TILE, TILE), Image.NEAREST)
            render.paste(lt, (c * TILE, r * TILE))
    render_path = BUILD / f"newski_{layer}_64.png"
    render.save(render_path)
    print(f"[{layer}] wrote render: {render_path} ({render.size})")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/newski_legend_pipeline.py <layer_name>", file=sys.stderr)
        sys.exit(2)
    run(sys.argv[1])
