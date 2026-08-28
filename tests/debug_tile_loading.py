"""Debug script to check shoreline tile loading."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tilemap_generator.paint_map_png import load_grass_from_sheet
from PIL import Image

# Load shoreline tiles
shoreline_path = Path("/workspace/examples/shorelines.png")
tile_size = 16
shoreline_range = (1, 55)  # From terrain.bitmask.json

print(f"Loading shoreline tiles from: {shoreline_path}")
print(f"Tile size: {tile_size}x{tile_size}")
print(f"Tile range: {shoreline_range}")
print()

try:
    tiles = load_grass_from_sheet(
        shoreline_path,
        tile_size,
        tile_range=shoreline_range,
        tileset_json_path=None
    )
    
    print(f"Loaded {len(tiles)} tiles")
    print(f"Tiles is None: {tiles is None}")
    if tiles:
        print(f"First tile: {tiles[0]}")
        print(f"First tile type: {type(tiles[0])}")
        if tiles[0]:
            print(f"First tile size: {tiles[0].size}")
            print(f"First tile mode: {tiles[0].mode}")
        
        # Check tile 7 (should be SE corner for mask 6)
        if len(tiles) > 6:
            tile_7 = tiles[6]  # 0-indexed, so tile 7 is at index 6
            print(f"\nTile 7 (index 6, for mask=6 SE corner):")
            print(f"  Tile: {tile_7}")
            print(f"  Type: {type(tile_7)}")
            if tile_7:
                print(f"  Size: {tile_7.size}")
                print(f"  Mode: {tile_7.mode}")
                if hasattr(tile_7, "mode") and "A" in tile_7.mode:
                    alpha = tile_7.getchannel("A")
                    extrema = alpha.getextrema()
                    print(f"  Alpha range: {extrema}")
                    print(f"  Is visible (alpha max > 8): {extrema[1] > 8}")
    else:
        print("Tiles list is empty!")
        
except Exception as e:
    print(f"Error loading tiles: {e}")
    import traceback
    traceback.print_exc()

# Also check the shoreline_map
import json
terrain_config = Path("/workspace/terrain.bitmask.json")
with open(terrain_config) as f:
    config = json.load(f)

shoreline_map = config["shoreline"]["shoreline_map"]
print(f"\nShoreline bitmask map (from terrain.bitmask.json):")
for mask, tile_id in sorted(shoreline_map.items(), key=lambda x: int(x[0])):
    print(f"  mask {mask:2s} -> tile {tile_id:2d}")

print(f"\nFor mask 6 (SE corner, water S+E):")
print(f"  Expected tile ID: {shoreline_map['6']}")
print(f"  Expected tile index (0-based): {shoreline_map['6'] - 1}")
