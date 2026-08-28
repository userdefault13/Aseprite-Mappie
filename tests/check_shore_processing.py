"""Check shore_ascii_lines after processing."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tilemap_generator.paint_map_png import (
    close_ocean_shoreline_gaps,
    close_lake_shoreline_gaps,
    fill_bay_diagonal_shoreline,
    demote_shoreline_without_water_neighbor,
    filter_isolated_lake_shoreline,
    propagate_shore_masks,
    get_ocean_connected_mask,
    get_water_mask_grid,
)

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

width = max(len(line) for line in ascii_lines)
height = len(ascii_lines)
ocean_connected = get_ocean_connected_mask(ascii_lines, frozenset("~`"), 0, width, height)
water_mask_grid = get_water_mask_grid(ascii_lines, frozenset("~`"), 0, width, height)

shore_ascii_lines = close_ocean_shoreline_gaps(ascii_lines)
shore_ascii_lines = close_lake_shoreline_gaps(shore_ascii_lines, water_chars=frozenset("~"))
shore_ascii_lines = fill_bay_diagonal_shoreline(shore_ascii_lines, ocean_connected, width, height)
shore_ascii_lines = demote_shoreline_without_water_neighbor(shore_ascii_lines, ocean_connected, width, height)
shore_ascii_lines = filter_isolated_lake_shoreline(shore_ascii_lines)

print("Original ASCII (1,1):", ascii_lines[1][1])
print("Processed shore_ascii_lines (1,1):", shore_ascii_lines[1][1])

print("\nOriginal row 1:", ascii_lines[1])
print("Processed row 1:", shore_ascii_lines[1])
