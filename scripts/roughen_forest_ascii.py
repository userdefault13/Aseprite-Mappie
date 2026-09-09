#!/usr/bin/env python3
"""Post-process an ASCII map to roughen T/F forest edges.

Example:
  PYTHONPATH=src python scripts/roughen_forest_ascii.py maps/wc2_hillsbrad/hillsbrad.txt \\
      --out maps/wc2_hillsbrad/hillsbrad.txt --seed 11
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tilemap_generator.forest_edge import roughen_forest_edges


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("ascii_path", type=Path)
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--iterations", type=int, default=3)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--erode", type=float, default=0.55)
    p.add_argument("--grow", type=float, default=0.35)
    p.add_argument("--grass", default=".", help="Grass char to erode into (default .)")
    args = p.parse_args()

    lines = [ln.rstrip("\n") for ln in args.ascii_path.read_text().splitlines() if ln.strip() != ""]
    grid = [list(row) for row in lines]
    stats = roughen_forest_edges(
        grid,
        iterations=args.iterations,
        seed=args.seed,
        erode_p=args.erode,
        grow_p=args.grow,
        forest_chars={"T", "F"},
        grow_onto={args.grass, "G", "."},
        grass_char=args.grass,
        default_forest_char="T" if any("T" in row for row in lines) else "F",
    )
    out = args.out or args.ascii_path
    out.write_text("\n".join("".join(row) for row in grid) + "\n")
    print(f"wrote {out} eroded={stats['eroded']} grown={stats['grown']} nibbled={stats['nibbled']}")


if __name__ == "__main__":
    main()
