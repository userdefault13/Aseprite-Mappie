from __future__ import annotations

import argparse
import random

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
    subparsers.add_parser("menu", help="Interactive menu.", add_help=False)

    return parser


def normalize_forwarded_args(raw_args: list[str]) -> list[str]:
    if raw_args and raw_args[0] == "--":
        return raw_args[1:]
    return raw_args


def prompt_str(label: str, default: str) -> str:
    value = input(f"{label} [{default}]: ").strip()
    return value if value else default


def prompt_int(label: str, default: int) -> int:
    while True:
        value = input(f"{label} [{default}]: ").strip()
        if not value:
            return default
        try:
            return int(value)
        except ValueError:
            print("Enter a valid integer.")


def prompt_float(label: str, default: float) -> float:
    while True:
        value = input(f"{label} [{default}]: ").strip()
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


def run_prompted_map_gen() -> None:
    print("\nGenerate New ASCII Map\n")
    r = random.Random()
    width = prompt_int("Width", r.randint(48, 128))
    height = prompt_int("Height", r.randint(48, 128))
    # Default clearing size scales with map (must be odd, fit 4+ spawns)
    default_clearing = min(15, min(width, height) // 2)
    if default_clearing % 2 == 0:
        default_clearing = max(3, default_clearing - 1)
    else:
        default_clearing = max(3, default_clearing)
    tree_density = prompt_float("Tree density", round(r.uniform(0.12, 0.32), 2))
    forest_density = prompt_float("Forest density", round(r.uniform(0.45, 0.75), 2))
    water_density = prompt_float("Water density", round(r.uniform(0.06, 0.18), 2))
    spawn_count = prompt_int("Spawn count", r.randint(4, 12))
    spawn_clearing_size = prompt_int("Spawn clearing size", default_clearing)
    join_point_count = prompt_int("Join point count (0 = auto)", r.choice([0, 0, 0, 2, 3, 4]))
    path_width_threshold = prompt_int("Path width threshold", r.choice([2, 3, 3, 4]))
    path_perlin_scale = prompt_float("Path Perlin scale", round(r.uniform(10.0, 18.0), 1))
    path_perlin_weight = prompt_float("Path Perlin weight", round(r.uniform(1.2, 2.2), 1))
    mine_count = prompt_int("Mine count", r.randint(2, 6))
    shop_count = prompt_int("Shop count", r.randint(2, 5))
    creep_zone_count = prompt_int("Creep zone count", r.randint(4, 10))
    creep_zone_radius = prompt_int("Creep zone radius", r.randint(2, 4))
    dead_end_count = prompt_int("Dead-end count", r.randint(4, 12))
    require_secret_npc = prompt_bool("Require single-path secret NPC", r.choice([True, True, False]))
    seed = prompt_int("Seed", r.randint(0, 99999))
    out = prompt_str("Output ASCII map path", "maps/generated_map.txt")
    legend_out = input("Legend output path [auto from --out]: ").strip()
    preview_in_aseprite = prompt_bool("Open preview in Aseprite when done", r.choice([True, False]))
    preview_tile_size = prompt_int("Preview tile pixel size", r.choice([4, 6, 8, 8, 12, 16]))
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
        "--seed",
        str(seed),
        "--out",
        out,
        "--preview-tile-size",
        str(preview_tile_size),
    ]

    if require_secret_npc:
        args.append("--require-secret-npc-path")
    if legend_out:
        args.extend(["--legend-out", legend_out])
    if preview_out:
        args.extend(["--preview-out", preview_out])
    if preview_in_aseprite:
        args.append("--preview-in-aseprite")

    print("\nRunning map generation...\n")
    map_gen_cli.main(args)


def run_prompted_paint() -> None:
    print("\nPaint ASCII Map in Aseprite\n")
    r = random.Random()
    ascii_path = prompt_str("ASCII map path", "maps/generated_map.txt")
    out_path = prompt_str("Output .aseprite path", "build/map.aseprite")
    tile_size = prompt_int("Tile size (pixels per cell)", 16)
    treeset_path = input("Tree tileset path [blank = solid colors only]: ").strip()
    grass_dir = ""
    water_tile = ""
    dirt_tile = ""
    if treeset_path:
        grass_dir = input("Grass tile directory [blank = solid colors]: ").strip()
        water_tile = input("Water tile path [blank = auto or solid]: ").strip()
        dirt_tile = input("Dirt tile path [blank = solid]: ").strip()
    open_after = prompt_bool("Open in Aseprite when done", r.choice([True, False]))

    args = ["paint", "--ascii", ascii_path, "--out", out_path, "--tile-size", str(tile_size)]
    if treeset_path:
        args.extend(["--treeset", treeset_path])
    if grass_dir:
        args.extend(["--grass-dir", grass_dir])
    if water_tile:
        args.extend(["--water-tile", water_tile])
    if dirt_tile:
        args.extend(["--dirt-tile", dirt_tile])
    if open_after:
        args.append("--open")

    print("\nRunning paint...\n")
    aseprite_cli.main(args)


def run_menu() -> None:
    while True:
        print("\nTilemap CLI Menu")
        print("1. Generate new ASCII map")
        print("2. Paint ASCII map in Aseprite")
        print("3. Exit")
        choice = input("Select an option [1-3]: ").strip()
        if choice == "1":
            run_prompted_map_gen()
            return
        if choice == "2":
            run_prompted_paint()
            return
        if choice in ("3", "q", "quit", "exit"):
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

    parser.error(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
