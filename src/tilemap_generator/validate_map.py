"""Post-gen validation against map-criteria profile.validation."""
from __future__ import annotations

from typing import Any

from tilemap_generator.engines.moba_lanes import MobaLanesResult, PATH, GRASS, TREE, FOREST


class MapValidationError(ValueError):
    """Generated map failed profile validation."""


def _band_rows(center_row: int, band_tiles: int, rows: int) -> range:
    half = max(1, band_tiles) // 2
    lo = max(0, center_row - half)
    hi = min(rows - 1, center_row + half)
    while (hi - lo + 1) < band_tiles and (lo > 0 or hi < rows - 1):
        if lo > 0:
            lo -= 1
        if (hi - lo + 1) < band_tiles and hi < rows - 1:
            hi += 1
    return range(lo, hi + 1)


def validate_moba_result(profile: dict[str, Any], result: MobaLanesResult) -> None:
    v = profile.get("validation") or {}
    if not v:
        return

    walk = profile.get("walkability") or {}
    path_char = (walk.get("path_char") or PATH)[:1]
    solid = set(walk.get("solid_chars") or [TREE, FOREST, "R"])
    walkable = set(walk.get("walkable_chars") or [GRASS, ".", path_char, "D", "S", "N"])
    layout = profile.get("layout") or {}
    band_tiles = int(layout.get("path_band_tiles") or 5)
    canvas = profile["canvas"]
    tile = int(canvas["tile"])
    tol = v.get("tolerances") or {}
    lane_tol = float(tol.get("lane_y_px") or 8)
    gap_tol = float(tol.get("gap_x_px") or 16)

    grid = result.grid
    rows, cols = result.height, result.width

    if v.get("pixel_size_must_match_canvas"):
        width_px = cols * tile
        height_px = rows * tile
        game_w = canvas.get("game_w")
        game_h = canvas.get("game_h")
        # Allow width_px == game_w or game_w+tile (94*16=1504 vs 1500)
        if game_w is not None and abs(width_px - int(game_w)) > tile:
            raise MapValidationError(
                f"Canvas width_px {width_px} does not match profile game_w {game_w} (tol {tile}px)"
            )
        if game_h is not None and abs(height_px - int(game_h)) > tile:
            raise MapValidationError(
                f"Canvas height_px {height_px} does not match profile game_h {game_h} (tol {tile}px)"
            )
        if cols != int(canvas["cols"]) or rows != int(canvas["rows"]):
            raise MapValidationError(
                f"Grid size {cols}x{rows} != profile canvas {canvas['cols']}x{canvas['rows']}"
            )

    if v.get("require_continuous_lanes"):
        for lane in result.lanes:
            r0 = int(lane["row"])
            band = list(_band_rows(r0, band_tiles, rows))
            # At least one row in the band must be continuous walkable/path across all cols
            ok = False
            for r in band:
                solid_hits = sum(1 for c in range(cols) if grid[r][c] in solid)
                pathish = sum(1 for c in range(cols) if grid[r][c] in walkable or grid[r][c] == path_char)
                if solid_hits == 0 and pathish == cols:
                    ok = True
                    break
            if not ok:
                # softer: majority path chars
                for r in band:
                    path_n = sum(1 for c in range(cols) if grid[r][c] == path_char)
                    if path_n >= cols * 0.85 and all(grid[r][c] not in solid for c in range(cols)):
                        ok = True
                        break
            if not ok:
                raise MapValidationError(
                    f"Lane '{lane['id']}' row~{r0} is not a continuous walkable path band"
                )

            # y tolerance vs profile
            expected_ys = list((layout.get("lanes_y_px") or []))
            idx = next((i for i, l in enumerate(result.lanes) if l["id"] == lane["id"]), None)
            if idx is not None and idx < len(expected_ys):
                if abs(float(lane["y_px"]) - float(expected_ys[idx])) > lane_tol:
                    raise MapValidationError(
                        f"Lane '{lane['id']}' y_px {lane['y_px']} off profile {expected_ys[idx]} (tol {lane_tol})"
                    )

    if v.get("forbid_solid_in_path_band"):
        for lane in result.lanes:
            for r in _band_rows(int(lane["row"]), band_tiles, rows):
                for c in range(cols):
                    if grid[r][c] in solid:
                        raise MapValidationError(
                            f"Solid '{grid[r][c]}' in path band at ({c},{r}) lane '{lane['id']}'"
                        )

    if v.get("require_gap_connectivity"):
        gap_cols = [int(g["col"]) for g in result.gaps]
        expected_gaps = list(((layout.get("forest") or {}).get("gaps") or {}).get("cols") or [])
        path_rows: set[int] = set()
        for lane in result.lanes:
            path_rows.update(_band_rows(int(lane["row"]), band_tiles, rows))
        # Between-lane row ranges (exclusive of path bands)
        lane_rows_sorted = sorted(int(l["row"]) for l in result.lanes)
        inter_ranges: list[range] = []
        for a, b in zip(lane_rows_sorted, lane_rows_sorted[1:]):
            lo, hi = a + 1, b - 1
            if lo <= hi:
                inter_ranges.append(range(lo, hi + 1))
        for i, gc in enumerate(gap_cols):
            if i < len(expected_gaps) and abs(gc - int(expected_gaps[i])) > max(1, int(gap_tol // tile)):
                raise MapValidationError(
                    f"Gap col {gc} off profile {expected_gaps[i]} (tol {gap_tol}px)"
                )
            for rr in inter_ranges:
                for r in rr:
                    if r in path_rows:
                        continue
                    ch = grid[r][gc]
                    if ch in solid:
                        raise MapValidationError(
                            f"Gap col {gc} blocked by solid '{ch}' at row {r}"
                        )

    if v.get("require_pois"):
        required = set(v.get("require_pois") or [])
        present = {s.type for s in result.structures}
        missing = required - present
        if missing:
            raise MapValidationError(f"Missing required POI types: {sorted(missing)}")
        # Count sanity from rules when present
        rules = (profile.get("pois") or {}).get("rules") or []
        lane_count = len(result.lanes)
        for rule in rules:
            ptype = rule.get("type")
            if ptype == "nest" and rule.get("per_team"):
                need = int(rule["per_team"]) * 2  # player+enemy
                got = sum(1 for s in result.structures if s.type == "nest")
                if got < need:
                    raise MapValidationError(f"Expected >= {need} nests, got {got}")
            if ptype == "spire" and rule.get("per_team_per_lane"):
                need = int(rule["per_team_per_lane"]) * 2 * lane_count
                got = sum(1 for s in result.structures if s.type == "spire")
                if got < need:
                    raise MapValidationError(f"Expected >= {need} spires, got {got}")
            if ptype == "den" and rule.get("per_team_per_lane"):
                need = int(rule["per_team_per_lane"]) * 2 * lane_count
                got = sum(1 for s in result.structures if s.type == "den")
                if got < need:
                    raise MapValidationError(f"Expected >= {need} dens, got {got}")
