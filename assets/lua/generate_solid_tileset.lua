-- Create a solid-color terrain tileset from env vars for reproducible CLI runs.
local tileW = tonumber(os.getenv("TILE_W") or "16")
local tileH = tonumber(os.getenv("TILE_H") or "16")
local cols = tonumber(os.getenv("COLS") or "8")
local rows = tonumber(os.getenv("ROWS") or "8")
local out = os.getenv("OUT") or "terrain_tileset.aseprite"
local spec = os.getenv("TILES_SPEC") or ""

local sprite = Sprite(tileW * cols, tileH * rows, ColorMode.RGB)
app.activeSprite = sprite

local layer = sprite.layers[1]
local cel = layer:cel(1)
local image = cel.image

local function fillTile(tileId, r, g, b, a)
  local idx = tileId - 1
  if idx < 0 then
    return
  end
  local col = idx % cols
  local row = math.floor(idx / cols)
  if row >= rows then
    return
  end
  local x0 = col * tileW
  local y0 = row * tileH
  local color = app.pixelColor.rgba(r, g, b, a)
  for y = y0, y0 + tileH - 1 do
    for x = x0, x0 + tileW - 1 do
      image:drawPixel(x, y, color)
    end
  end
end

for entry in string.gmatch(spec, "[^;]+") do
  local id, r, g, b, a = string.match(entry, "^(%d+):(%d+),(%d+),(%d+),(%d+)$")
  if id then
    fillTile(tonumber(id), tonumber(r), tonumber(g), tonumber(b), tonumber(a))
  end
end

sprite:saveAs(out)
print("Wrote " .. out)
