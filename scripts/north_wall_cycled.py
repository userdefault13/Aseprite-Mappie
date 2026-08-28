#!/usr/bin/env python3
"""
North Wall Cycled - Create continuous north wall from newski connector pieces.

Combines: HorizontalmidTowersNorth{small,large} + northsouthconnector + northGate
Outputs: build/citadel_north_wall.png (tileable horizontal strip with gate in center)
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Error: Pillow required. Install with: pip install Pillow", file=sys.stderr)
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = PROJECT_ROOT / "build"


def create_north_wall() -> None:
    """Create north wall with gate in center, towers and connectors on sides."""
    
    # Load components
    try:
        small = Image.open(BUILD_DIR / "newski_HorizontalmidTowersNorthsmall.png")
        large = Image.open(BUILD_DIR / "newski_HorizontalmidTowersNorthlarge.png")
        connector = Image.open(BUILD_DIR / "newski_northsouthconnector.png")
        gate = Image.open(BUILD_DIR / "newski_northGate.png")
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Run scripts/newski_legend_pipeline.py first to export layers.", file=sys.stderr)
        sys.exit(1)

    # Get dimensions
    tile_w = connector.width
    tile_h = connector.height

    # Create pattern: connector-small-connector-large-connector-GATE-connector-large-connector-small-connector
    # This creates a symmetrical wall with gate in center
    pattern = [
        connector, small, connector, large, connector,  # Left side
        gate,  # Center gate
        connector, large, connector, small, connector,  # Right side (mirrored)
    ]
    
    # Create composite horizontal strip
    total_width = tile_w * len(pattern)
    composite = Image.new("RGBA", (total_width, tile_h), (0, 0, 0, 0))
    
    x_offset = 0
    for piece in pattern:
        composite.paste(piece, (x_offset, 0), piece if piece.mode == "RGBA" else None)
        x_offset += tile_w

    out_path = BUILD_DIR / "citadel_north_wall.png"
    composite.save(out_path)
    print(f"✓ Created {out_path.name} ({composite.width}x{composite.height}px)")


if __name__ == "__main__":
    create_north_wall()
