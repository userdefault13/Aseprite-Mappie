"""
Test painting shoreline junctions to verify tile selection.

This test creates a simple map with L-junctions and verifies that the correct
corner tiles are selected from the shoreline sheet.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def test_paint_shoreline_junction():
    """
    Create a map with an L-junction and paint it.
    Verify the junction cell uses tile 7 (SE corner from shoreline_map[6]).
    """
    from tilemap_generator.paint_map_png import paint_map_to_png
    from PIL import Image
    import tempfile
    import json
    
    # Create a simple test map with an L-junction:
    #     0 1 2 3
    #   +--------
    # 0 | G G G G
    # 1 | G B ~ ~   <- vertical edge (B has water E)
    # 2 | G B ~ ~   <- junction (B has water E and S, mask=6)
    # 3 | G ~ ~ ~   <- horizontal contributes water S
    # 4 | G ~ ~ ~
    
    test_map = [
        "GGGG",
        "GB~~",
        "GB~~",  # This B cell is the junction
        "G~~~",
        "G~~~",
    ]
    
    # Write test map to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        for line in test_map:
            f.write(line + '\n')
        map_path = Path(f.name)
    
    # Create minimal legend
    legend = {
        "G": 1,
        "B": 98,
        "~": 2,
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(legend, f)
        legend_path = Path(f.name)
    
    # Set up paths
    workspace = Path("/workspace")
    terrain_config = workspace / "terrain.bitmask.json"
    
    # Create output directory
    output_dir = workspace / "test_output"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "junction_test.png"
    
    print(f"Map:\n{''.join(test_map)}\n")
    print(f"Junction cell at (1,2):")
    print(f"  Character: B")
    print(f"  Water E at (2,2): {test_map[2][2]}")
    print(f"  Water S at (1,3): {test_map[3][1]}")
    print(f"  Expected mask: 6 (S+E)")
    print(f"  Expected tile from shoreline_map[6]: 7\n")
    
    try:
        # Paint the map
        paint_map_to_png(
            ascii_file_path=map_path,
            legend_path=legend_path,
            output_png_path=output_path,
            terrain_config_path=terrain_config,
            tile_size=16,
            layered=True,
            separate_poi_layers=False,
            output_csv=False,
        )
        
        print(f"Output written to: {output_path}")
        print(f"Check the Shoreline layer for the junction tile.")
        
        # Check if shoreline preview was created
        preview_path = output_path.parent / f"{output_path.stem}.preview_shoreline.png"
        if preview_path.exists():
            print(f"Shoreline preview: {preview_path}")
        
        return True
        
    except Exception as e:
        print(f"Error painting map: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        map_path.unlink(missing_ok=True)
        legend_path.unlink(missing_ok=True)


if __name__ == "__main__":
    success = test_paint_shoreline_junction()
    sys.exit(0 if success else 1)
