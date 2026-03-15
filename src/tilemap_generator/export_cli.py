"""CLI for exporting tile indices from tilemap layers to JSON and CSV."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .export_tilemap import run_export


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export tile indices from tilemap layers to JSON and CSV.",
    )
    parser.add_argument(
        "input",
        help="Input tilemap file (Tiled JSON .tiled.json or similar).",
    )
    parser.add_argument(
        "-o",
        "--out",
        default=None,
        help="Output path prefix. Default: <input_stem>_export",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=True,
        help="Export JSON (default: on).",
    )
    parser.add_argument(
        "--no-json",
        action="store_false",
        dest="json",
        help="Skip JSON export.",
    )
    parser.add_argument(
        "--csv",
        action="store_true",
        default=True,
        help="Export CSV per layer (default: on).",
    )
    parser.add_argument(
        "--no-csv",
        action="store_false",
        dest="csv",
        help="Skip CSV export.",
    )
    parser.add_argument(
        "--csv-single",
        action="store_true",
        help="Export only first layer to a single CSV (no per-layer files).",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    out_prefix = Path(args.out) if args.out else input_path.with_name(f"{input_path.stem}_export")

    try:
        written = run_export(
            input_path,
            out_prefix,
            export_json_flag=args.json,
            export_csv_flag=args.csv,
            csv_single=args.csv_single,
        )
        for p in written:
            print(f"Wrote {p}")
    except (FileNotFoundError, ValueError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
