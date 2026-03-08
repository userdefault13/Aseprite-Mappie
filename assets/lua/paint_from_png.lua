-- Build layered .aseprite (layer order: Water, Grass, Dirt, Trees - ascending).
-- Env: OUT, WATER_PNG, GRASS_PNG, DIRT_PNG, TREES_PNG
local outPath = os.getenv("OUT")
local waterPath = os.getenv("WATER_PNG")
local grassPath = os.getenv("GRASS_PNG")
local dirtPath = os.getenv("DIRT_PNG")
local treesPath = os.getenv("TREES_PNG")

if not outPath or outPath == "" then
  error("OUT required")
end
if not grassPath or grassPath == "" or not treesPath or treesPath == "" then
  error("GRASS_PNG and TREES_PNG required")
end

local grassImg = Image{ fromFile = grassPath }
local treesImg = Image{ fromFile = treesPath }
local w = grassImg.width
local h = grassImg.height

local sprite = Sprite(w, h, ColorMode.RGBA)
app.activeSprite = sprite

-- Layer 1: Water (bottom)
local waterLayer = sprite.layers[1]
waterLayer.name = "Water"
local waterImg
if waterPath and waterPath ~= "" then
  waterImg = Image{ fromFile = waterPath }
else
  waterImg = Image(w, h, ColorMode.RGBA)
  waterImg:clear(0)
end
sprite.cels[1].image = waterImg

-- Layer 2: Grass
local grassLayer = sprite:newLayer()
grassLayer.name = "Grass"
sprite:newCel(grassLayer, 1, grassImg, Point(0, 0))

-- Layer 3: Dirt
local dirtLayer = sprite:newLayer()
dirtLayer.name = "Dirt"
local dirtImg
if dirtPath and dirtPath ~= "" then
  dirtImg = Image{ fromFile = dirtPath }
else
  dirtImg = Image(w, h, ColorMode.RGBA)
  dirtImg:clear(0)
end
sprite:newCel(dirtLayer, 1, dirtImg, Point(0, 0))

-- Layer 4: Trees (top)
local treesLayer = sprite:newLayer()
treesLayer.name = "Trees"
sprite:newCel(treesLayer, 1, treesImg, Point(0, 0))

sprite:saveAs(outPath)
print("Wrote " .. outPath)
