# L-Junction Shoreline Autotiling Fix

## Summary

Fixed the shoreline L-junction autotiling bug where concave inner corners (formed by two straight shoreline edges meeting at 90°) were rendering incorrectly with overlapping straight tiles instead of proper inner corner tiles.

## The Bug

When painting this ASCII map:
```
GGGGGG~~~~
GBBBBB~~~~
GB~~~~~~~~
GB~~~~~~~~
GB~~~~~~~~
GB~~~~~~~~
~~~~~~~~~~
~~~~~~~~~~
```

The B cell at (1,1) - the "elbow" of the L-junction - was using the wrong tile, causing:
- Disconnected gray rock edges (vertical and horizontal straights didn't connect)
- Visual artifact at the junction
- Two overlapping straight tiles instead of one inner corner

## Root Cause

The B cell at (1,1) has:
- Water mask = 0 (no direct NESW water)
- Neighbors: N=G, E=B, S=B, W=G (pattern: direct_top_right)

This specific L-junction pattern wasn't being handled before hundreds of lines of other junction special cases in `_pick_grass_tile()`, so it fell through to incorrect tile selection.

## The Fix

### Code Changes (`src/tilemap_generator/paint_map_png.py`)

Added early L-junction detection at the START of `_pick_grass_tile()`:

```python
# CRITICAL FIX FOR L-JUNCTION BUG: Handle B cells with wmask=0 that form L-junctions
if shore_ch == "B" and wmask == 0 and shoreline_sheet_path and shoreline_sheet_path.exists():
    has_n_b = shore_ascii_lines[y - 1][x] == "B" if y > 0 and x < len(shore_ascii_lines[y - 1]) else False
    has_e_b = shore_ascii_lines[y][x + 1] == "B" if x + 1 < width and x + 1 < len(shore_ascii_lines[y]) else False
    has_s_b = shore_ascii_lines[y + 1][x] == "B" if y + 1 < height and x < len(shore_ascii_lines[y + 1]) else False
    has_w_b = shore_ascii_lines[y][x - 1] == "B" if x > 0 else False
    
    l_junction_tile = None
    # E and S neighbors are B (horizontal + vertical straight) -> top-right inner corner
    if not has_n_b and has_e_b and has_s_b and not has_w_b:
        l_junction_tile = shoreline_inset_direct_corner_tiles.get("direct_top_right")
    # ... (other three orientations)
    
    if l_junction_tile is not None:
        # Return the inner corner tile
        return grass_shoreline[l_junction_tile - shore_start], True
```

### Configuration Changes (`terrain.bitmask.json`)

Configured the correct inner corner tiles:

```json
"inset_corner_tiles": {
  "top_left": 38,    // SW inner: cliffs on L+B
  "top_right": 37,   // SE inner: cliffs on R+B  ← THIS ONE for the bug
  "bottom_left": 40, // NW inner: cliffs on L+T
  "bottom_right": 39 // NE inner: cliffs on R+T
},
"inset_direct_corner_tiles": {
  "top_left": 38,
  "top_right": 37,   // ← Maps direct_top_right pattern to tile 37
  "bottom_left": 40,
  "bottom_right": 39
}
```

**Important**: The `shoreline_map` masks 3/6/9/12 remain mapped to OUTER convex corner tiles 4/7/10/13 (not inner corners). These are two-water-side corners.

## Inner Corner Tiles (examples/shorelines.png)

- **Tile 37** (1-based): SE inner corner - gray rock on RIGHT and BOTTOM
- **Tile 38** (1-based): SW inner corner - gray rock on LEFT and BOTTOM
- **Tile 39** (1-based): NE inner corner - gray rock on RIGHT and TOP
- **Tile 40** (1-based): NW inner corner - gray rock on LEFT and TOP

## Verification

### Regression Test (`tests/test_l_junction_regression.py`)

Paints the exact ASCII from the bug report and verifies:
- Elbow (1,1): tile 37 (pixel-perfect match)
- Horizontal straights (2,1)(3,1)(4,1): tile 5
- Vertical straights (1,2)(1,3)(1,4): tile 3

Run with: `python3 tests/test_l_junction_regression.py`

### Proof Image (`build/proof_l_junction.png`)

Visual proof showing:
- 5x5 junction crop with grid overlay
- Labeled key cells
- Reference tiles (37, 3, 5) with descriptions
- Success indicators confirming connected edges

Generate with: `python3 tests/create_proof_l_junction.py`

## Result

✓ Gray rock edges connect seamlessly in a clean 90° inner corner
✓ No overlapping straight tiles
✓ No visual artifacts at junction
✓ All four L-junction orientations supported

## Files Changed

- `src/tilemap_generator/paint_map_png.py`: L-junction detection logic
- `terrain.bitmask.json`: Inner corner tile configuration
- `tests/test_l_junction_regression.py`: Regression test
- `tests/create_proof_l_junction.py`: Proof image generator
- `build/proof_l_junction.png`: Visual proof
