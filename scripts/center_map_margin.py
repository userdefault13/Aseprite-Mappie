"""Shift all real map content by (+ROW_OFF, +COL_OFF) inside the existing grid so
that empty margin chunks appear on the top/left (and extra on bottom/right).

Current state (after expand_map_boundaries.py to 148-wide):
  - real content at rows 0..127, cols 0..127
  - empty chunks at rows 128..147 or cols 128..147 (right/bottom margin only)

After this shift (+10,+10):
  - real content at rows 10..137, cols 10..137
  - empty margin everywhere else (top rows 0..9, left cols 0..9, bottom 138..147, right 138..147)

Steps:
  1. Delete all empty chunk files (row>=128 or col>=128).
  2. Two-pass rename real files (r,c) -> (r+ROW_OFF, c+COL_OFF).
  3. Create empty margin chunks for all positions outside the real region.

Operates IN PLACE. Backs up master.json.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

CHUNKS = Path("/Users/juliuswong/Dev/gotchiverse-2d/public/maps/chunks")
ROW_OFF = 10
COL_OFF = 10


def main():
    master_path = CHUNKS / "master.json"
    master = json.loads(master_path.read_text())
    W = int(master["chunksHorizontal"])
    H = int(master["chunksVertical"])
    assert W == H, "non-square grid"
    assert W == 148, f"expected 148-wide, got {W}"

    # 1. delete empty chunk files (row>=128 or col>=128)
    deleted = 0
    for p in CHUNKS.glob("chunk*.json"):
        stem = p.stem
        if not (stem.startswith("chunk") and stem[5:].isdigit()):
            continue
        cid = int(stem[5:])
        r, c = cid // W, cid % W
        if r >= 128 or c >= 128:
            p.unlink()
            deleted += 1
    print(f"deleted {deleted} empty edge chunk files")

    # gather remaining (real) chunk ids
    real_ids = []
    for p in CHUNKS.glob("chunk*.json"):
        stem = p.stem
        if stem.startswith("chunk") and stem[5:].isdigit():
            real_ids.append(int(stem[5:]))
    real_ids.sort()
    print(f"real chunk files remaining: {len(real_ids)} (ids {real_ids[0]}..{real_ids[-1]})")

    def new_id(cid: int) -> int:
        r, c = cid // W, cid % W
        return (r + ROW_OFF) * W + (c + COL_OFF)

    # sanity: new ids unique and within grid
    new_ids = [new_id(i) for i in real_ids]
    assert len(set(new_ids)) == len(new_ids), "new ids collide"
    assert max(new_ids) < W * H, f"new id {max(new_ids)} out of range"

    # 2. two-pass rename
    shutil.copy2(master_path, CHUNKS / "master.json.bak2")
    print("backed up master.json -> master.json.bak2")

    print("Pass 1: real -> .tmp")
    for cid in real_ids:
        (CHUNKS / f"chunk{cid}.json").rename(CHUNKS / f"chunk{cid}.tmp")
    print(f"  renamed {len(real_ids)} to .tmp")

    print("Pass 2: .tmp -> shifted ids")
    for cid in real_ids:
        (CHUNKS / f"chunk{cid}.tmp").rename(CHUNKS / f"chunk{new_id(cid)}.json")
    print(f"  renamed {len(real_ids)} to final shifted ids")

    # 3. create empty margin chunks for positions outside real region
    # real region now: rows 10..137, cols 10..137
    template = json.loads((CHUNKS / f"chunk{(ROW_OFF)*W+COL_OFF}.json").read_text())
    for layer in template.get("layers", []):
        if isinstance(layer, dict) and "data" in layer:
            w = layer.get("width", master.get("chunkWidth", 66))
            h = layer.get("height", master.get("chunkHeight", 66))
            layer["data"] = [0] * (w * h)

    margin_ids = []
    for r in range(W):
        for c in range(W):
            if not (ROW_OFF <= r < ROW_OFF + 128 and COL_OFF <= c < COL_OFF + 128):
                margin_ids.append(r * W + c)
    print(f"creating {len(margin_ids)} empty margin chunk files")
    for nid in margin_ids:
        p = CHUNKS / f"chunk{nid}.json"
        if not p.exists():
            p.write_text(json.dumps(template))

    # master.json unchanged (still 148x148, 21904)
    leftover = list(CHUNKS.glob("chunk*.tmp"))
    if leftover:
        for p in leftover:
            p.unlink()
    print(f"DONE. real at rows {ROW_OFF}..{ROW_OFF+127}, cols {COL_OFF}..{COL_OFF+127}")
    print(f"total chunk files now: {len(list(CHUNKS.glob('chunk*.json')))}")


if __name__ == "__main__":
    main()
