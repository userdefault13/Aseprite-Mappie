-- Build layered .aseprite (layer order: WaterDeep, WaterShallow, WaterLake, WaterRiver, Grass, LakeBank, Shoreline, Hill, Dirt, Trees, POI, ...).
-- Env: OUT, WATER_PNG, WATER_SHALLOW_PNG, WATER_DEEP_PNG, WATER_LAKE_PNG, WATER_RIVER_PNG, GRASS_PNG, SHORELINE_PNG, LAKEBANK_PNG, ...
local outPath = os.getenv("OUT")
local waterPath = os.getenv("WATER_PNG")
local waterShallowPath = os.getenv("WATER_SHALLOW_PNG")
local waterDeepPath = os.getenv("WATER_DEEP_PNG")
local waterLakePath = os.getenv("WATER_LAKE_PNG")
local waterRiverPath = os.getenv("WATER_RIVER_PNG")
local grassPath = os.getenv("GRASS_PNG")
local shorelinePath = os.getenv("SHORELINE_PNG")
local lakebankPath = os.getenv("LAKEBANK_PNG")
local hillPath = os.getenv("HILL_PNG")
local dirtPath = os.getenv("DIRT_PNG")
local treesPath = os.getenv("TREES_PNG")
local poiPath = os.getenv("POI_PNG")
local poiSpawnPath = os.getenv("POI_SPAWN_PNG")
local poiJoinPath = os.getenv("POI_JOIN_PNG")
local poiMinePath = os.getenv("POI_MINE_PNG")
local poiShopPath = os.getenv("POI_SHOP_PNG")
local poiCreepPath = os.getenv("POI_CREEP_PNG")
local poiDeadEndPath = os.getenv("POI_DEAD_END_PNG")
local poiSecretPath = os.getenv("POI_SECRET_PNG")

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

-- Layer 1: Water Deep (ocean deep, bottom)
local waterDeepLayer = sprite.layers[1]
waterDeepLayer.name = "WaterDeep"
local waterDeepImg
if waterDeepPath and waterDeepPath ~= "" then
  waterDeepImg = Image{ fromFile = waterDeepPath }
else
  waterDeepImg = Image(w, h, ColorMode.RGBA)
  waterDeepImg:clear(0)
end
sprite.cels[1].image = waterDeepImg

-- Layer 2: Water Shallow (ocean shallow)
local waterShallowLayer = sprite:newLayer()
waterShallowLayer.name = "WaterShallow"
local waterShallowImg
if waterShallowPath and waterShallowPath ~= "" then
  waterShallowImg = Image{ fromFile = waterShallowPath }
else
  waterShallowImg = Image(w, h, ColorMode.RGBA)
  waterShallowImg:clear(0)
end
sprite:newCel(waterShallowLayer, 1, waterShallowImg, Point(0, 0))

-- Layer 3: Water Lake
local waterLakeLayer = sprite:newLayer()
waterLakeLayer.name = "WaterLake"
local waterLakeImg
if waterLakePath and waterLakePath ~= "" then
  waterLakeImg = Image{ fromFile = waterLakePath }
else
  waterLakeImg = Image(w, h, ColorMode.RGBA)
  waterLakeImg:clear(0)
end
sprite:newCel(waterLakeLayer, 1, waterLakeImg, Point(0, 0))

-- Layer 4: Water River
local waterRiverLayer = sprite:newLayer()
waterRiverLayer.name = "WaterRiver"
local waterRiverImg
if waterRiverPath and waterRiverPath ~= "" then
  waterRiverImg = Image{ fromFile = waterRiverPath }
else
  waterRiverImg = Image(w, h, ColorMode.RGBA)
  waterRiverImg:clear(0)
end
sprite:newCel(waterRiverLayer, 1, waterRiverImg, Point(0, 0))

-- Layer 5: Grass
local grassLayer = sprite:newLayer()
grassLayer.name = "Grass"
sprite:newCel(grassLayer, 1, grassImg, Point(0, 0))

-- Layer 6: LakeBank (lake/river and land adjacent tiles only)
local lakebankLayer = sprite:newLayer()
lakebankLayer.name = "LakeBank"
local lakebankImg
if lakebankPath and lakebankPath ~= "" then
  lakebankImg = Image{ fromFile = lakebankPath }
else
  lakebankImg = Image(w, h, ColorMode.RGBA)
  lakebankImg:clear(0)
end
sprite:newCel(lakebankLayer, 1, lakebankImg, Point(0, 0))

-- Layer 7: Shoreline (ocean/land adjacent tiles only)
local shorelineLayer = sprite:newLayer()
shorelineLayer.name = "Shoreline"
local shorelineImg
if shorelinePath and shorelinePath ~= "" then
  shorelineImg = Image{ fromFile = shorelinePath }
else
  shorelineImg = Image(w, h, ColorMode.RGBA)
  shorelineImg:clear(0)
end
sprite:newCel(shorelineLayer, 1, shorelineImg, Point(0, 0))

-- Layer 8+: Hill, Dirt, Trees, POI...
local hillLayer = sprite:newLayer()
hillLayer.name = "Hill"
local hillImg
if hillPath and hillPath ~= "" then
  hillImg = Image{ fromFile = hillPath }
else
  hillImg = Image(w, h, ColorMode.RGBA)
  hillImg:clear(0)
end
sprite:newCel(hillLayer, 1, hillImg, Point(0, 0))

-- Layer 8: Dirt
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

-- Layer 9: Trees
local treesLayer = sprite:newLayer()
treesLayer.name = "Trees"
sprite:newCel(treesLayer, 1, treesImg, Point(0, 0))

-- Layer 10: POI (combined)
local poiLayer = sprite:newLayer()
poiLayer.name = "POI"
local poiImg
if poiPath and poiPath ~= "" then
  poiImg = Image{ fromFile = poiPath }
else
  poiImg = Image(w, h, ColorMode.RGBA)
  poiImg:clear(0)
end
sprite:newCel(poiLayer, 1, poiImg, Point(0, 0))

local function addPoiLayer(name, path)
  local layer = sprite:newLayer()
  layer.name = name
  local img
  if path and path ~= "" then
    img = Image{ fromFile = path }
  else
    img = Image(w, h, ColorMode.RGBA)
    img:clear(0)
  end
  sprite:newCel(layer, 1, img, Point(0, 0))
end
addPoiLayer("Spawn", poiSpawnPath)
addPoiLayer("Join", poiJoinPath)
addPoiLayer("Mine", poiMinePath)
addPoiLayer("Shop", poiShopPath)
addPoiLayer("Creep", poiCreepPath)
addPoiLayer("DeadEnd", poiDeadEndPath)
addPoiLayer("Secret", poiSecretPath)

sprite:saveAs(outPath)
print("Wrote " .. outPath)
