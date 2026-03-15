-- Assemble layered .aseprite from per-terrain PNGs (map-gen preview).
-- Layer order (bottom to top): Water, Grass, Shoreline, Lake, River, Hill, Trees, Dirt, POI.
-- Env: OUT, WIDTH, HEIGHT, WATER_PNG, GRASS_PNG, SHORELINE_PNG, LAKE_PNG, RIVER_PNG,
--      HILL_PNG, TREES_PNG, DIRT_PNG, POI_PNG
local outPath = os.getenv("OUT")
local w = tonumber(os.getenv("WIDTH")) or 64
local h = tonumber(os.getenv("HEIGHT")) or 64

if not outPath or outPath == "" then
  error("OUT required")
end

local function loadLayer(path)
  if path and path ~= "" then
    local f = io.open(path, "rb")
    if f then
      f:close()
      return Image{ fromFile = path }
    end
  end
  return nil
end

local function emptyImage(width, height)
  local img = Image(width, height, ColorMode.RGBA)
  img:clear(0)
  return img
end

local layerSpecs = {
  { name = "Water",   env = "WATER_PNG" },
  { name = "Grass",   env = "GRASS_PNG" },
  { name = "Shoreline", env = "SHORELINE_PNG" },
  { name = "Lake",    env = "LAKE_PNG" },
  { name = "River",   env = "RIVER_PNG" },
  { name = "Hill",    env = "HILL_PNG" },
  { name = "Trees",   env = "TREES_PNG" },
  { name = "Dirt",    env = "DIRT_PNG" },
  { name = "POI",     env = "POI_PNG" },
}

-- Use first available layer to get dimensions
local refImg = nil
for _, spec in ipairs(layerSpecs) do
  local path = os.getenv(spec.env)
  local img = loadLayer(path)
  if img then
    refImg = img
    w = img.width
    h = img.height
    break
  end
end

if not refImg then
  error("At least one layer PNG required (WATER_PNG, GRASS_PNG, etc.)")
end

local sprite = Sprite(w, h, ColorMode.RGBA)
app.activeSprite = sprite

for i, spec in ipairs(layerSpecs) do
  local path = os.getenv(spec.env)
  local img = loadLayer(path)
  if not img then
    img = emptyImage(w, h)
  end
  local layer = (i == 1) and sprite.layers[1] or sprite:newLayer()
  layer.name = spec.name
  if i == 1 then
    sprite.cels[1].image = img
  else
    sprite:newCel(layer, 1, img, Point(0, 0))
  end
end

sprite:saveAs(outPath)
print("Wrote " .. outPath)
