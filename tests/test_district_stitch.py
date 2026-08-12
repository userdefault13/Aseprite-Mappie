"""Unit tests for district_cli: bbox parsing, block pasting, stitching, layer splits, manifest.

These tests do NOT invoke Aseprite. They test the Python-side logic only:
- parse_chunks_bbox
- paste_block
- stitch_layers (with synthetic chunk files in a temp dir)
- build_layer_splits (GID -> local index conversion, per-tileset splitting)
- build_manifest (schema validation)
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure src/ is on the path
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tilemap_generator.district_cli import (
    build_layer_splits,
    build_manifest,
    load_master,
    parse_chunks_bbox,
    paste_block,
    stitch_layers,
)


class TestParseChunksBbox(unittest.TestCase):
    def test_standard_bbox(self):
        self.assertEqual(parse_chunks_bbox("0-3,0-3"), (0, 3, 0, 3))

    def test_asymmetric_bbox(self):
        self.assertEqual(parse_chunks_bbox("2-5,10-15"), (2, 5, 10, 15))

    def test_single_range(self):
        self.assertEqual(parse_chunks_bbox("5-5,7-7"), (5, 5, 7, 7))

    def test_missing_comma_raises(self):
        with self.assertRaises(ValueError):
            parse_chunks_bbox("0-3")

    def test_bad_range_raises(self):
        with self.assertRaises(ValueError):
            parse_chunks_bbox("3-0,0-3")  # a > b

    def test_non_numeric_raises(self):
        with self.assertRaises(ValueError):
            parse_chunks_bbox("a-b,0-3")


class TestPasteBlock(unittest.TestCase):
    def test_simple_paste(self):
        dst = [0] * 16  # 4x4
        src = [1, 2, 3, 4]  # 2x2
        paste_block(dst, src, src_w=2, src_h=2, dst_w=4, dst_x=1, dst_y=1)
        # Row 1: positions (1,1), (2,1), (1,2), (2,2) -> indices 5,6,9,10
        self.assertEqual(dst[5], 1)
        self.assertEqual(dst[6], 2)
        self.assertEqual(dst[9], 3)
        self.assertEqual(dst[10], 4)

    def test_paste_at_origin(self):
        dst = [0] * 9  # 3x3
        src = [5, 6, 7, 8]  # 2x2
        paste_block(dst, src, src_w=2, src_h=2, dst_w=3, dst_x=0, dst_y=0)
        self.assertEqual(dst[0], 5)
        self.assertEqual(dst[1], 6)
        self.assertEqual(dst[3], 7)
        self.assertEqual(dst[4], 8)

    def test_out_of_bounds_skipped(self):
        dst = [0] * 4  # 2x2
        src = [1, 2, 3, 4]  # 2x2
        paste_block(dst, src, src_w=2, src_h=2, dst_w=2, dst_x=1, dst_y=1)
        # Only src top-left (0,0)=1 maps to dst (1,1)=index 3; rest out of bounds
        self.assertEqual(dst[3], 1)
        # Everything else stays 0
        self.assertEqual(dst[0], 0)
        self.assertEqual(dst[1], 0)
        self.assertEqual(dst[2], 0)


def make_chunk_json(
    chunk_id: int,
    tilesets: list[dict],
    layers: list[dict],
    width: int = 2,
    height: int = 2,
) -> dict:
    """Build a minimal Tiled TMJ chunk dict."""
    return {
        "type": "map",
        "orientation": "orthogonal",
        "tilewidth": 64,
        "tileheight": 64,
        "width": width,
        "height": height,
        "layers": layers,
        "tilesets": tilesets,
    }


def make_tileset(name: str, firstgid: int, tilecount: int = 4) -> dict:
    return {
        "name": name,
        "firstgid": firstgid,
        "tilewidth": 64,
        "tileheight": 64,
        "tilecount": tilecount,
        "columns": 2,
        "margin": 0,
        "spacing": 0,
        "image": f"sprites/{name}.png",
        "imagewidth": 128,
        "imageheight": 128,
    }


class TestStitchLayers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.maps_root = Path(self.tmp.name)
        # master.json: 4x4 grid of 2x2-tile chunks
        self.master = {
            "chunkWidth": 2,
            "chunkHeight": 2,
            "chunksHorizontal": 4,
            "chunksVertical": 4,
            "chunksTotal": 16,
        }
        (self.maps_root / "master.json").write_text(json.dumps(self.master))

    def tearDown(self):
        self.tmp.cleanup()

    def _write_chunk(self, chunk_id: int, layers: list[dict], tilesets: list[dict]):
        chunk = make_chunk_json(chunk_id, tilesets, layers, width=2, height=2)
        (self.maps_root / f"chunk{chunk_id}.json").write_text(json.dumps(chunk))

    def test_stitch_2x2_district(self):
        """Stitch 4 chunks (2x2) into a 4x4 tile grid."""
        ts = [make_tileset("tsA", firstgid=1, tilecount=4)]
        # Chunk 0 (0,0): all tile gid=1
        self._write_chunk(0, [{"type": "tilelayer", "name": "L", "width": 2, "height": 2, "data": [1, 1, 1, 1]}], ts)
        # Chunk 1 (1,0): all tile gid=2
        self._write_chunk(1, [{"type": "tilelayer", "name": "L", "width": 2, "height": 2, "data": [2, 2, 2, 2]}], ts)
        # Chunk 4 (0,1): all tile gid=3
        self._write_chunk(4, [{"type": "tilelayer", "name": "L", "width": 2, "height": 2, "data": [3, 3, 3, 3]}], ts)
        # Chunk 5 (1,1): all tile gid=4
        self._write_chunk(5, [{"type": "tilelayer", "name": "L", "width": 2, "height": 2, "data": [4, 4, 4, 4]}], ts)

        tiled_layers, tilesets_by_name = stitch_layers(
            self.maps_root, self.master, x0=0, x1=1, y0=0, y1=1
        )
        self.assertIn("L", tiled_layers)
        self.assertEqual(tiled_layers["L"]["width"], 4)
        self.assertEqual(tiled_layers["L"]["height"], 4)
        # Row 0 (chunk 0 left, chunk 1 right): [1,1,2,2]
        self.assertEqual(tiled_layers["L"]["data"][0:4], [1, 1, 2, 2])
        # Row 2 (chunk 4 left, chunk 5 right): [3,3,4,4]
        self.assertEqual(tiled_layers["L"]["data"][8:12], [3, 3, 4, 4])
        self.assertIn("tsA", tilesets_by_name)

    def test_stitch_skips_non_tilelayers(self):
        ts = [make_tileset("tsA", firstgid=1)]
        self._write_chunk(
            0,
            [
                {"type": "objectgroup", "name": "objects", "width": 2, "height": 2, "objects": []},
                {"type": "tilelayer", "name": "L", "width": 2, "height": 2, "data": [1, 0, 0, 0]},
            ],
            ts,
        )
        tiled_layers, _ = stitch_layers(self.maps_root, self.master, 0, 0, 0, 0)
        self.assertIn("L", tiled_layers)
        self.assertNotIn("objects", tiled_layers)

    def test_stitch_missing_chunk_raises(self):
        with self.assertRaises(FileNotFoundError):
            stitch_layers(self.maps_root, self.master, 0, 0, 0, 0)


class TestBuildLayerSplits(unittest.TestCase):
    def test_split_per_tileset_1based(self):
        """GIDs are converted to 1-based Aseprite tile indices; 0 = empty."""
        tilesets_by_name = {
            "tsA": make_tileset("tsA", firstgid=1, tilecount=4),
            "tsB": make_tileset("tsB", firstgid=100, tilecount=4),
        }
        repacked = {
            "tsA": {"name": "tsA", "firstgid": 1, "png_path": "/tmp/a.png", "columns": 2, "tile_count": 4, "tile_width": 64, "tile_height": 64, "animations": []},
            "tsB": {"name": "tsB", "firstgid": 100, "png_path": "/tmp/b.png", "columns": 2, "tile_count": 4, "tile_width": 64, "tile_height": 64, "animations": []},
        }
        # 1x2 layer: cell 0 -> tsA gid 1 (local 0 -> Aseprite 1), cell 1 -> tsB gid 100 (local 0 -> Aseprite 1)
        tiled_layers = {
            "L": {"width": 2, "height": 1, "data": [1, 100]}
        }
        splits = build_layer_splits(tiled_layers, tilesets_by_name, repacked)
        # Should produce 2 splits: L__tsA and L__tsB
        names = sorted(s["name"] for s in splits)
        self.assertEqual(names, ["L__tsA", "L__tsB"])
        for s in splits:
            self.assertEqual(s["width"], 2)
            self.assertEqual(s["height"], 1)
            # Each split has exactly one non-zero cell (value 1 = first tile in Aseprite)
            self.assertEqual(sum(1 for v in s["data"] if v > 0), 1)
            self.assertIn(1, s["data"])

    def test_split_skips_empty_tilesets(self):
        tilesets_by_name = {
            "tsA": make_tileset("tsA", firstgid=1, tilecount=4),
            "tsB": make_tileset("tsB", firstgid=100, tilecount=4),
        }
        repacked = {
            "tsA": {"name": "tsA", "png_path": "/tmp/a.png", "columns": 2, "tile_count": 4, "tile_width": 64, "tile_height": 64, "animations": []},
            "tsB": {"name": "tsB", "png_path": "/tmp/b.png", "columns": 2, "tile_count": 4, "tile_width": 64, "tile_height": 64, "animations": []},
        }
        # Layer only uses tsA, not tsB
        tiled_layers = {"L": {"width": 2, "height": 1, "data": [1, 2]}}
        splits = build_layer_splits(tiled_layers, tilesets_by_name, repacked)
        # Only L__tsA should appear
        self.assertEqual(len(splits), 1)
        self.assertEqual(splits[0]["name"], "L__tsA")
        # GID 1 -> local 0 -> Aseprite 1; GID 2 -> local 1 -> Aseprite 2
        self.assertEqual(splits[0]["data"], [1, 2])

    def test_split_handles_empty_cells(self):
        tilesets_by_name = {"tsA": make_tileset("tsA", firstgid=1, tilecount=4)}
        repacked = {"tsA": {"name": "tsA", "png_path": "/tmp/a.png", "columns": 2, "tile_count": 4, "tile_width": 64, "tile_height": 64, "animations": []}}
        # 1x3 layer: [0 (empty), gid 1 (tsA first), 0 (empty)]
        tiled_layers = {"L": {"width": 3, "height": 1, "data": [0, 1, 0]}}
        splits = build_layer_splits(tiled_layers, tilesets_by_name, repacked)
        self.assertEqual(len(splits), 1)
        self.assertEqual(splits[0]["data"], [0, 1, 0])


class TestBuildManifest(unittest.TestCase):
    def test_manifest_schema(self):
        repacked = {
            "tsA": {
                "name": "tsA", "firstgid": 1, "png_path": "/tmp/a.png",
                "columns": 2, "tile_count": 4, "tile_width": 64, "tile_height": 64,
                "animations": [{"tile_index": 0, "frames": [{"cel": 0, "duration_ms": 400}]}],
            }
        }
        splits = [{"name": "L__tsA", "tileset_name": "tsA", "width": 2, "height": 1, "data": [1, 0]}]
        manifest = build_manifest(tiles_w=2, tiles_h=1, tile_size=64, repacked=repacked, splits=splits)
        self.assertEqual(manifest["sprite_width"], 128)
        self.assertEqual(manifest["sprite_height"], 64)
        self.assertEqual(manifest["tile_size"], 64)
        self.assertEqual(len(manifest["tilesets"]), 1)
        self.assertEqual(manifest["tilesets"][0]["name"], "tsA")
        self.assertEqual(len(manifest["tilesets"][0]["animations"]), 1)
        self.assertEqual(manifest["layers"], splits)


class TestLoadMaster(unittest.TestCase):
    def test_load_valid_master(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "master.json").write_text(json.dumps({
                "chunkWidth": 66, "chunkHeight": 66,
                "chunksHorizontal": 128, "chunksVertical": 80, "chunksTotal": 10240,
            }))
            m = load_master(root)
            self.assertEqual(m["chunkWidth"], 66)
            self.assertEqual(m["chunksHorizontal"], 128)

    def test_missing_master_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                load_master(Path(tmp))

    def test_missing_key_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "master.json").write_text(json.dumps({"chunkWidth": 66}))
            with self.assertRaises(ValueError):
                load_master(root)


if __name__ == "__main__":
    unittest.main()
