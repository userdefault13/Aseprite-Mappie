-- Add newski.png as a new top layer in an existing .aseprite, positioned at (0,0).
-- Env: NEWSKI_PNG, TARGET_ASEPRITE
local newski_path = os.getenv("NEWSKI_PNG")
local target_path = os.getenv("TARGET_ASEPRITE")
assert(newski_path and target_path, "NEWSKI_PNG and TARGET_ASEPRITE env vars required")

local sprite = app.open(target_path)
assert(sprite, "Could not open target .aseprite: " .. target_path)

-- Load newski.png as a sprite to grab its image.
local newski = Sprite{fromFile=newski_path}
assert(newski, "Could not load newski.png: " .. newski_path)

-- newski.png loads as a single-frame sprite; grab frame 0 cel image (merged).
local newski_img = Image(newski.width, newski.height, newski.colorMode)
local src_cel = newski.cels[1]
if src_cel then
  newski_img:drawImage(src_cel.image, 0, 0)
end

-- Create a new layer at the top of the target sprite and paste the image.
local new_layer = sprite:newLayer()
new_layer.name = "newski_overlay"
local cel = sprite:newCel(new_layer, 1, newski_img, 0, 0)
cel.position = Point(0, 0)

newski:close()
sprite:saveAs(target_path)
print("Added newski_overlay layer to " .. target_path)
