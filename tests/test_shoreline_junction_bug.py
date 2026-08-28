"""Test for shoreline L-junction bug where inner corners don't form properly."""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tilemap_generator.paint_map_png import get_water_adjacency_bitmask


def test_shoreline_l_junction_vertical_meets_horizontal():
    """
    Test case: vertical shoreline (water E) meets horizontal shoreline (water S).
    
    The junction cell (1,1) should have water adjacency mask = 6 (S+E).
    Expected tile from shoreline_map: mask 6 -> tile 7 (SE inner corner).
    
    Current bug: junction shows two separate edge tiles instead of corner tile.
    
    Map layout:
        0 1 2
      +-----
    0 | G B G
    1 | B . ~  (. is junction: should be B with mask 6)
    2 | G ~ ~
    
    Where:
    - G = grass (interior)
    - B = beach/shoreline
    - ~ = water
    - . = the junction cell (should be B)
    """
    ascii_map = [
        "GBG",
        "B.~",
        "G~~",
    ]
    
    water_chars = frozenset("~`")
    
    # Test the junction cell at (1,1) - it's marked as '.' but should be 'B'
    # with water to the E and S
    junction_mask = get_water_adjacency_bitmask(
        ascii_map, x=1, y=1, water_chars=water_chars, border_width=0
    )
    
    # Expected: mask 6 (S+E) because water is at (2,1)=E and (1,2)=S
    # Bit values: N=1, E=2, S=4, W=8
    # S+E = 4+2 = 6
    assert junction_mask == 6, f"Junction mask should be 6 (S+E), got {junction_mask}"
    
    # Also test the vertical edge cell at (1,0) - should have water E only
    vertical_mask = get_water_adjacency_bitmask(
        ascii_map, x=1, y=0, water_chars=water_chars, border_width=0
    )
    assert vertical_mask == 2, f"Vertical edge mask should be 2 (E), got {vertical_mask}"
    
    # Also test the horizontal edge cell at (0,1) - should have water S only
    horizontal_mask = get_water_adjacency_bitmask(
        ascii_map, x=0, y=1, water_chars=water_chars, border_width=0
    )
    assert horizontal_mask == 4, f"Horizontal edge mask should be 4 (S), got {horizontal_mask}"


def test_shoreline_l_junction_all_four_orientations():
    """Test all four L-junction orientations (NE, SE, SW, NW corners)."""
    
    # SE corner: water E and S
    map_se = [
        "GBG",
        "B.~",  # junction at (1,1)
        "G~~",
    ]
    mask_se = get_water_adjacency_bitmask(map_se, 1, 1, frozenset("~"), 0)
    assert mask_se == 6, f"SE corner should be mask 6 (S+E), got {mask_se}"
    
    # SW corner: water W and S
    map_sw = [
        "GBG",
        "~.B",  # junction at (1,1)
        "~~G",
    ]
    mask_sw = get_water_adjacency_bitmask(map_sw, 1, 1, frozenset("~"), 0)
    assert mask_sw == 12, f"SW corner should be mask 12 (S+W), got {mask_sw}"
    
    # NE corner: water N and E
    map_ne = [
        "G~~",
        "B.~",  # junction at (1,1)
        "GBG",
    ]
    mask_ne = get_water_adjacency_bitmask(map_ne, 1, 1, frozenset("~"), 0)
    assert mask_ne == 3, f"NE corner should be mask 3 (N+E), got {mask_ne}"
    
    # NW corner: water N and W
    map_nw = [
        "~~G",
        "~.B",  # junction at (1,1)
        "GBG",
    ]
    mask_nw = get_water_adjacency_bitmask(map_nw, 1, 1, frozenset("~"), 0)
    assert mask_nw == 9, f"NW corner should be mask 9 (N+W), got {mask_nw}"


if __name__ == "__main__":
    test_shoreline_l_junction_vertical_meets_horizontal()
    test_shoreline_l_junction_all_four_orientations()
    print("All shoreline junction tests passed!")
