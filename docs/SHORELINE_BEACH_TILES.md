# Shoreline / Beach Tile Handling

This document describes how shoreline and beach tiles are identified, expanded, and painted in the Aseprite-Mappie pipeline.

---

## Overview

Shoreline tiles are land cells adjacent to water. The system distinguishes three types:

| Char | Name | Description |
|------|------|-------------|
| **B** | Continent shoreline | Grass adjacent to ocean (map edge or water connected to ocean via NESW) |
| **L** | Lake shoreline | Grass adjacent to inland water (lakes/ponds not connected to ocean) |
| **R** | River bank | Grass adjacent to river water that does NOT connect to ocean |

**Precedence:** Continent (B) > Lake (L) > River (R). A cell touching both ocean and lake water becomes B.

---

## 1. Map Generation: Identifying Shoreline Cells

### Ocean vs Lake Detection

- **Ocean-connected water:** Water cells reachable via NESW from the map edge. In island mode, the outer 2-tile border is treated as ocean.
- **Lake water:** Inland water not connected to the ocean.
- **River water:** Narrow channels (exactly 2 opposite water neighbors: N+S or E+W).

### Cell Classification

1. **`continent_shoreline_cells`** — Grass adjacent to map edge or ocean-connected water → **B**
2. **`lake_shoreline_cells`** — Grass adjacent to inland water, excluding continent shore → **L**
3. **`river_bank_cells`** — Grass adjacent to river water (no ocean outlet), excluding B and L → **R**

### Beach Expansion by Height

Low land near water can be expanded into a wider beach band:

- **`beach_height_max`** (default 0.45): Max height for a cell to be considered beach. Cells with height ≤ this value can be promoted to shoreline.
- **`shoreline_expand_depth`** (default 0): How many tiles inland to expand. `0` = strict 1-tile border; higher values widen the beach where land is low.
- **`expand_shoreline_by_height`** expands continent shore, lake shore, and river bank using a heightmap (Perlin noise). Only grass cells with height ≤ `beach_height_max` are expanded.

### Shoreline Gap Closing

**`close_ocean_shoreline_gaps`** promotes land cells to B so the shoreline chain stays connected:

- Fills single-tile gaps between shoreline cells
- Promotes tree bridges when diagonal shoreline cells would otherwise be disconnected
- Extends shoreline through path cells (P) adjacent to water
- Trims landward corners from 2×2 shoreline blocks (avoids square blobs)
- Enforces: any land directly adjacent to ocean-connected water must be B

---

## 2. Water Adjacency Bitmask

Each shoreline cell gets a **4-bit water adjacency mask** based on NESW neighbors:

| Bit | Direction | Value |
|-----|-----------|-------|
| N   | North     | 1     |
| E   | East      | 2     |
| S   | South     | 4     |
| W   | West      | 8     |

**Examples:**

- `0` — No water (interior)
- `1` — Water N
- `5` — Water N+S (vertical edge)
- `10` — Water E+W (horizontal edge)
- `7` — Water N+E+S (peninsula/bay)
- `15` — Water all sides (island)

Out-of-bounds (map edge) counts as water when `water_border_width > 0`.

### Mask Propagation

For expanded beach bands, cells in the middle of a B/L/R region may not touch water directly. **`propagate_shore_masks`** infers their mask from neighboring shoreline cells so the correct tile is chosen (e.g. when using a dedicated shoreline sheet).

---

## 3. Paint Step: Tile Selection

### Tile Sources

- **`shoreline_path`** (e.g. `shorelines.aseprite`): Dedicated continent shoreline tiles. Uses `shoreline.shoreline_map` for bitmask → tile index.
- **`grass_path`** with `grass_shoreline`: Shoreline tiles embedded in the grass sheet (e.g. indices 98–118). Uses `grass_shoreline` mapping.
- **`lakesrivers_path`**: Lake and river tiles. Uses `lake.lake_map` and `river.river_map`.

### Selection Order

For each B/L/R cell, the paint logic tries (in order):

1. **Special tiles** — Explicit junctions (T-junctions, beach_west, beach_east, lake_east)
2. **Inset corner tiles** — Inland cells surrounded by shoreline (no direct water) that connect diagonal shoreline chains
3. **Lake shoreline** — L cells use `lake_map` or `lake_shoreline` when available
4. **River bank** — R cells use `river_map` for masks 5 (N+S) and 10 (E+W)
5. **Extended shoreline** — Peninsula/island masks (7, 11, 13, 14, 15) use `grass_shoreline_extended_range` when set
6. **Continent shoreline** — B cells use `shoreline_map` (if `shoreline_path` set) or `grass_shoreline_map`

### Special Tiles

| Context | Condition | Tile |
|---------|-----------|------|
| Ocean T-junction (water W) | mask=8, N+S+E shore, no W | `tee_west` |
| Ocean T-junction (water E) | mask=2, N+S+W shore, no E | `tee_east` |
| Lake meets beach (W) | mask=2, W=beach, no E | `beach_west` |
| Lake meets beach (E) | mask=8, N+S+E=beach, no W | `beach_east` |
| Lake east edge | mask=8, N+S shore, no E/W | `lake_east` |
| Lake above N-edge (U inlet) | South neighbor is L and would get tile 6 (N edge) | `south_of_n_edge` |

### Inset Corner Tiles

Inland cells with no direct water adjacency but surrounded by shoreline get **inset** tiles (e.g. corners 36–39, edges, center). These fill gaps when water divides the shoreline. Patterns include:

- `top`, `left`, `right`, `bottom` — 3 sides shoreline
- `direct_top_left`, `direct_top_right`, etc. — 2 adjacent corners
- `top_left`, `top_right`, etc. — Opposite sides, resolved via diagonal shoreline continuity

### Extended Shoreline (Peninsula / Island)

Masks **7, 11, 13, 14, 15** (3 or 4 sides water) can use a separate tile range:

- `grass_shoreline_extended_range` (e.g. 114–118)
- Maps to 5 tiles for peninsula and island shapes

### River Banks

- **Mask 5** (N+S): Vertical river
- **Mask 10** (E+W): Horizontal river
- `grass_shoreline_river_range` provides 2 tiles for these cases

---

## 4. Terrain Config (`terrain.bitmask.json`)

### Shoreline Section

```json
"shoreline": {
  "range": [1, 42],
  "shoreline_map": {
    "0": 10, "1": 2, "2": 3, "3": 4, "4": 5, "5": 6, "6": 7, "7": 8,
    "8": 9, "9": 10, "10": 11, "11": 16, "12": 13, "13": 16, "14": 15, "15": 13
  },
  "special_tiles": { "lake_east": 9, "tee_west": 32, "tee_east": 33 },
  "inset_corner_tiles": { "top_left": 36, "top_right": 37, "bottom_left": 38, "bottom_right": 39 },
  "inset_edge_tiles": { "right": 15, "bottom": 33, "center": 42 }
}
```

`shoreline_map` maps bitmask 0–15 to 1-based tile index in the shoreline sheet.

### Lake Section

```json
"lake": {
  "range": [1, 9],
  "lake_map": { "0": 1, "1": 6, "2": 8, "3": 2, ... },
  "special_tiles": { "beach_west": 7 }
}
```

### Lake Tile Layout (lakesrivers.aseprite)

When `lakesrivers_path` is set, the pipeline loads lake tiles 1–9 from the exported sheet. Tiles must be in **row-major order** matching `lake_map`:

| Position | Tile ID | Bitmasks | Role |
|----------|----------|----------|------|
| 1 | 1 | 0, 15 | Interior / all sides |
| 2 | 2 | 3, 7 | N+E corner |
| 3 | 3 | 6, 14 | S+E corner |
| 4 | 4 | 9, 11, 13 | N+W corner |
| 5 | 5 | 12 | S+W corner |
| 6 | 6 | 1, 5 | N edge |
| 7 | 7 | 4 | S edge |
| 8 | 8 | 2, 10 | E edge |
| 9 | 9 | 8 | W edge |

Tiles 10–11 are reserved for rivers (masks 5=N+S, 10=E+W).

**Fallback:** When `lakesrivers_path` is unset, lake tiles come from the grass sheet via `lake_shoreline` (indices 51–59). The `lake_shoreline` mapping uses grass.png tile IDs; `lake_map` uses 1–9 for the dedicated lakesrivers sheet.

### Grass Shoreline (Fallback)

When `shoreline_path` is not set, `grass_shoreline` maps bitmask → tile index in the grass sheet (e.g. 98–118):

```json
"grass_shoreline": {
  "0": 1, "1": 101, "2": 99, "3": 100, "4": 101, "5": 101, "6": 109, ...
},
"grass_shoreline_range": [98, 118],
"grass_shoreline_lake_range": [51, 59],
"grass_shoreline_extended_range": [114, 118],
"grass_shoreline_river_range": [60, 61]
```

---

## 5. Bitmask Reference (0–15)

| Mask | Water sides | Description |
|------|-------------|--------------|
| 0 | none | Interior (no water) |
| 1 | N | Water north |
| 2 | E | Water east |
| 3 | N+E | Top-right corner |
| 4 | S | Water south |
| 5 | N+S | Vertical edge |
| 6 | S+E | Bottom-right corner |
| 7 | N+E+S | Peninsula/bay |
| 8 | W | Water west |
| 9 | N+W | Top-left corner |
| 10 | E+W | Horizontal edge |
| 11 | N+E+W | Peninsula/bay |
| 12 | S+W | Bottom-left corner |
| 13 | S+W+N | Peninsula/bay |
| 14 | S+E+W | Peninsula/bay |
| 15 | all | Island (water all sides) |

---

## 6. Layer Output

When painting with layered output:

- **Shoreline** layer: Ocean (B) tiles
- **LakeBank** layer: Lake (L) and river (R) tiles
- **Ground** layer: Interior grass only (no shoreline tiles)

This separation allows verification and editing of shoreline vs interior terrain independently.
