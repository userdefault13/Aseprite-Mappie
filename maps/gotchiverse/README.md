# Gotchiverse World Maps

This directory contains procedurally generated maps for the Gotchiverse using the Mappie tilemap generator.

## Maps

### gotchiverse_world.txt (200x200)
**Main world map** featuring diverse biomes and terrain types.
- 12 spawn points with large clearings (17x17)
- 8 join points for inter-region connectivity
- High diversity: forests (60%), trees (25%), water (12%), hills (8%)
- 6 mines, 5 shops, 8 creep zones
- Island mode with beach shorelines
- Secret NPC hidden path
- **Seed**: 1337

**Stats**: 1,928 path tiles, 4,800 water, 3,202 hills, 6,000 forest, 4,000 trees

### daark_forest.txt (128x128)
**Dense forest region** inspired by the "Tree of Fud" area.
- Very high tree density (45%) with 80% forest clustering
- Dark, mysterious atmosphere with 8 creep zones
- 6 spawn points with medium clearings (13x13)
- Low water presence (5%) for land-focused exploration
- Narrow paths (width 2) winding through dense foliage
- Continent mode with forested borders
- **Seed**: 6660

**Stats**: 973 path tiles, 819 water, 492 hills, 5,898 forest, 1,475 trees

### defi_desert.txt (128x128)
**Open desert biome** with sparse vegetation and rocky terrain.
- Low tree density (8%) for wide open spaces
- High hill density (15%) for mountainous desert landscape
- Minimal water (2%) - oasis-style placement
- 8 spawn points with standard clearings (15x15)
- Wide paths (width 4-5) for desert travel
- 5 mines (resource extraction theme), 4 shops
- Continent mode
- **Seed**: 4200

**Stats**: 2,292 path tiles, 328 water, 2,219 hills, 393 forest, 918 trees

### rofl_reefs.txt (128x128)
**Coastal/reef biome** with high water density.
- High water coverage (25%) for archipelago feel
- Island mode with extensive shorelines and beaches
- Moderate tree density (18%) on land areas
- 6 spawn points with smaller clearings (11x11)
- 6 creep zones near water
- Balanced hills (5%) for coastal cliffs
- **Seed**: 7777

**Stats**: 476 path tiles, 4,096 water, 819 hills, 1,474 forest, 1,475 trees

### citaadel.txt (96x96)
**Fortress/city map** for The Citaadel region.
- Smaller map (96x96) for concentrated urban/fortress area
- 4 large spawn points (21x21) for town squares/plazas
- Low tree density (10%) - cleared for construction
- 4 shops, 2 mines, 2 creep zones
- Wide paths (width 4-5) for main thoroughfares
- Minimal hills (5%) for flat construction zones
- Continent mode
- **Seed**: 1111

**Stats**: 828 path tiles, 737 water, 465 hills, 369 forest, 553 trees

### mount_oomf.txt (128x128)
**Mountain region** with high elevation and mining opportunities.
- Very high hill density (25%) for dramatic mountains
- 8 mines (highest count) for mountain resources
- Moderate tree density (15%) with 55% forest
- 6 spawn points (13x13) in mountain valleys
- Low water (6%) - mountain streams
- 8 dead-end paths for mountain trails
- Continent mode
- **Seed**: 9999

**Stats**: 1,644 path tiles, 983 water, 1,974 hills, 1,352 forest, 1,106 trees

## Map Features

All maps include:
- **Terrain Types**: Water (`~` shallow, `` ` `` deep), Grass (`G`), Trees (`T`), Forest (`F`), Hills (`I`), Dirt paths (`P`)
- **Shorelines**: Beach (`B`), Lake shore (`L`), River banks (`R`)
- **Points of Interest**: 
  - Spawns (`S`) - player start locations
  - Joins (`J`) - region connection points
  - Mines (`M`) - resource gathering
  - Shops (`H`) - trading posts
  - Creep zones (`C`) - enemy territories
  - Dead ends (`D`) - exploration rewards
  - Secret NPCs (`N`) - hidden characters
- **Path System**: Perlin-noise guided network connecting all spawns and joins
- **Terrain Rules**: 
  - 1-tile buffer between paths and water/trees/hills
  - No POIs on shorelines
  - Connected path network (no islands)
  - Hills connected via NESW only (no diagonal-only clusters)

## Usage

### Convert to Tilemap

```bash
tilemap-app map \
  --ascii maps/gotchiverse/gotchiverse_world.txt \
  --legend maps/gotchiverse/gotchiverse_world.legend.json \
  --tile-width 16 \
  --tile-height 16 \
  --out-prefix build/gotchiverse_world \
  --tree-logic
```

### Paint in Aseprite

```bash
tilemap-app tileset paint \
  --ascii maps/gotchiverse/gotchiverse_world.txt \
  --out build/gotchiverse_world.aseprite \
  --tile-size 16 \
  --terrain-config terrain.bitmask.json \
  --treeset examples/trees.aseprite \
  --open
```

## Regeneration

To regenerate any map with different parameters:

```bash
python3 scripts/ascii_map_gen.py \
  --width 128 \
  --height 128 \
  --tree-density 0.22 \
  --forest-density 0.65 \
  --water-density 0.10 \
  --hill-density 0.08 \
  --spawn-count 8 \
  --spawn-clearing-size 15 \
  --path-width-threshold 3 \
  --mine-count 4 \
  --shop-count 3 \
  --creep-zone-count 6 \
  --dead-end-count 8 \
  --require-secret-npc-path \
  --map-mode island \
  --seed YOUR_SEED \
  --out maps/gotchiverse/your_map.txt
```

## Legend

Default tile IDs (see `*.legend.json` files):
- `G` (Grass) = 1
- `~` (Shallow water) = 2
- `` ` `` (Deep water) = 3
- `T` (Tree) = 4
- `F` (Forest) = 5
- `P` (Path/Dirt) = 6
- `S` (Spawn) = 7
- `J` (Join) = 8
- `M` (Mine) = 9
- `H` (Shop/House) = 10
- `C` (Creep) = 11
- `D` (Dead end) = 12
- `N` (Secret NPC) = 13
- `I` (Hill) = 14
- `B` (Beach/Ocean shore) = 98
- `L` (Lake shore) = 51
- `R` (River bank) = 60

## Map Modes

- **Island Mode**: 2-tile water border, creates beaches and shorelines
- **Continent Mode**: 2-tile land border with trees (70% tree coverage)

## Related Regions

These generated maps can represent:
- The Citaadel (citaadel.txt) - fortress with four corner towers
- North Beach & South Beach (use island mode with high water)
- ROFL Reefs (rofl_reefs.txt) - coastal archipelago
- Broken Line - linear path feature (use high path_width_threshold)
- Defi Desert (defi_desert.txt) - arid biome
- Genesis Blocks - structured/urban (low tree density)
- Caaverns - (future: underground tileset)
- Alpha River Valley - (use high water with river banks)
- Yield Fields - (low tree, flat terrain)
- Daark Forest (daark_forest.txt) - Tree of Fud
- The Aarena - (circular structure, future template)
- Laughing Peaks & Mount Oomf (mount_oomf.txt) - mountain ranges
- Shelnot Pass - (mountain pass, narrow width)
- Open Steppe - (minimal trees, flat)
- Poly Lakes - (multiple lake clusters)
- Phaantastic Grounds - (mixed terrain)
- Maagma Springs - (high creep zones, volcanic theme)
- Liquidator Ruins - (high dead ends, abandoned theme)
- Infinity Cliffs - (extreme hills at borders)
- Inpassable Sea - (water border)
- The Ranging Range - (varied elevation)
- Aalpha Lake - (large central lake)

## Generation Date

Generated: August 28, 2026
Generator Version: Aseprite-Mappie (commit 182d04c)
