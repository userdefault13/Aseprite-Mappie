"""Open a gotchiverse district (rect of Tiled TMJ chunks) as a layered .aseprite file.

Reads chunkN.json files from a gotchiverse maps-root, stitches a bounding rect
of chunks into one big tilemap per Tiled layer, repacks the referenced tilesets
for Aseprite (margin/spacing -> tight grid), and invokes an Aseprite Lua script
to build a .aseprite with tilemap layers + preserved tile animations.

Open-only: no write-back to TMJ in this version.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from tilemap_generator.aseprite_cli import resolve_aseprite_bin, run


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TILE_SIZE = 64
# Aseprite's .aseprite format stores sprite dimensions as 16-bit values, so a
# sprite cannot exceed 65535px on either axis. Sprites past this silently
# corrupt on save (reopen as 2048x2048 or 0x0). We downscale tiles to fit.
MAX_ASEPRITE_DIM = 65535
TILE_SIZE_CASCADE = (64, 32, 16, 8, 4, 2, 1)


def fit_tile_size(tile_size: int, tiles_w: int, tiles_h: int) -> int:
    """Largest cascade tile size (<= requested) whose district sprite fits
    Aseprite's 65535px dimension limit; downscales in halves as needed."""
    longest = max(tiles_w, tiles_h)
    fitted = next(
        (t for t in TILE_SIZE_CASCADE if t <= tile_size and t * longest <= MAX_ASEPRITE_DIM),
        None,
    )
    if fitted is None:
        raise ValueError(
            f"District is {tiles_w}x{tiles_h} tiles; even at 1px/tile it would be "
            f"{longest}px, exceeding Aseprite's {MAX_ASEPRITE_DIM}px limit."
        )
    return fitted


def parse_chunks_bbox(spec: str) -> tuple[int, int, int, int]:
    """Parse a chunk bbox spec like "0-3,0-3" into (x0, x1, y0, y1) inclusive."""
    spec = spec.strip()
    if "," not in spec:
        raise ValueError(
            'Chunk bbox must be "x0-x1,y0-y1" (e.g. "0-3,0-3"). '
            f"Got: {spec!r}"
        )
    x_part, y_part = spec.split(",", 1)

    def parse_range(part: str, name: str) -> tuple[int, int]:
        part = part.strip()
        m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", part)
        if not m:
            raise ValueError(
                f'Chunk {name}-range must be "a-b" (e.g. "0-3"). Got: {part!r}'
            )
        a, b = int(m.group(1)), int(m.group(2))
        if a < 0 or b < a:
            raise ValueError(f"Chunk {name}-range invalid: {a}-{b}. Need 0 <= a <= b.")
        return a, b

    x0, x1 = parse_range(x_part, "x")
    y0, y1 = parse_range(y_part, "y")
    return x0, x1, y0, y1


def paste_block(
    dst_data: list[int],
    src_data: list[int],
    src_w: int,
    src_h: int,
    dst_w: int,
    dst_x: int,
    dst_y: int,
) -> None:
    """Copy a src_w x src_h block from src_data into dst_data at (dst_x, dst_y).

    Both arrays are flat row-major. dst_data has width dst_w. src_data has
    width src_w. Out-of-bounds dst writes are skipped.
    """
    for sy in range(src_h):
        dy = dst_y + sy
        if dy < 0:
            continue
        for sx in range(src_w):
            dx = dst_x + sx
            if dx < 0 or dx >= dst_w:
                continue
            dst_idx = dy * dst_w + dx
            if dst_idx >= len(dst_data):
                continue
            src_idx = sy * src_w + sx
            if src_idx >= len(src_data):
                continue
            dst_data[dst_idx] = src_data[src_idx]


def load_master(maps_root: Path) -> dict:
    master_path = maps_root / "master.json"
    if not master_path.exists():
        raise FileNotFoundError(f"master.json not found in maps-root: {maps_root}")
    master = json.loads(master_path.read_text(encoding="utf-8"))
    for key in ("chunkWidth", "chunkHeight", "chunksHorizontal", "chunksVertical"):
        if key not in master:
            raise ValueError(f"master.json missing required key: {key}")
    return master


def load_chunk(maps_root: Path, chunk_id: int) -> dict:
    path = maps_root / f"chunk{chunk_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Chunk file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def stitch_layers(
    maps_root: Path,
    master: dict,
    x0: int,
    x1: int,
    y0: int,
    y1: int,
) -> tuple[dict[str, dict], dict[str, dict]]:
    """Load every chunk in the bbox and stitch per-Tiled-layer into big GID grids.

    Returns:
        (tiled_layers, tilesets_by_name)
        tiled_layers: {layer_name: {width, height, data: [gid, ...]}}
        tilesets_by_name: {tileset_name: tileset_dict} (union across chunks)
    """
    chunk_w = int(master["chunkWidth"])
    chunk_h = int(master["chunkHeight"])
    chunks_h = int(master["chunksHorizontal"])
    tiles_w = (x1 - x0 + 1) * chunk_w
    tiles_h = (y1 - y0 + 1) * chunk_h

    tiled_layers: dict[str, dict] = {}
    tilesets_by_name: dict[str, dict] = {}

    for cy in range(y0, y1 + 1):
        for cx in range(x0, x1 + 1):
            chunk_id = cy * chunks_h + cx
            chunk = load_chunk(maps_root, chunk_id)

            for ts in chunk.get("tilesets", []):
                name = ts.get("name")
                if not name:
                    continue
                if name not in tilesets_by_name:
                    tilesets_by_name[name] = ts

            for layer in chunk.get("layers", []):
                if not isinstance(layer, dict):
                    continue
                if layer.get("type") != "tilelayer":
                    continue
                data = layer.get("data")
                if not isinstance(data, list):
                    continue
                lw = layer.get("width")
                lh = layer.get("height")
                if not (isinstance(lw, int) and isinstance(lh, int)):
                    continue
                if lw != chunk_w or lh != chunk_h:
                    raise ValueError(
                        f"Chunk {chunk_id} layer {layer.get('name')!r} has size "
                        f"{lw}x{lh}, expected {chunk_w}x{chunk_h}"
                    )
                key = layer.get("name", "Layer")
                if key not in tiled_layers:
                    tiled_layers[key] = {
                        "width": tiles_w,
                        "height": tiles_h,
                        "data": [0] * (tiles_w * tiles_h),
                    }
                paste_block(
                    tiled_layers[key]["data"],
                    data,
                    src_w=chunk_w,
                    src_h=chunk_h,
                    dst_w=tiles_w,
                    dst_x=(cx - x0) * chunk_w,
                    dst_y=(cy - y0) * chunk_h,
                )

    return tiled_layers, tilesets_by_name


def resolve_tileset_image(ts: dict, maps_root: Path) -> Path | None:
    """Resolve a Tiled tileset image path against maps-root and common fallbacks.

    Tiled stores e.g. ``sprites/alchem.png`` relative to the chunk file. Gotchiverse
    keeps the PNGs in ``maps/sprites/`` (parent of ``maps/chunks/``). Also try
    ``sprites/<tileset_name>.png`` when the TMJ image filename doesn't match disk.
    """
    name = ts.get("name", "tileset")
    image_rel = ts.get("image") or ""
    candidates: list[Path] = []
    if image_rel:
        candidates.append(maps_root / image_rel)
        candidates.append(maps_root.parent / image_rel)
    # Name-based fallback (e.g. statues.png vs statue_soldat_stone1_angles.png)
    candidates.append(maps_root / "sprites" / f"{name}.png")
    candidates.append(maps_root.parent / "sprites" / f"{name}.png")
    seen: set[str] = set()
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.exists():
            return path
    return None


def repack_tileset(
    ts: dict,
    maps_root: Path,
    out_dir: Path,
    target_tile_size: int | None = None,
) -> dict:
    """Slice a Tiled tileset PNG (with margin/spacing) into a tight-grid PNG.

    If ``target_tile_size`` is set (and differs from the native tile size),
    each tile is resized (Lanczos) to ``target_tile_size`` square so the final
    district sprite stays within Aseprite's dimension limits.

    Returns a dict with keys: name, firstgid, png_path, columns, tile_count,
    tile_width, tile_height, animations.
    """
    from PIL import Image  # local import to keep module importable without Pillow

    name = ts.get("name", "tileset")
    firstgid = int(ts.get("firstgid", 1))
    tile_w = int(ts.get("tilewidth", DEFAULT_TILE_SIZE))
    tile_h = int(ts.get("tileheight", DEFAULT_TILE_SIZE))
    margin = int(ts.get("margin", 0) or 0)
    spacing = int(ts.get("spacing", 0) or 0)
    columns = int(ts.get("columns", 0) or 0)
    tile_count = int(ts.get("tilecount", 0) or 0)
    image_rel = ts.get("image")
    if not image_rel:
        raise ValueError(f"Tileset {name!r} has no image path")

    image_path = resolve_tileset_image(ts, maps_root)
    if image_path is None:
        raise FileNotFoundError(
            f"Tileset {name!r} image not found (tried {image_rel} and sprites/{name}.png)"
        )

    if columns <= 0:
        img_w = int(ts.get("imagewidth", 0) or 0)
        if img_w <= 0:
            with Image.open(image_path) as im:
                img_w, _ = im.size
        usable_w = img_w - 2 * margin + spacing
        columns = usable_w // (tile_w + spacing) if (tile_w + spacing) > 0 else 0
        if columns <= 0:
            raise ValueError(
                f"Tileset {name!r}: cannot derive columns from image width {img_w}"
            )

    if tile_count <= 0:
        with Image.open(image_path) as im:
            img_w, img_h = im.size
        usable_w = img_w - 2 * margin + spacing
        usable_h = img_h - 2 * margin + spacing
        cols = usable_w // (tile_w + spacing) if (tile_w + spacing) > 0 else 0
        rows = usable_h // (tile_h + spacing) if (tile_h + spacing) > 0 else 0
        tile_count = cols * rows

    rows = (tile_count + columns - 1) // columns if columns > 0 else 0

    downscale = target_tile_size is not None and (
        target_tile_size != tile_w or target_tile_size != tile_h
    )
    out_tw = target_tile_size if downscale else tile_w
    out_th = target_tile_size if downscale else tile_h

    # Slice + repack
    src = Image.open(image_path).convert("RGBA")
    sheet = Image.new("RGBA", (columns * out_tw, rows * out_th), (0, 0, 0, 0))
    for idx in range(tile_count):
        sx = idx % columns
        sy = idx // columns
        left = margin + sx * (tile_w + spacing)
        top = margin + sy * (tile_h + spacing)
        tile = src.crop((left, top, left + tile_w, top + tile_h))
        if downscale and (out_tw != tile_w or out_th != tile_h):
            tile = tile.resize((out_tw, out_th), Image.LANCZOS)
        sheet.paste(tile, (sx * out_tw, sy * out_th))
    src.close()

    safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
    out_path = out_dir / f"{safe_name}.png"
    sheet.save(out_path)
    sheet.close()

    # Collect animations: Tiled stores them in tilesets[].tiles[].animation
    # as [{duration, tileid}, ...]. tileid is the LOCAL tile index (0-based).
    animations: list[dict] = []
    for tile_entry in ts.get("tiles", []) or []:
        if not isinstance(tile_entry, dict):
            continue
        tile_id = tile_entry.get("id")
        if not isinstance(tile_id, int):
            continue
        anim = tile_entry.get("animation")
        if not isinstance(anim, list) or not anim:
            continue
        frames = []
        for frame in anim:
            if not isinstance(frame, dict):
                continue
            ftid = frame.get("tileid")
            fdur = frame.get("duration")
            if not (isinstance(ftid, int) and isinstance(fdur, (int, float))):
                continue
            frames.append({"cel": int(ftid), "duration_ms": int(fdur)})
        if frames:
            animations.append({"tile_index": int(tile_id), "frames": frames})

    return {
        "name": name,
        "firstgid": firstgid,
        "png_path": str(out_path),
        "columns": columns,
        "tile_count": tile_count,
        "tile_width": out_tw,
        "tile_height": out_th,
        "animations": animations,
    }


def build_layer_splits(
    tiled_layers: dict[str, dict],
    tilesets_by_name: dict[str, dict],
    repacked: dict[str, dict],
) -> list[dict]:
    """Split each Tiled layer per-tileset, convert GIDs -> local indices, skip empties.

    Returns a list of {name, tileset_name, width, height, data: [local_index, ...]}.
    """
    # Build firstgid-sorted list of tilesets for GID lookup
    ts_list = sorted(
        tilesets_by_name.values(),
        key=lambda t: int(t.get("firstgid", 1)),
    )

    def gid_to_tileset(gid: int) -> tuple[dict | None, int]:
        """Return (tileset_dict, local_index) for a global GID, or (None, 0) if empty.

        local_index is 1-based to match Aseprite's convention (tile 0 = empty,
        user tiles start at 1). Returns (None, 0) for empty cells.
        """
        if gid <= 0:
            return None, 0
        chosen: dict | None = None
        for ts in ts_list:
            fg = int(ts.get("firstgid", 1))
            tc = int(ts.get("tilecount", 0) or 0)
            if gid >= fg and (tc <= 0 or gid < fg + tc):
                chosen = ts
                break
        if chosen is None and ts_list:
            # Fallback to last tileset whose firstgid <= gid
            for ts in ts_list:
                fg = int(ts.get("firstgid", 1))
                if gid >= fg:
                    chosen = ts
        if chosen is None:
            return None, 0
        # +1 so 0 = empty, 1 = first tile (Aseprite convention)
        local = gid - int(chosen.get("firstgid", 1)) + 1
        return chosen, local

    splits: list[dict] = []
    for layer_name, layer in tiled_layers.items():
        width = layer["width"]
        height = layer["height"]
        data = layer["data"]
        # Bucket cells per-tileset
        per_ts: dict[str, list[int]] = {}
        per_ts_nonempty: dict[str, bool] = {}
        for ts_name in repacked:
            per_ts[ts_name] = [0] * (width * height)
            per_ts_nonempty[ts_name] = False
        for i, gid in enumerate(data):
            ts_dict, local = gid_to_tileset(gid)
            if ts_dict is None:
                continue
            ts_name = ts_dict.get("name")
            if ts_name not in per_ts:
                continue
            per_ts[ts_name][i] = local
            per_ts_nonempty[ts_name] = True
        for ts_name, nonempty in per_ts_nonempty.items():
            if not nonempty:
                continue
            splits.append({
                "name": f"{layer_name}__{ts_name}",
                "tileset_name": ts_name,
                "width": width,
                "height": height,
                "data": per_ts[ts_name],
            })
    return splits


def build_manifest(
    tiles_w: int,
    tiles_h: int,
    tile_size: int,
    repacked: dict[str, dict],
    splits: list[dict],
) -> dict:
    """Build the JSON manifest consumed by the Lua importer."""
    return {
        "sprite_width": tiles_w * tile_size,
        "sprite_height": tiles_h * tile_size,
        "tile_size": tile_size,
        "tilesets": list(repacked.values()),
        "layers": splits,
    }


def command_open(args: argparse.Namespace) -> None:
    maps_root = Path(args.maps_root).expanduser()
    if not maps_root.is_dir():
        raise FileNotFoundError(f"maps-root is not a directory: {maps_root}")

    x0, x1, y0, y1 = parse_chunks_bbox(args.chunks)
    master = load_master(maps_root)
    chunks_h = int(master["chunksHorizontal"])
    chunks_v = int(master["chunksVertical"])
    if x1 >= chunks_h or y1 >= chunks_v:
        raise ValueError(
            f"Chunk bbox {x0}-{x1},{y0}-{y1} out of range for grid "
            f"{chunks_h}x{chunks_v}"
        )

    if args.tile_size <= 0:
        raise ValueError("--tile-size must be > 0")

    out_path = Path(args.out).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    tiles_w = (x1 - x0 + 1) * int(master["chunkWidth"])
    tiles_h = (y1 - y0 + 1) * int(master["chunkHeight"])
    tile_size = fit_tile_size(args.tile_size, tiles_w, tiles_h)
    if tile_size != args.tile_size:
        print(
            f"  District {tiles_w}x{tiles_h} tiles exceeds Aseprite's "
            f"{MAX_ASEPRITE_DIM}px limit at {args.tile_size}px/tile; "
            f"downscaling tiles to {tile_size}px (sprite {tiles_w}*{tile_size}x"
            f"{tiles_h}*{tile_size}px)."
        )

    print(f"Stitching district chunks {x0}-{x1},{y0}-{y1} from {maps_root} ...")
    tiled_layers, tilesets_by_name = stitch_layers(
        maps_root, master, x0, x1, y0, y1
    )
    print(
        f"  Stitched {len(tiled_layers)} Tiled layers; "
        f"{len(tilesets_by_name)} tilesets referenced"
    )

    with tempfile.TemporaryDirectory(prefix="mappie_district_") as tmp:
        tmp_path = Path(tmp)
        repacked: dict[str, dict] = {}
        for name, ts in tilesets_by_name.items():
            try:
                repacked[name] = repack_tileset(
                    ts, maps_root, tmp_path, target_tile_size=tile_size
                )
            except FileNotFoundError as e:
                print(f"  Warning: skipping tileset {name!r}: {e}", file=sys.stderr)
        if not repacked:
            raise FileNotFoundError("No tileset images could be resolved from maps-root")
        print(f"  Repacked {len(repacked)} tilesets")

        splits = build_layer_splits(tiled_layers, tilesets_by_name, repacked)
        if args.only_tilesets:
            prefixes = [p.strip() for p in args.only_tilesets.split(",") if p.strip()]
            kept = [
                s for s in splits
                if any(s["tileset_name"].startswith(p) for p in prefixes)
            ]
            if not kept:
                raise ValueError(
                    f"--only-tilesets matched no layers (available tilesets: "
                    f"{sorted({s['tileset_name'] for s in splits})})"
                )
            print(
                f"  Filtered to {len(kept)} layers via --only-tilesets "
                f"({len(splits) - len(kept)} removed)"
            )
            splits = kept
        print(f"  Built {len(splits)} Aseprite tilemap layer splits")

        manifest = build_manifest(tiles_w, tiles_h, tile_size, repacked, splits)
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        lua_script = PROJECT_ROOT / "assets" / "lua" / "import_district.lua"
        if not lua_script.exists():
            raise FileNotFoundError(f"Missing Lua script: {lua_script}")

        env = os.environ.copy()
        env["MANIFEST_PATH"] = str(manifest_path.resolve())
        env["OUT"] = str(out_path.resolve())

        aseprite_bin = resolve_aseprite_bin(args.aseprite_bin)
        print(f"  Invoking Aseprite to build {out_path} ...")
        run([str(aseprite_bin), "-b", "--script", str(lua_script)], env=env)

    print(f"Wrote {out_path}")

    if args.open:
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Open a gotchiverse district (rect of Tiled TMJ chunks) as a "
            "layered .aseprite file."
        )
    )
    parser.add_argument(
        "--aseprite-bin",
        default=None,
        help="Optional explicit path to aseprite binary.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    open_parser = subparsers.add_parser(
        "open", help="Stitch chunks + open as .aseprite in Aseprite."
    )
    open_parser.add_argument(
        "--maps-root",
        required=True,
        help="Path to gotchiverse maps/chunks dir (contains master.json + chunkN.json).",
    )
    open_parser.add_argument(
        "--chunks",
        required=True,
        help='Chunk bbox "x0-x1,y0-y1" (inclusive). Example: "0-3,0-3".',
    )
    open_parser.add_argument(
        "--out",
        required=True,
        help="Output .aseprite path.",
    )
    open_parser.add_argument(
        "--tile-size",
        type=int,
        default=DEFAULT_TILE_SIZE,
        help=f"Pixels per tile (default {DEFAULT_TILE_SIZE}).",
    )
    open_parser.add_argument(
        "--open",
        action="store_true",
        help="Open the result in Aseprite GUI when done.",
    )
    open_parser.add_argument(
        "--only-tilesets",
        default=None,
        help=(
            "Comma-separated tileset name prefixes; keep only layers bound to "
            'matching tilesets (e.g. "tower" keeps the citadel tower walls).'
        ),
    )

    return parser


def run_from_args(args: argparse.Namespace) -> None:
    if args.command == "open":
        command_open(args)
    else:
        raise ValueError(f"Unsupported command: {args.command}")


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    run_from_args(args)


if __name__ == "__main__":
    main()
