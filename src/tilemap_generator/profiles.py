"""Load and apply Mappie map-criteria profiles."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = PROJECT_ROOT / "docs" / "contracts" / "map-criteria.schema.json"


class ProfileError(ValueError):
    """Invalid or unusable criteria profile."""


def load_profile(path: str | Path) -> dict[str, Any]:
    p = Path(path).expanduser()
    if not p.is_absolute():
        candidate = (Path.cwd() / p).resolve()
        if not candidate.exists():
            candidate = (PROJECT_ROOT / p).resolve()
        p = candidate
    if not p.exists():
        raise ProfileError(f"Profile not found: {path}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProfileError(f"Profile JSON invalid ({p}): {exc}") from exc
    if not isinstance(data, dict):
        raise ProfileError("Profile must be a JSON object")
    for key in ("id", "version", "genre", "canvas", "layout", "walkability", "outputs"):
        if key not in data:
            raise ProfileError(f"Profile missing required field: {key}")
    layout = data.get("layout") or {}
    if not isinstance(layout, dict) or "engine" not in layout:
        raise ProfileError("Profile layout.engine is required")
    _soft_validate_schema(data)
    data["_profile_path"] = str(p)
    return data


def _soft_validate_schema(data: dict[str, Any]) -> None:
    if not SCHEMA_PATH.exists():
        return
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as exc:
        raise ProfileError(f"Profile failed schema validation: {exc.message}") from exc


def apply_profile_to_args(args: Any, profile: dict[str, Any]) -> None:
    """Fill argparse namespace from profile; CLI values that were explicitly set win when non-None overrides."""
    canvas = profile["canvas"]
    art = profile.get("art") or {}

    if getattr(args, "width", None) in (None, 0):
        args.width = int(canvas["cols"])
    if getattr(args, "height", None) in (None, 0):
        args.height = int(canvas["rows"])

    def _maybe_density(attr: str, key: str, default: float = 0.0) -> None:
        cur = getattr(args, attr, None)
        if cur is None:
            setattr(args, attr, float(art.get(key, default)))

    # Densities: if still at argparse "unset" sentinel None, take from profile
    if getattr(args, "tree_density", None) is None:
        args.tree_density = float(art.get("tree_density", 0.22))
    if getattr(args, "forest_density", None) is None:
        args.forest_density = float(art.get("forest_density", 0.65))
    if getattr(args, "water_density", None) is None:
        args.water_density = float(art.get("water_density", 0.0))
    if getattr(args, "hill_density", None) is None:
        args.hill_density = float(art.get("hill_density", 0.0))

    if not getattr(args, "seed", None):
        args.seed = int(profile.get("seed_default") or 0)

    if not getattr(args, "terrain_config", None):
        tc = art.get("terrain_config") or ""
        if tc:
            args.terrain_config = tc

    hint = art.get("map_mode_hint")
    if hint in ("island", "continent") and getattr(args, "map_mode", None) is None:
        args.map_mode = hint

    tile = int(canvas.get("tile") or 16)
    if getattr(args, "preview_tile_size", None) in (None, 0):
        args.preview_tile_size = tile

    args.profile = profile
    args.profile_id = profile.get("id")
