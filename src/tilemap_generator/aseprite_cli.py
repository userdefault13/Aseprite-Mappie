from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from tilemap_generator.tree_logic import to_tile_rows_with_trees


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAC_ASEPRITE_BIN = Path("/Applications/Aseprite.app/Contents/MacOS/aseprite")
SOLID_TILE_COLORS: dict[str, tuple[int, int, int, int]] = {
    "G": (104, 178, 76, 255),
    ".": (104, 178, 76, 255),
    "~": (72, 132, 224, 255),
    "T": (46, 108, 54, 255),
    "F": (30, 78, 40, 255),
    "P": (181, 152, 102, 255),
    "S": (250, 228, 92, 255),
    "J": (255, 161, 77, 255),
    "M": (125, 126, 134, 255),
    "H": (214, 123, 73, 255),
    "C": (194, 76, 76, 255),
    "D": (240, 95, 95, 255),
    "N": (86, 208, 220, 255),
}
CHAR_PRIORITY = list(SOLID_TILE_COLORS.keys())


def resolve_aseprite_bin(explicit: str | None) -> Path:
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)

    env_bin = os.getenv("ASEPRITE_BIN")
    if env_bin:
        candidates.append(env_bin)

    in_path = shutil.which("aseprite")
    if in_path:
        candidates.append(in_path)

    if MAC_ASEPRITE_BIN.exists():
        candidates.append(str(MAC_ASEPRITE_BIN))

    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        path = Path(candidate).expanduser()
        if path.exists() and path.is_file():
            return path

    raise FileNotFoundError(
        "Aseprite binary not found. Set --aseprite-bin or ASEPRITE_BIN, "
        "or install the 'aseprite' CLI in PATH."
    )


def load_legend(path: Path) -> dict[str, int]:
    if not path.exists():
        raise FileNotFoundError(f"Legend file not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not raw:
        raise ValueError("Legend JSON must be a non-empty object")

    legend: dict[str, int] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or len(key) != 1:
            raise ValueError(f"Legend key must be one character. Got: {key!r}")
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"Legend value for {key!r} must be a non-negative integer.")
        legend[key] = value
    return legend


def run(cmd: list[str], env: dict[str, str] | None = None) -> None:
    subprocess.run(cmd, check=True, env=env)


def command_check(args: argparse.Namespace) -> None:
    aseprite_bin = resolve_aseprite_bin(args.aseprite_bin)
    print(f"Aseprite CLI found: {aseprite_bin}")


def command_init(args: argparse.Namespace) -> None:
    aseprite_bin = resolve_aseprite_bin(args.aseprite_bin)
    legend = load_legend(Path(args.legend))

    cols = args.cols
    if cols <= 0:
        raise ValueError("--cols must be > 0")

    max_tile_id = max(legend.values())
    required_tiles = max(1, max_tile_id)
    rows = args.rows if args.rows else math.ceil(required_tiles / cols)
    if rows <= 0:
        raise ValueError("--rows must be > 0")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lua_script = PROJECT_ROOT / "assets/lua/init_tileset.lua"
    if not lua_script.exists():
        raise FileNotFoundError(f"Missing Lua template: {lua_script}")

    env = os.environ.copy()
    env["TILE_W"] = str(args.tile_width)
    env["TILE_H"] = str(args.tile_height)
    env["COLS"] = str(cols)
    env["ROWS"] = str(rows)
    env["OUT"] = str(out_path)

    run([str(aseprite_bin), "-b", "--script", str(lua_script)], env=env)
    print(
        f"Initialized {out_path} with {cols}x{rows} tiles "
        f"({required_tiles} required by legend max tile ID {max_tile_id})."
    )


def _default_legend() -> dict[str, int]:
    return {
        "G": 1,
        ".": 1,
        "~": 2,
        "T": 3,
        "F": 4,
        "P": 5,
        "S": 6,
        "J": 7,
        "M": 8,
        "H": 9,
        "C": 10,
        "D": 11,
        "N": 12,
    }


def command_paint(args: argparse.Namespace) -> None:
    aseprite_bin = resolve_aseprite_bin(args.aseprite_bin)
    ascii_path = Path(args.ascii)
    if not ascii_path.exists():
        raise FileNotFoundError(f"ASCII map not found: {ascii_path}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    tile_size = args.tile_size
    if tile_size <= 0:
        raise ValueError("--tile-size must be > 0")

    lines = [ln.rstrip("\n\r") for ln in ascii_path.read_text(encoding="utf-8").splitlines()]
    if not lines:
        raise ValueError("ASCII map is empty")

    treeset_path = Path(args.treeset) if args.treeset else None

    if treeset_path:
        # GotchiCraft-style: Python/PIL composites PNGs, Lua loads them
        if not treeset_path.exists():
            for base in (PROJECT_ROOT / "examples", PROJECT_ROOT):
                candidate = base / treeset_path
                if candidate.exists():
                    treeset_path = candidate
                    break
            else:
                raise FileNotFoundError(
                    f"Treeset not found: {args.treeset} "
                    f"(tried cwd, examples/, project root)"
                )
        legend_path = Path(args.legend) if args.legend else ascii_path.with_suffix(".legend.json")
        legend = load_legend(legend_path) if legend_path.exists() else _default_legend()
        tile_rows = to_tile_rows_with_trees(
            lines, legend, tree_chars={"T", "F"}, seed=args.tree_seed
        )

        from tilemap_generator.paint_map_png import (
            export_treeset_to_png,
            paint_map_to_png,
        )

        grass_dir: Path | None = None
        grass_sheet_path: Path | None = None
        grass_path_resolved: Path | None = None
        if args.grass_dir:
            grass_path = Path(args.grass_dir)
            if not grass_path.exists():
                for base in (PROJECT_ROOT / "examples", PROJECT_ROOT):
                    candidate = base / grass_path
                    if candidate.exists():
                        grass_path = candidate
                        break
                else:
                    grass_path = None
            if grass_path and grass_path.exists():
                grass_path_resolved = grass_path

        water_path: Path | None = None
        water_aseprite_path: Path | None = None
        if args.water_tile:
            wp = Path(args.water_tile)
            if not wp.exists():
                for base in (PROJECT_ROOT / "examples", PROJECT_ROOT):
                    candidate = base / wp
                    if candidate.exists():
                        wp = candidate
                        break
                else:
                    wp = None
            if wp and wp.exists():
                if wp.suffix.lower() in (".aseprite", ".ase"):
                    water_aseprite_path = wp
                else:
                    water_path = wp

        dirt_path: Path | None = None
        dirt_aseprite_path: Path | None = None
        dirt_input = args.dirt_tile or "examples/dirt.aseprite"
        if dirt_input:
            dp = Path(dirt_input)
            if not dp.exists():
                for base in (PROJECT_ROOT / "examples", PROJECT_ROOT):
                    candidate = base / dp
                    if candidate.exists():
                        dp = candidate
                        break
                else:
                    dp = None
            if dp and dp.exists():
                if dp.suffix.lower() in (".aseprite", ".ase"):
                    dirt_aseprite_path = dp
                else:
                    dirt_path = dp

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            trees_sheet = tmp_path / "trees_sheet.png"
            water_png = tmp_path / "water.png"
            grass_png = tmp_path / "grass.png"
            dirt_png = tmp_path / "dirt.png"
            trees_png = tmp_path / "trees.png"

            # Resolve grass_dir vs grass_sheet_path
            if grass_path_resolved:
                if grass_path_resolved.is_dir():
                    grass_dir = grass_path_resolved
                elif grass_path_resolved.suffix.lower() in (".aseprite", ".ase"):
                    grass_sheet_path = tmp_path / "grass_sheet.png"
                    export_treeset_to_png(
                        grass_path_resolved, grass_sheet_path, aseprite_bin
                    )
                elif grass_path_resolved.suffix.lower() == ".png":
                    grass_sheet_path = grass_path_resolved

            # Auto-find Water.png near grass path (GotchiCraft layout)
            if water_path is None and water_aseprite_path is None and grass_path_resolved is not None:
                base = grass_path_resolved.parent
                if grass_path_resolved.is_file():
                    base = grass_path_resolved.parent
                for parent in (base, base.parent):
                    candidate = parent / "Water.png"
                    if candidate.exists():
                        water_path = candidate
                        break

            # Export water .aseprite to PNG (first frame for animations)
            if water_aseprite_path is not None:
                water_sheet = tmp_path / "water_sheet.png"
                export_treeset_to_png(water_aseprite_path, water_sheet, aseprite_bin)
                # Extract first frame from sheet (handles single frame or horizontal strip)
                try:
                    from PIL import Image
                    img = Image.open(water_sheet)
                    if img.mode != "RGBA":
                        img = img.convert("RGBA")
                    w, h = img.size
                    # First frame: square (h x h) for horizontal strip, or full if single
                    frame_size = min(w, h)
                    frame = img.crop((0, 0, frame_size, frame_size))
                    if frame_size != tile_size:
                        frame = frame.resize(
                            (tile_size, tile_size), Image.Resampling.NEAREST
                        )
                    water_tile_path = tmp_path / "water_tile.png"
                    frame.save(water_tile_path)
                    water_path = water_tile_path
                except Exception:
                    water_path = water_sheet  # fallback to full sheet

            # Export dirt .aseprite to PNG (full sheet for path autotiling)
            if dirt_aseprite_path is not None:
                dirt_sheet = tmp_path / "dirt_sheet.png"
                export_treeset_to_png(dirt_aseprite_path, dirt_sheet, aseprite_bin)
                dirt_path = dirt_sheet

            # Parse grass tile range (e.g. "19-30")
            grass_tile_range: tuple[int, int] | None = (19, 30)
            if args.grass_tile_range:
                parts = args.grass_tile_range.split("-")
                if len(parts) == 2:
                    try:
                        grass_tile_range = (int(parts[0]), int(parts[1]))
                    except ValueError:
                        pass

            export_treeset_to_png(treeset_path, trees_sheet, aseprite_bin)
            paint_map_to_png(
                ascii_lines=lines,
                legend=legend,
                tile_rows=tile_rows,
                tile_size=tile_size,
                trees_sheet_path=trees_sheet,
                water_out=water_png,
                grass_out=grass_png,
                dirt_out=dirt_png,
                trees_out=trees_png,
                grass_dir=grass_dir,
                grass_sheet_path=grass_sheet_path,
                grass_tile_range=grass_tile_range,
                water_path=water_path,
                dirt_path=dirt_path,
                seed=args.tree_seed,
            )

            lua_script = PROJECT_ROOT / "assets/lua/paint_from_png.lua"
            if not lua_script.exists():
                raise FileNotFoundError(f"Missing Lua script: {lua_script}")
            env = os.environ.copy()
            env["OUT"] = str(out_path.resolve())
            env["WATER_PNG"] = str(water_png)
            env["GRASS_PNG"] = str(grass_png)
            env["DIRT_PNG"] = str(dirt_png)
            env["TREES_PNG"] = str(trees_png)
            run([str(aseprite_bin), "-b", "--script", str(lua_script)], env=env)
    else:
        # No treeset: Lua paints solid colors only
        lua_script = PROJECT_ROOT / "assets/lua/paint_ascii_map.lua"
        if not lua_script.exists():
            raise FileNotFoundError(f"Missing Lua script: {lua_script}")
        env = os.environ.copy()
        env["MAP_ASCII_PATH"] = str(ascii_path.resolve())
        env["TILE_W"] = str(tile_size)
        env["TILE_H"] = str(tile_size)
        env["OUT"] = str(out_path.resolve())
        run([str(aseprite_bin), "-b", "--script", str(lua_script)], env=env)

    print(f"Painted {ascii_path} -> {out_path}")
    if args.open:
        run([str(aseprite_bin), str(out_path)])


def command_edit(args: argparse.Namespace) -> None:
    aseprite_bin = resolve_aseprite_bin(args.aseprite_bin)
    source = Path(args.source)
    if not source.exists():
        raise FileNotFoundError(f"Missing tileset file: {source}")
    run([str(aseprite_bin), str(source)])


def command_export(args: argparse.Namespace) -> None:
    aseprite_bin = resolve_aseprite_bin(args.aseprite_bin)
    source = Path(args.source)
    if not source.exists():
        raise FileNotFoundError(f"Missing tileset file: {source}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sheet = out_dir / f"{source.stem}.png"
    data = out_dir / f"{source.stem}.json"

    cmd = [
        str(aseprite_bin),
        "-b",
        str(source),
        "--sheet",
        str(sheet),
        "--data",
        str(data),
        "--sheet-type",
        args.sheet_type,
        "--format",
        args.data_format,
        "--list-tags",
        "--list-layers",
    ]
    run(cmd)
    print(f"Wrote {sheet}")
    print(f"Wrote {data}")


def fallback_color_for_id(tile_id: int) -> tuple[int, int, int, int]:
    seed = (tile_id * 1103515245 + 12345) & 0xFFFFFFFF
    r = 50 + (seed & 0x7F)
    g = 50 + ((seed >> 8) & 0x7F)
    b = 50 + ((seed >> 16) & 0x7F)
    return (r, g, b, 255)


def choose_char_for_tile_id(legend: dict[str, int]) -> dict[int, str]:
    priority: dict[str, int] = {char: idx for idx, char in enumerate(CHAR_PRIORITY)}
    by_id: dict[int, list[str]] = {}
    for char, tile_id in legend.items():
        if tile_id <= 0:
            continue
        by_id.setdefault(tile_id, []).append(char)

    selected: dict[int, str] = {}
    for tile_id, chars in by_id.items():
        chars_sorted = sorted(chars, key=lambda c: (priority.get(c, 10_000), c))
        selected[tile_id] = chars_sorted[0]
    return selected


def build_tile_spec_string(legend: dict[str, int], max_tile_id: int) -> str:
    char_by_id = choose_char_for_tile_id(legend)
    entries: list[str] = []
    for tile_id in range(1, max_tile_id + 1):
        char = char_by_id.get(tile_id, "")
        color = SOLID_TILE_COLORS.get(char, fallback_color_for_id(tile_id))
        r, g, b, a = color
        entries.append(f"{tile_id}:{r},{g},{b},{a}")
    return ";".join(entries)


def command_terrain(args: argparse.Namespace) -> None:
    aseprite_bin = resolve_aseprite_bin(args.aseprite_bin)
    legend = load_legend(Path(args.legend))

    cols = args.cols
    if cols <= 0:
        raise ValueError("--cols must be > 0")

    positive_ids = [tile_id for tile_id in legend.values() if tile_id > 0]
    if not positive_ids:
        raise ValueError("Legend must include at least one positive tile ID for terrain generation.")

    max_tile_id = max(positive_ids)
    required_tiles = max(1, max_tile_id)
    rows = args.rows if args.rows else math.ceil(required_tiles / cols)
    if rows <= 0:
        raise ValueError("--rows must be > 0")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lua_script = PROJECT_ROOT / "assets/lua/generate_solid_tileset.lua"
    if not lua_script.exists():
        raise FileNotFoundError(f"Missing Lua template: {lua_script}")

    env = os.environ.copy()
    env["TILE_W"] = str(args.tile_width)
    env["TILE_H"] = str(args.tile_height)
    env["COLS"] = str(cols)
    env["ROWS"] = str(rows)
    env["OUT"] = str(out_path)
    env["TILES_SPEC"] = build_tile_spec_string(legend, max_tile_id)

    run([str(aseprite_bin), "-b", "--script", str(lua_script)], env=env)
    print(
        f"Generated solid terrain tileset {out_path} with {cols}x{rows} tiles "
        f"(max tile ID {max_tile_id})."
    )

    if args.export_dir:
        export_args = argparse.Namespace(
            aseprite_bin=args.aseprite_bin,
            source=str(out_path),
            out_dir=args.export_dir,
            sheet_type=args.sheet_type,
            data_format=args.data_format,
        )
        command_export(export_args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aseprite tileset workflow helper for init/edit/export/check."
    )
    parser.add_argument(
        "--aseprite-bin",
        default=None,
        help="Optional explicit path to aseprite binary.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("check", help="Verify Aseprite CLI is available.")

    init_parser = subparsers.add_parser(
        "init", help="Create a blank .aseprite tileset based on map legend IDs."
    )
    init_parser.add_argument("--legend", required=True, help="Legend JSON path.")
    init_parser.add_argument("--out", required=True, help="Output .aseprite path.")
    init_parser.add_argument("--tile-width", type=int, required=True)
    init_parser.add_argument("--tile-height", type=int, required=True)
    init_parser.add_argument("--cols", type=int, default=8)
    init_parser.add_argument(
        "--rows",
        type=int,
        default=0,
        help="Optional explicit row count. Defaults to legend-driven auto size.",
    )

    paint_parser = subparsers.add_parser(
        "paint",
        help="Paint an ASCII map as a colored .aseprite file (one tile per character).",
    )
    paint_parser.add_argument("--ascii", required=True, help="Path to ASCII map file.")
    paint_parser.add_argument("--out", required=True, help="Output .aseprite path.")
    paint_parser.add_argument(
        "--tile-size",
        type=int,
        default=16,
        help="Pixel size per tile (default 16).",
    )
    paint_parser.add_argument(
        "--open",
        action="store_true",
        help="Open the painted .aseprite file in Aseprite after creation.",
    )
    paint_parser.add_argument(
        "--treeset",
        default="",
        help="Path to tree tileset .aseprite (paints T/F with tree logic tiles).",
    )
    paint_parser.add_argument(
        "--legend",
        default="",
        help="Legend JSON for tree logic (default: <ascii>.legend.json).",
    )
    paint_parser.add_argument(
        "--tree-seed",
        type=int,
        default=42,
        help="RNG seed for tree tile variation (with --treeset).",
    )
    paint_parser.add_argument(
        "--grass-dir",
        default="",
        help="Directory with grass tile PNGs (GotchiCraft-style). Requires --treeset.",
    )
    paint_parser.add_argument(
        "--water-tile",
        default="",
        help="Path to water tile PNG or .aseprite. Requires --treeset.",
    )
    paint_parser.add_argument(
        "--dirt-tile",
        default="",
        help="Path to dirt tile PNG or .aseprite (for P=path cells). Requires --treeset.",
    )
    paint_parser.add_argument(
        "--grass-tile-range",
        default="19-30",
        help="For grass sheet: tile range to use (1-based inclusive). Default: 19-30.",
    )

    edit_parser = subparsers.add_parser("edit", help="Open a .aseprite file in Aseprite GUI.")
    edit_parser.add_argument("--source", required=True, help="Source .aseprite path.")

    export_parser = subparsers.add_parser(
        "export", help="Export spritesheet PNG + Aseprite JSON metadata."
    )
    export_parser.add_argument("--source", required=True, help="Source .aseprite path.")
    export_parser.add_argument("--out-dir", required=True, help="Output directory.")
    export_parser.add_argument("--sheet-type", default="rows")
    export_parser.add_argument("--data-format", default="json-array")

    terrain_parser = subparsers.add_parser(
        "terrain",
        help="Create a solid-color terrain tileset in Aseprite from legend tile IDs.",
    )
    terrain_parser.add_argument("--legend", required=True, help="Legend JSON path.")
    terrain_parser.add_argument("--out", required=True, help="Output .aseprite path.")
    terrain_parser.add_argument("--tile-width", type=int, required=True)
    terrain_parser.add_argument("--tile-height", type=int, required=True)
    terrain_parser.add_argument("--cols", type=int, default=8)
    terrain_parser.add_argument(
        "--rows",
        type=int,
        default=0,
        help="Optional explicit row count. Defaults to legend-driven auto size.",
    )
    terrain_parser.add_argument(
        "--export-dir",
        default="",
        help="Optional export directory for immediate PNG/JSON export.",
    )
    terrain_parser.add_argument("--sheet-type", default="rows")
    terrain_parser.add_argument("--data-format", default="json-array")

    return parser


def run_from_args(args: argparse.Namespace) -> None:
    if args.command == "check":
        command_check(args)
    elif args.command == "paint":
        command_paint(args)
    elif args.command == "init":
        if args.tile_width <= 0 or args.tile_height <= 0:
            raise ValueError("--tile-width and --tile-height must be > 0")
        command_init(args)
    elif args.command == "edit":
        command_edit(args)
    elif args.command == "export":
        command_export(args)
    elif args.command == "terrain":
        if args.tile_width <= 0 or args.tile_height <= 0:
            raise ValueError("--tile-width and --tile-height must be > 0")
        command_terrain(args)
    else:
        raise ValueError(f"Unsupported command: {args.command}")


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    run_from_args(args)
