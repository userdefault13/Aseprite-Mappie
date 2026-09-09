# Tilemap Generator

Generate tilemap outputs from an ASCII layout and a legend JSON:

- `<name>.csv` for simple import workflows
- `<name>.tiled.json` for Tiled-compatible maps

Use Aseprite as the source editor for tileset art, then validate map legend IDs
against exported Aseprite metadata.

## ASCII Map Generation

Generate a new ASCII layout with:

- canvas size (`--width`, `--height`)
- tree density (`--tree-density`)
- forest density (`--forest-density`)
- water density (`--water-density`)
- grass as base ground tile (`G`)
- spawn points with required grass clearings (`--spawn-count`, `--spawn-clearing-size`)
- join-point path network (`--join-point-count`)
- path width threshold (`--path-width-threshold`)
- Perlin-guided path shaping (`--path-perlin-scale`, `--path-perlin-weight`)
- mines, shops, creep zones, and dead ends (`--mine-count`, `--shop-count`, `--creep-zone-count`, `--dead-end-count`)
- optional single-path secret NPC branch (`--require-secret-npc-path`)
- optional path hiding (`--hide-path`) — no path corridors; spawns and joins remain, terrain stays grass
- **map mode**: `--map-mode island` (2-tile water border) or `--map-mode continent` (2-tile land-with-trees border)
- optional visual preview output (`--preview-out`, `--preview-tile-size`)
- optional auto-open preview in Aseprite (`--preview-in-aseprite`)
- **layered preview** (default): terrain separated into layers (Water, Grass, Shoreline, Lake, River, Hill, Trees, Dirt, POI); use `--no-preview-layered` for flat BMP
- **heightmap** for hills and shorelines: `--height-noise-scale`, `--hill-threshold`, `--beach-height-max` — hills only on high land; low land near water gets wider beaches

```bash
python3 scripts/ascii_map_gen.py \
  --width 128 \
  --height 128 \
  --tree-density 0.22 \
  --forest-density 0.65 \
  --water-density 0.10 \
  --spawn-count 8 \
  --spawn-clearing-size 15 \
  --path-width-threshold 3 \
  --mine-count 4 \
  --shop-count 3 \
  --creep-zone-count 6 \
  --dead-end-count 8 \
  --preview-in-aseprite \
  --require-secret-npc-path \
  --seed 42 \
  --out maps/generated_map.txt
```

By default this also writes `maps/generated_map.legend.json` so you can convert
immediately with `ascii_to_tilemap.py` or `tilemap-app map ...`.
The generated legend maps both `G` and `.` to ground tile ID `1`.

## Quick Start

```bash
python3 scripts/ascii_to_tilemap.py \
  --ascii maps/sample_room.txt \
  --legend maps/sample_room.legend.json \
  --tile-width 32 \
  --tile-height 32 \
  --out-prefix build/sample_room \
  --tileset-source tilesets/overworld.tsx
```

This writes:

- `build/sample_room.csv`
- `build/sample_room.tiled.json`

### Export Tile Indices (JSON / CSV)

Read tile indices from Tiled JSON tilemap layers and export in game-friendly formats:

- **JSON** — Structured per-layer format, easy to parse in games (Unity, Godot, etc.)
- **CSV** — Simple grid of numbers per layer, good for Unreal, custom engines, spreadsheets

```bash
python3 scripts/export_tilemap.py build/sample_room.tiled.json -o build/exported
# Writes: build/exported.json, build/exported_Ground.csv (per layer)

tilemap-app export build/sample_room.tiled.json -o build/exported
# Same via tilemap-app

# Options:
#   --no-json     Skip JSON export
#   --no-csv      Skip CSV export
#   --csv-single  Export only first layer to one CSV file
```

### Aseprite Extension: Export Tiles Metadata

Export tileset tiles and metadata (index, id, data, x, y) directly from Aseprite to JSON and CSV:

```bash
make extension-build
# Creates build/export-tiles-metadata.aseprite-extension
```

Install via **Edit > Preferences > Extensions > Add Extension**, then use **File > Export Tiles Metadata** when a sprite is open. Supports both tileset-based sprites and frame-based spritesheets.

### Tree Logic (GotchiCraft-style)

When converting maps with trees (`T`) or forest (`F`), use `--tree-logic` to apply
contextual tile resolution:

- **Vertical runs (2+ tiles):** 2-tile runs use top (19) + bottom (26); 3+ use top (13), middle (20), bottom (27)
- **Single trees:** Default tile 33 (85%), 15% chance of variants 25, 29, 32, 34, 35

Requires a tileset with tree segment tiles (e.g. Sprout Lands trees.aseprite). Use
`--tree-config path/to/config.json` to override defaults, or `--tree-seed N` for
reproducible variation.

```bash
tilemap-app map \
  --ascii maps/generated_map.txt \
  --legend maps/generated_map.legend.json \
  --tile-width 32 \
  --tile-height 32 \
  --out-prefix build/generated_map \
  --tree-logic \
  --tree-seed 42
```

### Paint ASCII Map in Aseprite

Render the ASCII map as a colored `.aseprite` file (one pixel tile per character). Uses solid colors for ground/water/paths; with `--treeset`, paints T/F cells using tree logic tiles from your treeset:

```bash
tilemap-app tileset paint \
  --ascii maps/generated_map.txt \
  --out build/map.aseprite \
  --tile-size 16 \
  --treeset examples/trees-Recovered.aseprite \
  --open
```

- `--tile-size` — Pixels per cell (default 16).
- `--export-map` / `--no-export-map` — Auto-generate JSON and CSV tile indices after painting (default: on). Writes `<out_stem>.tiled.json` and `<out_stem>.csv` next to the .aseprite file. Requires a legend file (`<ascii>.legend.json` or `--legend`).
- With `--treeset`, trees are drawn on a separate **Trees** layer above **Ground** for easy editing.
- `--treeset` — Path to tree tileset .aseprite (7×5 layout). Default: `examples/trees.aseprite` if present.
- `--legend` — Legend JSON (default: `<ascii>.legend.json`).
- `--tree-seed` — RNG seed for tree variation.
- `--grass-dir` — Grass tiles: directory with PNGs, or `.aseprite`/`.png` sheet. Default: `examples/grass.aseprite`.
- `--water-tile` — Path to water tile PNG or `.aseprite` (uses first frame). Default: `examples/water.aseprite`.
- `--dirt-tile` — Path to dirt tile PNG or `.aseprite` (for P=path cells). Default: `examples/dirt.aseprite`. Defaults to `examples/dirt.aseprite`. For path autotiling, use a 4×4 tile sheet (16 tiles, 64×64 px for 16px tiles). Tiles are indexed by connectivity: N=1, E=2, S=4, W=8 (bitmask 0–15). See `examples/Bitmask references 1.png` and `examples/Bitmask references 2.png` for the tile layout reference. Single-tile fallback uses the same tile for all path cells.

**Tree painting (GotchiCraft-style):** When `--treeset` is used, Python/PIL composites grass and trees to PNGs, then Aseprite Lua loads them into layers. With `--grass-dir`, grass cells use random tile variants (e.g. Sprout Lands `Grass_tiles_v2_Mid`, `Grass_tiles_v2_Mid_Grass1`, etc.). Requires Pillow (`pip install Pillow`).

**Extended grass shoreline (ocean, lake, river, peninsula):** The paint step uses water adjacency (N=1, E=2, S=4, W=8) to pick shoreline tiles. See `examples/Bitmask references 1.png` for the full layout.

**Terrain config (centralized):** Use `--terrain-config examples/terrain.bitmask.json` or `--terrain-config terrain.bitmask.json` to supply grass, water, dirt, trees, hills paths, legend (char→tile_id), and bitmask settings from one file. Auto-uses `examples/terrain.bitmask.json` or `terrain.bitmask.json` when omitted. The JSON can include `legend`, `grass_path`, `water_path`, `dirt_path`, `trees_path`, `hill_path` (relative to config file) plus `grass_shoreline`, `lake_shoreline`, and tile ranges. Legend: `G` = grass interior (1-13), `B` = continent shoreline (98-118), `L` = lake shoreline (51-59), `R` = river bank (60-61), `I` = hill (14-50), `~` = shallow water, backtick = deep water, `T`/`F` = trees. Map generation (`map-gen`) uses the legend and enforces `_rules` (e.g. trees cannot be placed on shoreline tiles; shoreline cells use `B`) when `--terrain-config` is set; paint uses it for tree logic and tile resolution. Overrides `--grass-dir`, `--water-tile`, `--dirt-tile`, `--treeset`, `--grass-bitmask` when set.

**Hill paint (bitmask autotiling):** When `hill_path` and `hill` config are set in terrain.bitmask.json, hills (`I` cells) are painted like shorelines: only the **perimeter** gets hill cliff tiles. Interior hill cells (all 4 NESW neighbors are hills) are rendered as **grass**—the top of the hill formation. Map generation connects hills via **NESW only** (no diagonal-only clusters) and fills grass holes inside hill formations so the perimeter border is one continuous cliff edge. The `hill.range` and `hill.hill_map` map bitmask 0–15 to 1-based tile IDs in the hill tileset. Hills are exported to a separate layer for easy editing in Aseprite.

**Bitmask only:** Use `--grass-bitmask` to supply only shoreline mappings without path overrides.

| Context | Range | Masks | Use |
|---------|-------|-------|-----|
| Ocean (continent border) | 1–15 | all | Water connected via NESW to 2-tile border; grass adjacent = B |
| Lake (interior water) | 4–18 | all | Inland water (not connected to ocean); grass adjacent = L |
| River banks | `--grass-shoreline-river-range` | 5 (N+S), 10 (E+W) | Water on opposite sides |
| Peninsula/island | `--grass-shoreline-extended-range` | 7,11,13,14,15 | 3 or 4 sides water |

## Aseprite Workflow

1. Check Aseprite CLI availability:

```bash
python3 scripts/aseprite_tileset.py check
```

2. Initialize a blank tileset canvas sized from your legend tile IDs:

```bash
python3 scripts/aseprite_tileset.py init \
  --legend maps/sample_room.legend.json \
  --out assets/tilesets/sample_room_tileset.aseprite \
  --tile-width 32 \
  --tile-height 32 \
  --cols 4
```

2b. Or auto-generate a solid-color terrain tileset from legend IDs:

```bash
python3 scripts/aseprite_tileset.py terrain \
  --legend maps/generated_map.legend.json \
  --out assets/tilesets/generated_terrain.aseprite \
  --tile-width 32 \
  --tile-height 32 \
  --cols 4 \
  --export-dir build/tilesets
```

This writes a `.aseprite` file plus exported PNG/JSON using simple color blocks
for symbols like `G`, `~`, `T`, `F`, `P`, `S`, `M`, `H`, `C`, `D`, `N`.

3. Open and tweak tiles in Aseprite:

```bash
python3 scripts/aseprite_tileset.py edit \
  --source assets/tilesets/sample_room_tileset.aseprite
```

4. Export spritesheet + Aseprite JSON metadata:

```bash
python3 scripts/aseprite_tileset.py export \
  --source assets/tilesets/sample_room_tileset.aseprite \
  --out-dir build/tilesets
```

5. Generate map outputs and validate legend IDs against exported tileset capacity:

```bash
python3 scripts/ascii_to_tilemap.py \
  --ascii maps/sample_room.txt \
  --legend maps/sample_room.legend.json \
  --tile-width 32 \
  --tile-height 32 \
  --out-prefix build/sample_room \
  --tileset-source tilesets/overworld.tsx \
  --aseprite-data build/tilesets/sample_room_tileset.json
```

## Makefile Commands

One-command workflow targets:

```bash
make map-gen
make aseprite-check
make tileset-init
make tileset-terrain
make tileset-edit
make tileset-export
make map-build
make map-build-validated
make pipeline
```

With overrides:

```bash
make map-gen CANVAS_WIDTH=128 CANVAS_HEIGHT=128 DEAD_END_COUNT=10 MINE_COUNT=6 SHOP_COUNT=4
make tileset-init TILE_WIDTH=16 TILE_HEIGHT=16 COLS=8
make tileset-terrain LEGEND=maps/generated_map.legend.json TILESET_ASE=assets/tilesets/generated.aseprite
make map-build MAP_OUT_PREFIX=build/room01 TILESET_SOURCE=tilesets/overworld.tsx
```

## District Opener (Gotchiverse)

Open a rectangular district of gotchiverse citaadel chunks as a layered
`.aseprite` file for viewing/editing in Aseprite. Reads Tiled TMJ chunk files,
stitches them into one big tilemap per Tiled layer, repacks the referenced
tilesets (margin/spacing -> tight grid), and invokes an Aseprite Lua script
to build a `.aseprite` with tilemap layers.

### Usage

```bash
tilemap-app district open \
  --maps-root /path/to/gotchiverse-2d/public/maps/chunks \
  --chunks 0-3,0-3 \
  --out build/district_4x4.aseprite \
  --tile-size 64 \
  --open
```

Arguments:

- `--maps-root` — directory containing `master.json` + `chunkN.json` files.
- `--chunks x0-x1,y0-y1` — inclusive bounding rect of chunk IDs (e.g. `0-3,0-3` = 4x4 district).
- `--out` — output `.aseprite` path.
- `--tile-size` — pixels per tile (default 64; citaadel is 64x64).
- `--open` — open the result in Aseprite GUI when done.
- `--aseprite-bin` — optional explicit path to the Aseprite binary.

Or via the dedicated CLI:

```bash
tilemap-district open \
  --maps-root /path/to/gotchiverse-2d/public/maps/chunks \
  --chunks 0-1,0-1 \
  --out build/district_2x2.aseprite \
  --open
```

### How it works

1. **Stitch**: loads each chunk TMJ in the bbox and composites per-Tiled-layer
   GID grids into one big grid (`(x1-x0+1)*chunkWidth x (y1-y0+1)*chunkHeight` tiles).
2. **Repack tilesets**: slices each Tiled tileset PNG (with margin/spacing)
   into a tight grid that Aseprite expects (PIL).
3. **Split per tileset**: each Tiled layer is split into N Aseprite tilemap
   layers, one per tileset actually used (Aseprite tilemap layers bind to a
   single tileset). Empty splits are skipped. Layer naming:
   `<tiled_layer>__<tileset_name>`.
4. **Build**: an Aseprite Lua script (`assets/lua/import_district.lua`) creates
   the sprite, tilesets, tilemap layers, and fills cells. Tile index 0 is
   empty; user tiles start at 1 (Aseprite convention).

### Tile animations

Tiled per-tile frame animations (e.g. `alchem`, `roads`) are carried in the
manifest. Aseprite has no native per-tile animation Lua API as of current
versions, so animations are flattened to frame 0 and the metadata is stashed
in `tileset.data` for future recovery. A warning is printed when animations
are present.

### Limitations (current version)

- **Open-only**: no write-back to chunk TMJ files. Edits in Aseprite are not
  automatically exported back.
- **Citaadel biome only**: tested against the existing citaadel chunk
  pipeline. New biomes (hyrule-castle, houses-interior, etc.) are not yet
  supported.
- **Mixed tile sizes**: the 128x128 `unplayable` tileset is handled as a
  separate Aseprite tileset with its own tile size.

## Install As CLI Command

On macOS with Homebrew Python, use a virtual environment (avoids `externally-managed-environment`):

```bash
cd /path/to/Aseprite-Mappie

# Create venv (once)
python3 -m venv .venv

# Activate venv (each new terminal)
source .venv/bin/activate

# Install Mappie
pip install -e .

# Run Mappie
tilemap-app
```

Or with system pip (if allowed):

```bash
python3 -m pip install -e .
```

CLI commands (after install):

```bash
# Legacy map command
tilemap-gen \
  --ascii maps/sample_room.txt \
  --legend maps/sample_room.legend.json \
  --tile-width 32 \
  --tile-height 32 \
  --out-prefix build/sample_room

# Unified app CLI
tilemap-app
# opens interactive menu:
# 1) Generate new ASCII map (prompts for all required values, and can auto-open preview in Aseprite)

tilemap-app map-gen \
  --width 128 \
  --height 128 \
  --tree-density 0.22 \
  --forest-density 0.65 \
  --water-density 0.10 \
  --spawn-count 8 \
  --spawn-clearing-size 15 \
  --path-width-threshold 3 \
  --mine-count 4 \
  --shop-count 3 \
  --creep-zone-count 6 \
  --dead-end-count 8 \
  --preview-in-aseprite \
  --require-secret-npc-path \
  --out maps/generated_map.txt

tilemap-app map \
  --ascii maps/sample_room.txt \
  --legend maps/sample_room.legend.json \
  --tile-width 32 \
  --tile-height 32 \
  --out-prefix build/sample_room

tilemap-app tileset check
tilemap-app tileset init --legend maps/sample_room.legend.json --out assets/tilesets/sample_room_tileset.aseprite --tile-width 32 --tile-height 32 --cols 4
tilemap-app tileset terrain --legend maps/generated_map.legend.json --out assets/tilesets/generated_terrain.aseprite --tile-width 32 --tile-height 32 --cols 4 --export-dir build/tilesets

tilemap-app district open --maps-root /path/to/gotchiverse-2d/public/maps/chunks --chunks 0-1,0-1 --out build/district_2x2.aseprite --tile-size 64 --open

# Dedicated generator command
tilemap-mapgen --width 128 --height 128 --tree-density 0.22 --forest-density 0.65 --water-density 0.10 --spawn-count 8 --spawn-clearing-size 15 --path-width-threshold 3 --mine-count 4 --shop-count 3 --creep-zone-count 6 --dead-end-count 8 --preview-in-aseprite --require-secret-npc-path --out maps/generated_map.txt
```

## Input Format

ASCII map file:

- one row per line
- one character per tile
- all lines must be the same width

Legend JSON:

- object mapping one-character keys to integer tile IDs
- tile IDs are non-negative (`0` is empty; tiles typically start at `1`)
- example:

```json
{
  "#": 1,
  ".": 2,
  "~": 3
}
```

## Notes

- tile ID `0` is valid and represents empty tile in Tiled.
- use `--tileset-source path/to/tileset.tsx` to add an external tileset reference.
- use `--aseprite-data path/to/export.json` to ensure legend IDs fit your Aseprite tileset.

## Author

**Julius Wong** (userDef@ult) — [userdefault.dev](https://www.userdefault.dev) · [GitHub](https://github.com/userdefault13) · [X](https://x.com/userDefault_0x)

Freelance engineer working on AI agent orchestration, AI developer tooling, and Unity/WebGL
multiplayer games. Write-up of the game art pipeline work behind this project:
[userdefault.dev/work/aseprite-pixel-tools](https://www.userdefault.dev/work/aseprite-pixel-tools).

Available for freelance and contract work — [book a consult](https://www.userdefault.dev/hire),
or read more about [Unity & WebGL game development](https://www.userdefault.dev/services/unity-game-development).
