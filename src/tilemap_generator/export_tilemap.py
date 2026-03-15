"""Export tile indices from tilemap layers to JSON and CSV."""
from __future__ import annotations

import csv
import json
from pathlib import Path


def load_tiled_json(path: Path) -> dict:
    """Load and validate a Tiled JSON file."""
    if not path.exists():
        raise FileNotFoundError(f"Tilemap file not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Expected a JSON object (Tiled map format)")

    return raw


def extract_tile_layers(tiled: dict) -> list[dict]:
    """Extract tile layers (type=tilelayer) from Tiled JSON."""
    layers = []
    for layer in tiled.get("layers", []):
        if not isinstance(layer, dict):
            continue
        if layer.get("type") != "tilelayer":
            continue
        data = layer.get("data")
        if not isinstance(data, list):
            continue
        width = layer.get("width")
        height = layer.get("height")
        if not isinstance(width, int) or not isinstance(height, int):
            continue
        if width <= 0 or height <= 0:
            continue
        if len(data) != width * height:
            continue
        layers.append({
            "name": layer.get("name", "Layer"),
            "width": width,
            "height": height,
            "data": data,
        })
    return layers


def to_grid(data: list[int], width: int, height: int) -> list[list[int]]:
    """Convert flat row-major data to 2D grid."""
    return [data[y * width : (y + 1) * width] for y in range(height)]


def export_json(
    layers: list[dict],
    tile_width: int,
    tile_height: int,
    out_path: Path,
) -> None:
    """Export layers to a game-friendly JSON format."""
    payload = {
        "tilewidth": tile_width,
        "tileheight": tile_height,
        "layers": [
            {
                "name": layer["name"],
                "width": layer["width"],
                "height": layer["height"],
                "data": layer["data"],
            }
            for layer in layers
        ],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def export_csv_per_layer(layers: list[dict], out_prefix: Path) -> list[Path]:
    """Export each layer to a separate CSV file. Returns list of written paths."""
    written: list[Path] = []
    for layer in layers:
        grid = to_grid(layer["data"], layer["width"], layer["height"])
        safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in layer["name"])
        csv_path = out_prefix.with_name(f"{out_prefix.name}_{safe_name}.csv")
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for row in grid:
                writer.writerow(row)
        written.append(csv_path)
    return written


def export_csv_single(
    layers: list[dict],
    out_path: Path,
    layer_index: int = 0,
) -> Path:
    """Export a single layer to CSV. Default: first layer."""
    if not layers:
        raise ValueError("No tile layers to export")
    idx = min(max(0, layer_index), len(layers) - 1)
    layer = layers[idx]
    grid = to_grid(layer["data"], layer["width"], layer["height"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for row in grid:
            writer.writerow(row)
    return out_path


def run_export(
    input_path: Path,
    out_prefix: Path,
    *,
    export_json_flag: bool = True,
    export_csv_flag: bool = True,
    csv_single: bool = False,
) -> list[str]:
    """Run export and return list of written file paths."""
    tiled = load_tiled_json(input_path)
    layers = extract_tile_layers(tiled)

    if not layers:
        raise ValueError("No tile layers found in input")

    tile_width = tiled.get("tilewidth", 32)
    tile_height = tiled.get("tileheight", 32)
    written: list[str] = []

    if export_json_flag:
        json_path = out_prefix.with_suffix(".json")
        export_json(layers, tile_width, tile_height, json_path)
        written.append(str(json_path))

    if export_csv_flag:
        if csv_single:
            csv_path = out_prefix.with_suffix(".csv")
            export_csv_single(layers, csv_path)
            written.append(str(csv_path))
        else:
            for p in export_csv_per_layer(layers, out_prefix):
                written.append(str(p))

    return written
