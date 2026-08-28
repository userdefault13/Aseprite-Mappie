"""Check if inset_candidate is True for the elbow."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tilemap_generator.paint_map_png import get_water_adjacency_bitmask

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

x, y = 1, 1
ch = ascii_lines[y][x]
wmask = get_water_adjacency_bitmask(ascii_lines, x, y, frozenset("~"), 0)

print(f"Elbow at ({x},{y}):")
print(f"  ch = '{ch}'")
print(f"  wmask = {wmask}")

# Check if it's adjacent to a shoreline cell
def adjacent_to_shoreline(x, y):
    for dx, dy in [(-1,0), (1,0), (0,-1), (0,1)]:
        nx, ny = x + dx, y + dy
        if 0 <= ny < len(ascii_lines) and 0 <= nx < len(ascii_lines[ny]):
            if ascii_lines[ny][nx] == 'B':
                return True
    return False

# Check if adjacent shoreline has water
def adjacent_to_shoreline_with_water(x, y):
    for dx, dy in [(-1,0), (1,0), (0,-1), (0,1)]:
        nx, ny = x + dx, y + dy
        if 0 <= ny < len(ascii_lines) and 0 <= nx < len(ascii_lines[ny]):
            if ascii_lines[ny][nx] == 'B':
                # Check if this B cell has water adjacent to it
                b_mask = get_water_adjacency_bitmask(ascii_lines, nx, ny, frozenset("~"), 0)
                if b_mask != 0:
                    return True
    return False

adj_shore = adjacent_to_shoreline(x, y)
adj_shore_water = adjacent_to_shoreline_with_water(x, y)

print(f"  adjacent_to_shoreline = {adj_shore}")
print(f"  adjacent_to_shoreline_with_water = {adj_shore_water}")

# inset_candidate logic from the code
land_chars = frozenset("G.P")
inset_candidate = (
    (ch in land_chars)
    and wmask == 0
    and adj_shore
    and adj_shore_water
)

explicit_shore = ch == "B"

print(f"\nChecks:")
print(f"  ch in land_chars: {ch in land_chars}")
print(f"  wmask == 0: {wmask == 0}")
print(f"  adjacent_to_shoreline: {adj_shore}")
print(f"  adjacent_to_shoreline_with_water: {adj_shore_water}")
print(f"  inset_candidate: {inset_candidate}")
print(f"  explicit_shore: {explicit_shore}")
print(f"  explicit_shore and wmask == 0: {explicit_shore and wmask == 0}")

print(f"\nConclusion:")
if inset_candidate:
    print("  Will call _get_ocean_inset_special_tile, but if it returns None,")
    print("  will fall back to _pick_interior_grass() at line 4698-4699")
elif explicit_shore and wmask == 0:
    print("  Will call _get_ocean_inset_special_tile with allow_shore_cell=True")
    print("  This should work for B cells with wmask==0")
else:
    print("  Will NOT use inset logic")
