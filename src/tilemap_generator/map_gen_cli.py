from __future__ import annotations

import argparse
import heapq
import json
import os
import random
import shutil
import struct
import subprocess
from pathlib import Path


GRASS_CHAR = "G"
WATER_CHAR = "~"
TREE_CHAR = "T"
FOREST_CHAR = "F"
PATH_CHAR = "P"
SPAWN_CHAR = "S"
JOIN_CHAR = "J"
MINE_CHAR = "M"
SHOP_CHAR = "H"
CREEP_CHAR = "C"
DEAD_END_CHAR = "D"
SECRET_NPC_CHAR = "N"

Point = tuple[int, int]
MAC_ASEPRITE_BIN = Path("/Applications/Aseprite.app/Contents/MacOS/aseprite")
PREVIEW_COLORS: dict[str, tuple[int, int, int]] = {
    GRASS_CHAR: (104, 178, 76),
    ".": (104, 178, 76),
    WATER_CHAR: (72, 132, 224),
    TREE_CHAR: (46, 108, 54),
    FOREST_CHAR: (30, 78, 40),
    PATH_CHAR: (181, 152, 102),
    SPAWN_CHAR: (250, 228, 92),
    JOIN_CHAR: (255, 161, 77),
    MINE_CHAR: (125, 126, 134),
    SHOP_CHAR: (214, 123, 73),
    CREEP_CHAR: (194, 76, 76),
    DEAD_END_CHAR: (240, 95, 95),
    SECRET_NPC_CHAR: (86, 208, 220),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a procedural ASCII map with spawn clearings, Perlin-guided paths, "
            "and gameplay POIs."
        )
    )
    parser.add_argument("--width", type=int, required=True, help="Map width in tiles.")
    parser.add_argument("--height", type=int, required=True, help="Map height in tiles.")
    parser.add_argument(
        "--tree-density",
        type=float,
        required=True,
        help="Fraction of map covered by vegetation (0.0 to 1.0).",
    )
    parser.add_argument(
        "--forest-density",
        type=float,
        required=True,
        help="Fraction of vegetation that becomes forest clusters (0.0 to 1.0).",
    )
    parser.add_argument(
        "--water-density",
        type=float,
        required=True,
        help="Fraction of map covered by water (0.0 to 1.0).",
    )
    parser.add_argument("--spawn-count", type=int, default=8, help="Number of spawn points.")
    parser.add_argument(
        "--spawn-clearing-size",
        type=int,
        default=15,
        help="Odd square size of guaranteed grass clearing around each spawn.",
    )
    parser.add_argument(
        "--join-point-count",
        type=int,
        default=0,
        help="Join points for path network (0 = auto based on spawn count).",
    )
    parser.add_argument(
        "--path-width-threshold",
        type=int,
        default=3,
        help="Minimum path width in tiles.",
    )
    parser.add_argument(
        "--path-perlin-scale",
        type=float,
        default=14.0,
        help="Perlin scale for path shaping (larger = smoother).",
    )
    parser.add_argument(
        "--path-perlin-weight",
        type=float,
        default=1.8,
        help="How strongly Perlin field influences routing cost.",
    )
    parser.add_argument("--mine-count", type=int, default=4, help="Number of mines to place.")
    parser.add_argument("--shop-count", type=int, default=3, help="Number of shops to place.")
    parser.add_argument(
        "--creep-zone-count",
        type=int,
        default=6,
        help="Number of creep zones to place.",
    )
    parser.add_argument(
        "--creep-zone-radius",
        type=int,
        default=2,
        help="Creep zone radius in tiles.",
    )
    parser.add_argument(
        "--dead-end-count",
        type=int,
        default=8,
        help="Number of dead-end path branches to add.",
    )
    parser.add_argument(
        "--require-secret-npc-path",
        action="store_true",
        help="If set, adds one secret NPC reachable by exactly one branch path.",
    )
    parser.add_argument("--seed", type=int, default=0, help="Optional RNG seed.")
    parser.add_argument("--out", required=True, help="Output ASCII map path.")
    parser.add_argument(
        "--legend-out",
        default="",
        help="Optional legend JSON path (defaults to <out>.legend.json).",
    )
    parser.add_argument(
        "--preview-out",
        default="",
        help="Optional BMP preview path (defaults to <out>.preview.bmp when preview is enabled).",
    )
    parser.add_argument(
        "--preview-tile-size",
        type=int,
        default=8,
        help="Pixel size per tile in preview image.",
    )
    parser.add_argument(
        "--preview-in-aseprite",
        action="store_true",
        help="Open a generated map preview in Aseprite when done.",
    )
    parser.add_argument(
        "--aseprite-bin",
        default="",
        help="Optional explicit path to aseprite binary for preview opening.",
    )
    return parser


def validate_density(value: float, name: str) -> None:
    if value < 0.0 or value > 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0")


def sign(value: int) -> int:
    if value < 0:
        return -1
    if value > 0:
        return 1
    return 0


def clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, value))


def all_positions(width: int, height: int) -> list[Point]:
    return [(x, y) for y in range(height) for x in range(width)]


def neighbors4(x: int, y: int, width: int, height: int) -> list[Point]:
    out: list[Point] = []
    if x > 0:
        out.append((x - 1, y))
    if x < width - 1:
        out.append((x + 1, y))
    if y > 0:
        out.append((x, y - 1))
    if y < height - 1:
        out.append((x, y + 1))
    return out


def manhattan(a: Point, b: Point) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def square_cells(center: Point, half: int, width: int, height: int) -> set[Point]:
    cx, cy = center
    out: set[Point] = set()
    for y in range(cy - half, cy + half + 1):
        for x in range(cx - half, cx + half + 1):
            if 0 <= x < width and 0 <= y < height:
                out.add((x, y))
    return out


def dilate_cells(cells: set[Point], radius: int, width: int, height: int) -> set[Point]:
    if radius <= 0:
        return set(cells)
    out: set[Point] = set()
    for cx, cy in cells:
        for y in range(cy - radius, cy + radius + 1):
            if y < 0 or y >= height:
                continue
            for x in range(cx - radius, cx + radius + 1):
                if x < 0 or x >= width:
                    continue
                out.add((x, y))
    return out


def place_spawn_points(
    width: int, height: int, spawn_count: int, clearing_size: int, rng: random.Random
) -> list[Point]:
    if spawn_count <= 0:
        raise ValueError("--spawn-count must be > 0")
    if clearing_size <= 0 or clearing_size % 2 == 0:
        raise ValueError("--spawn-clearing-size must be a positive odd integer.")
    if width < clearing_size or height < clearing_size:
        raise ValueError(
            f"Map {width}x{height} is too small for clearing size {clearing_size}."
        )

    half = clearing_size // 2
    candidates = [
        (x, y)
        for y in range(half, height - half)
        for x in range(half, width - half)
    ]
    rng.shuffle(candidates)

    spawn_points: list[Point] = []
    for candidate in candidates:
        overlap = False
        for existing in spawn_points:
            if (
                abs(candidate[0] - existing[0]) <= clearing_size
                and abs(candidate[1] - existing[1]) <= clearing_size
            ):
                overlap = True
                break
        if overlap:
            continue
        spawn_points.append(candidate)
        if len(spawn_points) == spawn_count:
            return spawn_points

    raise ValueError(
        f"Could not place {spawn_count} spawn points with {clearing_size}x{clearing_size} clearings. "
        "Increase canvas size or reduce spawn count/clearing size."
    )


def build_clearing_cells(
    spawn_points: list[Point], clearing_size: int, width: int, height: int
) -> set[Point]:
    half = clearing_size // 2
    cells: set[Point] = set()
    for point in spawn_points:
        cells.update(square_cells(point, half, width, height))
    return cells


def place_join_points(
    width: int, height: int, join_count: int, forbidden: set[Point], rng: random.Random
) -> list[Point]:
    if join_count <= 0:
        return []

    candidates = [point for point in all_positions(width, height) if point not in forbidden]
    if len(candidates) < join_count:
        raise ValueError(
            f"Not enough space for {join_count} join points after spawn clearings."
        )

    selected: list[Point] = [rng.choice(candidates)]
    remaining = set(candidates)
    remaining.remove(selected[0])

    while len(selected) < join_count:
        best_point: Point | None = None
        best_score = -1
        for point in remaining:
            score = min(manhattan(point, chosen) for chosen in selected)
            if score > best_score:
                best_score = score
                best_point = point
        if best_point is None:
            break
        selected.append(best_point)
        remaining.remove(best_point)

    if len(selected) < join_count:
        raise ValueError(f"Could not place all {join_count} join points.")
    return selected


def build_mst(points: list[Point]) -> list[tuple[Point, Point]]:
    if len(points) < 2:
        return []

    visited = {0}
    edges: list[tuple[Point, Point]] = []
    while len(visited) < len(points):
        best: tuple[int, int, int] | None = None
        for i in visited:
            for j in range(len(points)):
                if j in visited:
                    continue
                dist = manhattan(points[i], points[j])
                if best is None or dist < best[0]:
                    best = (dist, i, j)
        if best is None:
            break
        _, i, j = best
        visited.add(j)
        edges.append((points[i], points[j]))
    return edges


def spawn_anchor_outside_clearing(
    spawn: Point,
    target: Point,
    clearing_half: int,
    path_radius: int,
    width: int,
    height: int,
) -> Point:
    sx, sy = spawn
    tx, ty = target
    dx = tx - sx
    dy = ty - sy
    offset = clearing_half + path_radius + 1

    if abs(dx) >= abs(dy):
        step = sign(dx) or 1
        anchor = (sx + step * offset, sy)
    else:
        step = sign(dy) or 1
        anchor = (sx, sy + step * offset)

    return (
        clamp(anchor[0], 0, width - 1),
        clamp(anchor[1], 0, height - 1),
    )


def fade(t: float) -> float:
    return t * t * t * (t * (t * 6 - 15) + 10)


def lerp(a: float, b: float, t: float) -> float:
    return a + t * (b - a)


def hash01(ix: int, iy: int, seed: int) -> float:
    n = ix * 374761393 + iy * 668265263 + seed * 700001
    n = (n ^ (n >> 13)) * 1274126177
    n = n ^ (n >> 16)
    return (n & 0xFFFFFFFF) / 0xFFFFFFFF


def value_noise_2d(x: float, y: float, seed: int) -> float:
    x0 = int(x // 1)
    y0 = int(y // 1)
    x1 = x0 + 1
    y1 = y0 + 1
    sx = fade(x - x0)
    sy = fade(y - y0)
    n00 = hash01(x0, y0, seed)
    n10 = hash01(x1, y0, seed)
    n01 = hash01(x0, y1, seed)
    n11 = hash01(x1, y1, seed)
    nx0 = lerp(n00, n10, sx)
    nx1 = lerp(n01, n11, sx)
    return lerp(nx0, nx1, sy)


def perlin_like(x: float, y: float, seed: int) -> float:
    total = 0.0
    amplitude = 1.0
    frequency = 1.0
    norm = 0.0
    for octave in range(3):
        total += amplitude * value_noise_2d(x * frequency, y * frequency, seed + octave * 9973)
        norm += amplitude
        amplitude *= 0.5
        frequency *= 2.0
    return total / norm if norm > 0 else 0.5


def fallback_l_path(start: Point, end: Point) -> list[Point]:
    x, y = start
    tx, ty = end
    out = [(x, y)]
    while x != tx:
        x += sign(tx - x)
        out.append((x, y))
    while y != ty:
        y += sign(ty - y)
        out.append((x, y))
    return out


def find_perlin_path(
    start: Point,
    end: Point,
    width: int,
    height: int,
    forbidden: set[Point],
    seed: int,
    scale: float,
    weight: float,
) -> list[Point]:
    if start == end:
        return [start]

    scale = max(scale, 1.0)
    open_heap: list[tuple[float, Point]] = []
    heapq.heappush(open_heap, (0.0, start))
    came_from: dict[Point, Point] = {}
    g_score: dict[Point, float] = {start: 0.0}

    while open_heap:
        _, current = heapq.heappop(open_heap)
        if current == end:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()
            return path

        cx, cy = current
        for nx, ny in neighbors4(cx, cy, width, height):
            neighbor = (nx, ny)
            if neighbor in forbidden and neighbor not in (start, end):
                continue
            noise = perlin_like(nx / scale, ny / scale, seed)
            step_cost = 1.0 + (1.0 - noise) * max(weight, 0.0)
            tentative = g_score[current] + step_cost
            if tentative >= g_score.get(neighbor, float("inf")):
                continue
            came_from[neighbor] = current
            g_score[neighbor] = tentative
            heuristic = manhattan(neighbor, end)
            heapq.heappush(open_heap, (tentative + heuristic, neighbor))

    return fallback_l_path(start, end)


def carve_path(
    grid: list[list[str]],
    route: list[Point],
    path_width: int,
    path_cells: set[Point],
    forbidden: set[Point],
) -> None:
    height = len(grid)
    width = len(grid[0])
    radius = path_width // 2
    for cx, cy in route:
        for y in range(cy - radius, cy + radius + 1):
            if y < 0 or y >= height:
                continue
            for x in range(cx - radius, cx + radius + 1):
                if x < 0 or x >= width:
                    continue
                cell = (x, y)
                if cell in forbidden:
                    continue
                if grid[y][x] in (SPAWN_CHAR, JOIN_CHAR):
                    continue
                grid[y][x] = PATH_CHAR
                path_cells.add(cell)


def route_is_valid(route: list[Point], forbidden: set[Point], blocked_paths: set[Point]) -> bool:
    if len(route) < 2:
        return False
    for cell in route:
        if cell in forbidden:
            return False
        if cell in blocked_paths:
            return False
    return True


def path_degree(cell: Point, path_cells: set[Point], width: int, height: int) -> int:
    x, y = cell
    return sum(1 for n in neighbors4(x, y, width, height) if n in path_cells)


def build_branch(
    grid: list[list[str]],
    path_cells: set[Point],
    base_forbidden: set[Point],
    rng: random.Random,
    seed: int,
    scale: float,
    weight: float,
    path_width: int,
    min_length: int,
    max_length: int,
    search_attempts: int,
) -> list[Point] | None:
    height = len(grid)
    width = len(grid[0])
    path_radius = path_width // 2

    connector_pool = [
        c for c in path_cells if path_degree(c, path_cells, width, height) <= 2
    ]
    if not connector_pool:
        connector_pool = list(path_cells)
    if not connector_pool:
        return None

    candidate_targets = [
        p
        for p in all_positions(width, height)
        if p not in base_forbidden and p not in path_cells and grid[p[1]][p[0]] == GRASS_CHAR
    ]
    if not candidate_targets:
        return None

    path_buffer = dilate_cells(path_cells, max(path_radius, 1), width, height)

    for attempt in range(search_attempts):
        connector = rng.choice(connector_pool)
        cx, cy = connector
        starts = [
            n
            for n in neighbors4(cx, cy, width, height)
            if n not in base_forbidden and n not in path_cells and grid[n[1]][n[0]] == GRASS_CHAR
        ]
        if not starts:
            continue
        start = rng.choice(starts)

        local_targets = [
            p
            for p in candidate_targets
            if min_length <= manhattan(p, connector) <= max_length
        ]
        if not local_targets:
            continue
        rng.shuffle(local_targets)
        local_targets = local_targets[: min(120, len(local_targets))]

        branch_forbidden = set(base_forbidden) | (path_buffer - {start})
        for target in local_targets:
            route = find_perlin_path(
                start,
                target,
                width,
                height,
                forbidden=branch_forbidden,
                seed=seed + attempt * 17,
                scale=scale,
                weight=weight,
            )
            if len(route) < min_length:
                continue
            if not route_is_valid(route, branch_forbidden, path_cells):
                continue
            return route

    return None


def place_clustered(
    grid: list[list[str]],
    fill_char: str,
    target_count: int,
    rng: random.Random,
    blocked: set[Point],
) -> int:
    if target_count <= 0:
        return 0

    height = len(grid)
    width = len(grid[0])
    available = [
        (x, y)
        for x, y in all_positions(width, height)
        if grid[y][x] == GRASS_CHAR and (x, y) not in blocked
    ]
    if not available:
        return 0

    seed_count = max(1, min(len(available), target_count, int(target_count * 0.08) + 1))
    seeds = rng.sample(available, k=seed_count)
    frontier = list(seeds)

    placed = 0
    for x, y in seeds:
        if grid[y][x] == GRASS_CHAR and (x, y) not in blocked:
            grid[y][x] = fill_char
            placed += 1
            if placed >= target_count:
                return placed

    while placed < target_count and frontier:
        idx = rng.randrange(len(frontier))
        x, y = frontier[idx]
        expanded = False
        neighbors = neighbors4(x, y, width, height)
        rng.shuffle(neighbors)
        for nx, ny in neighbors:
            if grid[ny][nx] != GRASS_CHAR or (nx, ny) in blocked:
                continue
            grid[ny][nx] = fill_char
            frontier.append((nx, ny))
            placed += 1
            expanded = True
            break
        if not expanded:
            frontier.pop(idx)

    if placed < target_count:
        available = [
            (x, y)
            for x, y in all_positions(width, height)
            if grid[y][x] == GRASS_CHAR and (x, y) not in blocked
        ]
        rng.shuffle(available)
        for x, y in available[: target_count - placed]:
            grid[y][x] = fill_char
            placed += 1

    return placed


def pick_spread_points(candidates: list[Point], count: int, rng: random.Random) -> list[Point]:
    if count <= 0:
        return []
    if len(candidates) < count:
        raise ValueError(f"Not enough valid positions for count={count}.")

    selected: list[Point] = [rng.choice(candidates)]
    remaining = set(candidates)
    remaining.remove(selected[0])

    while len(selected) < count:
        best: Point | None = None
        best_score = -1
        for point in remaining:
            score = min(manhattan(point, chosen) for chosen in selected)
            if score > best_score:
                best_score = score
                best = point
        if best is None:
            break
        selected.append(best)
        remaining.remove(best)

    if len(selected) < count:
        raise ValueError(f"Could not place all {count} spread points.")
    return selected


def place_access_pois(
    grid: list[list[str]],
    path_cells: set[Point],
    blocked: set[Point],
    count: int,
    marker: str,
    label: str,
    rng: random.Random,
) -> list[Point]:
    if count <= 0:
        return []

    height = len(grid)
    width = len(grid[0])
    candidates: list[Point] = []
    for x, y in all_positions(width, height):
        if (x, y) in blocked:
            continue
        if grid[y][x] == WATER_CHAR:
            continue
        if not any(n in path_cells for n in neighbors4(x, y, width, height)):
            continue
        candidates.append((x, y))

    if len(candidates) < count:
        raise ValueError(
            f"Not enough accessible tiles for {label} count={count}. "
            "Increase map size or lower feature counts."
        )

    points = pick_spread_points(candidates, count, rng)
    for x, y in points:
        grid[y][x] = marker
    return points


def place_creep_zones(
    grid: list[list[str]],
    count: int,
    radius: int,
    blocked: set[Point],
    rng: random.Random,
) -> tuple[list[Point], set[Point]]:
    if count <= 0:
        return [], set()
    if radius <= 0:
        raise ValueError("--creep-zone-radius must be > 0")

    height = len(grid)
    width = len(grid[0])
    candidates = [
        p
        for p in all_positions(width, height)
        if p not in blocked and grid[p[1]][p[0]] != WATER_CHAR
    ]
    if len(candidates) < count:
        raise ValueError(
            f"Not enough free cells for creep-zone-count={count}. "
            "Increase map size or reduce feature counts."
        )

    centers = pick_spread_points(candidates, count, rng)
    creep_cells: set[Point] = set()

    for cx, cy in centers:
        for y in range(cy - radius, cy + radius + 1):
            if y < 0 or y >= height:
                continue
            for x in range(cx - radius, cx + radius + 1):
                if x < 0 or x >= width:
                    continue
                if manhattan((cx, cy), (x, y)) > radius:
                    continue
                cell = (x, y)
                if cell in blocked:
                    continue
                if grid[y][x] == WATER_CHAR:
                    continue
                grid[y][x] = CREEP_CHAR
                creep_cells.add(cell)
    return centers, creep_cells


def resolve_aseprite_bin(explicit: str) -> Path:
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)

    env_candidate = os.getenv("ASEPRITE_BIN")
    if env_candidate:
        candidates.append(env_candidate)

    in_path = shutil.which("aseprite")
    if in_path:
        candidates.append(in_path)

    if MAC_ASEPRITE_BIN.exists():
        candidates.append(str(MAC_ASEPRITE_BIN))

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        path = Path(candidate).expanduser()
        if path.exists() and path.is_file():
            return path

    raise FileNotFoundError(
        "Aseprite binary not found. Set --aseprite-bin or ASEPRITE_BIN."
    )


def write_preview_bmp(path: Path, grid: list[list[str]], tile_size: int) -> None:
    if tile_size <= 0:
        raise ValueError("--preview-tile-size must be > 0")
    if not grid or not grid[0]:
        raise ValueError("Cannot preview empty grid.")

    tiles_h = len(grid)
    tiles_w = len(grid[0])
    img_w = tiles_w * tile_size
    img_h = tiles_h * tile_size
    row_bytes = img_w * 3
    padding = (4 - (row_bytes % 4)) % 4
    pixel_data_size = (row_bytes + padding) * img_h
    file_size = 14 + 40 + pixel_data_size

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.write(struct.pack("<2sIHHI", b"BM", file_size, 0, 0, 54))
        f.write(struct.pack("<IIIHHIIIIII", 40, img_w, img_h, 1, 24, 0, pixel_data_size, 2835, 2835, 0, 0))

        for py in range(img_h - 1, -1, -1):
            tile_y = py // tile_size
            row = bytearray()
            for px in range(img_w):
                tile_x = px // tile_size
                char = grid[tile_y][tile_x]
                r, g, b = PREVIEW_COLORS.get(char, (255, 0, 255))
                row.extend((b, g, r))
            if padding:
                row.extend(b"\x00" * padding)
            f.write(row)


def open_in_aseprite(path: Path, aseprite_bin: str) -> None:
    binary = resolve_aseprite_bin(aseprite_bin)
    subprocess.run([str(binary), str(path)], check=True)


def write_ascii(path: Path, grid: list[list[str]]) -> None:
    lines = ["".join(row) for row in grid]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_legend(path: Path) -> None:
    legend = {
        GRASS_CHAR: 1,
        ".": 1,
        WATER_CHAR: 2,
        TREE_CHAR: 3,
        FOREST_CHAR: 4,
        PATH_CHAR: 5,
        SPAWN_CHAR: 6,
        JOIN_CHAR: 7,
        MINE_CHAR: 8,
        SHOP_CHAR: 9,
        CREEP_CHAR: 10,
        DEAD_END_CHAR: 11,
        SECRET_NPC_CHAR: 12,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(legend, indent=2) + "\n", encoding="utf-8")


def run_from_args(args: argparse.Namespace) -> None:
    if args.width <= 0 or args.height <= 0:
        raise ValueError("--width and --height must be positive integers.")
    if args.path_width_threshold <= 0:
        raise ValueError("--path-width-threshold must be > 0.")
    if args.preview_tile_size <= 0:
        raise ValueError("--preview-tile-size must be > 0.")
    if args.mine_count < 0 or args.shop_count < 0 or args.creep_zone_count < 0:
        raise ValueError("Mine/shop/creep counts must be non-negative.")
    if args.dead_end_count < 0:
        raise ValueError("--dead-end-count must be non-negative.")

    validate_density(args.tree_density, "--tree-density")
    validate_density(args.forest_density, "--forest-density")
    validate_density(args.water_density, "--water-density")
    if args.tree_density + args.water_density > 1.0:
        raise ValueError("--tree-density + --water-density cannot exceed 1.0")

    rng = random.Random(args.seed)
    path_width = args.path_width_threshold
    if path_width % 2 == 0:
        path_width += 1
    path_radius = path_width // 2

    spawn_points = place_spawn_points(
        args.width, args.height, args.spawn_count, args.spawn_clearing_size, rng
    )
    clearing_half = args.spawn_clearing_size // 2
    clearing_cells = build_clearing_cells(
        spawn_points, args.spawn_clearing_size, args.width, args.height
    )

    join_count = args.join_point_count if args.join_point_count > 0 else max(2, args.spawn_count // 2)
    join_points = place_join_points(
        args.width, args.height, join_count, forbidden=clearing_cells, rng=rng
    )

    grid = [[GRASS_CHAR for _ in range(args.width)] for _ in range(args.height)]
    for x, y in join_points:
        grid[y][x] = JOIN_CHAR
    for x, y in spawn_points:
        grid[y][x] = SPAWN_CHAR

    path_cells: set[Point] = set()
    path_forbidden = set(clearing_cells)

    for spawn in spawn_points:
        target = min(join_points, key=lambda p: manhattan(spawn, p))
        anchor = spawn_anchor_outside_clearing(
            spawn, target, clearing_half, path_radius, args.width, args.height
        )
        route = find_perlin_path(
            anchor,
            target,
            args.width,
            args.height,
            path_forbidden,
            seed=args.seed + 911,
            scale=args.path_perlin_scale,
            weight=args.path_perlin_weight,
        )
        carve_path(grid, route, path_width, path_cells, path_forbidden)

    for a, b in build_mst(join_points):
        route = find_perlin_path(
            a,
            b,
            args.width,
            args.height,
            path_forbidden,
            seed=args.seed + 1911,
            scale=args.path_perlin_scale,
            weight=args.path_perlin_weight,
        )
        carve_path(grid, route, path_width, path_cells, path_forbidden)

    dead_end_points: list[Point] = []
    branch_forbidden = set(clearing_cells)
    for i in range(args.dead_end_count):
        route = build_branch(
            grid=grid,
            path_cells=path_cells,
            base_forbidden=branch_forbidden,
            rng=rng,
            seed=args.seed + 3000 + i * 29,
            scale=args.path_perlin_scale,
            weight=args.path_perlin_weight,
            path_width=path_width,
            min_length=max(8, args.spawn_clearing_size // 2),
            max_length=max(14, min(args.width, args.height) // 3),
            search_attempts=180,
        )
        if route is None:
            raise ValueError(
                f"Could not place dead-end branch {i + 1}/{args.dead_end_count}. "
                "Increase canvas size or reduce dead-end count."
            )
        carve_path(grid, route, path_width, path_cells, branch_forbidden)
        dead_end_points.append(route[-1])

    secret_npc_point: Point | None = None
    if args.require_secret_npc_path:
        route = build_branch(
            grid=grid,
            path_cells=path_cells,
            base_forbidden=branch_forbidden,
            rng=rng,
            seed=args.seed + 9001,
            scale=args.path_perlin_scale,
            weight=args.path_perlin_weight,
            path_width=path_width,
            min_length=max(12, args.spawn_clearing_size),
            max_length=max(20, min(args.width, args.height) // 2),
            search_attempts=260,
        )
        if route is None:
            raise ValueError(
                "Could not place secret NPC branch with single-path constraint. "
                "Increase canvas size or reduce feature/path density."
            )
        carve_path(grid, route, path_width, path_cells, branch_forbidden)
        secret_npc_point = route[-1]

    # Enforce spawn clearings and key markers after all path carving.
    for x, y in clearing_cells:
        grid[y][x] = GRASS_CHAR
    for x, y in join_points:
        grid[y][x] = JOIN_CHAR
    for x, y in spawn_points:
        grid[y][x] = SPAWN_CHAR
    for x, y in dead_end_points:
        grid[y][x] = DEAD_END_CHAR
    if secret_npc_point is not None:
        grid[secret_npc_point[1]][secret_npc_point[0]] = SECRET_NPC_CHAR

    protected_cells = (
        set(clearing_cells)
        | set(spawn_points)
        | set(join_points)
        | set(dead_end_points)
        | ({secret_npc_point} if secret_npc_point else set())
    )

    total_tiles = args.width * args.height
    terrain_blocked = protected_cells | set(path_cells)
    placeable = sum(
        1
        for x, y in all_positions(args.width, args.height)
        if grid[y][x] == GRASS_CHAR and (x, y) not in terrain_blocked
    )

    water_target = min(int(round(total_tiles * args.water_density)), placeable)
    water_placed = place_clustered(grid, WATER_CHAR, water_target, rng, terrain_blocked)

    remaining_placeable = sum(
        1
        for x, y in all_positions(args.width, args.height)
        if grid[y][x] == GRASS_CHAR and (x, y) not in terrain_blocked
    )
    vegetation_target = min(int(round(total_tiles * args.tree_density)), remaining_placeable)
    forest_target = int(round(vegetation_target * args.forest_density))
    tree_target = max(0, vegetation_target - forest_target)
    forest_placed = place_clustered(grid, FOREST_CHAR, forest_target, rng, terrain_blocked)

    tree_candidates = [
        (x, y)
        for x, y in all_positions(args.width, args.height)
        if grid[y][x] == GRASS_CHAR and (x, y) not in terrain_blocked
    ]
    rng.shuffle(tree_candidates)
    tree_placed = 0
    for x, y in tree_candidates[:tree_target]:
        grid[y][x] = TREE_CHAR
        tree_placed += 1

    creep_centers, creep_cells = place_creep_zones(
        grid=grid,
        count=args.creep_zone_count,
        radius=args.creep_zone_radius,
        blocked=terrain_blocked,
        rng=rng,
    )

    poi_blocked = terrain_blocked | creep_cells
    mine_points = place_access_pois(
        grid=grid,
        path_cells=path_cells,
        blocked=poi_blocked,
        count=args.mine_count,
        marker=MINE_CHAR,
        label="mines",
        rng=rng,
    )
    poi_blocked |= set(mine_points)

    shop_points = place_access_pois(
        grid=grid,
        path_cells=path_cells,
        blocked=poi_blocked,
        count=args.shop_count,
        marker=SHOP_CHAR,
        label="shops",
        rng=rng,
    )

    # Re-assert protected markers in case any placement touched them.
    for x, y in spawn_points:
        grid[y][x] = SPAWN_CHAR
    for x, y in join_points:
        grid[y][x] = JOIN_CHAR
    for x, y in dead_end_points:
        grid[y][x] = DEAD_END_CHAR
    if secret_npc_point is not None:
        grid[secret_npc_point[1]][secret_npc_point[0]] = SECRET_NPC_CHAR

    out_path = Path(args.out)
    legend_path = Path(args.legend_out) if args.legend_out else out_path.with_suffix(".legend.json")
    write_ascii(out_path, grid)
    write_legend(legend_path)

    preview_path: Path | None = None
    if args.preview_in_aseprite or args.preview_out:
        preview_path = Path(args.preview_out) if args.preview_out else out_path.with_suffix(".preview.bmp")
        write_preview_bmp(preview_path, grid, args.preview_tile_size)
        print(f"Wrote {preview_path}")
        if args.preview_in_aseprite:
            try:
                open_in_aseprite(preview_path, args.aseprite_bin)
            except (FileNotFoundError, subprocess.CalledProcessError) as exc:
                print(f"Warning: failed to open preview in Aseprite: {exc}")

    print(f"Wrote {out_path}")
    print(f"Wrote {legend_path}")
    print(
        "Stats: "
        f"spawns={len(spawn_points)}, joins={len(join_points)}, "
        f"dead_ends={len(dead_end_points)}, secret_npc={'1' if secret_npc_point else '0'}, "
        f"path_tiles={len(path_cells)}, mines={len(mine_points)}, shops={len(shop_points)}, "
        f"creep_zones={len(creep_centers)}, water={water_placed}, forest={forest_placed}, "
        f"trees={tree_placed}, path_width={path_width}"
    )


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    run_from_args(args)


if __name__ == "__main__":
    main()
