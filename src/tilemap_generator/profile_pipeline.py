"""Run criteria-profile map generation pipelines (moba_lanes, etc.)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tilemap_generator.engines.moba_lanes import generate_moba_lanes_map
from tilemap_generator.game_contract import build_game_contract, write_game_contract, write_meta_json
from tilemap_generator.legend import DEFAULT_LEGEND, get_legend_from_config
from tilemap_generator.tree_logic import to_tile_rows_with_trees
from tilemap_generator.validate_map import MapValidationError, validate_moba_result

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def write_ascii(path: Path, grid: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join("".join(row) for row in grid) + "\n", encoding="utf-8")


def write_legend(path: Path, legend: dict[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(legend, indent=2) + "\n", encoding="utf-8")


def run_moba_lanes_profile(args: argparse.Namespace, profile: dict[str, Any]) -> None:
    seed = int(getattr(args, "seed", 0) or profile.get("seed_default") or 0)
    result = generate_moba_lanes_map(profile, seed)

    try:
        validate_moba_result(profile, result)
    except MapValidationError as exc:
        raise SystemExit(f"Validation failed: {exc}") from exc

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.suffix.lower() == ".txt":
        ascii_path = out_path
        prefix = out_path.with_suffix("")
    else:
        ascii_path = Path(str(out_path) + ".txt")
        prefix = Path(str(out_path))

    legend_path = Path(args.legend_out) if getattr(args, "legend_out", "") else prefix.with_suffix(".legend.json")
    outputs = profile.get("outputs") or {}

    legend = DEFAULT_LEGEND.copy()
    terrain_config = getattr(args, "terrain_config", "") or (profile.get("art") or {}).get("terrain_config") or ""
    if terrain_config:
        tc_path = Path(terrain_config)
        if not tc_path.exists():
            for base in (PROJECT_ROOT / "examples", PROJECT_ROOT):
                cand = base / tc_path
                if cand.exists():
                    tc_path = cand
                    break
        if tc_path.exists():
            from tilemap_generator.paint_map_png import load_terrain_config

            cfg = load_terrain_config(tc_path, project_root=PROJECT_ROOT)
            lg = get_legend_from_config(cfg)
            if lg:
                legend = lg

    if outputs.get("ascii", True):
        write_ascii(ascii_path, result.grid)
        print(f"Wrote {ascii_path}")
    if outputs.get("legend", True):
        write_legend(legend_path, legend)
        print(f"Wrote {legend_path}")

    csv_path = prefix.with_suffix(".csv")
    tiled_path = prefix.with_suffix(".tiled.json")
    build_prefix = PROJECT_ROOT / "build" / prefix.name
    build_prefix.parent.mkdir(parents=True, exist_ok=True)

    lines = ["".join(row) for row in result.grid]
    tile_rows = to_tile_rows_with_trees(lines, legend, tree_chars={"T", "F"}, seed=seed, strict=False)
    if outputs.get("csv", True):
        csv_content = "\n".join(",".join(str(tid) for tid in row) for row in tile_rows) + "\n"
        for dest in (csv_path, build_prefix.with_suffix(".csv")):
            dest.write_text(csv_content, encoding="utf-8")
            print(f"Wrote {dest}")

    if outputs.get("tiled_json", True):
        flat = [tid for row in tile_rows for tid in row]
        tiled = {
            "compressionlevel": -1,
            "height": result.height,
            "infinite": False,
            "layers": [
                {
                    "data": flat,
                    "height": result.height,
                    "id": 1,
                    "name": "Ground",
                    "opacity": 1,
                    "type": "tilelayer",
                    "visible": True,
                    "width": result.width,
                    "x": 0,
                    "y": 0,
                }
            ],
            "nextlayerid": 2,
            "nextobjectid": 1,
            "orientation": "orthogonal",
            "renderorder": "right-down",
            "tiledversion": "1.11.0",
            "tileheight": result.tile,
            "tilewidth": result.tile,
            "type": "map",
            "version": "1.10",
            "width": result.width,
            "tilesets": [],
        }
        payload = json.dumps(tiled) + "\n"
        for dest in (tiled_path, build_prefix.with_suffix(".tiled.json")):
            dest.write_text(payload, encoding="utf-8")
            print(f"Wrote {dest}")

    artifacts = {
        "tiled_json": build_prefix.with_suffix(".tiled.json").name,
        "ascii": ascii_path.name,
        "legend": legend_path.name,
        "preview_png": prefix.with_suffix(".preview.png").name,
        "meta_json": prefix.with_suffix(".meta.json").name,
    }

    if outputs.get("game_json", True):
        contract = build_game_contract(profile=profile, result=result, seed=seed, artifacts=artifacts)
        write_game_contract(build_prefix.with_suffix(".game.json"), contract)
        write_game_contract(prefix.with_suffix(".game.json"), contract)
        print(f"Wrote {build_prefix.with_suffix('.game.json')}")
        print(f"Wrote {prefix.with_suffix('.game.json')}")

    if outputs.get("meta_json", True):
        write_meta_json(prefix.with_suffix(".meta.json"), profile, result)
        write_meta_json(build_prefix.with_suffix(".meta.json"), profile, result)
        print(f"Wrote {prefix.with_suffix('.meta.json')}")

    if outputs.get("preview_png", True):
        try:
            from PIL import Image
        except ImportError:
            print("Note: Pillow not installed; skipping preview_png")
        else:
            colors = {
                "G": (104, 178, 76, 255),
                ".": (104, 178, 76, 255),
                "P": (181, 152, 102, 255),
                "T": (46, 108, 54, 255),
                "F": (30, 78, 40, 255),
                "S": (250, 228, 92, 255),
                "D": (240, 95, 95, 255),
                "N": (86, 208, 220, 255),
                "R": (125, 126, 134, 255),
            }
            tw = result.tile
            img = Image.new("RGBA", (result.width * tw, result.height * tw), (0, 0, 0, 255))
            px = img.load()
            for y, row in enumerate(result.grid):
                for x, ch in enumerate(row):
                    rgba = colors.get(ch, (80, 80, 80, 255))
                    for dy in range(tw):
                        for dx in range(tw):
                            px[x * tw + dx, y * tw + dy] = rgba
            preview = prefix.with_suffix(".preview.png")
            img.save(preview)
            img.save(build_prefix.with_suffix(".preview.png"))
            print(f"Wrote {preview}")

    print(
        f"moba_lanes profile={profile.get('id')} seed={seed} "
        f"size={result.width}x{result.height} structures={len(result.structures)} gaps={len(result.gaps)}"
    )
