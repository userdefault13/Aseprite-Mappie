"""Check actual shoreline sheet dimensions."""
from PIL import Image

img_path = "/workspace/examples/shorelines.png"
img = Image.open(img_path)

print(f"Image: {img_path}")
print(f"Size: {img.size}")
print(f"Mode: {img.mode}")

tile_size = 16
cols = img.size[0] // tile_size
rows = img.size[1] // tile_size
total_tiles = cols * rows

print(f"\nWith {tile_size}x{tile_size} tiles:")
print(f"  Columns: {cols}")
print(f"  Rows: {rows}")
print(f"  Total tiles: {total_tiles}")
print(f"\nConfig says range [1, 55] = 55 tiles")
print(f"Actual tiles available: {total_tiles}")
print(f"Mismatch: {55 - total_tiles} tiles short!")
