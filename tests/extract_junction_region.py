"""Extract and analyze a region of the generated map shoreline."""
from PIL import Image

# Load the full shoreline preview
img = Image.open("/workspace/maps/generated_map.preview_shoreline.png")
print(f"Full image size: {img.size}")

# Extract a region (top-left corner where we know there are B cells)
# From ASCII: lines 2-10, columns 0-20
tile_size = 16
x_start = 0
y_start = 2 * tile_size
width = 20 * tile_size
height = 15 * tile_size

region = img.crop((x_start, y_start, x_start + width, y_start + height))
region.save("/workspace/test_output/shoreline_topleft_region.png")
print(f"Extracted region saved: /workspace/test_output/shoreline_topleft_region.png")
print(f"Region size: {region.size} ({width//tile_size}x{height//tile_size} tiles)")

# Try to find a specific L-junction
# Looking at ASCII line 9 (y=9): ``~~~~BGGPGTGGP...
# The B at column 5 should form some kind of junction
junction_x = 5 * tile_size
junction_y = 9 * tile_size
junction_tile = img.crop((junction_x, junction_y, junction_x + tile_size, junction_y + tile_size))
junction_tile.save("/workspace/test_output/junction_at_5_9.png")
print(f"Junction tile at (5,9) saved")

# Extract a 3x3 region around it for context
context_x = 4 * tile_size
context_y = 8 * tile_size
context = img.crop((context_x, context_y, context_x + 3*tile_size, context_y + 3*tile_size))
context.save("/workspace/test_output/junction_context_3x3.png")
print(f"3x3 context around junction saved")
