from __future__ import annotations

import json
from pathlib import Path

import pytest

from tilemap_generator.engines.moba_lanes import generate_moba_lanes_map
from tilemap_generator.game_contract import build_game_contract
from tilemap_generator.profiles import ProfileError, load_profile
from tilemap_generator.validate_map import MapValidationError, validate_moba_result

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "profiles" / "moba_3lane_lunacia.json"


def test_load_profile():
    p = load_profile(PROFILE)
    assert p["id"] == "moba_3lane_lunacia"
    assert p["layout"]["engine"] == "moba_lanes"


def test_moba_lanes_layout_and_validation():
    profile = load_profile(PROFILE)
    result = generate_moba_lanes_map(profile, seed=77)
    assert result.width == 94 and result.height == 50
    assert len(result.lanes) == 3
    assert len(result.gaps) == 3
    validate_moba_result(profile, result)
    # continuous path on mid lane center row
    mid = next(l for l in result.lanes if l["id"] == "mid")
    row = result.grid[int(mid["row"])]
    assert all(ch not in ("T", "F", "R") for ch in row)
    assert sum(1 for ch in row if ch == "P") >= 80


def test_game_json_shape():
    profile = load_profile(PROFILE)
    result = generate_moba_lanes_map(profile, seed=77)
    contract = build_game_contract(profile=profile, result=result, seed=77, artifacts={})
    assert contract["schema_version"] == 1
    assert contract["profile_id"] == "moba_3lane_lunacia"
    assert len(contract["lanes"]) == 3
    assert len(contract["forest"]["gaps"]) == 3
    types = {s["type"] for s in contract["structures"]}
    assert {"nest", "spire", "den"} <= types
    nests = [s for s in contract["structures"] if s["type"] == "nest"]
    assert len(nests) == 2


def test_validation_fails_when_gap_blocked():
    profile = load_profile(PROFILE)
    result = generate_moba_lanes_map(profile, seed=77)
    # Block a gap column with forest
    gc = result.gaps[0]["col"]
    # Block only between mid/bot lanes so continuous-lane checks still pass
    for r in range(28, 40):
        result.grid[r][gc] = "F"
    with pytest.raises(MapValidationError, match="Gap col"):
        validate_moba_result(profile, result)


def test_missing_profile():
    with pytest.raises(ProfileError):
        load_profile("profiles/does_not_exist.json")
