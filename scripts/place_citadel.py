#!/usr/bin/env python3
"""
Place Citadel structures in ASCII maps.

Adds a rectangular Citadel fortress with:
- Four corner towers (O)
- North/South/East/West walls (W)
- Optional gates in walls

Usage:
  python3 scripts/place_citadel.py --ascii maps/mymap.txt --out maps/mymap_citadel.txt --x 50 --y 50 --width 20 --height 16
"""
from __future__ import annotations

import argparse
from pathlib import Path


def place_citadel(
    ascii_lines: list[str],
    cx: int,
    cy: int,
    width: int,
    height: int,
    gate_north: bool = True,
    gate_south: bool = False,
) -> list[str]:
    """
    Place Citadel structure on ASCII map.
    
    Args:
        ascii_lines: Map rows
        cx, cy: Top-left corner of Citadel
        width, height: Citadel dimensions (must be >= 4x4 for corners)
        gate_north, gate_south: Add gates in north/south walls
        
    Returns:
        Modified map with Citadel placed
    """
    grid = [list(line) for line in ascii_lines]
    map_h = len(grid)
    map_w = len(grid[0]) if grid else 0
    
    if width < 4 or height < 4:
        raise ValueError("Citadel must be at least 4x4 (for 4 corners)")
    
    # Place corners (O = tower)
    corners = [
        (cx, cy),  # Top-left
        (cx + width - 1, cy),  # Top-right
        (cx, cy + height - 1),  # Bottom-left
        (cx + width - 1, cy + height - 1),  # Bottom-right
    ]
    
    for x, y in corners:
        if 0 <= y < map_h and 0 <= x < map_w:
            grid[y][x] = 'O'
    
    # Place north wall (W = wall segment)
    gate_x = cx + width // 2  # Gate in center
    for x in range(cx + 1, cx + width - 1):
        if 0 <= cy < map_h and 0 <= x < map_w:
            if gate_north and x == gate_x:
                grid[cy][x] = 'G'  # Gate is grass (or could be special char)
            else:
                grid[cy][x] = 'W'
    
    # Place south wall
    for x in range(cx + 1, cx + width - 1):
        y = cy + height - 1
        if 0 <= y < map_h and 0 <= x < map_w:
            if gate_south and x == gate_x:
                grid[y][x] = 'G'
            else:
                grid[y][x] = 'W'
    
    # Place west wall
    for y in range(cy + 1, cy + height - 1):
        if 0 <= y < map_h and 0 <= cx < map_w:
            grid[y][cx] = 'W'
    
    # Place east wall
    for y in range(cy + 1, cy + height - 1):
        x = cx + width - 1
        if 0 <= y < map_h and 0 <= x < map_w:
            grid[y][x] = 'W'
    
    return [''.join(row) for row in grid]


def main() -> None:
    parser = argparse.ArgumentParser(description="Place Citadel in ASCII map")
    parser.add_argument("--ascii", type=Path, required=True, help="Input ASCII map")
    parser.add_argument("--out", type=Path, required=True, help="Output ASCII map with Citadel")
    parser.add_argument("--x", type=int, required=True, help="Citadel top-left X coordinate")
    parser.add_argument("--y", type=int, required=True, help="Citadel top-left Y coordinate")
    parser.add_argument("--width", type=int, default=20, help="Citadel width (default: 20)")
    parser.add_argument("--height", type=int, default=16, help="Citadel height (default: 16)")
    parser.add_argument("--gate-north", action="store_true", default=True, help="Add north gate")
    parser.add_argument("--gate-south", action="store_true", help="Add south gate")
    args = parser.parse_args()
    
    # Load map
    with open(args.ascii, 'r') as f:
        lines = [line.rstrip('\n') for line in f]
    
    # Place Citadel
    result = place_citadel(
        lines,
        args.x, args.y,
        args.width, args.height,
        args.gate_north, args.gate_south,
    )
    
    # Write output
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, 'w') as f:
        for line in result:
            f.write(line + '\n')
    
    print(f"✓ Placed {args.width}x{args.height} Citadel at ({args.x},{args.y})")
    print(f"✓ Wrote {args.out}")


if __name__ == "__main__":
    main()
