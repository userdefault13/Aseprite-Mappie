#!/usr/bin/env python3
"""Export tile indices from tilemap layers to JSON and CSV.

Reads Tiled JSON (.tiled.json) or similar tilemap files and exports:
- JSON: Structured per-layer format, easy to parse in games
- CSV: Simple grid of numbers per layer, good for Unreal, custom engines, etc.

Example:
  python scripts/export_tilemap.py build/sample_room.tiled.json -o build/exported
  # Writes build/exported.json and build/exported_<layer>.csv per layer
"""
from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "src"))

    from tilemap_generator.export_cli import main as cli_main

    cli_main()


if __name__ == "__main__":
    main()
