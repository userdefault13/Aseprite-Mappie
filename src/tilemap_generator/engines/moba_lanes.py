"""moba_lanes layout engine: lanes → forest bands → gap punches → Nest/Spire/Den POIs."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

from tilemap_generator.forest_edge import roughen_forest_edges

GRASS = "G"
PATH = "P"
TREE = "T"
FOREST = "F"
NEST = "N"
SPIRE = "S"
DEN = "D"

CHAR_FOR_TYPE = {"nest": NEST, "spire": SPIRE, "den": DEN}


@dataclass
class Structure:
    type: str
    team: str
    lane: str | None
    tier: int | None
    x: float
    y: float
    char: str


@dataclass
class MobaLanesResult:
    grid: list[list[str]]
    structures: list[Structure]
    lanes: list[dict[str, Any]]
    bases: dict[str, Any]
    forest_rects: list[dict[str, float]]
    gaps: list[dict[str, Any]]
    width: int
    height: int
    tile: int


def _px_to_col(x_px: float, tile: int, cols: int) -> int:
    return max(0, min(cols - 1, int(round(x_px / tile))))


def _px_to_row(y_px: float, tile: int, rows: int) -> int:
    return max(0, min(rows - 1, int(round(y_px / tile))))


def _band_rows(center_row: int, band_tiles: int, rows: int) -> range:
    half = max(1, band_tiles) // 2
    # For odd bands, center inclusive with floor half below/above
    lo = max(0, center_row - half)
    hi = min(rows - 1, center_row + half)
    # Ensure at least band_tiles when possible
    while (hi - lo + 1) < band_tiles and (lo > 0 or hi < rows - 1):
        if lo > 0:
            lo -= 1
        if (hi - lo + 1) < band_tiles and hi < rows - 1:
            hi += 1
    return range(lo, hi + 1)


def _place_forest_clusters(
    grid: list[list[str]],
    eligible: list[tuple[int, int]],
    forest_frac: float,
    tree_frac: float,
    rng: random.Random,
) -> None:
    if not eligible:
        return
    rng.shuffle(eligible)
    n = len(eligible)
    forest_n = int(round(n * max(0.0, min(1.0, forest_frac))))
    # Remaining vegetation as single trees among leftover grass cells in eligible
    # tree_frac is overall vegetation density relative to band; forest_frac of that is F
    veg_n = int(round(n * max(0.0, min(1.0, tree_frac))))
    forest_n = min(forest_n, veg_n)
    tree_n = max(0, veg_n - forest_n)

    # Cluster forests: seed then grow
    seeds = eligible[: max(1, forest_n // 8 or 1)]
    forest_cells: set[tuple[int, int]] = set()
    for sx, sy in seeds:
        if len(forest_cells) >= forest_n:
            break
        forest_cells.add((sx, sy))
    # Grow
    guard = 0
    while len(forest_cells) < forest_n and guard < forest_n * 20:
        guard += 1
        if not forest_cells:
            break
        cx, cy = rng.choice(tuple(forest_cells))
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1)):
            nx, ny = cx + dx, cy + dy
            if (nx, ny) in eligible and (nx, ny) not in forest_cells:
                forest_cells.add((nx, ny))
                if len(forest_cells) >= forest_n:
                    break
    for x, y in forest_cells:
        if grid[y][x] == GRASS:
            grid[y][x] = FOREST

    placed = 0
    for x, y in eligible:
        if placed >= tree_n:
            break
        if grid[y][x] == GRASS:
            grid[y][x] = TREE
            placed += 1


def _forest_rects_from_profile(
    layout: dict[str, Any],
    lanes: list[dict[str, Any]],
    tile: int,
    cols: int,
    rows: int,
) -> list[dict[str, float]]:
    """Build forest collision rects between lanes, split by gaps (matches lunacia reference pattern)."""
    forest = layout.get("forest") or {}
    band_h = float(forest.get("band_height_px") or 110)
    x_margin = float(forest.get("x_margin_px") or 180)
    gaps_cfg = forest.get("gaps") or {}
    gap_xs = list(gaps_cfg.get("x_px") or [])
    half_w = float(gaps_cfg.get("half_width_px") or 50)

    # Vertical centers between consecutive lanes
    lane_ys = [float(l["y_px"]) for l in lanes]
    mid_ys: list[float] = []
    for i in range(len(lane_ys) - 1):
        mid_ys.append((lane_ys[i] + lane_ys[i + 1]) / 2.0)

    # Horizontal segments: margin → gap, between gaps, last gap → right margin
    width_px = cols * tile
    cuts = [x_margin]
    for gx in gap_xs:
        cuts.append(float(gx) - half_w)
        cuts.append(float(gx) + half_w)
    cuts.append(width_px - x_margin)

    rects: list[dict[str, float]] = []
    for my in mid_ys:
        y0 = my - band_h / 2.0
        i = 0
        while i + 1 < len(cuts):
            x0, x1 = cuts[i], cuts[i + 1]
            # odd pairs after first are gap interiors (skip)
            if i % 2 == 1:
                i += 1
                continue
            w = x1 - x0
            if w >= tile:
                rects.append({"x": x0, "y": y0, "w": w, "h": band_h})
            i += 1
    return rects


def generate_moba_lanes_map(profile: dict[str, Any], seed: int) -> MobaLanesResult:
    canvas = profile["canvas"]
    layout = profile["layout"]
    art = profile.get("art") or {}
    walk = profile.get("walkability") or {}

    tile = int(canvas["tile"])
    cols = int(canvas["cols"])
    rows = int(canvas["rows"])
    rng = random.Random(seed)

    path_char = (walk.get("path_char") or PATH)[:1]
    forest_chars = walk.get("forest_chars") or [TREE, FOREST]

    lane_ids = list(layout.get("lane_ids") or [f"lane{i}" for i in range(int(layout.get("lane_count") or 3))])
    lanes_y = list(layout.get("lanes_y_px") or [])
    lanes_row = list(layout.get("lanes_row") or [])
    if len(lanes_row) < len(lane_ids):
        # derive from y
        lanes_row = [_px_to_row(y, tile, rows) for y in lanes_y]
    if len(lanes_y) < len(lane_ids):
        lanes_y = [float(r * tile) for r in lanes_row]

    band_tiles = int(layout.get("path_band_tiles") or max(1, int(round(float(layout.get("path_band_px") or 72) / tile))))
    path_half_h_px = float(layout.get("path_band_px") or band_tiles * tile) / 2.0

    lanes_meta = []
    for i, lid in enumerate(lane_ids):
        lanes_meta.append(
            {
                "id": lid,
                "y_px": float(lanes_y[i]),
                "row": int(lanes_row[i]),
                "path_half_h_px": path_half_h_px,
            }
        )

    grid = [[GRASS for _ in range(cols)] for _ in range(rows)]

    # 1) Path bands
    path_rows: set[int] = set()
    for lane in lanes_meta:
        for r in _band_rows(int(lane["row"]), band_tiles, rows):
            path_rows.add(r)
            for c in range(cols):
                grid[r][c] = path_char

    # 2) Forest ONLY inside the same AABB strips Lunacia uses for collision.
    #    No border/orphan trees outside rects (those looked solid but weren't collidable,
    #    while sparse grass inside rects felt like invisible walls).
    forest_cfg = layout.get("forest") or {}
    forest_rects = _forest_rects_from_profile(layout, lanes_meta, tile, cols, rows)

    # Dense fill: almost every cell in each rect becomes forest/tree
    fill_frac = float(art.get("forest_fill_frac") or max(0.85, float(art.get("forest_density") or 0.7)))
    tree_vs_forest = float(art.get("tree_density") or 0.28)
    for rect in forest_rects:
        c0 = max(0, int(rect["x"] // tile))
        c1 = min(cols, int(math.ceil((rect["x"] + rect["w"]) / tile)))
        r0 = max(0, int(rect["y"] // tile))
        r1 = min(rows, int(math.ceil((rect["y"] + rect["h"]) / tile)))
        cells = [(c, r) for r in range(r0, r1) for c in range(c0, c1)
                 if r not in path_rows and grid[r][c] == GRASS]
        rng.shuffle(cells)
        n_fill = int(round(len(cells) * min(1.0, max(0.0, fill_frac))))
        n_tree = int(round(n_fill * min(0.35, tree_vs_forest)))
        for i, (c, r) in enumerate(cells[:n_fill]):
            grid[r][c] = TREE if i < n_tree else FOREST

    # 3) Gap punches — clear vertical corridors of walkable grass through forest
    gaps_cfg = forest_cfg.get("gaps") or {}
    gap_cols = list(gaps_cfg.get("cols") or [])
    gap_xs = list(gaps_cfg.get("x_px") or [])
    half_w_px = float(gaps_cfg.get("half_width_px") or 50)
    half_cols = max(1, int(round(half_w_px / tile)))
    if not gap_cols and gap_xs:
        gap_cols = [_px_to_col(x, tile, cols) for x in gap_xs]
    if not gap_xs and gap_cols:
        gap_xs = [float(c * tile) for c in gap_cols]

    gaps_meta = []
    for i, gc in enumerate(gap_cols):
        gx = float(gap_xs[i]) if i < len(gap_xs) else float(gc * tile)
        gaps_meta.append({"x_px": gx, "half_width_px": half_w_px, "col": int(gc)})
        for r in range(rows):
            if r in path_rows:
                continue
            for c in range(max(0, gc - half_cols), min(cols, gc + half_cols + 1)):
                if grid[r][c] in (TREE, FOREST, *forest_chars):
                    grid[r][c] = GRASS

    # 3b) Roughen forest edges inside collision rects (keep gaps + lanes clear)
    art_edge = art if isinstance(art, dict) else {}
    edge_iters = int(
        art_edge.get(
            "forest_edge_iterations",
            (forest_cfg.get("edge_iterations") if isinstance(forest_cfg, dict) else None) or 2,
        )
    )
    if edge_iters > 0 and forest_rects:
        gap_blocked: set[tuple[int, int]] = set()
        for gc in gap_cols:
            for r in range(rows):
                for c in range(max(0, gc - half_cols), min(cols, gc + half_cols + 1)):
                    gap_blocked.add((c, r))
        eligible: set[tuple[int, int]] = set()
        for rect in forest_rects:
            c0 = max(0, int(rect["x"] // tile))
            c1 = min(cols, int(math.ceil((rect["x"] + rect["w"]) / tile)))
            r0 = max(0, int(rect["y"] // tile))
            r1 = min(rows, int(math.ceil((rect["y"] + rect["h"]) / tile)))
            for r in range(r0, r1):
                if r in path_rows:
                    continue
                for c in range(c0, c1):
                    if (c, r) in gap_blocked:
                        continue
                    eligible.add((c, r))
        roughen_forest_edges(
            grid,
            iterations=edge_iters,
            seed=seed + 777,
            # Softer than open-world: keep fill high inside collision AABBs
            erode_p=float(art_edge.get("forest_edge_erode", 0.35)),
            grow_p=float(art_edge.get("forest_edge_grow", 0.5)),
            forest_chars={TREE, FOREST},
            grow_onto={GRASS},
            protected_chars={PATH, NEST, SPIRE, DEN},
            eligible=eligible,
            default_forest_char=FOREST,
            grass_char=GRASS,
        )
        # Re-assert gap corridors stay walkable
        for gc in gap_cols:
            for r in range(rows):
                if r in path_rows:
                    continue
                for c in range(max(0, gc - half_cols), min(cols, gc + half_cols + 1)):
                    if grid[r][c] in (TREE, FOREST):
                        grid[r][c] = GRASS

    # 4) POIs
    bases = dict(layout.get("bases") or {})
    structures: list[Structure] = []
    pois = profile.get("pois") or {}
    legend_map = pois.get("legend") or {"N": "nest", "S": "spire", "D": "den"}
    type_to_char = {v: k for k, v in legend_map.items()}

    def stamp(ch: str, x_px: float, y_px: float) -> tuple[int, int]:
        c = _px_to_col(x_px, tile, cols)
        r = _px_to_row(y_px, tile, rows)
        grid[r][c] = ch
        # clear neighbors slightly for readability on path
        for dc, dr in ((0, 0),):
            rr, cc = r + dr, c + dc
            if 0 <= rr < rows and 0 <= cc < cols:
                grid[rr][cc] = ch
        return c, r

    for rule in pois.get("rules") or []:
        ptype = str(rule.get("type") or "")
        ch = type_to_char.get(ptype) or CHAR_FOR_TYPE.get(ptype) or "S"
        placement = rule.get("placement")

        if placement == "base_center":
            for team, base in bases.items():
                x = float(base.get("x_px") or 0)
                # nest on mid lane vertically
                mid = next((l for l in lanes_meta if l["id"] == "mid"), lanes_meta[len(lanes_meta) // 2])
                y = float(mid["y_px"])
                stamp(ch, x, y)
                structures.append(
                    Structure(type=ptype, team=str(team), lane=None, tier=None, x=x, y=y, char=ch)
                )
            continue

        if placement in ("along_lane", "near_base_lane"):
            player_xs = rule.get("player_x_px")
            enemy_xs = rule.get("enemy_x_px")
            tiers = list(rule.get("tiers") or [])
            for lane in lanes_meta:
                y = float(lane["y_px"])
                lid = str(lane["id"])
                # player
                if isinstance(player_xs, list):
                    for ti, x in enumerate(player_xs):
                        tier = tiers[ti] if ti < len(tiers) else (ti + 1 if ptype == "spire" else None)
                        stamp(ch, float(x), y)
                        structures.append(
                            Structure(
                                type=ptype,
                                team="player",
                                lane=lid,
                                tier=tier,
                                x=float(x),
                                y=y,
                                char=ch,
                            )
                        )
                elif player_xs is not None:
                    stamp(ch, float(player_xs), y)
                    structures.append(
                        Structure(
                            type=ptype, team="player", lane=lid, tier=None, x=float(player_xs), y=y, char=ch
                        )
                    )
                # enemy
                if isinstance(enemy_xs, list):
                    for ti, x in enumerate(enemy_xs):
                        tier = tiers[ti] if ti < len(tiers) else (ti + 1 if ptype == "spire" else None)
                        stamp(ch, float(x), y)
                        structures.append(
                            Structure(
                                type=ptype,
                                team="enemy",
                                lane=lid,
                                tier=tier,
                                x=float(x),
                                y=y,
                                char=ch,
                            )
                        )
                elif enemy_xs is not None:
                    stamp(ch, float(enemy_xs), y)
                    structures.append(
                        Structure(
                            type=ptype, team="enemy", lane=lid, tier=None, x=float(enemy_xs), y=y, char=ch
                        )
                    )

    # forest_rects already computed above to match tile fill

    return MobaLanesResult(
        grid=grid,
        structures=structures,
        lanes=lanes_meta,
        bases=bases,
        forest_rects=forest_rects,
        gaps=gaps_meta,
        width=cols,
        height=rows,
        tile=tile,
    )
