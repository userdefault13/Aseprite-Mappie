"""Check if elbow is adjacent to lake shoreline."""
ascii_lines = [
    "GGGGGG~~~~",
    "GBBBBB~~~~",
    "GB~~~~~~~~",
    "GB~~~~~~~~",
    "GB~~~~~~~~",
    "GB~~~~~~~~",
    "~~~~~~~~~~",
    "~~~~~~~~~~",
]

x, y = 1, 1

# Check neighbors for 'L'
for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
    nx, ny = x + dx, y + dy
    if 0 <= ny < len(ascii_lines) and 0 <= nx < len(ascii_lines[ny]):
        nch = ascii_lines[ny][nx]
        if nch == 'L':
            print(f"Found 'L' at ({nx}, {ny})")
            break
else:
    print("No 'L' cells adjacent to elbow")
