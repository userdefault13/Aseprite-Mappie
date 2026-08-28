"""Analyze the actual L-junction geometry."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tilemap_generator.paint_map_png import get_water_adjacency_bitmask

# The user's exact ASCII
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

print("Map:")
for i, line in enumerate(ascii_lines):
    print(f"  {i}: {line}")

print("\nWater adjacency masks for B cells:")
for y in range(len(ascii_lines)):
    for x in range(len(ascii_lines[y])):
        ch = ascii_lines[y][x]
        if ch == "B":
            mask = get_water_adjacency_bitmask(ascii_lines, x, y, frozenset("~"), 0)
            print(f"  B at ({x},{y}): mask={mask}")

print("\nThe L-junction elbow:")
print("  Position (1,1): 'B' with mask=0 (no direct water)")
print("  North (1,0): 'G' - grass")
print("  East (2,1): 'B' - horizontal straight (water S)")
print("  South (1,2): 'B' - vertical straight (water E)")
print("  West (0,1): 'G' - grass")
print("\nThis is an INSET corner - no direct water, but connects two shoreline edges.")
