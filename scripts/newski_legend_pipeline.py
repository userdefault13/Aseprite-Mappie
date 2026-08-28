#!/usr/bin/env python3
"""
Newski Citadel Pipeline - Export layers from newski.aseprite and upscale 8px -> 64px.

Layers in newski.aseprite:
- Corner towers: topleftcorner, toprightcorner, bottomleftcorner, bottomrightcorner
- Mid towers: leftmidtower{small,med,large}, rightmidtower{small,med,large}
- Horizontal towers: HorizontalmidTowersNorth{small,large}, HorizontalmidTowersSouth{small,large}
- Gates: northGate, southGate
- Connectors: northsouthconnector, westeastconnector

Exports to build/ as 64px tiles for Mappie painting.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Default newski source (user's local path)
DEFAULT_NEWSKI_SOURCE = Path("/Users/juliuswong/Downloads/newski.aseprite")

# All layers to export from newski.aseprite
NEWSKI_LAYERS = [
    "topleftcorner",
    "toprightcorner", 
    "bottomleftcorner",
    "bottomrightcorner",
    "leftmidtowersmall",
    "leftmidtowermed",
    "leftmidtowerlarge",
    "rightmidtowersmall",
    "rightmidtowermed",
    "rightmidtowerlarge",
    "HorizontalmidTowersNorthsmall",
    "HorizontalmidTowersNorthlarge",
    "HorizontalmidTowersSouthsmall",
    "HorizontalmidTowersSouthlarge",
    "northGate",
    "southGate",
    "northsouthconnector",
    "westeastconnector",
]

def find_aseprite() -> Path | None:
    """Find Aseprite binary."""
    candidates = [
        Path("/Applications/Aseprite.app/Contents/MacOS/aseprite"),
        Path("/usr/local/bin/aseprite"),
        Path("/usr/bin/aseprite"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    # Try PATH
    import shutil
    ase = shutil.which("aseprite")
    return Path(ase) if ase else None


def export_layer(
    aseprite_bin: Path,
    source: Path,
    layer_name: str,
    out_path: Path,
    scale: int = 8,
) -> None:
    """Export a single layer from newski.aseprite at 8x scale (8px -> 64px)."""
    cmd = [
        str(aseprite_bin),
        "-b",
        str(source),
        "--layer", layer_name,
        "--scale", str(scale),
        "--save-as", str(out_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"✓ Exported {layer_name} -> {out_path.name} (8x scale)")
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to export {layer_name}: {e.stderr.decode()}", file=sys.stderr)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Export newski.aseprite layers to build/")
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_NEWSKI_SOURCE,
        help=f"Path to newski.aseprite (default: {DEFAULT_NEWSKI_SOURCE})",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=PROJECT_ROOT / "build",
        help="Output directory (default: build/)",
    )
    parser.add_argument(
        "--scale",
        type=int,
        default=8,
        help="Scale factor for 8px -> 64px conversion (default: 8)",
    )
    parser.add_argument(
        "--aseprite-bin",
        type=Path,
        help="Path to Aseprite binary (auto-detected if not provided)",
    )
    args = parser.parse_args()

    # Find Aseprite
    aseprite_bin = args.aseprite_bin or find_aseprite()
    if not aseprite_bin:
        print("Error: Aseprite binary not found. Use --aseprite-bin to specify.", file=sys.stderr)
        sys.exit(1)

    # Check source
    if not args.source.exists():
        print(f"Error: newski.aseprite not found at {args.source}", file=sys.stderr)
        print("Use --source to specify the correct path.", file=sys.stderr)
        sys.exit(1)

    # Create output directory
    args.out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Exporting {len(NEWSKI_LAYERS)} layers from {args.source.name}...")
    print(f"Scale: {args.scale}x (8px -> {8 * args.scale}px)")
    print()

    # Export each layer
    for layer_name in NEWSKI_LAYERS:
        out_path = args.out_dir / f"newski_{layer_name}.png"
        export_layer(aseprite_bin, args.source, layer_name, out_path, args.scale)

    # Also export a flattened version for reference
    flattened_path = args.out_dir / "newski_flattened.png"
    cmd = [
        str(aseprite_bin),
        "-b",
        str(args.source),
        "--scale", str(args.scale),
        "--save-as", str(flattened_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"✓ Exported flattened -> {flattened_path.name}")
    except subprocess.CalledProcessError:
        pass  # Non-critical

    print()
    print(f"✓ Exported {len(NEWSKI_LAYERS)} layers to {args.out_dir}/")
    print()
    print("Next steps:")
    print("  1. Run west_wall_cycled.py, north_wall_cycled.py, east_wall_cycled.py")
    print("  2. Generate world maps with Citadel structures")


if __name__ == "__main__":
    main()
