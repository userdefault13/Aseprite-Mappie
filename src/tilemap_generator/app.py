from __future__ import annotations

import argparse
import json
import platform
import random
import subprocess
import sys
from pathlib import Path

from tilemap_generator import aseprite_cli
from tilemap_generator import cli as map_cli
from tilemap_generator import map_gen_cli


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Unified Tilemap Generator CLI. "
            "Use 'map-gen' to create ASCII maps, 'map' to convert ASCII->tilemap, "
            "and 'tileset' for Aseprite workflows. Run without args for interactive menu."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=False)

    subparsers.add_parser(
        "map-gen", help="Procedural ASCII map generation commands.", add_help=False
    )
    subparsers.add_parser("map", help="Map generation commands.", add_help=False)
    subparsers.add_parser("tileset", help="Aseprite tileset commands.", add_help=False)
    subparsers.add_parser(
        "export", help="Export tile indices from tilemap layers to JSON/CSV.", add_help=False
    )
    subparsers.add_parser("menu", help="Interactive menu.", add_help=False)

    return parser


def normalize_forwarded_args(raw_args: list[str]) -> list[str]:
    if raw_args and raw_args[0] == "--":
        return raw_args[1:]
    return raw_args


def prompt_str(label: str, default: str) -> str:
    value = input(f"{label} [{default}]: ").strip()
    return value if value else default


def prompt_int(label: str, default: int, range_hint: str = "") -> int:
    hint = f" ({range_hint})" if range_hint else ""
    while True:
        value = input(f"{label}{hint} [{default}]: ").strip()
        if not value:
            return default
        try:
            return int(value)
        except ValueError:
            print("Enter a valid integer.")


def prompt_float(label: str, default: float, range_hint: str = "") -> float:
    hint = f" ({range_hint})" if range_hint else ""
    while True:
        value = input(f"{label}{hint} [{default}]: ").strip()
        if not value:
            return default
        try:
            return float(value)
        except ValueError:
            print("Enter a valid number.")


def prompt_bool(label: str, default: bool) -> bool:
    default_text = "y" if default else "n"
    while True:
        value = input(f"{label} [y/n, default {default_text}]: ").strip().lower()
        if not value:
            return default
        if value in ("y", "yes", "1", "true"):
            return True
        if value in ("n", "no", "0", "false"):
            return False
        print("Enter y or n.")


def _project_root() -> Path:
    """Repository root (parent of ``src/``)."""
    return Path(__file__).resolve().parents[2]


def _resolve_user_path(raw: str) -> Path:
    p = Path(raw).expanduser()
    if p.is_absolute():
        return p
    cwd = Path.cwd() / p
    if cwd.exists():
        return cwd.resolve()
    root = _project_root() / p
    return root.resolve()


def _hill_sixteen_mask_table_markdown(legend_path: Path) -> str:
    """Return the ``| Mask | Cardinals set | ...`` table from ``HILL_MASK_LEGEND.md``."""
    if not legend_path.exists():
        return f"(Legend file not found: {legend_path})\n"
    lines = legend_path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.startswith("| Mask | Cardinals set |"):
            chunk: list[str] = []
            j = i
            while j < len(lines) and lines[j].strip() and lines[j].startswith("|"):
                chunk.append(lines[j])
                j += 1
            return "\n".join(chunk) + "\n"
    return "(Could not find 16-mask table in legend.)\n"


def _legend_subsection(
    legend_path: Path,
    start_heading_line: str,
    *,
    stop_at_line: str | None = None,
) -> str:
    if not legend_path.exists():
        return f"(Legend file not found: {legend_path})\n"
    lines = legend_path.read_text(encoding="utf-8").splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == start_heading_line.strip():
            start = i
            break
    if start is None:
        return f"(Section not found: {start_heading_line!r})\n"
    out: list[str] = []
    for line in lines[start:]:
        if stop_at_line and line.strip() == stop_at_line.strip():
            break
        out.append(line)
    return "\n".join(out).strip() + "\n"


def _coerce_hill_map_tile_value(raw: object, *, mask: int, builtin_default: int) -> int:
    if isinstance(raw, bool):
        return builtin_default
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    try:
        return int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return builtin_default


def prompt_edit_hill_map_mask_tile() -> None:
    """Load terrain JSON, prompt mask and tile, confirm, then optionally write ``hill.hill_map``."""
    from tilemap_generator.paint_map_png import HILL_MAP

    default_cfg = str(_project_root() / "examples" / "terrain.bitmask.json")
    raw_path = input(f"This JSON file path? [{default_cfg}]: ").strip() or default_cfg
    cfg_path = _resolve_user_path(raw_path)
    if not cfg_path.exists():
        print(f"File not found: {cfg_path}", file=sys.stderr)
        return
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}", file=sys.stderr)
        return
    hill = data.get("hill")
    if not isinstance(hill, dict):
        print("Config has no 'hill' object.", file=sys.stderr)
        return
    hm = hill.get("hill_map")
    if not isinstance(hm, dict):
        print("Config 'hill' has no 'hill_map' object.", file=sys.stderr)
        return

    while True:
        mask = prompt_int("Which mask to edit (0–15)", 0, "0-15")
        if 0 <= mask <= 15:
            break
        print("Mask must be an integer from 0 to 15.")

    key = str(mask)
    cur = hm.get(key)
    builtin_tile = int(HILL_MAP.get(mask, HILL_MAP.get(0, 1)))
    from_tile = _coerce_hill_map_tile_value(cur, mask=mask, builtin_default=builtin_tile)

    new_tile = prompt_int(
        "Which tile to use (1-based hills.aseprite tile index)",
        from_tile,
        ">=1",
    )
    if new_tile < 1:
        print("Tile index should be >= 1.", file=sys.stderr)
        return

    if new_tile == from_tile:
        print(f"Mask {mask} already uses tile {from_tile}. No change made.")
        return

    msg = (
        f"Changing mask {mask} from tile {from_tile} to tile {new_tile}. "
        "Are you sure you want to proceed?"
    )
    if not prompt_bool(msg, False):
        print("Cancelled.")
        return

    hm[key] = new_tile
    try:
        with cfg_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
    except OSError as e:
        print(f"Could not write file: {e}", file=sys.stderr)
        return
    print(f"Saved hill.hill_map[{key!r}] = {new_tile} in {cfg_path}")


def _open_in_system_default(path: Path) -> None:
    path = path.resolve()
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(["open", str(path)], check=False)
        elif system == "Windows":
            subprocess.run(["cmd", "/c", "start", "", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except OSError as e:
        print(f"Could not open file: {e}", file=sys.stderr)


def run_mask_legend_and_edit() -> None:
    """Show the 16-mask table, then submenu: edit hill_map, docs, or back."""
    legend = _project_root() / "docs" / "HILL_MASK_LEGEND.md"
    det_heading = "### Deterministic variety (stable per cell)"
    split_heading = "### Split mask (separate maps by geometry class)"

    while True:
        print("\n--- Hill masks (0–15) — default `HILL_MAP` tile ids ---\n")
        print(_hill_sixteen_mask_table_markdown(legend))
        print("1. Edit hill_map (mask + default tile)")
        print("2. Deterministic variety (reference)")
        print("3. Split mask (reference)")
        print("4. Back")
        sub = input("Select [1-4]: ").strip() or "4"
        if sub == "1":
            prompt_edit_hill_map_mask_tile()
            input("(Press Enter to continue.) ")
            continue
        if sub == "2":
            print("\n--- Deterministic variety ---\n")
            print(
                _legend_subsection(
                    legend,
                    det_heading,
                    stop_at_line=split_heading,
                )
            )
            input("(Press Enter to continue.) ")
            continue
        if sub == "3":
            print("\n--- Split mask ---\n")
            print(_legend_subsection(legend, split_heading, stop_at_line=None))
            input("(Press Enter to continue.) ")
            continue
        if sub == "4":
            break
        print("Invalid option.")

    if not prompt_bool("Open terrain bitmask JSON in your default editor", False):
        return
    cfg_hint = str(_project_root() / "examples" / "terrain.bitmask.json")
    raw = input(f"Path [{cfg_hint}]: ").strip() or cfg_hint
    cfg_path = _resolve_user_path(raw)
    if not cfg_path.exists():
        print(f"File not found: {cfg_path}", file=sys.stderr)
        return
    _open_in_system_default(cfg_path)


def _run_map_gen_defaults() -> None:
    """Run map generation with sensible defaults (no prompts)."""
    args = [
        "--width", "128",
        "--height", "128",
        "--tree-density", "0.22",
        "--forest-density", "0.65",
        "--water-density", "0.10",
        "--hill-density", "0.04",
        "--spawn-count", "8",
        "--spawn-clearing-size", "15",
        "--join-point-count", "0",
        "--path-width-threshold", "3",
        "--path-perlin-scale", "14.0",
        "--path-perlin-weight", "1.8",
        "--mine-count", "4",
        "--shop-count", "3",
        "--creep-zone-count", "6",
        "--creep-zone-radius", "2",
        "--dead-end-count", "8",
        "--map-mode", "island",
        "--shoreline-erode-iterations", "2",
        "--seed", "0",
        "--out", "maps/generated_map.txt",
        "--terrain-config", "examples/terrain.bitmask.json",
        "--preview-tile-size", "16",
        "--preview-in-aseprite",
    ]
    print("\nRunning map generation with defaults...\n")
    map_gen_cli.main(args)
    print("\n1. Send to paint")
    print("2. Back to menu")
    choice = input("Select [1-2]: ").strip() or "1"
    if choice == "1":
        _run_send_to_paint(
            ascii_path="maps/generated_map.txt",
            default_out="build/map.aseprite",
            ascii_includes_water_border=True,
            default_terrain_config="examples/terrain.bitmask.json",
        )
    else:
        run_menu()


def run_prompted_map_gen() -> None:
    print("\nGenerate New ASCII Map\n")
    print("1. Auto generate via defaults")
    print("2. Continue to custom")
    mode = input("Select [1-2]: ").strip() or "1"
    if mode == "1":
        _run_map_gen_defaults()
        return
    r = random.Random()
    width = prompt_int("Width", 128, "8-512")
    height = prompt_int("Height", 128, "8-512")
    # Default clearing size scales with map (must be odd, fit 4+ spawns)
    default_clearing = min(15, min(width, height) // 2)
    if default_clearing % 2 == 0:
        default_clearing = max(3, default_clearing - 1)
    else:
        default_clearing = max(3, default_clearing)
    tree_density = prompt_float("Tree density", round(r.uniform(0.12, 0.32), 2), "0.0-1.0")
    forest_density = prompt_float("Forest density", round(r.uniform(0.45, 0.75), 2), "0.0-1.0")
    water_max = 1.0 - tree_density
    while True:
        water_density = prompt_float(
            "Water density",
            round(min(0.18, water_max * 0.9) if water_max > 0 else 0.01, 2),
            f"0.0-{water_max:.2f} (tree+water ≤ 1.0)",
        )
        if tree_density + water_density <= 1.0:
            break
        print(f"  Tree + water = {tree_density + water_density:.2f} exceeds 1.0. Please re-enter.")
    hill_density = prompt_float("Hill density", round(r.uniform(0.0, 0.08), 2), "0.0-1.0")
    spawn_count = prompt_int("Spawn count", r.randint(4, 12), "1-32")
    spawn_clearing_size = prompt_int("Spawn clearing size", default_clearing, "3-31 odd")
    join_point_count = prompt_int("Join point count (0 = auto)", r.choice([0, 0, 0, 2, 3, 4]), "0-16")
    path_width_threshold = prompt_int("Path width threshold", r.choice([2, 3, 3, 4]), "1-8")
    path_perlin_scale = prompt_float("Path Perlin scale", round(r.uniform(10.0, 18.0), 1), "4-24")
    path_perlin_weight = prompt_float("Path Perlin weight", round(r.uniform(1.2, 2.2), 1), "0.5-4.0")
    mine_count = prompt_int("Mine count", r.randint(2, 6), "0-20")
    shop_count = prompt_int("Shop count", r.randint(2, 5), "0-16")
    creep_zone_count = prompt_int("Creep zone count", r.randint(4, 10), "0-24")
    creep_zone_radius = prompt_int("Creep zone radius", r.randint(2, 4), "1-6")
    dead_end_count = prompt_int("Dead-end count", r.randint(4, 12), "0-32")
    require_secret_npc = prompt_bool("Require single-path secret NPC", r.choice([True, True, False]))
    hide_path = prompt_bool("Hide path (no path corridors)", False)
    map_mode = input("Map mode (island=ocean border, continent=land+trees border) [island]: ").strip().lower() or "island"
    if map_mode not in ("island", "continent"):
        map_mode = "island"
    water_border_width = 2 if map_mode == "island" else 0
    shoreline_erode = prompt_int("Shoreline erosion iterations (0=off, 2=default, more=rougher coastlines)", 2, "0-6")
    seed = prompt_int("Seed", r.randint(0, 99999), "0 = random")
    out = prompt_str("Output ASCII map path", "maps/generated_map.txt")
    terrain_config = input("Terrain config (legend + paths: grass, shoreline, hills, rivers, lakes) [examples/terrain.bitmask.json or blank]: ").strip()
    legend_out = input("Legend output path [auto from --out]: ").strip()
    preview_in_aseprite = prompt_bool("Open preview in Aseprite when done", True)
    preview_tile_size = prompt_int("Preview tile pixel size", 16, "2-32")
    preview_out = input("Preview BMP path [auto from --out]: ").strip()

    args = [
        "--width",
        str(width),
        "--height",
        str(height),
        "--tree-density",
        str(tree_density),
        "--forest-density",
        str(forest_density),
        "--water-density",
        str(water_density),
        "--hill-density",
        str(hill_density),
        "--spawn-count",
        str(spawn_count),
        "--spawn-clearing-size",
        str(spawn_clearing_size),
        "--join-point-count",
        str(join_point_count),
        "--path-width-threshold",
        str(path_width_threshold),
        "--path-perlin-scale",
        str(path_perlin_scale),
        "--path-perlin-weight",
        str(path_perlin_weight),
        "--mine-count",
        str(mine_count),
        "--shop-count",
        str(shop_count),
        "--creep-zone-count",
        str(creep_zone_count),
        "--creep-zone-radius",
        str(creep_zone_radius),
        "--dead-end-count",
        str(dead_end_count),
        "--map-mode",
        map_mode,
        "--shoreline-erode-iterations",
        str(shoreline_erode),
        "--seed",
        str(seed),
        "--out",
        out,
        "--preview-tile-size",
        str(preview_tile_size),
    ]

    if require_secret_npc:
        args.append("--require-secret-npc-path")
    if hide_path:
        args.append("--hide-path")
    if terrain_config:
        args.extend(["--terrain-config", terrain_config])
    if legend_out:
        args.extend(["--legend-out", legend_out])
    if preview_out:
        args.extend(["--preview-out", preview_out])
    if preview_in_aseprite:
        args.append("--preview-in-aseprite")

    print("\nRunning map generation...\n")
    map_gen_cli.main(args)

    print("\n1. Send to paint")
    print("2. Back to menu")
    choice = input("Select [1-2]: ").strip() or "1"
    if choice == "1":
        _run_send_to_paint(
            ascii_path=out,
            default_out="build/map.aseprite",
            ascii_includes_water_border=(map_mode == "island"),
            default_terrain_config=terrain_config or None,
        )
    else:
        run_menu()


def _run_send_to_paint(
    ascii_path: str | None = None,
    default_out: str = "build/map.aseprite",
    ascii_includes_water_border: bool = False,
    default_terrain_config: str | None = None,
) -> None:
    """After 'Send to paint': prompt use auto defaults vs custom, then run paint."""
    print("\n1. Use auto defaults")
    print("2. Continue to custom")
    choice = input("Select [1-2]: ").strip() or "1"
    if choice == "1":
        _run_paint_defaults(
            ascii_path=ascii_path or "maps/generated_map.txt",
            default_out=default_out,
            ascii_includes_water_border=ascii_includes_water_border,
            default_terrain_config=default_terrain_config,
        )
    else:
        run_prompted_paint(
            ascii_path=ascii_path,
            default_out=default_out,
            ascii_includes_water_border=ascii_includes_water_border,
            default_terrain_config=default_terrain_config,
        )


def _run_paint_defaults(
    ascii_path: str = "maps/generated_map.txt",
    default_out: str = "build/map.aseprite",
    ascii_includes_water_border: bool = False,
    default_terrain_config: str | None = None,
) -> None:
    """Run paint with sensible defaults (no prompts)."""
    args = [
        "paint",
        "--ascii", ascii_path,
        "--out", default_out,
        "--tile-size", "16",
        "--treeset", "examples/trees.aseprite",
        "--open",
    ]
    if default_terrain_config:
        args.extend(["--terrain-config", default_terrain_config])
    print("\nRunning paint with defaults...\n")
    aseprite_cli.main(args)


def run_prompted_paint(
    ascii_path: str | None = None,
    default_out: str = "build/map.aseprite",
    ascii_includes_water_border: bool = False,
    default_terrain_config: str | None = None,
) -> None:
    print("\nPaint ASCII Map in Aseprite\n")
    r = random.Random()
    ascii_path = prompt_str("ASCII map path", ascii_path or "maps/generated_map.txt")
    out_path = prompt_str("Output .aseprite path", default_out)
    tile_size = prompt_int("Tile size (pixels per cell)", 16, "8-64")
    treeset_path = input("Tree tileset path [examples/trees.aseprite]: ").strip() or "examples/trees.aseprite"
    terrain_default = default_terrain_config or ""
    terrain_config = input(f"Terrain config (grass/water/dirt/trees + shoreline/hills/rivers/lakes + legend + bitmask) [{terrain_default or 'blank'}]: ").strip() or terrain_default
    args = ["paint", "--ascii", ascii_path, "--out", out_path, "--tile-size", str(tile_size)]
    args.extend(["--treeset", treeset_path])
    if terrain_config:
        args.extend(["--terrain-config", terrain_config])
    else:
        grass_dir = input("Grass tile path [examples/grass.aseprite]: ").strip() or "examples/grass.aseprite"
        water_tile = input("Water tile path [examples/water.aseprite]: ").strip() or "examples/water.aseprite"
        dirt_tile = input("Dirt tile path [examples/dirt.aseprite]: ").strip() or "examples/dirt.aseprite"
        default_border = 0 if ascii_includes_water_border else 2
        water_border_width = prompt_int("Water border width (0 = in ASCII)", default_border, "0-8")
        grass_shoreline_range = input("Grass shoreline tiles (e.g. 1-56 for grass.png) [1-56]: ").strip() or "1-56"
        grass_shoreline_extended = input("Extended shoreline (peninsula/island, 5 tiles e.g. 19-23) [blank=off]: ").strip()
        grass_shoreline_river = input("River bank tiles (2 tiles for N+S, E+W e.g. 24-25) [blank=off]: ").strip()
        args.extend(["--grass-dir", grass_dir])
        args.extend(["--water-tile", water_tile])
        args.extend(["--dirt-tile", dirt_tile])
        args.extend(["--water-border-width", str(water_border_width)])
        args.extend(["--grass-shoreline-range", grass_shoreline_range])
        if grass_shoreline_extended:
            args.extend(["--grass-shoreline-extended-range", grass_shoreline_extended])
        if grass_shoreline_river:
            args.extend(["--grass-shoreline-river-range", grass_shoreline_river])
    open_after = prompt_bool("Open in Aseprite when done", True)
    if open_after:
        args.append("--open")

    print("\nRunning paint...\n")
    aseprite_cli.main(args)


def run_menu() -> None:
    while True:
        print("\nTilemap CLI Menu")
        print("1. Generate new ASCII map")
        print("2. Paint ASCII map in Aseprite")
        print("3. View or edit mask (legend + optional terrain config)")
        print("4. Exit")
        choice = input("Select an option [1-4]: ").strip()
        if choice == "1":
            run_prompted_map_gen()
            return
        if choice == "2":
            run_prompted_paint()
            return
        if choice == "3":
            run_mask_legend_and_edit()
            continue
        if choice in ("4", "q", "quit", "exit"):
            print("Exiting.")
            return
        print("Invalid option.")


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args, unknown = parser.parse_known_args(argv)

    forwarded = normalize_forwarded_args(unknown)
    if args.command is None:
        if forwarded:
            parser.error(f"Unsupported arguments: {' '.join(forwarded)}")
        run_menu()
        return

    if args.command == "menu":
        run_menu()
        return

    if args.command == "map-gen":
        if not forwarded:
            map_gen_cli.main(["--help"])
            return
        map_gen_cli.main(forwarded)
        return

    if args.command == "map":
        if not forwarded:
            map_cli.main(["--help"])
            return
        map_cli.main(forwarded)
        return

    if args.command == "tileset":
        if not forwarded:
            aseprite_cli.main(["--help"])
            return
        aseprite_cli.main(forwarded)
        return

    if args.command == "export":
        from tilemap_generator import export_cli

        if not forwarded:
            export_cli.main(["--help"])
            return
        export_cli.main(forwarded)
        return

    parser.error(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
