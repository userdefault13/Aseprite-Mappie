# Export Tiles Metadata

Aseprite extension that exports tileset tiles and metadata (index, id, data, x, y) to JSON and CSV.

## Features

- **Tileset mode**: Exports all tiles from the active sprite's first tileset
- **Frame mode**: Exports each frame as a tile (for spritesheets without tilesets)
- **JSON output**: `source`, `tile_width`, `tile_height`, `total_tiles`, `tiles` array
- **CSV output**: `index,id,x,y,data` rows

## Installation

1. Zip the extension folder:
   ```bash
   cd extensions
   zip -r export-tiles-metadata.aseprite-extension export-tiles-metadata/
   ```

2. Install in Aseprite:
   - **Edit > Preferences > Extensions > Add Extension**
   - Select `export-tiles-metadata.aseprite-extension`

   Or double-click the `.aseprite-extension` file (macOS/Windows).

3. Restart Aseprite if needed.

## Usage

1. Open a sprite (tileset or spritesheet)
2. **File > Export Tiles Metadata** (or the menu where your extension appears)
3. Choose output path and formats (JSON, CSV)
4. *(Optional)* Select a config file to merge `legend` and `tree_config` into the JSON
5. Click Export

### Merging config (legend, tree_config, bitmask)

To include legend, tree logic, and/or bitmask in the JSON, select a config file. Supported formats:

- **Combined**: `{"legend": {...}, "tree_config": {...}, "grass_shoreline": {...}, ...}`
- **Legend only**: `{"G": 1, ".": 1, "~": 2, ...}` (single-char keys → numbers)
- **Bitmask**: `examples/grass.bitmask.json` — shoreline mappings for paint pipeline

When bitmask keys are present (`grass_shoreline`, `lake_shoreline`, ranges), they are merged into the output. Use the resulting JSON with `--grass-bitmask` when painting ASCII maps.

## Output Format

### JSON

```json
{
  "source": "path/to/sprite.aseprite (tileset: default)",
  "tile_width": 32,
  "tile_height": 32,
  "total_tiles": 56,
  "tiles": [
    { "index": 1, "id": 1, "data": "", "x": 0, "y": 0 },
    { "index": 2, "id": 2, "data": "grass", "x": 1, "y": 0 }
  ],
  "legend": { "G": 1, ".": 1, "~": 2, "T": 3 },
  "tree_config": { "single": 33, "vertical_2_top": 19, "vertical_2_bottom": 26 }
}
```

`legend` and `tree_config` are added when you select a config file during export.

### CSV

```csv
index,id,x,y,data
1,1,0,0,""
2,2,1,0,"grass"
```

- **index**: 1-based tile index in the tileset
- **id**: From tile properties `id`, tile `data` (if numeric), or index
- **x, y**: Grid position in the tileset
- **data**: User-defined tile data string
