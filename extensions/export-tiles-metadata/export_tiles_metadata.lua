-- Export Tiles Metadata
-- Exports tileset tiles (index, id, data, x, y) to JSON and CSV.

local function getTileCount(tileset)
  -- Try tileset.length (Aseprite 1.3+), use pcall to avoid __index errors
  local ok, len = pcall(function() return tileset.length end)
  if ok and len ~= nil and type(len) == "number" then
    return len
  end
  -- Fallback: iterate until tile returns nil
  local count = 0
  for i = 1, 10000 do
    local ok2, tile = pcall(function() return tileset:tile(i) end)
    if not ok2 or not tile then
      break
    end
    count = i
  end
  return count
end

local function safeGet(obj, key, default)
  if obj == nil then return default end
  local ok, val = pcall(function() return obj[key] end)
  return (ok and val ~= nil) and val or default
end

local function collectTilesetTiles(tileset)
  local tiles = {}
  local grid = safeGet(tileset, "grid", nil)
  local tw, th = 32, 32
  if grid then
    local ts = safeGet(grid, "tileSize", nil)
    if ts then
      tw = tonumber(safeGet(ts, "width", 32)) or 32
      th = tonumber(safeGet(ts, "height", 32)) or 32
    end
  end
  local total = getTileCount(tileset)
  local cols = math.max(1, math.ceil(math.sqrt(total)))

  for i = 1, total do
    local ok, tile = pcall(function() return tileset:tile(i) end)
    if ok and tile then
      local x = (i - 1) % cols
      local y = math.floor((i - 1) / cols)
      local idx = tonumber(safeGet(tile, "index", i)) or i
      local id = idx
      local props = safeGet(tile, "properties", nil)
      if props then
        local propId = safeGet(props, "id", nil)
        if propId ~= nil then id = propId end
      end
      if id == idx then
        local dataStr = safeGet(tile, "data", "") or ""
        if type(dataStr) == "string" and dataStr ~= "" then
          local num = tonumber(dataStr)
          id = (num ~= nil) and num or idx
        end
      end
      tiles[#tiles + 1] = {
        index = idx,
        id = id,
        data = tostring(safeGet(tile, "data", "") or ""),
        x = x,
        y = y,
      }
    end
  end
  return tiles, tw, th
end

local function collectGridTiles(sprite)
  -- Slice single-frame sprite by its grid (for tileset images like grass.png)
  local tiles = {}
  local sw = tonumber(safeGet(sprite, "width", 0)) or 0
  local sh = tonumber(safeGet(sprite, "height", 0)) or 0
  local gridBounds = safeGet(sprite, "gridBounds", nil)
  local tw = 16
  local th = 16
  if gridBounds then
    tw = tonumber(safeGet(gridBounds, "width", 16)) or 16
    th = tonumber(safeGet(gridBounds, "height", 16)) or 16
  end
  if tw <= 0 or th <= 0 or sw <= 0 or sh <= 0 then
    return tiles, 16, 16
  end
  local cols = math.floor(sw / tw)
  local rows = math.floor(sh / th)
  if cols <= 0 or rows <= 0 then
    return tiles, tw, th
  end
  local total = cols * rows
  for i = 1, total do
    local x = (i - 1) % cols
    local y = math.floor((i - 1) / cols)
    tiles[#tiles + 1] = {
      index = i,
      id = i,
      data = "",
      x = x,
      y = y,
    }
  end
  return tiles, tw, th
end

local function collectFrameTiles(sprite)
  local tiles = {}
  local tw = tonumber(safeGet(sprite, "width", 32)) or 32
  local th = tonumber(safeGet(sprite, "height", 32)) or 32
  local frames = safeGet(sprite, "frames", {})
  local frameCount = (type(frames) == "table" and #frames) or 0

  if frameCount <= 1 then
    -- Single frame: slice by grid if it yields multiple tiles (tileset image)
    local gridTiles, gridTw, gridTh = collectGridTiles(sprite)
    if #gridTiles > 1 then
      return gridTiles, gridTw, gridTh
    end
    -- Fallback: treat as 1x1
    tiles[#tiles + 1] = {
      index = 1,
      id = 1,
      data = "",
      x = 0,
      y = 0,
    }
    return tiles, tw, th
  end

  -- Multi-frame: each frame is a tile, laid out in a grid
  local cols = math.ceil(math.sqrt(frameCount))
  for i = 1, frameCount do
    local x = (i - 1) % cols
    local y = math.floor((i - 1) / cols)
    tiles[#tiles + 1] = {
      index = i,
      id = i,
      data = "",
      x = x,
      y = y,
    }
  end
  -- Tile size: assume frames are same size, use first cel
  local cels = safeGet(sprite, "cels", {})
  if type(cels) == "table" then
    for _, cel in ipairs(cels) do
      if cel then
        local img = safeGet(cel, "image", nil)
        if img then
          tw = tonumber(safeGet(img, "width", tw)) or tw
          th = tonumber(safeGet(img, "height", th)) or th
          break
        end
      end
    end
  end
  return tiles, tw, th
end

local function exportFromSprite(sprite)
  local tiles = {}
  local tw, th = 32, 32
  local source = tostring(safeGet(sprite, "filename", "") or "unsaved")

  local tilesets = safeGet(sprite, "tilesets", nil)
  if tilesets and type(tilesets) == "table" and #tilesets > 0 then
    -- Tileset-based: use first tileset
    local tileset = tilesets[1]
    if tileset then
      tiles, tw, th = collectTilesetTiles(tileset)
      local tsName = safeGet(tileset, "name", "default")
      source = source .. " (tileset: " .. tostring(tsName) .. ")"
    end
  end

  if #tiles == 0 then
    -- Frame-based: treat each frame as a tile
    tiles, tw, th = collectFrameTiles(sprite)
  end

  return {
    source = source,
    tile_width = tw,
    tile_height = th,
    total_tiles = #tiles,
    tiles = tiles,
  }
end

local function loadConfigFile(configPath)
  if not configPath or configPath == "" then return nil, nil end
  local f = io.open(configPath, "r")
  if not f then return nil, nil end
  local content = f:read("*a")
  f:close()
  if not content or content == "" then return nil, nil end
  local ok, data = pcall(function() return json.decode(content) end)
  if not ok or not data or type(data) ~= "table" then return nil, nil end
  local legend = data.legend
  local treeConfig = data.tree_config
  -- If no explicit legend/tree_config, treat whole object as legend (char -> id)
  if not legend and not treeConfig then
    local hasStringKeys = false
    for k, v in pairs(data) do
      if type(k) == "string" and #k == 1 and type(v) == "number" then
        hasStringKeys = true
        break
      end
    end
    if hasStringKeys then legend = data end
  end
  return legend, treeConfig
end

local function mergeConfig(out, configPath)
  local legend, treeConfig = loadConfigFile(configPath)
  if legend and type(legend) == "table" then
    out.legend = legend
  end
  if treeConfig and type(treeConfig) == "table" then
    out.tree_config = treeConfig
  end
  -- Also merge bitmask config (grass_shoreline, lake_shoreline, ranges, masks)
  local f = io.open(configPath, "r")
  if f then
    local content = f:read("*a")
    f:close()
    if content and content ~= "" then
      local ok, data = pcall(function() return json.decode(content) end)
      if ok and data and type(data) == "table" then
        local bitmaskKeys = {
          "grass_tile_range", "grass_shoreline", "lake_shoreline",
          "grass_shoreline_range", "grass_shoreline_lake_range",
          "grass_shoreline_extended_range", "grass_shoreline_river_range",
          "extended_shoreline_masks", "river_masks", "interior_corner_masks"
        }
        for _, key in ipairs(bitmaskKeys) do
          if data[key] ~= nil then out[key] = data[key] end
        end
      end
    end
  end
end

local function writeJson(data, path)
  if not json or not json.encode then
    error("json.encode not available (Aseprite 1.3-rc5+ required)")
  end
  local text = json.encode(data)
  local f = io.open(path, "w")
  if not f then
    error("Cannot write file: " .. path)
  end
  f:write(text)
  f:close()
end

local function writeCsv(data, path)
  local f = io.open(path, "w")
  if not f then
    error("Cannot write file: " .. path)
  end
  f:write("index,id,x,y,data\n")
  for _, t in ipairs(data.tiles) do
    local dataEsc = (t.data or ""):gsub('"', '""')
    f:write(string.format('%d,%s,%d,%d,"%s"\n', t.index, tostring(t.id), t.x, t.y, dataEsc))
  end
  f:close()
end

local function runExport()
  local sprite = app.activeSprite
  if not sprite then
    app.alert("No active sprite. Open a sprite first.")
    return
  end

  local defaultPath = "export"
  local fn = safeGet(sprite, "filename", "")
  if fn and fn ~= "" then
    local ok, stem = pcall(function() return app.fs.filePathAndTitle(fn) end)
    if ok and stem and stem ~= "" then defaultPath = stem end
  else
    local ok, cur = pcall(function() return app.fs.currentPath end)
    if ok and cur then
      local ok2, joined = pcall(function() return app.fs.joinPath(cur, "export") end)
      if ok2 and joined then defaultPath = joined end
    end
  end

  local dlg = Dialog("Export Tiles Metadata")
  dlg:file {
    id = "path",
    title = "Save JSON/CSV to",
    filename = defaultPath,
    save = true,
    entry = true,
    filetypes = { "json" },
  }
  dlg:file {
    id = "config",
    title = "Merge config (legend + tree_config, optional)",
    filename = "",
    open = true,
    entry = true,
    filetypes = { "json" },
  }
  dlg:check {
    id = "export_json",
    label = "Export JSON",
    selected = true,
  }
  dlg:check {
    id = "export_csv",
    label = "Export CSV",
    selected = true,
  }
  dlg:button { id = "ok", text = "Export" }
  dlg:button { id = "cancel", text = "Cancel" }
  dlg:show()

  local data = dlg.data
  if not data.ok then
    return
  end

  local path = (data and data.path) and tostring(data.path) or ""
  if not path or path == "" then
    app.alert("No output path specified.")
    return
  end

  -- Ensure path has no extension for our stem
  local okPath, pathStem = pcall(function() return app.fs.filePathAndTitle(path) end)
  path = (okPath and pathStem and pathStem ~= "") and pathStem or path:gsub("%.[^%.]+$", "") or "export"

  if not data.export_json and not data.export_csv then
    app.alert("Select at least one format (JSON or CSV).")
    return
  end

  local ok, err = pcall(function()
    local out = exportFromSprite(sprite)
    local configPath = (data and data.config) and tostring(data.config) or ""
    if configPath and configPath ~= "" and data.export_json then
      mergeConfig(out, configPath)
    end
    local written = {}
    if data.export_json then
      local jsonPath = path .. ".json"
      writeJson(out, jsonPath)
      written[#written + 1] = jsonPath
    end
    if data.export_csv then
      local csvPath = path .. ".csv"
      writeCsv(out, csvPath)
      written[#written + 1] = csvPath
    end
    app.alert("Exported " .. out.total_tiles .. " tiles to:\n" .. table.concat(written, "\n"))
  end)

  if not ok then
    app.alert("Export failed: " .. tostring(err))
  end
end

function init(plugin)
  plugin:newCommand {
    id = "ExportTilesMetadata",
    title = "Export Tiles Metadata",
    group = "file_export",
    onclick = function()
      runExport()
    end,
    onenabled = function()
      return app.activeSprite ~= nil
    end,
  }
end

function exit(plugin)
end
