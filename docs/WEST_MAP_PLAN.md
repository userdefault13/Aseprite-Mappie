# Plan: New "West" Map Library (editor-only, in gotchiverse-2d, scripted terrain)

Goal: create a new JSON map library to the west of the citadel — a folder of Tiled TMJ `chunkN.json` + `master.json` matching the existing gotchiverse format — then develop it via scripted base terrain.

**Scope decisions (user-confirmed):**
- Location: `gotchiverse-2d/public/maps/west/` (game-integrated location; editor-only for now — no game wiring).
- Footprint: 4 districts wide × 6 districts tall west of the citadel = **64 × 96 chunks** (each district = 16×16 chunks).
- Authoring: scripted base terrain first (no Aseprite write-back yet).
- Game integration (const.game.ts, assetsController, MapController, minimap): **out of scope for now**.

## Context & grounding

- Chunk format (from `gotchiverse-2d/public/maps/chunks/chunk0.json`):
  - Tiled TMJ, `orientation=orthogonal`, tile 64×64, layer 66×66.
  - Layers: `alchemica`, `tower_bottom`, `tower_top`.
  - `tilesets` block: 17 firstgid-ordered entries (alchem, tower1-4, roads, alchem_glow, parcel, statues, lights, gates, objects, unplayable, ...).
- `master.json`: `chunkWidth/Height = 66`, `chunksHorizontal / chunksVertical`.
- Chunk id = `row * chunksHorizontal + col` (0-based).
- West layout: grid **64 wide × 96 tall** → 6144 chunks (id 0..6143).
- Location choice: `public/maps/west/` holds `master.json` + `chunkN.json` **directly** (aarena-style), so tileset PNGs resolve via `maps_root.parent/sprites` (`resolve_tileset_image`) with no district_cli change.
- Size caveat: each chunk ≈25–35KB (4356-cell arrays × 3 layers, + tilesets if duplicated). 6144 chunks ≈ **~160–220MB** on disk. Matches citaadel's existing scale (361MB).
- District geometry: each district = 16×16 chunks (66×66 tiles each → 1056×1056 tiles; at 64px/tile = 67584px which must downscale to 32px, per the existing `fit_tile_size` fix).

## Design decisions

1. **`tilesets` stored once in `master.json`**, not duplicated per chunk — avoids ~150MB of repeated tileset blocks.
   - Requires small `district_cli` tweak: merge `master.json["tilesets"]` into the stitcher union so empty-chunk maps still repack/open with the right palette.
2. **West district IDs**: `W1..W24` (row-major), derived from config; same 16-chunk bbox math as citaadel districts.
3. **Base terrain (scripted)**: config-driven brush —
   - solid "ground" fill on `alchemica`
   - road-grid pattern on `tower_bottom`
   - GIDs validated against tileset `firstgid` ranges so only in-range tiles are written.
   - Default tiles chosen by sampling existing animated/content chunks; adjustable in a brush config styled after `examples/terrain.bitmask.json`.

## Implementation steps

1. **Config** (`gotchiverse.config.json`):
   - Add `maps: { citaadel: {root, cols, rows}, west: {root: <...>/public/maps/west, cols: 4, rows: 6} }`.
   - Keep `maps_root` as a citaadel alias for backward compatibility.

2. **district_cli — stitcher fallback**:
   - In `stitch_layers` (or `command_open`), seed `tilesets_by_name` from `master.json["tilesets"]` when present, so maps with no per-chunk tilesets still get the union.

3. **district_cli — `scaffold`**:
   - New command: `scaffold --maps-root <west> --grid 64x96`.
   - Writes `master.json` (grid + tilesets from a real citaadel `chunk0.json`) + all 6144 empty `chunkN.json` files (exact TMJ schema, 3 zero layers, omitted tilesets).
   - Unit tests: master keys valid; chunk naming `chunkN.json` with N = `y*64 + x`; each chunk 3 layers of 66×66 zeros.

4. **district_cli — `fill` (tilebrush)**:
   - New command: `fill --maps-root <west> --brush <json> --chunks x0-x1,y0-y1`.
   - Loads each chunk in bbox, applies brush pattern (solid / road-grid) per layer, writes back preserving all other JSON fields (backgroundcolor, nextlayerid, etc.).
   - Validation: write only in-range GIDs; parse→write is idempotent (byte-stable aside from intended edits).

5. **app.py menu**:
   - Add "Which map library?" step (citaadel / west, driven by config `maps`) before the district picker.
   - District list per map; default maps-root follows the selected library.
   - Existing district picker + full-map/specific-chunk logic is reused/generalized.

6. **Verify**:
   - Scaffold a tiny grid (4×4) → `open` a west district → assert valid sprite via the aseprite Lua probe (dims = tiles × tile_size, layers present, tilesets loaded, content non-blank).
   - Full 64×96 scaffold + spot-open a couple of chunks.
   - Run existing `tests/test_district_stitch.py`.

## Out of scope (future/not now)

- Game wiring: `MAP_CONFIG_BY_ID['west']`, `ENABLED_MAPS`, `assetsController`/`MapController` folder mapping, minimap, spawn bounds.
- Aseprite paint → write-back (`district_cli write`) as a later authoring method.
- Tile animations (already flattened to frame 0 by `assets/lua/import_district.lua`).