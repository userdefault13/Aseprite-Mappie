-- Paint an ASCII map as a colored tilemap in Aseprite.
-- Env: MAP_ASCII_PATH, TILE_W, TILE_H, OUT
-- Optional (tree tiles): TREESET_PATH, RESOLVED_TREES_PATH
local mapPath = os.getenv("MAP_ASCII_PATH")
local tileW = tonumber(os.getenv("TILE_W") or "16")
local tileH = tonumber(os.getenv("TILE_H") or "16")
local out = os.getenv("OUT") or "map.aseprite"
local treesetPath = os.getenv("TREESET_PATH")
local resolvedPath = os.getenv("RESOLVED_TREES_PATH")
local useTreeset = treesetPath and treesetPath ~= "" and resolvedPath and resolvedPath ~= ""

if not mapPath or mapPath == "" then
  print("Error: MAP_ASCII_PATH must be set")
  return
end

local colors = {
  ["G"] = { 104, 178, 76, 255 },
  ["."] = { 104, 178, 76, 255 },
  ["~"] = { 72, 132, 224, 255 },
  ["`"] = { 48, 96, 180, 255 },
  ["T"] = { 46, 108, 54, 255 },
  ["F"] = { 30, 78, 40, 255 },
  ["P"] = { 181, 152, 102, 255 },
  ["S"] = { 250, 228, 92, 255 },
  ["J"] = { 255, 161, 77, 255 },
  ["M"] = { 125, 126, 134, 255 },
  ["H"] = { 214, 123, 73, 255 },
  ["C"] = { 194, 76, 76, 255 },
  ["D"] = { 240, 95, 95, 255 },
  ["N"] = { 86, 208, 220, 255 },
}
local defaultColor = { 255, 0, 255, 255 }

local lines = {}
local width = 0
for line in io.lines(mapPath) do
  local row = line:gsub("\r", "")
  table.insert(lines, row)
  if #row > width then
    width = #row
  end
end

local height = #lines
if height == 0 or width == 0 then
  print("Error: ASCII map is empty")
  return
end

-- Parse resolved tree tiles (row,col) -> tile_id (for T/F cells only)
local resolvedTrees = {}
if useTreeset then
  local y = 1
  for line in io.lines(resolvedPath) do
    local row = line:gsub("\r", "")
    resolvedTrees[y] = {}
    local x = 1
    for cell in string.gmatch(row, "[^,]+") do
      local tid = tonumber(cell)
      resolvedTrees[y][x] = tid or 0
      x = x + 1
    end
    y = y + 1
  end
end

local sprite = Sprite(width * tileW, height * tileH, ColorMode.RGB)
app.activeSprite = sprite

local groundLayer = sprite.layers[1]
groundLayer.name = "Ground"
local groundCel = groundLayer:cel(1)
local groundImage = groundCel.image

local treesLayer = nil
local treesImage = nil
if useTreeset then
  treesLayer = sprite:newLayer()
  treesLayer.name = "Trees"
  local treesCel = sprite:newCel(treesLayer, 1)
  treesImage = treesCel and treesCel.image or nil
end

local treesetSprite = nil
local treesetImage = nil
local treesetTileW, treesetTileH = tileW, tileH
local treesetCols = 7

if useTreeset then
  app.open(treesetPath)
  treesetSprite = app.sprites[#app.sprites]
  if not treesetSprite then
    print("Warning: Could not open treeset, falling back to colors")
    useTreeset = false
  else
    -- Flattened composite: Image(sprite) or drawSprite fallback for multi-layer treesets.
    treesetImage = Image(treesetSprite)
    if not treesetImage or treesetImage.width == 0 then
      local composite = Image(treesetSprite.width, treesetSprite.height, ColorMode.RGB)
      composite:clear(app.pixelColor.rgba(0, 0, 0, 0))
      composite:drawSprite(treesetSprite, 1, Point(0, 0))
      treesetImage = composite
    end
    if treesetImage and treesetImage.width > 0 and treesetImage.height > 0 then
      -- Treeset layout: 7 cols x 5 rows (configurable via TREESET_COLS, TREESET_ROWS)
      treesetCols = tonumber(os.getenv("TREESET_COLS")) or 7
      local treesetRows = tonumber(os.getenv("TREESET_ROWS")) or 5
      treesetTileW = math.floor(treesetImage.width / treesetCols)
      treesetTileH = math.floor(treesetImage.height / treesetRows)
    else
      treesetImage = nil
      useTreeset = false
    end
  end
end

-- Paste tile using Image:drawImage (handles transparency/compositing)
local function drawTileWithDrawImage(tileId, dstX, dstY, dstImage)
  if not treesetImage or tileId < 1 or not dstImage then return end
  local idx = tileId - 1
  local col = idx % treesetCols
  local row = math.floor(idx / treesetCols)
  local sx0 = col * treesetTileW
  local sy0 = row * treesetTileH
  local srcW, srcH = treesetTileW, treesetTileH
  if srcW <= 0 or srcH <= 0 then return end
  local tileRect = Rectangle(sx0, sy0, srcW, srcH)
  local tileImg = Image(treesetImage, tileRect)
  if not tileImg then return end
  if srcW ~= tileW or srcH ~= tileH then
    tileImg:resize(tileW, tileH)
  end
  dstImage:drawImage(tileImg, Point(dstX, dstY), 255, BlendMode.NORMAL)
end

-- Pass 1: draw ground for ALL cells (T/F -> grass so trees layer shows through)
for y, row in ipairs(lines) do
  for x = 1, width do
    local ch = row:sub(x, x)
    if ch == "" then ch = "." end
    if useTreeset and (ch == "T" or ch == "F") then ch = "G" end
    local px0 = (x - 1) * tileW
    local py0 = (y - 1) * tileH
    local rgb = colors[ch] or defaultColor
    local color = app.pixelColor.rgba(rgb[1], rgb[2], rgb[3], rgb[4])
    for py = py0, py0 + tileH - 1 do
      for px = px0, px0 + tileW - 1 do
        groundImage:drawPixel(px, py, color)
      end
    end
  end
end

-- Pass 2: draw tree tiles on Trees layer (T/F cells only)
-- Use drawImage for correct transparency/compositing
if useTreeset and treesetImage and treesImage then
  for y, row in ipairs(lines) do
    for x = 1, width do
      local ch = row:sub(x, x)
      if ch == "T" or ch == "F" then
        local tileId = resolvedTrees[y] and resolvedTrees[y][x]
        if tileId and tileId > 0 then
          local px0 = (x - 1) * tileW
          local py0 = (y - 1) * tileH
          drawTileWithDrawImage(tileId, px0, py0, treesImage)
        end
      end
    end
  end
end

sprite:saveAs(out)
print("Wrote " .. out)
