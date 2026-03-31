from __future__ import annotations

import argparse
import json
from pathlib import Path

from .tree_logic import DEFAULT_TREE_CONFIG, apply_hill_interior_grass_tile_rows, to_tile_rows_with_trees


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate CSV and Tiled JSON tilemaps from an ASCII layout."
    )
    parser.add_argument(
        "--ascii",
        dest="ascii_path",
        required=True,
        help="Path to ASCII map file (one character per tile).",
    )
    parser.add_argument(
        "--legend",
        dest="legend_path",
        required=True,
        help="Path to legend JSON mapping characters to tile IDs.",
    )
    parser.add_argument(
        "--tile-width",
        type=int,
        required=True,
        help="Tile width in pixels.",
    )
    parser.add_argument(
        "--tile-height",
        type=int,
        required=True,
        help="Tile height in pixels.",
    )
    parser.add_argument(
        "--out-prefix",
        required=True,
        help="Output prefix path (writes <prefix>.csv and <prefix>.tiled.json).",
    )
    parser.add_argument(
        "--layer-name",
        default="Ground",
        help="Tile layer name in Tiled JSON output.",
    )
    parser.add_argument(
        "--tileset-source",
        default="",
        help='Optional TSX path to reference in Tiled JSON "tilesets".',
    )
    parser.add_argument(
        "--aseprite-data",
        default="",
        help=(
            "Optional Aseprite JSON data export for legend validation "
            "(checks max tile ID against exported tileset capacity)."
        ),
    )
    parser.add_argument(
        "--tree-logic",
        action="store_true",
        help="Apply GotchiCraft-style tree tile resolution (vertical runs, single variants).",
    )
    parser.add_argument(
        "--tree-config",
        default="",
        help="Path to tree config JSON (overrides defaults when --tree-logic).",
    )
    parser.add_argument(
        "--tree-seed",
        type=int,
        default=42,
        help="RNG seed for tree tile variation (used with --tree-logic).",
    )
    return parser


def load_ascii_map(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"ASCII map file not found: {path}")

    lines = [line.rstrip("\n") for line in path.read_text(encoding="utf-8").splitlines()]
    if not lines:
        raise ValueError("ASCII map file is empty.")

    width = len(lines[0])
    if width == 0:
        raise ValueError("ASCII map first line is empty.")

    for index, line in enumerate(lines, start=1):
        if len(line) != width:
            raise ValueError(
                f"ASCII map line {index} width {len(line)} does not match expected width {width}."
            )
    return lines


def load_legend(path: Path) -> dict[str, int]:
    if not path.exists():
        raise FileNotFoundError(f"Legend file not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Legend JSON must be an object mapping characters to tile IDs.")

    legend: dict[str, int] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or len(key) != 1:
            raise ValueError(f"Legend key must be exactly one character. Got: {key!r}")
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"Legend value for {key!r} must be a non-negative integer.")
        legend[key] = value
    return legend


def load_aseprite_tile_capacity(
    path: Path, tile_width: int, tile_height: int
) -> int:
    if not path.exists():
        raise FileNotFoundError(f"Aseprite data file not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(raw, dict):
        meta = raw.get("meta")
        if isinstance(meta, dict):
            size = meta.get("size")
            if (
                isinstance(size, dict)
                and isinstance(size.get("w"), int)
                and isinstance(size.get("h"), int)
            ):
                sheet_w = int(size["w"])
                sheet_h = int(size["h"])
                if sheet_w <= 0 or sheet_h <= 0:
                    raise ValueError("Aseprite sheet size must be positive.")
                if sheet_w % tile_width != 0 or sheet_h % tile_height != 0:
                    raise ValueError(
                        f"Aseprite sheet size {sheet_w}x{sheet_h} is not divisible by "
                        f"tile size {tile_width}x{tile_height}."
                    )
                return (sheet_w // tile_width) * (sheet_h // tile_height)

    frames: object
    if isinstance(raw, dict):
        frames = raw.get("frames")
    elif isinstance(raw, list):
        frames = raw
    else:
        raise ValueError("Aseprite data must be a JSON object or JSON array.")

    if isinstance(frames, list):
        if not frames:
            raise ValueError("Aseprite data has no frames.")
        return len(frames)
    if isinstance(frames, dict):
        if not frames:
            raise ValueError("Aseprite data has no frames.")
        return len(frames)

    raise ValueError(
        "Could not read tileset capacity from Aseprite data. "
        "Expected either meta.size or a frame list."
    )


def validate_legend_against_tileset(
    legend: dict[str, int],
    tile_capacity: int,
    tree_config: dict | None = None,
) -> None:
    max_tile_id = max(legend.values())
    if tree_config:
        tree_ids = [
            tree_config.get("single", 33),
            tree_config.get("vertical_2_top", 19),
            tree_config.get("vertical_2_bottom", 26),
            tree_config.get("vertical_3_top", 13),
            tree_config.get("vertical_3_mid", 20),
            tree_config.get("vertical_3_bottom", 27),
        ]
        tree_ids.extend(tree_config.get("single_alts", []))
        max_tile_id = max(max_tile_id, *tree_ids)
    if max_tile_id > tile_capacity:
        raise ValueError(
            f"Legend/tree config requires tile ID {max_tile_id}, but Aseprite export only has "
            f"{tile_capacity} tile slot(s). Add more tiles or update legend IDs."
        )


def to_tile_rows(lines: list[str], legend: dict[str, int]) -> list[list[int]]:
    """Convert ASCII to tile IDs via legend. Map-building rules are enforced in map_gen_cli."""
    rows: list[list[int]] = []
    for y, line in enumerate(lines):
        row: list[int] = []
        for x, char in enumerate(line):
            if char not in legend:
                raise ValueError(
                    f"Character {char!r} at x={x}, y={y} not found in legend."
                )
            row.append(legend[char])
        rows.append(row)
    return apply_hill_interior_grass_tile_rows(rows, lines, legend)


def write_csv(path: Path, rows: list[list[int]]) -> None:
    csv_content = "\n".join(",".join(str(tile_id) for tile_id in row) for row in rows) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(csv_content, encoding="utf-8")


def build_tiled_json(
    rows: list[list[int]],
    tile_width: int,
    tile_height: int,
    layer_name: str,
    tileset_source: str,
) -> dict:
    height = len(rows)
    width = len(rows[0])
    data = [tile_id for row in rows for tile_id in row]

    map_json = {
        "compressionlevel": -1,
        "height": height,
        "infinite": False,
        "layers": [
            {
                "data": data,
                "height": height,
                "id": 1,
                "name": layer_name,
                "opacity": 1,
                "type": "tilelayer",
                "visible": True,
                "width": width,
                "x": 0,
                "y": 0,
            }
        ],
        "nextlayerid": 2,
        "nextobjectid": 1,
        "orientation": "orthogonal",
        "renderorder": "right-down",
        "tiledversion": "1.11.0",
        "tileheight": tile_height,
        "tilewidth": tile_width,
        "type": "map",
        "version": "1.10",
        "width": width,
    }

    if tileset_source:
        map_json["tilesets"] = [{"firstgid": 1, "source": tileset_source}]
    else:
        map_json["tilesets"] = []

    return map_json


def write_tiled_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run_from_args(args: argparse.Namespace) -> None:
    if args.tile_width <= 0 or args.tile_height <= 0:
        raise ValueError("--tile-width and --tile-height must be positive integers.")

    ascii_path = Path(args.ascii_path)
    legend_path = Path(args.legend_path)
    out_prefix = Path(args.out_prefix)

    lines = load_ascii_map(ascii_path)
    legend = load_legend(legend_path)

    use_tree_logic = args.tree_logic or bool(args.tree_config)
    tree_config: dict | None = None
    if use_tree_logic:
        if args.tree_config:
            tree_config_path = Path(args.tree_config)
            if not tree_config_path.exists():
                raise FileNotFoundError(f"Tree config file not found: {tree_config_path}")
            tree_config = {
                **DEFAULT_TREE_CONFIG,
                **json.loads(tree_config_path.read_text(encoding="utf-8")),
            }
        else:
            tree_config = DEFAULT_TREE_CONFIG.copy()

    if args.aseprite_data:
        tile_capacity = load_aseprite_tile_capacity(
            Path(args.aseprite_data), args.tile_width, args.tile_height
        )
        validate_legend_against_tileset(legend, tile_capacity, tree_config)

    if use_tree_logic:
        rows = to_tile_rows_with_trees(
            lines,
            legend,
            tree_chars={"T", "F"},
            tree_config=tree_config,
            seed=args.tree_seed,
        )
    else:
        rows = to_tile_rows(lines, legend)

    csv_path = out_prefix.with_suffix(".csv")
    tiled_path = out_prefix.with_suffix(".tiled.json")

    write_csv(csv_path, rows)
    tiled_payload = build_tiled_json(
        rows=rows,
        tile_width=args.tile_width,
        tile_height=args.tile_height,
        layer_name=args.layer_name,
        tileset_source=args.tileset_source,
    )
    write_tiled_json(tiled_path, tiled_payload)

    print(f"Wrote {csv_path}")
    print(f"Wrote {tiled_path}")


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    run_from_args(args)


if __name__ == "__main__":
    main()
