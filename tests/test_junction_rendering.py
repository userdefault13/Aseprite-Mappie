"""
End-to-end test for shoreline L-junction rendering.

This test creates a minimal L-junction map, paints it, and verifies that
the junction cell uses the correct inner-corner tile (not two straight edges).
"""
import sys
from pathlib import Path
from PIL import Image
import tempfile
import json

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tilemap_generator.paint_map_png import paint_map_to_png


def test_l_junction_renders_inner_corner_tile():
    """
    Test that an L-junction (vertical edge meeting horizontal edge) renders
    the correct inner-corner tile, not overlapping straight-edge tiles.
    
    Map layout (SE inner corner):
         0 1 2 3
       +--------
     0 | G G G G
     1 | G B ~ ~   <- vertical edge (water E)
     2 | G B ~ ~   <- junction (water E+S, should use SE inner corner tile)
     3 | G ~ ~ ~   <- horizontal contributes water S
    """
    
    # Create test map with SE inner corner at (1,2)
    ascii_lines = [
        "GGGG",
        "GB~~",
        "GB~~",  # Junction at (1,2): water E and S
        "G~~~",
    ]
    
    # Create legend
    legend = {
        "G": 1,
        "B": 98,
        "~": 2,
    }
    
    # Create tile_rows (required by paint_map_to_png)
    tile_rows = []
    for line in ascii_lines:
        row = [legend.get(ch, 1) for ch in line]
        tile_rows.append(row)
    
    # Set up paths
    workspace = Path("/workspace")
    shoreline_sheet = workspace / "examples" / "shorelines.png"
    grass_sheet = workspace / "examples" / "grass.png"
    
    # Verify required sheets exist
    assert shoreline_sheet.exists(), f"Shoreline sheet not found: {shoreline_sheet}"
    assert grass_sheet.exists(), f"Grass sheet not found: {grass_sheet}"
    
    # Load the shoreline sheet to get reference tiles
    shoreline_img = Image.open(shoreline_sheet)
    tile_size = 16
    
    # Extract tiles from shoreline sheet (row-major order)
    def get_tile(img, tile_idx_0based, tile_size=16):
        """Extract tile at 0-based index from sheet (row-major)."""
        cols = img.size[0] // tile_size
        row = tile_idx_0based // cols
        col = tile_idx_0based % cols
        x, y = col * tile_size, row * tile_size
        return img.crop((x, y, x + tile_size, y + tile_size))
    
    # From terrain.bitmask.json: shoreline_map[6] = 39 (1-based tile ID)
    # So SE corner (mask 6) should use tile at index 38 (0-based)
    se_corner_tile = get_tile(shoreline_img, 38, tile_size)
    
    # Also get straight edge tiles that should NOT be used at junction
    # mask 2 (E only) -> tile 3 (1-based) = index 2 (0-based)
    # mask 4 (S only) -> tile 5 (1-based) = index 4 (0-based)
    e_edge_tile = get_tile(shoreline_img, 2, tile_size)
    s_edge_tile = get_tile(shoreline_img, 4, tile_size)
    
    # Create output directory
    output_dir = workspace / "test_output"
    output_dir.mkdir(exist_ok=True)
    
    # Create temp output files and minimal stub images
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        water_out = tmp_path / "water.png"
        grass_out = tmp_path / "grass.png"
        dirt_out = tmp_path / "dirt.png"
        trees_out = tmp_path / "trees.png"
        shoreline_out = tmp_path / "shoreline.png"
        
        # Create minimal stub images for required assets
        stub_img = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
        trees_stub = tmp_path / "trees_stub.png"
        water_stub = tmp_path / "water_stub.png"
        dirt_stub = tmp_path / "dirt_stub.png"
        stub_img.save(trees_stub)
        stub_img.save(water_stub)
        stub_img.save(dirt_stub)
        
        # Load terrain config
        terrain_config = workspace / "terrain.bitmask.json"
        with open(terrain_config) as f:
            terrain_cfg = json.load(f)
        
        # Paint the map
        try:
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
            
            # Read the painted shoreline layer
            if not shoreline_out.exists():
                raise AssertionError(f"Shoreline output not created: {shoreline_out}")
            
            painted = Image.open(shoreline_out)
            
            # Extract the junction cell at (1,2)
            junction_x = 1 * tile_size
            junction_y = 2 * tile_size
            junction_tile = painted.crop((
                junction_x,
                junction_y,
                junction_x + tile_size,
                junction_y + tile_size
            ))
            
            # Save debug images
            junction_tile.save(output_dir / "junction_painted.png")
            se_corner_tile.save(output_dir / "se_corner_expected.png")
            e_edge_tile.save(output_dir / "e_edge_wrong.png")
            s_edge_tile.save(output_dir / "s_edge_wrong.png")
            painted.save(output_dir / "full_shoreline_layer.png")
            
            print(f"\nDebug images saved to {output_dir}/")
            print(f"  junction_painted.png - What was actually painted at junction")
            print(f"  se_corner_expected.png - SE corner tile from sheet (expected)")
            print(f"  e_edge_wrong.png - E edge tile (should NOT be used)")
            print(f"  s_edge_wrong.png - S edge tile (should NOT be used)")
            print(f"  full_shoreline_layer.png - Complete painted shoreline layer")
            
            # Compare pixels: junction should match SE corner, not straight edges
            def tiles_match(tile1, tile2, threshold=0.95):
                """Check if two tiles match (at least threshold% identical pixels)."""
                if tile1.size != tile2.size:
                    return False
                
                pixels1 = list(tile1.getdata())
                pixels2 = list(tile2.getdata())
                
                matching = sum(1 for p1, p2 in zip(pixels1, pixels2) if p1 == p2)
                total = len(pixels1)
                match_pct = matching / total if total > 0 else 0
                
                print(f"    Pixel match: {matching}/{total} ({match_pct*100:.1f}%)")
                
                return match_pct >= threshold
            
            print(f"\nPixel comparison:")
            print(f"  Junction vs SE corner tile:")
            matches_se_corner = tiles_match(junction_tile, se_corner_tile)
            
            print(f"  Junction vs E edge tile:")
            matches_e_edge = tiles_match(junction_tile, e_edge_tile)
            
            print(f"  Junction vs S edge tile:")
            matches_s_edge = tiles_match(junction_tile, s_edge_tile)
            
            print(f"\nResults:")
            print(f"  Matches SE corner: {matches_se_corner}")
            print(f"  Matches E edge: {matches_e_edge}")
            print(f"  Matches S edge: {matches_s_edge}")
            
            # The bug: junction uses wrong tile (straight edge instead of corner)
            if not matches_se_corner:
                print(f"\n❌ BUG CONFIRMED: Junction does not use SE corner tile!")
                print(f"   Expected: Tile 7 (SE inner corner with connected gray edges)")
                print(f"   Actual: Wrong tile (likely straight edge or wrong orientation)")
                return False
            
            if matches_e_edge or matches_s_edge:
                print(f"\n❌ BUG CONFIRMED: Junction uses straight edge tile instead of corner!")
                return False
            
            print(f"\n✓ Junction correctly uses SE corner tile")
            return True
            
        except Exception as e:
            print(f"\nError during painting: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    success = test_l_junction_renders_inner_corner_tile()
    
    if not success:
        print("\n" + "="*60)
        print("TEST FAILED: L-junction rendering bug confirmed")
        print("="*60)
        sys.exit(1)
    else:
        print("\n" + "="*60)
        print("TEST PASSED: L-junction renders correctly")
        print("="*60)
        sys.exit(0)
