#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    src_path = repo_root / "src"
    sys.path.insert(0, str(src_path))

    from tilemap_generator.aseprite_cli import main as aseprite_main

    aseprite_main()


if __name__ == "__main__":
    main()

