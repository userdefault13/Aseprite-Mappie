"""Shared legend (char → tile_id) for ASCII maps. Used by map generation and paint pipeline."""
from __future__ import annotations

from typing import Any


# Canonical legend for procedural maps. Both map_gen and paint use this when no config overrides.
# G = grass interior (1-13), B = continent shore (98-118), L = lake shore (51-59), R = river bank (60-61), I = hill (14-50)
# ~ = shallow water (adjacent to land), ` = deep water (surrounded by water)
DEFAULT_LEGEND: dict[str, int] = {
    "G": 1,
    ".": 1,
    "B": 98,  # Continent shoreline
    "L": 51,  # Lake shoreline
    "R": 60,  # River bank
    "I": 14,  # Hill
    "~": 2,  # Shallow water
    "`": 3,  # Deep water
    "T": 4,
    "F": 5,
    "P": 6,
    "S": 7,
    "J": 8,
    "M": 9,
    "H": 10,
    "C": 11,
    "D": 12,
    "N": 13,
}


def get_legend_from_config(config: dict[str, Any] | None) -> dict[str, int] | None:
    """Extract and validate legend from terrain config. Returns None if missing or invalid."""
    if not config or not isinstance(config.get("legend"), dict):
        return None
    raw = config["legend"]
    legend: dict[str, int] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or len(key) != 1:
            continue
        if not isinstance(value, int) or value < 0:
            continue
        legend[key] = value
    return legend if legend else None


def resolve_legend(
    config: dict[str, Any] | None,
    file_legend: dict[str, int] | None,
) -> dict[str, int]:
    """Resolve legend: config > file > default."""
    cfg_legend = get_legend_from_config(config)
    if cfg_legend:
        return cfg_legend
    if file_legend:
        return file_legend
    return DEFAULT_LEGEND.copy()


def get_terrain_rules(config: dict[str, Any] | None) -> list[str]:
    """Extract _rules from terrain config. Returns empty list if missing."""
    if not config or not isinstance(config.get("_rules"), list):
        return []
    return [str(r) for r in config["_rules"] if isinstance(r, str)]
