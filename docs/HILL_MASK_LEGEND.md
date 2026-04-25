# Hill mask legend (4-bit cardinal)

This project uses the usual **NESW** bitmask for hill adjacency and related autotiles (`paint_map_png.py`).

## Bit encoding

| Bit | Direction | Value |
|-----|-----------|------:|
| N   | North     | 1 |
| E   | East      | 2 |
| S   | South     | 4 |
| W   | West      | 8 |

**Mask** = sum of bits where that cardinal neighbor is “on” (e.g. hill `I`, water for shoreline maps).  
Examples: **E+W** → `2 + 8` = **10**; **N+E+W** → `1 + 2 + 8` = **11**.

## All 16 masks (hills)

Default **1-based** tile IDs come from built-in `HILL_MAP` unless overridden in `terrain.bitmask.json` (`hill_map`).  
**Strict PNG paint** uses the **raw** cardinal mask (no diagonal inference); deep plateau interiors may paint **no** hill tile (grass only) even when raw mask is 15.

| Mask | Cardinals set | Default `HILL_MAP` tile id |
|-----:|---------------|---------------------------:|
| 0 | (none) | 1 |
| 1 | N | 12 |
| 2 | E | 11 |
| 3 | N+E | 4 |
| 4 | S | 10 |
| 5 | N+S | 9 |
| 6 | E+S | 2 |
| 7 | N+E+S | 9 |
| 8 | W | 13 |
| 9 | N+W | 5 |
| 10 | E+W | 8 |
| 11 | N+E+W | 8 |
| 12 | S+W | 3 |
| 13 | N+S+W | 7 |
| 14 | S+E+W | 6 |
| 15 | N+E+S+W | 14 |

Same bit order applies to **grass shoreline** (`GRASS_SHORELINE_MAP`) and **lake shoreline** (`LAKE_SHORELINE_MAP`) with different tile indices—see `paint_map_png.py` near those maps.

---

## Five ways to handle “one mask, many possible tiles”

When a single mask value could map to more than one correct piece of art, common approaches are:

1. **Primary tile + context overrides**  
   Keep one default in `hill_map[mask]`, then apply **neighbor / topology rules** (second passes, ridge vs tee, gates) to swap tiles where the mask alone is ambiguous.

2. **Deterministic variety**  
   Choose from a list using a **fixed function of `(x, y)`** (or parity / expanded neighborhood hash) so maps stay reproducible.

3. **Seeded random**  
   Pick from weighted variants with a **stable RNG seed** (global or per-chunk) when you want organic variation without hand-authored rules.

4. **Split the state**  
   If two tiles share a mask but mean different geometry, encode extra context: **second layer**, **inferred autotile mask**, or **more than 4 bits** in your data model.

5. **Animation**  
   Same mask → multiple frames; selection by **time** or **variant index** in the tileset.

For this repo’s **basic strict hill paint**, the model is **one tile id per mask** in `hill_map`; multi-tile behavior requires adding one of the patterns above on top.

---

## Example terrain shapes (reference only)

These keys are **not** read by the painter today; they document how you might extend `terrain.bitmask.json` later. Use the CLI menu **View or edit mask** to read this file while editing config.

### Deterministic variety (stable per cell)

Pick one tile from a fixed list using a deterministic function of `(x, y)` and mask so the same map always looks the same:

| Key | Type | Example | Meaning |
|-----|------|---------|---------|
| `hill_map` | object | `{ "10": 8, "11": 8 }` | Base tile per mask (fallback). |
| `mask_variants` | object of arrays | `{ "10": [8, 23, 24], "11": [32, 31] }` | Candidate tiles for masks with multiple valid looks. |
| `variant_mode` | string | `"xy_hash"` | Stable selector using `(x, y, mask)` style hashing (no RNG drift). |

```json
{
  "hill": {
    "hill_map": { "10": 8, "11": 8 },
    "mask_variants": {
      "10": [8, 23, 24],
      "11": [32, 31]
    },
    "variant_mode": "xy_hash"
  }
}
```

### Split mask (separate maps by geometry class)

Same 4-bit mask, different art depending on topology (ridge vs tee vs peninsula, etc.).
Implemented keys:

| Key | Type | Meaning |
|-----|------|---------|
| `split_mask_enabled_masks` | array of ints | Allowlist of masks (0-15) where split-mask JSON is allowed to override existing logic. |
| `split_mask_default_shape` | string | Fallback shape table name (default: `default`). |
| `maps_by_shape` | object of objects | Shape table: `shape -> { mask -> tile_id }`. |

Classifier shapes currently used by code: `ridge_vertical`, `ridge_horizontal`, `corner`, `tee`, `peninsula`, `cross`, and `default`.

```json
{
  "hill": {
    "split_mask_enabled_masks": [5, 10, 11],
    "split_mask_default_shape": "default",
    "maps_by_shape": {
      "default": { "5": 9, "10": 8, "11": 8 },
      "ridge_vertical": { "5": 9 },
      "ridge_horizontal": { "10": 6 },
      "tee": { "11": 30 }
    }
  }
}
```

Lookup order for enabled masks: `maps_by_shape[shape][mask]` → `maps_by_shape[split_mask_default_shape][mask]` → existing hardcoded hill logic (`hill_map` / ridge / tee passes).
