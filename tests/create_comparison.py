"""Create a before/after comparison of the junction fix."""
from PIL import Image, ImageDraw, ImageFont

# Load the corrected junction
fixed_junction = Image.open("/workspace/test_output/junction_painted.png")

# Load the old tile 7 that was incorrectly used
sheet = Image.open("/workspace/examples/shorelines.png")
tile_size = 16
old_tile_x, old_tile_y = (6 % 5) * tile_size, (6 // 5) * tile_size
old_junction = sheet.crop((old_tile_x, old_tile_y, old_tile_x + tile_size, old_tile_y + tile_size))

# Create comparison image
comparison_width = tile_size * 2 + 60
comparison_height = tile_size + 40
comparison = Image.new("RGBA", (comparison_width, comparison_height), (255, 255, 255, 255))

# Paste tiles
comparison.paste(old_junction, (10, 30))
comparison.paste(fixed_junction, (tile_size + 40, 30))

# Add labels
draw = ImageDraw.Draw(comparison)
draw.text((10, 10), "BEFORE (Tile 7)", fill=(255, 0, 0, 255))
draw.text((tile_size + 40, 10), "AFTER (Tile 39)", fill=(0, 128, 0, 255))

# Add title
draw.text((10, comparison_height - 10), "SE Inner Corner Fix", fill=(0, 0, 0, 255))

comparison.save("/workspace/test_output/junction_fix_comparison.png")
print("Saved comparison: /workspace/test_output/junction_fix_comparison.png")

# Also create a larger comparison showing the scenario
scenario_before = Image.new("RGB", (64, 64), (180, 180, 180))
scenario_after = Image.open("/workspace/test_output/scenario2_double_bend_shoreline.png")

# Scale up for visibility
scale = 4
scenario_after_scaled = scenario_after.resize(
    (scenario_after.width * scale, scenario_after.height * scale),
    Image.NEAREST
)

scenario_after_scaled.save("/workspace/test_output/scenario_after_4x.png")
print("Saved 4x scaled scenario: /workspace/test_output/scenario_after_4x.png")
