"""Debug version to trace tile selection for the elbow."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Monkey-patch to add debug output
original_get_ocean_inset_special_tile = None

def debug_wrapper(original_func):
    def wrapper(ax, ay, *, allow_shore_cell=False):
        result = original_func(ax, ay, allow_shore_cell=allow_shore_cell)
        if ax == 1 and ay == 1:
            print(f"DEBUG: _get_ocean_inset_special_tile({ax},{ay}, allow_shore_cell={allow_shore_cell}) -> {result}")
        return result
    return wrapper

# Import and patch
from tilemap_generator import paint_map_png
import tilemap_generator.paint_map_png as pm_module

# Find the function in the module's scope during painting
print("This approach won't work - the function is defined inside paint_map_to_png")
print("Let me check the actual painted tile index instead...")

# Load the painted crop and compare against all tiles
from PIL import Image

crop = Image.open("/workspace/test_output/user_ascii_elbow_crop.png")
sheet = Image.open("/workspace/examples/shorelines.png")

tile_size = 16
elbow_x = 1 * tile_size
elbow_y = 1 * tile_size
elbow_tile = crop.crop((elbow_x, elbow_y, elbow_x + tile_size, elbow_y + tile_size))

print(f"\nComparing elbow tile against all tiles in sheet:")
cols = sheet.size[0] // tile_size

best_match = -1
best_pct = 0.0

for idx in range(45):
    row = idx // cols
    col = idx % cols
    x, y = col * tile_size, row * tile_size
    tile = sheet.crop((x, y, x + tile_size, y + tile_size))
    
    pixels_elbow = list(elbow_tile.getdata())
    pixels_tile = list(tile.getdata())
    matching = sum(1 for p1, p2 in zip(pixels_elbow, pixels_tile) if p1 == p2)
    total = len(pixels_elbow)
    match_pct = matching / total if total > 0 else 0
    
    if match_pct > best_pct:
        best_pct = match_pct
        best_match = idx
    
    if match_pct > 0.95:
        print(f"  Tile {idx}: {match_pct*100:.1f}% match ✓")

print(f"\nBest match: Tile {best_match} ({best_pct*100:.1f}%)")
print(f"Expected: Tile 36 (inset corner for direct_top_right)")

# Check if it matches interior grass instead
grass_sheet = Image.open("/workspace/examples/grass.png")
grass_tile_1 = grass_sheet.crop((0, 0, tile_size, tile_size))
pixels_grass = list(grass_tile_1.getdata())
grass_match = sum(1 for p1, p2 in zip(pixels_elbow, pixels_grass) if p1 == p2) / len(pixels_elbow)
print(f"Match to grass tile 1: {grass_match*100:.1f}%")
