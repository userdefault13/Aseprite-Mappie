-- Build a layered .aseprite from a district manifest JSON.
-- Env: MANIFEST_PATH (path to manifest.json), OUT (output .aseprite path)
--
-- Manifest schema:
--   sprite_width, sprite_height (px), tile_size (int)
--   tilesets: [{name, firstgid, png_path, columns, tile_count, tile_width,
--               tile_height, animations: [{tile_index, frames: [{cel, duration_ms}]}]}]
--   layers: [{name, tileset_name, width, height, data: [aseprite_tile_index, ...]}]
--
-- Aseprite tile index 0 = empty; user tiles start at 1.
-- Tiled frame animations are NOT applied (no native Aseprite Lua API for per-tile
--   animation as of current versions). The manifest carries animation data so a
--   future revision can apply it; for now we flatten to frame 0 and warn.

local manifestPath = os.getenv("MANIFEST_PATH")
local outPath = os.getenv("OUT")
if not manifestPath or manifestPath == "" then
  error("MANIFEST_PATH required")
end
if not outPath or outPath == "" then
  error("OUT required")
end

-- JSON loader: prefer Aseprite built-in json module, fall back to bundled json.lua
-- (rxi/json.lua, MIT-licensed, lives next to this script).
local json
pcall(function() json = require("json") end)
if not json then
  local info = debug.getinfo(1, "S")
  local src = info and info.source or ""
  local script_dir = src:sub(2):match("(.*/)") or "./"
  local loader = loadfile(script_dir .. "json.lua")
  if loader then
    json = loader()
  end
end
if not json or not json.decode then
  error("Could not load a JSON module (neither built-in 'json' nor bundled json.lua)")
end

local f = io.open(manifestPath, "r")
if not f then error("Could not open manifest: " .. manifestPath) end
local raw = f:read("*a")
f:close()
local manifest = json.decode(raw)

local spriteW = tonumber(manifest.sprite_width)
local spriteH = tonumber(manifest.sprite_height)
local tileSize = tonumber(manifest.tile_size)
if not spriteW or not spriteH or not tileSize then
  error("manifest missing sprite_width/sprite_height/tile_size")
end

local sprite = Sprite(spriteW, spriteH, ColorMode.RGBA)
app.activeSprite = sprite

-- Remove the default layer that Sprite() creates; we add our own.
if #sprite.layers > 0 then
  sprite:deleteLayer(sprite.layers[1])
end

local animWarned = false

-- ---------------------------------------------------------------------------
-- import_tileset_png: slice the repacked PNG and assign tile images to tset.
-- PNG is a tight grid of columns x rows tiles, each tile_w x tile_h.
-- Aseprite tile 0 is empty; user tiles start at index 1.
-- ---------------------------------------------------------------------------
local function import_tileset_png(tset, png_path, columns, tile_count, tile_w, tile_h)
  local sheet = Image{ fromFile = png_path }
  if not sheet then error("Could not load tileset PNG: " .. png_path) end
  -- The tileset was created with newTileset(grid, tile_count + 1) so it
  -- already has tile_count + 1 empty slots (index 0 = empty, 1..tile_count = user tiles).
  for idx = 1, tile_count do
    local sx = (idx - 1) % columns
    local sy = math.floor((idx - 1) / columns)
    local left = sx * tile_w
    local top = sy * tile_h
    local tileImg = Image(sheet, Rectangle(left, top, tile_w, tile_h))
    tset:tile(idx).image = tileImg
  end
end

-- ---------------------------------------------------------------------------
-- apply_tile_animation: stub. Aseprite has no native per-tile animation Lua API
-- as of current versions. We record the animation data in tileset.data so it
-- can be recovered/exported later, and warn once.
-- ---------------------------------------------------------------------------
local function apply_tile_animation(tset, tile_index, frames)
  if not animWarned then
    animWarned = true
    print("WARNING: Aseprite has no native per-tile animation Lua API; "
      .. "flattening tile animations to frame 0. Animation metadata is stored "
      .. "in tileset.data for future recovery.")
  end
  -- Stash animation metadata as a JSON string in tileset.data (best-effort).
  -- This is informational only; not consumed by Aseprite natively.
  if tset.data and #tset.data > 0 then
    tset.data = tset.data .. "|"
  else
    tset.data = ""
  end
  local frame_strs = {}
  for i, fr in ipairs(frames) do
    frame_strs[i] = fr.cel .. ":" .. fr.duration_ms
  end
  tset.data = (tset.data or "") .. tile_index .. "=" .. table.concat(frame_strs, ",")
end

-- ---------------------------------------------------------------------------
-- fill_tilemap_cel: write tile indices into the cel's tilemap image.
-- data is a flat row-major array of Aseprite tile indices (0 = empty).
-- ---------------------------------------------------------------------------
local function fill_tilemap_cel(cel, data, width, height, tset)
  -- Tilemap cels use ColorMode.TILEMAP; each pixel is a tile reference.
  local spec = ImageSpec{
    width = width,
    height = height,
    colorMode = ColorMode.TILEMAP,
  }
  local img = Image(spec)
  img:clear()
  for y = 0, height - 1 do
    for x = 0, width - 1 do
      local i = y * width + x + 1  -- Lua is 1-based; data is 1-based array
      local tile_index = tonumber(data[i]) or 0
      if tile_index > 0 then
        local tile_value = app.pixelColor.tile(tile_index)
        img:putPixel(x, y, tile_value)
      end
    end
  end
  cel.image = img
end

-- ---------------------------------------------------------------------------
-- Build tilesets
-- ---------------------------------------------------------------------------
local tilesets = {}
for _, ts_spec in ipairs(manifest.tilesets) do
  local tw = tonumber(ts_spec.tile_width) or tileSize
  local th = tonumber(ts_spec.tile_height) or tileSize
  local grid = Rectangle(0, 0, tw, th)
  local tc = tonumber(ts_spec.tile_count) or 0
  -- Create tileset with tc+1 empty tiles (index 0 = empty, 1..tc = user tiles)
  local tset = sprite:newTileset(grid, tc + 1)
  tset.name = ts_spec.name
  import_tileset_png(
    tset,
    ts_spec.png_path,
    tonumber(ts_spec.columns) or 1,
    tc,
    tw,
    th
  )
  for _, anim in ipairs(ts_spec.animations or {}) do
    apply_tile_animation(tset, anim.tile_index, anim.frames)
  end
  tilesets[ts_spec.name] = tset
end

-- ---------------------------------------------------------------------------
-- Build tilemap layers
-- ---------------------------------------------------------------------------
for _, layer_spec in ipairs(manifest.layers) do
  local tset = tilesets[layer_spec.tileset_name]
  if not tset then
    error("Layer " .. layer_spec.name .. " references unknown tileset: "
      .. tostring(layer_spec.tileset_name))
  end
  local w = tonumber(layer_spec.width)
  local h = tonumber(layer_spec.height)
  local tw = tset.grid.tileSize.width
  local th = tset.grid.tileSize.height
  app.command.NewLayer{
    name = layer_spec.name,
    tilemap = true,
    gridBounds = Rectangle(0, 0, tw, th),
  }
  local layer = app.activeLayer
  layer.tileset = tset
  local spec = ImageSpec{ width = w, height = h, colorMode = ColorMode.TILEMAP }
  local cel = sprite:newCel(layer, 1, Image(spec), Point(0, 0))
  fill_tilemap_cel(cel, layer_spec.data, w, h, tset)
end

sprite:saveAs(outPath)
print("Wrote " .. outPath)
