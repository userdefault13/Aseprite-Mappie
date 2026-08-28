"""Paint the user's exact ASCII and check what tile is used at the elbow."""
import sys
from pathlib import Path
from PIL import Image
import tempfile
import json

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tilemap_generator.paint_map_png import paint_map_to_png

# User's exact ASCII
ascii_lines = [
    "GGGGGG~~~~",
    "GBBBBB~~~~",
    "GB~~~~~~~~",
    "GB~~~~~~~~",
    "GB~~~~~~~~",
    "GB~~~~~~~~",
    "~~~~~~~~~~",
    "~~~~~~~~~~",
]

legend = {"G": 1, "B": 98, "~": 2}
tile_rows = [[legend.get(ch, 1) for ch in line] for line in ascii_lines]

workspace = Path("/workspace")
shoreline_sheet = workspace / "examples" / "shorelines.png"
grass_sheet = workspace / "examples" / "grass.png"

tile_size = 16
output_dir = workspace / "test_output"
output_dir.mkdir(exist_ok=True)

def create_stub_assets(tmp_path, tile_size=16):
    stub_img = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
    trees_stub = tmp_path / "trees_stub.png"
    water_stub = tmp_path / "water_stub.png"
    dirt_stub = tmp_path / "dirt_stub.png"
    stub_img.save(trees_stub)
    stub_img.save(water_stub)
    stub_img.save(dirt_stub)
    return trees_stub, water_stub, dirt_stub

with tempfile.TemporaryDirectory() as tmpdir:
    tmp_path = Path(tmpdir)
    trees_stub, water_stub, dirt_stub = create_stub_assets(tmp_path, tile_size)
    
    water_out = tmp_path / "water.png"
    grass_out = tmp_path / "grass.png"
    dirt_out = tmp_path / "dirt.png"
    trees_out = tmp_path / "trees.png"
    shoreline_out = tmp_path / "shoreline.png"
    
    terrain_config = workspace / "terrain.bitmask.json"
    with open(terrain_config) as f:
        terrain_cfg = json.load(f)
    
    paint_map_to_png(
        ascii_lines=ascii_lines,
        legend=legend,
        tile_rows=tile_rows,
        tile_size=tile_size,
        trees_sheet_path=trees_stub,
        water_out=water_out,
        grass_out=grass_out,
        dirt_out=dirt_out,
        trees_out=trees_out,
        shoreline_out=shoreline_out,
        grass_sheet_path=grass_sheet,
        shoreline_sheet_path=shoreline_sheet,
        water_path=water_stub,
        dirt_path=dirt_stub,
        grass_bitmask_config=terrain_cfg,
        water_border_width=0,
        ascii_water_border=0,
        seed=42,
    )
    
    if shoreline_out.exists():
        painted = Image.open(shoreline_out)
        painted.save(output_dir / "user_ascii_shoreline.png")
        
        # Extract the 5x5 crop around the elbow (1,1)
        crop_x = 0 * tile_size
        crop_y = 0 * tile_size
        crop_width = 5 * tile_size
        crop_height = 5 * tile_size
        
        crop = painted.crop((crop_x, crop_y, crop_x + crop_width, crop_y + crop_height))
        crop.save(output_dir / "user_ascii_elbow_crop.png")
        
        # Extract just the elbow tile at (1,1)
        elbow_x = 1 * tile_size
        elbow_y = 1 * tile_size
        elbow_tile = painted.crop((elbow_x, elbow_y, elbow_x + tile_size, elbow_y + tile_size))
        elbow_tile.save(output_dir / "elbow_tile_painted.png")
        
        print(f"Saved full shoreline: {output_dir}/user_ascii_shoreline.png")
        print(f"Saved 5x5 crop: {output_dir}/user_ascii_elbow_crop.png")
        print(f"Saved elbow tile at (1,1): {output_dir}/elbow_tile_painted.png")
        
        # Compare against tile 36
        sheet = Image.open(shoreline_sheet)
        tile_36_row = 36 // 5
        tile_36_col = 36 % 5
        x, y = tile_36_col * tile_size, tile_36_row * tile_size
        tile_36 = sheet.crop((x, y, x + tile_size, y + tile_size))
        tile_36.save(output_dir / "tile_36_from_sheet.png")
        
        # Check if they match
        pixels_elbow = list(elbow_tile.getdata())
        pixels_36 = list(tile_36.getdata())
        matching = sum(1 for p1, p2 in zip(pixels_elbow, pixels_36) if p1 == p2)
        total = len(pixels_elbow)
        match_pct = matching / total if total > 0 else 0
        
        print(f"\nElbow tile vs Tile 36: {matching}/{total} pixels match ({match_pct*100:.1f}%)")
        
        if match_pct > 0.95:
            print("✓ Elbow IS using tile 36 (inset corner)")
        else:
            print("✗ Elbow is NOT using tile 36")
