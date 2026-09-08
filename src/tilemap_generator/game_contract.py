"""Emit playable *.game.json contracts from profile + generated layout."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from tilemap_generator.engines.moba_lanes import MobaLanesResult, Structure


def build_game_contract(
    *,
    profile: dict[str, Any],
    result: MobaLanesResult,
    seed: int,
    artifacts: dict[str, str] | None = None,
) -> dict[str, Any]:
    canvas = profile["canvas"]
    tile = int(canvas["tile"])
    cols = int(canvas["cols"])
    rows = int(canvas["rows"])
    walk = profile.get("walkability") or {}

    structures = [
        {
            "type": s.type,
            "team": s.team,
            "lane": s.lane,
            "tier": s.tier,
            "x": s.x,
            "y": s.y,
            "char": s.char,
        }
        for s in result.structures
    ]

    return {
        "schema_version": 1,
        "profile_id": profile.get("id"),
        "seed": int(seed),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "canvas": {
            "tile": tile,
            "cols": cols,
            "rows": rows,
            "width_px": cols * tile,
            "height_px": rows * tile,
        },
        "lanes": result.lanes,
        "bases": result.bases,
        "forest": {
            "rects": result.forest_rects,
            "gaps": result.gaps,
        },
        "walkability": {
            "solid_layer": "Forest",
            "walkable_chars": list(walk.get("walkable_chars") or []),
            "solid_chars": list(walk.get("solid_chars") or []),
        },
        "structures": structures,
        "artifacts": artifacts or {},
    }


def write_game_contract(path: Path, contract: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")


def write_meta_json(path: Path, profile: dict[str, Any], result: MobaLanesResult) -> None:
    canvas = profile["canvas"]
    meta = {
        "tile": result.tile,
        "cols": result.width,
        "rows": result.height,
        "game_w": canvas.get("game_w"),
        "game_h": canvas.get("game_h"),
        "lanes_y_px": [l["y_px"] for l in result.lanes],
        "lanes_row": [l["row"] for l in result.lanes],
        "gap_x_px": [g["x_px"] for g in result.gaps],
        "gap_col": [g["col"] for g in result.gaps],
        "profile_id": profile.get("id"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
