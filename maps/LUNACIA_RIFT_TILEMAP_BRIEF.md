# Lunacia Rift — tilemap brief (Aseprite-Mappie)

**Do not** ship one painted arena plate. Ship a **real tilemap**: ASCII → Tiled JSON/CSV → Aseprite-painted tileset.

## Deliverables
1. Keep / refine `maps/lunacia_rift.txt` + `maps/lunacia_rift.legend.json` (3 horizontal lanes, forest bands, 3 gaps).
2. Run `ascii_to_tilemap.py` → `build/lunacia_rift.tiled.json` + `.csv`.
3. Paint / assign tiles in Aseprite using existing terrain examples (`examples/grass|dirt|trees|…`) — Lunacia jungle feel (deep greens, dirt paths). Origins arena plates are **reference only**, not the map.
4. Export tileset PNG + metadata; drop copies into `~/Dev/lunacia-rift/assets/map/`:
   - `lunacia_rift.tiled.json`
   - `lunacia_rift.csv`
   - `lunacia_rift_tileset.png` (or linked tsx)
5. Optional: layered preview BMP/PNG for review.

## Hard layout (must match game collision)
| Spec | Value |
|------|-------|
| Playable | ~1500×800 (16px tiles → 94×50 = 1504×800 OK) |
| Lanes Y (px) | 130 / 400 / 670 |
| Path band | ~72px tall |
| Forest gaps X | 420 / 750 / 1080 (~100px clear) |
| Left | player Sanctuary / Nest |
| Right | enemy |
| Terms | Nest / Spire / Pack / Sanctuary / Den only |

## Legend (ASCII)
- `G` grass · `P` path · `T`/`F` forest (solid) · `R` rock · `D` Den · `S` Spire · `N` Nest

## Out of scope
- Island map-gen defaults (unsuitable)
- Full Origins PvE background plate as the map
- Sapidae/Axie GLBs as terrain

## Success
Walkable 3 lanes + cross-lane gaps match game.js forest collision; Tiled file loads; tileset looks hand-authored Lunacia jungle.
