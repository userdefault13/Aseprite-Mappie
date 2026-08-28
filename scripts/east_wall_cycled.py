#!/usr/bin/env python3
"""
East Wall Cycled - Create continuous east wall from newski connector pieces.

Combines: rightmidtower{small,med,large} + westeastconnector
Outputs: build/citadel_east_wall.png (tileable horizontal strip)
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


def create_east_wall() -> None:
    """Create east wall by cycling tower sizes with connectors."""
    
    # Load components
    try:
        small = Image.open(BUILD_DIR / "newski_rightmidtowersmall.png")
        med = Image.open(BUILD_DIR / "newski_rightmidtowermed.png")
        large = Image.open(BUILD_DIR / "newski_rightmidtowerlarge.png")
        connector = Image.open(BUILD_DIR / "newski_westeastconnector.png")
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Run scripts/newski_legend_pipeline.py first to export layers.", file=sys.stderr)
        sys.exit(1)

    # Get dimensions
    tile_w = connector.width
    tile_h = connector.height

    # Create pattern: small-connector-med-connector-large-connector (repeating)
    pattern = [small, connector, med, connector, large, connector]
    
    # Create composite horizontal strip (3 towers + 3 connectors = 6 tiles)
    total_width = tile_w * len(pattern)
    composite = Image.new("RGBA", (total_width, tile_h), (0, 0, 0, 0))
    
    x_offset = 0
    for piece in pattern:
        composite.paste(piece, (x_offset, 0), piece if piece.mode == "RGBA" else None)
        x_offset += tile_w

    out_path = BUILD_DIR / "citadel_east_wall.png"
    composite.save(out_path)
    print(f"✓ Created {out_path.name} ({composite.width}x{composite.height}px)")


if __name__ == "__main__":
    create_east_wall()
