"""Create a labeled grid of all shoreline tiles."""
from PIL import Image, ImageDraw, ImageFont

sheet = Image.open("/workspace/examples/shorelines.png")
tile_size = 16
cols = sheet.size[0] // tile_size
rows = sheet.size[1] // tile_size

# Create output image with labels
label_height = 12
output_width = cols * (tile_size + 2) + 4
output_height = rows * (tile_size + label_height + 2) + 4

output = Image.new("RGBA", (output_width, output_height), (255, 255, 255, 255))

for idx in range(cols * rows):
    row = idx // cols
    col = idx % cols
    
    # Extract tile
    x, y = col * tile_size, row * tile_size
    tile = sheet.crop((x, y, x + tile_size, y + tile_size))
    
    # Paste to output with spacing
    out_x = 2 + col * (tile_size + 2)
    out_y = 2 + row * (tile_size + label_height + 2)
    output.paste(tile, (out_x, out_y))
    
    # Add label below tile
    draw = ImageDraw.Draw(output)
    label = f"{idx}"
    bbox = draw.textbbox((0, 0), label)
    text_width = bbox[2] - bbox[0]
    label_x = out_x + (tile_size - text_width) // 2
    label_y = out_y + tile_size + 1
    draw.text((label_x, label_y), label, fill=(0, 0, 0, 255))

output.save("/workspace/test_output/shoreline_tiles_grid.png")
print(f"Saved labeled grid: /workspace/test_output/shoreline_tiles_grid.png")
print(f"Grid: {cols}x{rows} = {cols*rows} tiles")
