"""Debug the shoreline junction test to understand the coordinate system."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tilemap_generator.paint_map_png import get_water_adjacency_bitmask

# Map layout with coordinates:
#     x: 0 1 2
#   y:  +-----
#   0   | G B G
#   1   | B . ~
#   2   | G ~ ~

ascii_map = [
    "GBG",  # y=0
    "B.~",  # y=1
    "G~~",  # y=2
]

water_chars = frozenset("~`")

print("Map:")
for y, row in enumerate(ascii_map):
    print(f"  y={y}: {row}")
print()

# Test each cell
for y in range(len(ascii_map)):
    for x in range(len(ascii_map[y])):
        ch = ascii_map[y][x]
        mask = get_water_adjacency_bitmask(ascii_map, x, y, water_chars, 0)
        print(f"({x},{y}) = '{ch}' -> mask={mask}")

print("\nExpected:")
print("  (1,0) = 'B' should have water E at (2,0)='G' -> WRONG, no water there!")
print("  (1,1) = '.' should have water E at (2,1)='~' and S at (1,2)='~' -> mask 6")
print("  (0,1) = 'B' should have water S at (0,2)='G' -> WRONG, no water there!")
print("\nThe test map is wrong! Let me fix it:")

# Corrected map:
#     x: 0 1 2
#   y:  +-----
#   0   | G G G
#   1   | G B ~   (B at 1,1 is vertical edge with water E)
#   2   | G B ~   (B at 1,2 is the junction with water E and S)
#   3   | G ~ ~   (water at 1,3 and 2,3)

corrected_map = [
    "GGG",  # y=0
    "GB~",  # y=1 - vertical edge B
    "GB~",  # y=2 - junction B (water E and S)
    "G~~",  # y=3 - water
]

print("\nCorrected map:")
for y, row in enumerate(corrected_map):
    print(f"  y={y}: {row}")
print()

for y in range(len(corrected_map)):
    for x in range(len(corrected_map[y])):
        ch = corrected_map[y][x]
        mask = get_water_adjacency_bitmask(corrected_map, x, y, water_chars, 0)
        print(f"({x},{y}) = '{ch}' -> mask={mask}")

print("\nJunction at (1,2):")
junction_mask = get_water_adjacency_bitmask(corrected_map, 1, 2, water_chars, 0)
print(f"  mask={junction_mask} (expected 6 for S+E)")
print(f"  E neighbor at (2,2) = '{corrected_map[2][2]}' (should be water '~')")
print(f"  S neighbor at (1,3) = '{corrected_map[3][1]}' (should be water '~')")
