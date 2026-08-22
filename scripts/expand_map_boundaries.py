"""Expand (or further expand) the gotchiverse map by adding N chunks to each side.

Re-indexes all chunk files from the CURRENT grid width to a NEW grid width:
  cur_id = row * CUR_W + col   ->   new_id = row * NEW_W + col
  where row = cur_id // CUR_W, col = cur_id % CUR_W.

Two-pass rename to avoid collisions:
  Pass 1: chunkN.json -> chunkN.tmp
  Pass 2: chunkN.tmp -> chunk{new_id}.json

Then:
  - Update master.json: chunksHorizontal/Vertical CUR_W -> NEW_W, chunksTotal -> NEW_W*NEW_W.
  - Create new edge chunk files (the added rows/cols) using an existing chunk as a template
      (valid JSON structure, empty data).

Operates IN PLACE on the maps chunks dir. Backs up master.json first.

Usage:
  python scripts/expand_map_boundaries.py <new_width> [--apply]
  Without --apply it prints a summary only (dry run).

Examples:
  python scripts/expand_map_boundaries.py 148          # dry run to 148-wide
  python scripts/expand_map_boundaries.py 148 --apply   # do it
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

CHUNKS = Path("/Users/juliuswong/Dev/gotchiverse-2d/public/maps/chunks")


def run(new_w: int, apply: bool) -> None:
    master_path = CHUNKS / "master.json"
    master = json.loads(master_path.read_text())
    cur_w = int(master["chunksHorizontal"])
    cur_h = int(master["chunksVertical"])
    if cur_w != cur_h:
        raise ValueError(f"non-square grid not supported: {cur_w}x{cur_h}")
    if new_w <= cur_w:
        raise ValueError(f"new_width {new_w} must be > current {cur_w}")

    # gather existing chunk files
    chunk_files = [p for p in CHUNKS.glob("chunk*.json")
                    if p.name.startswith("chunk") and p.name.endswith(".json")
                    and p.stem[5:].isdigit()]
    chunk_ids = sorted(int(p.stem[5:]) for p in chunk_files)
    print(f"current grid: {cur_w}x{cur_h}, chunksTotal={master.get('chunksTotal')}")
    print(f"found {len(chunk_ids)} chunk files (ids {chunk_ids[0]}..{chunk_ids[-1]})")
    print(f"target grid: {new_w}x{new_w} (chunksTotal would be {new_w*new_w})")

    def new_id(cur: int) -> int:
        return (cur // cur_w) * new_w + (cur % cur_w)

    pairs = [(old, new_id(old)) for old in chunk_ids]
    new_ids = [n for _, n in pairs]
    if len(set(new_ids)) != len(new_ids):
        raise AssertionError("new ids collide")
    print(f"new id range: {min(new_ids)}..{max(new_ids)}")

    if not apply:
        print("DRY RUN — pass --apply to actually rename and update master.json")
        for old, new in pairs[:3] + pairs[-3:]:
            print(f"  chunk{old}.json -> chunk{new}.json  (row {old//cur_w} col {old%cur_w})")
        return

    # --- apply ---
    shutil.copy2(master_path, CHUNKS / "master.json.bak")
    print("backed up master.json -> master.json.bak")

    print("Pass 1: renaming to .tmp ...")
    for old in chunk_ids:
        (CHUNKS / f"chunk{old}.json").rename(CHUNKS / f"chunk{old}.tmp")
    print(f"  renamed {len(chunk_ids)} files to .tmp")

    print("Pass 2: renaming .tmp -> final ids ...")
    for old in chunk_ids:
        (CHUNKS / f"chunk{old}.tmp").rename(CHUNKS / f"chunk{new_id(old)}.json")
    print(f"  renamed {len(chunk_ids)} files to final ids")

    # template for new edge chunks (empty data)
    template = json.loads((CHUNKS / "chunk0.json").read_text())
    for layer in template.get("layers", []):
        if isinstance(layer, dict) and "data" in layer:
            w = layer.get("width", master.get("chunkWidth", 66))
            h = layer.get("height", master.get("chunkHeight", 66))
            layer["data"] = [0] * (w * h)

    # new edge ids: rows in [cur_h, new_w-1] across all new cols, and cols in [cur_w, new_w-1] for old rows
    new_edge_ids = []
    for r in range(cur_h, new_w):
        for c in range(new_w):
            new_edge_ids.append(r * new_w + c)
    for c in range(cur_w, new_w):
        for r in range(cur_h):
            new_edge_ids.append(r * new_w + c)
    print(f"creating {len(new_edge_ids)} new edge chunk files ...")
    for nid in new_edge_ids:
        p = CHUNKS / f"chunk{nid}.json"
        if not p.exists():
            p.write_text(json.dumps(template))

    master["chunksHorizontal"] = new_w
    master["chunksVertical"] = new_w
    master["chunksTotal"] = new_w * new_w
    master_path.write_text(json.dumps(master, indent=2))
    print(f"updated master.json: {new_w}x{new_w} chunks, chunkTotal={new_w*new_w}")

    leftover = list(CHUNKS.glob("chunk*.tmp"))
    if leftover:
        print(f"WARNING: {len(leftover)} .tmp files remain — removing")
        for p in leftover:
            p.unlink()
    print("DONE")


if __name__ == "__main__":
    args = sys.argv[1:]
    apply = "--apply" in args
    positional = [a for a in args if not a.startswith("-")]
    if not positional:
        print("Usage: python scripts/expand_map_boundaries.py <new_width> [--apply]", file=sys.stderr)
        sys.exit(2)
    run(int(positional[0]), apply)
