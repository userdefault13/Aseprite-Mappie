"""Regression test for L-junction shoreline autotiling bug.

Tests that B cells with wmask=0 forming L-junctions (two straight edges meeting
at a 90° angle) use the correct inner corner tile instead of overlapping straights.
"""
import sys
from pathlib import Path
import tempfile
import json
from PIL import Image

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tilemap_generator.paint_map_png import paint_map_to_png


def test_l_junction_se_inner_corner():
    """Test SE inner corner L-junction (E and S neighbors are B)."""
    # The exact ASCII from the bug report
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
    
    workspace = Path(__file__).parent.parent
    shoreline_sheet = workspace / "examples" / "shorelines.png"
    grass_sheet = workspace / "examples" / "grass.png"
    
    tile_size = 16
    
    def create_stub_assets(tmp_path):
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
        trees_stub, water_stub, dirt_stub = create_stub_assets(tmp_path)
        
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
        
        assert shoreline_out.exists(), "Shoreline layer not painted"
        
        painted = Image.open(shoreline_out)
        sheet = Image.open(shoreline_sheet)
        
        def get_sheet_tile(tile_id_1based):
            """Extract tile from sheet (1-based ID)."""
            idx = tile_id_1based - 1  # Convert to 0-based
            cols = 5
            row, col = idx // cols, idx % cols
            x, y = col * tile_size, row * tile_size
            return sheet.crop((x, y, x + tile_size, y + tile_size))
        
        def get_painted_tile(tx, ty):
            """Extract tile from painted image."""
            x, y = tx * tile_size, ty * tile_size
            return painted.crop((x, y, x + tile_size, y + tile_size))
        
        def tiles_match(t1, t2):
            """Check if two tiles are pixel-identical."""
            p1 = list(t1.getdata())
            p2 = list(t2.getdata())
            return all(a == b for a, b in zip(p1, p2))
        
        # Critical assertions: the L-junction elbow must use tile 37 (SE inner corner)
        elbow_tile = get_painted_tile(1, 1)
        expected_tile_37 = get_sheet_tile(37)
        assert tiles_match(elbow_tile, expected_tile_37), \
            "Elbow at (1,1) must use tile 37 (SE inner corner), not overlapping straights"
        
        # Verify neighboring straights are still correct
        for tx in [2, 3, 4]:
            horiz_tile = get_painted_tile(tx, 1)
            expected_tile_5 = get_sheet_tile(5)
            assert tiles_match(horiz_tile, expected_tile_5), \
                f"Horizontal straight at ({tx},1) must use tile 5"
        
        for ty in [2, 3, 4]:
            vert_tile = get_painted_tile(1, ty)
            expected_tile_3 = get_sheet_tile(3)
            assert tiles_match(vert_tile, expected_tile_3), \
                f"Vertical straight at (1,{ty}) must use tile 3"


if __name__ == "__main__":
    test_l_junction_se_inner_corner()
    print("✓ L-junction regression test PASSED")
