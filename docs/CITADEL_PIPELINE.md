# Citadel Structure Pipeline (Newski)

This pipeline exports and assembles Citadel fortress components from `newski.aseprite` for use in Gotchiverse world maps.

## Source File

**Location**: `/Users/juliuswong/Downloads/newski.aseprite`

**Original Resolution**: 8×8 pixels per tile  
**Export Resolution**: 64×64 pixels (8× upscale)

## Newski Layers

### Corner Towers (4)
- `topleftcorner`
- `toprightcorner`
- `bottomleftcorner`
- `bottomrightcorner`

### Mid Towers (6)
- `leftmidtowersmall`, `leftmidtowermed`, `leftmidtowerlarge`
- `rightmidtowersmall`, `rightmidtowermed`, `rightmidtowerlarge`

### Horizontal Towers (4)
- `HorizontalmidTowersNorthsmall`, `HorizontalmidTowersNorthlarge`
- `HorizontalmidTowersSouthsmall`, `HorizontalmidTowersSouthlarge`

### Gates (2)
- `northGate`
- `southGate`

### Connectors (2)
- `northsouthconnector` (vertical wall segments)
- `westeastconnector` (horizontal wall segments)

## Pipeline Steps

### Step 1: Export Layers

Export all individual layers from newski.aseprite at 8× scale:

```bash
python3 scripts/newski_legend_pipeline.py
```

**Options**:
- `--source PATH` - Path to newski.aseprite (default: `/Users/juliuswong/Downloads/newski.aseprite`)
- `--out-dir PATH` - Output directory (default: `build/`)
- `--scale N` - Scale factor (default: 8 for 8px → 64px)
- `--aseprite-bin PATH` - Aseprite binary path (auto-detected)

**Output**: Exports 18 PNG files to `build/newski_*.png`

### Step 2: Create Wall Composites

Assemble continuous wall strips from towers and connectors:

```bash
# West wall (left side)
python3 scripts/west_wall_cycled.py

# North wall (top, with gate)
python3 scripts/north_wall_cycled.py

# East wall (right side)
python3 scripts/east_wall_cycled.py
```

**Output**:
- `build/citadel_west_wall.png` - Small/Med/Large tower pattern with connectors
- `build/citadel_north_wall.png` - Symmetrical with center gate
- `build/citadel_east_wall.png` - Small/Med/Large tower pattern with connectors

**Note**: South wall uses the same pattern as north but typically no gate

### Step 3: Place Citadel in Map

Add Citadel structure to an ASCII map:

```bash
python3 scripts/place_citadel.py \
  --ascii maps/mymap.txt \
  --out maps/mymap_citadel.txt \
  --x 10 \
  --y 10 \
  --width 20 \
  --height 16 \
  --gate-north
```

**Options**:
- `--x, --y` - Top-left corner coordinates
- `--width, --height` - Citadel dimensions (minimum 4×4)
- `--gate-north` - Add gate in north wall (default: true)
- `--gate-south` - Add gate in south wall

**Placement Characters**:
- `O` - Tower (corners)
- `W` - Wall (sides)
- `G` - Gate (opening in wall)

### Step 4: Paint with Mappie

Paint the ASCII map with Citadel structures using the newski tiles:

```bash
tilemap-app tileset paint \
  --ascii maps/mymap_citadel.txt \
  --out build/mymap_citadel.aseprite \
  --tile-size 64 \
  --terrain-config terrain.bitmask.json \
  --treeset examples/trees.aseprite \
  --open
```

The painter will automatically use:
- `build/newski_topleftcorner.png` for top-left tower (O at top-left)
- `build/newski_toprightcorner.png` for top-right tower (O at top-right)
- `build/citadel_north_wall.png` for north wall (W on top edge)
- etc.

## Map Generator Integration

Citadel structures can be placed directly in ASCII maps or added during generation:

### Manual Placement

```python
from scripts.place_citadel import place_citadel

ascii_lines = [...]  # Your map
citadel_map = place_citadel(
    ascii_lines,
    cx=50, cy=50,  # Top-left position
    width=24, height=20,
    gate_north=True,
    gate_south=False,
)
```

### Generation Parameter (Future)

```bash
python3 scripts/ascii_map_gen.py \
  --width 128 \
  --height 128 \
  --citadel \
  --citadel-x 10 \
  --citadel-y 10 \
  --citadel-width 20 \
  --citadel-height 16 \
  --out maps/map_with_citadel.txt
```

## Legend Mapping

Citadel structures use these legend IDs:

```json
{
  "W": 119,  "O": 120
}
```

## Terrain Rules

1. **Citadel Placement**: Citadels should be placed on grass (`G`) terrain
2. **Buffer Zones**: Maintain 2-tile buffer from water and shorelines
3. **Path Access**: Ensure paths (`P`) connect to Citadel gates
4. **POI Exclusion**: No spawns/mines/shops inside Citadel walls

## Visual Layout

```
O W W W W W W W W W W W W W W W W W W O    (North wall with towers)
W . . . . . . . . . . . . . . . . . . W    (Interior - grass/path)
W . . . . . . . . . . . . . . . . . . W
W . . . . . . . . . . . . . . . . . . W
W . . . . . P P P P P P P . . . . . . W    (Great Portal center)
W . . . . . P P P P P P P . . . . . . W
W . . . . . P P P P P P P . . . . . . W
W . . . . . . . . . . . . . . . . . . W
O W W W W W W W W W W W W W W W W W W O    (South wall with towers)
```

## Gotchiverse "The Citaadel"

The Citaadel is the starting fortress in the Gotchiverse, featuring:
- **Four corner towers** with magenta/purple roofs and red flags
- **Stone walls** with crenellations
- **North gate** (Great Portal) with cyan/teal portal effect
- **Interior courtyard** with teal circuit-board pattern
- **32×24 tile footprint** (typical size for 128×128 maps)

## Files Generated

After running the complete pipeline:

```
build/
├── newski_topleftcorner.png             (64×64px)
├── newski_toprightcorner.png
├── newski_bottomleftcorner.png
├── newski_bottomrightcorner.png
├── newski_leftmidtowersmall.png
├── newski_leftmidtowermed.png
├── newski_leftmidtowerlarge.png
├── newski_rightmidtowersmall.png
├── newski_rightmidtowermed.png
├── newski_rightmidtowerlarge.png
├── newski_HorizontalmidTowersNorthsmall.png
├── newski_HorizontalmidTowersNorthlarge.png
├── newski_HorizontalmidTowersSouthsmall.png
├── newski_HorizontalmidTowersSouthlarge.png
├── newski_northGate.png
├── newski_southGate.png
├── newski_northsouthconnector.png
├── newski_westeastconnector.png
├── newski_flattened.png                 (reference)
├── citadel_west_wall.png                (384×64px - 6 tiles)
├── citadel_north_wall.png               (704×64px - 11 tiles with gate)
└── citadel_east_wall.png                (384×64px - 6 tiles)
```

## Quick Start

```bash
# 1. Export newski layers
python3 scripts/newski_legend_pipeline.py

# 2. Create wall composites
python3 scripts/west_wall_cycled.py
python3 scripts/north_wall_cycled.py
python3 scripts/east_wall_cycled.py

# 3. Generate a map
python3 scripts/ascii_map_gen.py \
  --width 128 --height 128 \
  --tree-density 0.2 --forest-density 0.6 --water-density 0.1 \
  --spawn-count 8 --spawn-clearing-size 15 \
  --out maps/gotchiverse_main.txt

# 4. Add Citadel
python3 scripts/place_citadel.py \
  --ascii maps/gotchiverse_main.txt \
  --out maps/gotchiverse_main_citadel.txt \
  --x 10 --y 10 \
  --width 24 --height 20

# 5. Paint it
tilemap-app tileset paint \
  --ascii maps/gotchiverse_main_citadel.txt \
  --out build/gotchiverse_main.aseprite \
  --tile-size 64 \
  --open
```

## Troubleshooting

### "newski.aseprite not found"
- Verify the file exists at `/Users/juliuswong/Downloads/newski.aseprite`
- Use `--source` to specify a different path

### "Aseprite binary not found"
- Install Aseprite or use `--aseprite-bin` to specify path
- macOS default: `/Applications/Aseprite.app/Contents/MacOS/aseprite`

### "Pillow required"
- Install with `pip install Pillow`

### Missing wall composites
- Run `west_wall_cycled.py`, `north_wall_cycled.py`, `east_wall_cycled.py` after exporting layers

## See Also

- `terrain.bitmask.json` - Citadel configuration section
- `src/tilemap_generator/legend.py` - Character mappings (W=119, O=120)
- `src/tilemap_generator/paint_map_png.py` - POI layer painting (CitadelWall, CitadelTower)

---

**Last Updated**: August 28, 2026  
**Newski Source**: 8×8px hand-pixel art by user  
**Export Scale**: 8× (64×64px for Gotchiverse world)
