"""
Test more complex L-junction scenarios that might trigger the bug.
"""
import sys
from pathlib import Path
from PIL import Image
import tempfile
import json

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tilemap_generator.paint_map_png import paint_map_to_png, get_water_adjacency_bitmask


def create_stub_assets(tmp_path, tile_size=16):
    """Create minimal stub PNGs for required assets."""
    stub_img = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
    trees_stub = tmp_path / "trees_stub.png"
    water_stub = tmp_path / "water_stub.png"
    dirt_stub = tmp_path / "dirt_stub.png"
    stub_img.save(trees_stub)
    stub_img.save(water_stub)
    stub_img.save(dirt_stub)
    return trees_stub, water_stub, dirt_stub


def paint_test_map(ascii_lines, output_name="test"):
    """Paint a test map and return the shoreline layer."""
    workspace = Path("/workspace")
    shoreline_sheet = workspace / "examples" / "shorelines.png"
    grass_sheet = workspace / "examples" / "grass.png"
    
    legend = {"G": 1, "B": 98, "~": 2, ".": 1}
    tile_rows = [[legend.get(ch, 1) for ch in line] for line in ascii_lines]
    
    tile_size = 16
    output_dir = workspace / "test_output"
    output_dir.mkdir(exist_ok=True)
    
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
            output_path = output_dir / f"{output_name}_shoreline.png"
            painted.save(output_path)
            return painted, output_path
    
    return None, None


def test_scenario_1_simple_l():
    """Scenario 1: Simple L-junction (already tested - passes)."""
    print("\n" + "="*60)
    print("Scenario 1: Simple L-junction")
    print("="*60)
    
    ascii_lines = [
        "GGGG",
        "GB~~",
        "GB~~",
        "G~~~",
    ]
    
    print("Map:")
    for i, line in enumerate(ascii_lines):
        print(f"  {i}: {line}")
    
    # Check water masks
    print("\nWater adjacency masks:")
    for y in range(len(ascii_lines)):
        for x in range(len(ascii_lines[y])):
            ch = ascii_lines[y][x]
            if ch == "B":
                mask = get_water_adjacency_bitmask(ascii_lines, x, y, frozenset("~"), 0)
                print(f"  B at ({x},{y}): mask={mask}")
    
    painted, path = paint_test_map(ascii_lines, "scenario1_simple_l")
    print(f"Output: {path}")
    return painted is not None


def test_scenario_2_double_bend():
    """Scenario 2: Shoreline with multiple bends (more realistic)."""
    print("\n" + "="*60)
    print("Scenario 2: Multiple bends in shoreline")
    print("="*60)
    
    ascii_lines = [
        "GGGGGG",
        "GBB~~~",
        "GB~~~~",
        "GB~~~~",
        "GBB~~~",
        "~~B~~~",
    ]
    
    print("Map:")
    for i, line in enumerate(ascii_lines):
        print(f"  {i}: {line}")
    
    # Check water masks
    print("\nWater adjacency masks:")
    for y in range(len(ascii_lines)):
        for x in range(len(ascii_lines[y])):
            ch = ascii_lines[y][x]
            if ch == "B":
                mask = get_water_adjacency_bitmask(ascii_lines, x, y, frozenset("~"), 0)
                print(f"  B at ({x},{y}): mask={mask}")
    
    painted, path = paint_test_map(ascii_lines, "scenario2_double_bend")
    print(f"Output: {path}")
    return painted is not None


def test_scenario_3_inner_corner_surrounded():
    """Scenario 3: Inner corner completely surrounded by other B cells."""
    print("\n" + "="*60)
    print("Scenario 3: Inner corner surrounded by B cells")
    print("="*60)
    
    ascii_lines = [
        "GGGGGG",
        "GBBB~~",
        "GB.B~~",  # . is grass, should be surrounded by B
        "GBBB~~",
        "G~~~~~",
    ]
    
    print("Map:")
    for i, line in enumerate(ascii_lines):
        print(f"  {i}: {line}")
    
    # Check water masks for the center cell
    print("\nWater adjacency mask for center grass (.)")
    mask = get_water_adjacency_bitmask(ascii_lines, 2, 2, frozenset("~"), 0)
    print(f"  . at (2,2): mask={mask} (should be 0, no direct water)")
    
    painted, path = paint_test_map(ascii_lines, "scenario3_surrounded")
    print(f"Output: {path}")
    return painted is not None


def test_scenario_4_bay_inlet():
    """Scenario 4: Bay or inlet (water indentation into land)."""
    print("\n" + "="*60)
    print("Scenario 4: Bay inlet")
    print("="*60)
    
    ascii_lines = [
        "GGGGGGGG",
        "GBBBBBBB",
        "GB~~~~BG",
        "GB~~~~BG",
        "GBBBBBGG",
        "GGGGGGGG",
    ]
    
    print("Map:")
    for i, line in enumerate(ascii_lines):
        print(f"  {i}: {line}")
    
    # Check water masks
    print("\nWater adjacency masks for inner corners:")
    for y in range(len(ascii_lines)):
        for x in range(len(ascii_lines[y])):
            ch = ascii_lines[y][x]
            if ch == "B":
                mask = get_water_adjacency_bitmask(ascii_lines, x, y, frozenset("~"), 0)
                if mask in [3, 6, 9, 12]:  # Corner masks
                    print(f"  B at ({x},{y}): mask={mask}")
    
    painted, path = paint_test_map(ascii_lines, "scenario4_bay")
    print(f"Output: {path}")
    return painted is not None


if __name__ == "__main__":
    print("Testing various L-junction and corner scenarios...")
    
    results = []
    results.append(("Simple L-junction", test_scenario_1_simple_l()))
    results.append(("Double bend", test_scenario_2_double_bend()))
    results.append(("Surrounded corner", test_scenario_3_inner_corner_surrounded()))
    results.append(("Bay inlet", test_scenario_4_bay_inlet()))
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for name, success in results:
        status = "✓" if success else "✗"
        print(f"{status} {name}")
    
    print(f"\nAll painted outputs saved to: /workspace/test_output/")
