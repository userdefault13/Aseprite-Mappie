from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from tilemap_generator.tree_logic import to_tile_rows_with_trees


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAC_ASEPRITE_BIN = Path.home() / "Library/Application Support/Steam/steamapps/common/Aseprite/Aseprite.app/Contents/MacOS/aseprite"
SOLID_TILE_COLORS: dict[str, tuple[int, int, int, int]] = {
    "G": (104, 178, 76, 255),
    ".": (104, 178, 76, 255),
    "~": (72, 132, 224, 255),
    "`": (48, 96, 180, 255),  # Deep water
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
    from tilemap_generator.legend import DEFAULT_LEGEND
    return DEFAULT_LEGEND.copy()


# Chars that use grass tiles (interior or shoreline); B = always shoreline
GRASS_LIKE_CHARS = frozenset("G.B")


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
    export_ascii_path = ascii_path
    export_ascii_temp: Path | None = None

    from tilemap_generator.paint_map_png import load_terrain_config

    terrain_cfg: dict | None = None
    terrain_config_input = getattr(args, "terrain_config", "") or ""
    if terrain_config_input:
        tc_path = Path(terrain_config_input)
        if not tc_path.exists():
            for base in (PROJECT_ROOT / "examples", PROJECT_ROOT):
                candidate = base / tc_path
                if candidate.exists():
                    tc_path = candidate
                    break
        if tc_path.exists():
            terrain_cfg = load_terrain_config(tc_path, project_root=PROJECT_ROOT)
    else:
        # Auto-use terrain config when not provided
        for candidate in (
            PROJECT_ROOT / "examples" / "terrain.bitmask.json",
            PROJECT_ROOT / "terrain.bitmask.json",
        ):
            if candidate.exists():
                terrain_cfg = load_terrain_config(candidate, project_root=PROJECT_ROOT)
                break

    treeset_input = (terrain_cfg and terrain_cfg.get("trees_path")) or args.treeset
    treeset_path = Path(treeset_input) if treeset_input else None
    if treeset_path is None:
        default_treeset = PROJECT_ROOT / "examples" / "trees.aseprite"
        if default_treeset.exists():
            treeset_path = default_treeset

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
        file_legend = load_legend(legend_path) if legend_path.exists() else None
        from tilemap_generator.legend import resolve_legend
        legend = resolve_legend(terrain_cfg, file_legend)
        tile_rows = to_tile_rows_with_trees(
            lines, legend, tree_chars={"T", "F"}, seed=args.tree_seed, strict=getattr(args, "strict", False)
        )

        from tilemap_generator.paint_map_png import (
            WATER_CHAR,
            close_ocean_shoreline_gaps,
            close_lake_shoreline_gaps,
            demote_shoreline_without_water_neighbor,
            export_treeset_to_png,
            fill_bay_diagonal_shoreline,
            filter_isolated_lake_shoreline,
            paint_map_to_png,
        )
        from tilemap_generator.paint_map_png import _ocean_connected_water_cells

        grass_dir: Path | None = None
        grass_sheet_path: Path | None = None
        grass_path_resolved: Path | None = None
        grass_input = (
            (terrain_cfg and terrain_cfg.get("grass_path"))
            or args.grass_dir
            or "examples/grass.aseprite"
        )
        if grass_input:
            grass_path = Path(grass_input)
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

        shoreline_path_resolved: Path | None = None
        shoreline_input = terrain_cfg.get("shoreline_path") if terrain_cfg else ""
        if shoreline_input:
            sp = Path(shoreline_input)
            if not sp.exists():
                for base in (PROJECT_ROOT / "examples", PROJECT_ROOT):
                    candidate = base / sp
                    if candidate.exists():
                        sp = candidate
                        break
                else:
                    sp = None
            if sp and sp.exists():
                shoreline_path_resolved = sp

        lakesrivers_path_resolved: Path | None = None
        lakesrivers_input = terrain_cfg.get("lakesrivers_path") if terrain_cfg else ""
        if lakesrivers_input:
            lrp = Path(lakesrivers_input)
            if not lrp.exists():
                for base in (PROJECT_ROOT / "examples", PROJECT_ROOT):
                    candidate = base / lrp
                    if candidate.exists():
                        lrp = candidate
                        break
                else:
                    lrp = None
            if lrp and lrp.exists():
                lakesrivers_path_resolved = lrp

        water_path: Path | None = None
        water_aseprite_path: Path | None = None
        water_input = (
            (terrain_cfg and terrain_cfg.get("water_path"))
            or args.water_tile
            or "examples/water.aseprite"
        )
        if water_input:
            wp = Path(water_input)
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
        dirt_input = (
            (terrain_cfg and terrain_cfg.get("dirt_path"))
            or args.dirt_tile
            or "examples/dirt.aseprite"
        )
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

        hill_path: Path | None = None
        hill_aseprite_path: Path | None = None
        hill_input = (terrain_cfg and terrain_cfg.get("hill_path")) or "examples/hills.aseprite"
        if hill_input:
            hp = Path(hill_input)
            if not hp.exists():
                for base in (PROJECT_ROOT / "examples", PROJECT_ROOT):
                    candidate = base / hp
                    if candidate.exists():
                        hp = candidate
                        break
                else:
                    hp = None
            if hp and hp.exists():
                if hp.suffix.lower() in (".aseprite", ".ase"):
                    hill_aseprite_path = hp
                else:
                    hill_path = hp

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            trees_sheet = tmp_path / "trees_sheet.png"
            water_png = tmp_path / "water.png"
            water_shallow_png = tmp_path / "water_shallow.png"
            water_deep_png = tmp_path / "water_deep.png"
            water_lake_png = tmp_path / "water_lake.png"
            water_river_png = tmp_path / "water_river.png"
            grass_png = tmp_path / "grass.png"
            dirt_png = tmp_path / "dirt.png"
            trees_png = tmp_path / "trees.png"
            poi_png = tmp_path / "poi.png"
            poi_layers_png = {
                "Spawn": tmp_path / "poi_spawn.png",
                "Join": tmp_path / "poi_join.png",
                "Mine": tmp_path / "poi_mine.png",
                "Shop": tmp_path / "poi_shop.png",
                "Creep": tmp_path / "poi_creep.png",
                "DeadEnd": tmp_path / "poi_dead_end.png",
                "Secret": tmp_path / "poi_secret.png",
            }

            # Shoreline (ocean) and LakeBank (lake/river) layers (persistent, next to output)
            shoreline_out = out_path.parent / (out_path.stem + "_shoreline.png")
            lakebank_out = out_path.parent / (out_path.stem + "_lakebank.png")
            hill_png = tmp_path / "hill.png"

            # Resolve grass_dir vs grass_sheet_path
            grass_json_path: Path | None = None
            if grass_path_resolved:
                if grass_path_resolved.is_dir():
                    grass_dir = grass_path_resolved
                elif grass_path_resolved.suffix.lower() in (".aseprite", ".ase"):
                    grass_json_candidate = grass_path_resolved.parent / (
                        grass_path_resolved.stem + ".json"
                    )
                    grass_sheet_path = tmp_path / "grass_sheet.png"
                    export_treeset_to_png(
                        grass_path_resolved,
                        grass_sheet_path,
                        aseprite_bin,
                        sheet_columns=11,
                        out_json=tmp_path / "grass_sheet.json",
                    )
                    grass_json_path = (
                        grass_json_candidate
                        if grass_json_candidate.exists()
                        else tmp_path / "grass_sheet.json"
                    )
                elif grass_path_resolved.suffix.lower() == ".png":
                    grass_sheet_path = grass_path_resolved

            # Resolve shoreline sheet (shorelines.aseprite for continent shoreline tiles)
            shoreline_sheet_path: Path | None = None
            if shoreline_path_resolved:
                if shoreline_path_resolved.suffix.lower() in (".aseprite", ".ase"):
                    shoreline_sheet_path = tmp_path / "shorelines_sheet.png"
                    # Use 5 columns to match common shoreline autotile layout (e.g. 5x7 = 35 tiles)
                    export_treeset_to_png(
                        shoreline_path_resolved,
                        shoreline_sheet_path,
                        aseprite_bin,
                        sheet_columns=5,
                    )
                elif shoreline_path_resolved.suffix.lower() == ".png":
                    shoreline_sheet_path = shoreline_path_resolved

            # Resolve lakes/rivers sheet (lakesrivers.aseprite for lake and river bank tiles)
            lakesrivers_sheet_path: Path | None = None
            if lakesrivers_path_resolved:
                if lakesrivers_path_resolved.suffix.lower() in (".aseprite", ".ase"):
                    lakesrivers_sheet_path = tmp_path / "lakesrivers_sheet.png"
                    export_treeset_to_png(
                        lakesrivers_path_resolved,
                        lakesrivers_sheet_path,
                        aseprite_bin,
                        sheet_columns=11,
                    )
                elif lakesrivers_path_resolved.suffix.lower() == ".png":
                    lakesrivers_sheet_path = lakesrivers_path_resolved

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

            # Export water .aseprite to PNG sheet (supports shallow + deep tiles)
            if water_aseprite_path is not None:
                water_sheet = tmp_path / "water_sheet.png"
                export_treeset_to_png(water_aseprite_path, water_sheet, aseprite_bin)
                water_path = water_sheet  # Full sheet: load_water_tiles handles 1 or 2+ tiles

            # Export dirt .aseprite to PNG (full sheet for path autotiling)
            if dirt_aseprite_path is not None:
                dirt_sheet = tmp_path / "dirt_sheet.png"
                export_treeset_to_png(dirt_aseprite_path, dirt_sheet, aseprite_bin)
                dirt_path = dirt_sheet

            # Export hills .aseprite to PNG (dedicated hill tileset)
            # sheet_columns must match your Aseprite grid so tile IDs 1,2,3… match row-major slices.
            hill_sheet_columns: int | None = None
            if terrain_cfg and isinstance(terrain_cfg.get("hill"), dict):
                _sc = terrain_cfg["hill"].get("sheet_columns")
                if isinstance(_sc, int) and _sc > 0:
                    hill_sheet_columns = _sc
            if hill_aseprite_path is not None:
                hill_sheet = tmp_path / "hill_sheet.png"
                export_treeset_to_png(
                    hill_aseprite_path,
                    hill_sheet,
                    aseprite_bin,
                    sheet_columns=hill_sheet_columns or 6,
                )
                hill_path = hill_sheet

            # Parse grass tile range (e.g. "19-30")
            grass_tile_range: tuple[int, int] | None = (19, 30)
            if args.grass_tile_range:
                parts = args.grass_tile_range.split("-")
                if len(parts) == 2:
                    try:
                        grass_tile_range = (int(parts[0]), int(parts[1]))
                    except ValueError:
                        pass

            # Parse grass shoreline range (e.g. "1-15")
            grass_shoreline_range: tuple[int, int] | None = (1, 56)
            if args.grass_shoreline_range:
                parts = args.grass_shoreline_range.split("-")
                if len(parts) == 2:
                    try:
                        grass_shoreline_range = (int(parts[0]), int(parts[1]))
                    except ValueError:
                        pass

            # Parse extended shoreline range (e.g. "19-23") for peninsula/island
            grass_shoreline_extended_range: tuple[int, int] | None = None
            if getattr(args, "grass_shoreline_extended_range", ""):
                parts = args.grass_shoreline_extended_range.split("-")
                if len(parts) == 2:
                    try:
                        grass_shoreline_extended_range = (int(parts[0]), int(parts[1]))
                    except ValueError:
                        pass

            # Parse river bank range (e.g. "24-25") for masks 5, 10
            grass_shoreline_river_range: tuple[int, int] | None = None
            if getattr(args, "grass_shoreline_river_range", ""):
                parts = args.grass_shoreline_river_range.split("-")
                if len(parts) == 2:
                    try:
                        grass_shoreline_river_range = (int(parts[0]), int(parts[1]))
                    except ValueError:
                        pass

            water_border_width = args.water_border_width or 2

            grass_bitmask_config = None
            if terrain_cfg:
                grass_bitmask_config = terrain_cfg
            elif getattr(args, "grass_bitmask", "") and Path(args.grass_bitmask).exists():
                from tilemap_generator.paint_map_png import load_bitmask_config

                grass_bitmask_config = load_bitmask_config(Path(args.grass_bitmask))

            export_treeset_to_png(treeset_path, trees_sheet, aseprite_bin)
            paint_map_to_png(
                ascii_lines=lines,
                legend=legend,
                tile_rows=tile_rows,
                tile_size=tile_size,
                trees_sheet_path=trees_sheet,
                water_out=water_png,
                water_shallow_out=water_shallow_png,
                water_deep_out=water_deep_png,
                water_lake_out=water_lake_png,
                water_river_out=water_river_png,
                grass_out=grass_png,
                dirt_out=dirt_png,
                trees_out=trees_png,
                poi_out=poi_png,
                poi_layers_out=poi_layers_png,
                shoreline_out=shoreline_out,
                lakebank_out=lakebank_out,
                hill_out=hill_png,
                hill_json_out=ascii_path.with_suffix(".hill.json"),
                grass_dir=grass_dir,
                grass_sheet_path=grass_sheet_path,
                grass_tile_range=grass_tile_range,
                grass_shoreline_range=grass_shoreline_range,
                grass_shoreline_lake_range=(4, 18),
                grass_shoreline_extended_range=grass_shoreline_extended_range,
                grass_shoreline_river_range=grass_shoreline_river_range,
                grass_bitmask_config=grass_bitmask_config,
                grass_json_path=grass_json_path,
                shoreline_sheet_path=shoreline_sheet_path,
                lakesrivers_sheet_path=lakesrivers_sheet_path,
                water_path=water_path,
                dirt_path=dirt_path,
                hill_path=hill_path,
                water_border_width=water_border_width,
                ascii_water_border=2,
                seed=args.tree_seed,
                strict=getattr(args, "strict", False),
            )
            closed_lines = close_ocean_shoreline_gaps(lines)
            closed_lines = close_lake_shoreline_gaps(
                closed_lines, water_chars=frozenset([WATER_CHAR])
            )
            _w = max(len(r) for r in closed_lines) if closed_lines else 0
            _h = len(closed_lines)
            if _w > 0 and _h > 0:
                _ocean = _ocean_connected_water_cells(closed_lines, _w, _h)
                closed_lines = fill_bay_diagonal_shoreline(
                    closed_lines, _ocean, _w, _h
                )
                closed_lines = demote_shoreline_without_water_neighbor(
                    closed_lines, _ocean, _w, _h
                )
            closed_lines = filter_isolated_lake_shoreline(closed_lines)
            if closed_lines != lines:
                with tempfile.NamedTemporaryFile(
                    "w",
                    suffix=".txt",
                    delete=False,
                    encoding="utf-8",
                ) as tmp_ascii:
                    tmp_ascii.write("\n".join(closed_lines) + "\n")
                    export_ascii_temp = Path(tmp_ascii.name)
                    export_ascii_path = export_ascii_temp

            lua_script = PROJECT_ROOT / "assets/lua/paint_from_png.lua"
            if not lua_script.exists():
                raise FileNotFoundError(f"Missing Lua script: {lua_script}")
            env = os.environ.copy()
            env["OUT"] = str(out_path.resolve())
            env["WATER_PNG"] = str(water_png)
            env["WATER_SHALLOW_PNG"] = str(water_shallow_png)
            env["WATER_DEEP_PNG"] = str(water_deep_png)
            env["WATER_LAKE_PNG"] = str(water_lake_png)
            env["WATER_RIVER_PNG"] = str(water_river_png)
            env["GRASS_PNG"] = str(grass_png)
            env["SHORELINE_PNG"] = str(shoreline_out.resolve())
            env["LAKEBANK_PNG"] = str(lakebank_out.resolve())
            env["HILL_PNG"] = str(hill_png)
            env["DIRT_PNG"] = str(dirt_png)
            env["TREES_PNG"] = str(trees_png)
            env["POI_PNG"] = str(poi_png)
            env["POI_SPAWN_PNG"] = str(poi_layers_png["Spawn"])
            env["POI_JOIN_PNG"] = str(poi_layers_png["Join"])
            env["POI_MINE_PNG"] = str(poi_layers_png["Mine"])
            env["POI_SHOP_PNG"] = str(poi_layers_png["Shop"])
            env["POI_CREEP_PNG"] = str(poi_layers_png["Creep"])
            env["POI_DEAD_END_PNG"] = str(poi_layers_png["DeadEnd"])
            env["POI_SECRET_PNG"] = str(poi_layers_png["Secret"])
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
    if treeset_path:
        stem = out_path.stem
        if (out_path.parent / (stem + "_shoreline.png")).exists():
            print(f"  Shoreline (ocean): {stem}_shoreline.png")
        if (out_path.parent / (stem + "_lakebank.png")).exists():
            print(f"  LakeBank (lake/river): {stem}_lakebank.png")

    # Auto-generate JSON and CSV tile indices when --export-map (default)
    if getattr(args, "export_map", True):
        legend_path = Path(args.legend) if args.legend else ascii_path.with_suffix(".legend.json")
        if legend_path.exists():
            from tilemap_generator import cli as map_cli

            out_prefix = out_path.with_suffix("")
            map_args = argparse.Namespace(
                ascii_path=str(export_ascii_path),
                legend_path=str(legend_path),
                tile_width=tile_size,
                tile_height=tile_size,
                out_prefix=str(out_prefix),
                layer_name="Ground",
                tileset_source="",
                aseprite_data="",
                tree_logic=bool(treeset_path),
                tree_config=args.tree_config if getattr(args, "tree_config", None) else "",
                tree_seed=args.tree_seed,
            )
            try:
                map_cli.run_from_args(map_args)
            except Exception as e:
                print(f"Warning: Could not export map JSON/CSV: {e}", file=sys.stderr)
            finally:
                if export_ascii_temp is not None and export_ascii_temp.exists():
                    export_ascii_temp.unlink()

    if args.open:
        # Launch Aseprite in background so "All Done!" prompt appears immediately
        try:
            subprocess.Popen(
                [str(aseprite_bin), str(out_path)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception as e:
            print(f"Note: Could not open in Aseprite: {e}", file=sys.stderr)

    print("\nAll Done!", flush=True)
    if sys.stdin.isatty():
        print("1. Back to main menu")
        print("2. Exit")
        choice = input("Select [1-2]: ").strip() or "1"
        if choice == "1":
            from tilemap_generator import app

            app.run_menu()
        else:
            print("Exiting.")


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
        default=True,
        dest="open",
        help="Open the painted .aseprite file in Aseprite after creation (default).",
    )
    paint_parser.add_argument(
        "--no-open",
        action="store_false",
        dest="open",
        help="Do not open the painted file in Aseprite.",
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
    paint_parser.add_argument(
        "--water-border-width",
        type=int,
        default=2,
        help="Tiles of water border around map (default 2).",
    )
    paint_parser.add_argument(
        "--grass-shoreline-range",
        default="1-56",
        help="Grass shoreline tile range (e.g. 1-56 for examples/grass.png). Default: 1-56.",
    )
    paint_parser.add_argument(
        "--grass-shoreline-extended-range",
        default="",
        help="Extended shoreline tiles for peninsula/island (5 tiles, e.g. 19-23). Optional.",
    )
    paint_parser.add_argument(
        "--grass-shoreline-river-range",
        default="",
        help="River bank tiles for water on opposite sides (2 tiles: N+S, E+W). Optional.",
    )
    paint_parser.add_argument(
        "--grass-bitmask",
        default="",
        help="Path to grass bitmask JSON (shoreline mappings). Overrides --grass-shoreline-* when set.",
    )
    paint_parser.add_argument(
        "--terrain-config",
        default="",
        help="Path to terrain config JSON. Auto-uses examples/terrain.bitmask.json when omitted. Centralizes grass, water, dirt paths and bitmask.",
    )
    paint_parser.add_argument(
        "--export-map",
        action="store_true",
        default=True,
        help="Auto-generate JSON and CSV tile indices after painting (default: on).",
    )
    paint_parser.add_argument(
        "--no-export-map",
        action="store_false",
        dest="export_map",
        help="Skip auto-generating JSON/CSV after painting.",
    )
    paint_parser.add_argument(
        "--strict",
        action="store_true",
        help="Follow ASCII map strictly: no random grass/tree variations, always use legend defaults.",
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
