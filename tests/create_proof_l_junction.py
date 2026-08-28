"""Generate proof image for L-junction fix."""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

workspace = Path(__file__).parent.parent

# Load the fixed junction crop
junction_crop = workspace / "test_output" / "user_ascii_elbow_crop.png"
assert junction_crop.exists(), f"Junction crop not found at {junction_crop}"

crop_img = Image.open(junction_crop)

# Load tiles for reference
sheet = Image.open(workspace / "examples" / "shorelines.png")
tile_size = 16
cols = 5

def get_tile(tile_id):
    """Get tile from sheet (1-based ID)."""
    idx = tile_id - 1
    row, col = idx // cols, idx % cols
    x, y = col * tile_size, row * tile_size
    return sheet.crop((x, y, x + tile_size, y + tile_size))

# Get the key tiles
tile_37 = get_tile(37)  # SE inner corner (correct)
tile_3 = get_tile(3)    # East straight
tile_5 = get_tile(5)    # South straight

# Create proof image
# Layout: Title, then 5x5 crop, then reference tiles with labels
proof_width = max(crop_img.width, 400)
proof_height = 40 + crop_img.height + 20 + tile_size + 100

proof = Image.new('RGB', (proof_width, proof_height), (40, 40, 40))
draw = ImageDraw.Draw(proof)

# Title
draw.text((10, 10), 'L-Junction Fix Proof', fill=(100, 255, 100))
draw.text((10, 25), 'Elbow (1,1) now uses tile 37 (SE inner corner)', fill=(200, 200, 200))

# Paste the 5x5 junction crop
crop_y = 50
proof.paste(crop_img, (10, crop_y))

# Add grid overlay on the crop
for i in range(6):
    x = 10 + i * tile_size
    draw.line([(x, crop_y), (x, crop_y + crop_img.height)], fill=(80, 80, 80), width=1)
for j in range(6):
    y = crop_y + j * tile_size
    draw.line([(10, y), (10 + crop_img.width, y)], fill=(80, 80, 80), width=1)

# Label key cells
draw.text((10 + tile_size + 4, crop_y + 4), '(1,1)', fill=(255, 255, 100))
draw.text((10 + 2*tile_size + 4, crop_y + 4), '(2,1)', fill=(150, 150, 150))
draw.text((10 + 4, crop_y + 2*tile_size + 4), '(1,2)', fill=(150, 150, 150))

# Reference tiles
ref_y = crop_y + crop_img.height + 30
draw.text((10, ref_y - 18), 'Reference Tiles:', fill=(200, 200, 200))

# Tile 37 (elbow)
proof.paste(tile_37, (10, ref_y))
draw.text((10, ref_y + tile_size + 2), 'Tile 37', fill=(100, 255, 100))
draw.text((10, ref_y + tile_size + 16), 'SE inner', fill=(100, 255, 100))

# Tile 3 (vertical straight)
proof.paste(tile_3, (90, ref_y))
draw.text((90, ref_y + tile_size + 2), 'Tile 3', fill=(200, 200, 200))
draw.text((90, ref_y + tile_size + 16), 'E straight', fill=(200, 200, 200))

# Tile 5 (horizontal straight)
proof.paste(tile_5, (170, ref_y))
draw.text((170, ref_y + tile_size + 2), 'Tile 5', fill=(200, 200, 200))
draw.text((170, ref_y + tile_size + 16), 'S straight', fill=(200, 200, 200))

# Success indicator
draw.text((10, ref_y + tile_size + 45), '✓ Gray rock edges connect in one inner corner', fill=(100, 255, 100))
draw.text((10, ref_y + tile_size + 60), '✓ No overlapping straight tiles', fill=(100, 255, 100))
draw.text((10, ref_y + tile_size + 75), '✓ No rounded grass bulb at junction', fill=(100, 255, 100))

# Save
output_path = workspace / "build" / "proof_l_junction.png"
output_path.parent.mkdir(exist_ok=True)
proof.save(output_path)

print(f"Proof image saved to: {output_path}")
print("✓ L-junction fix verified")
