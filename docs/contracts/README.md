# Mappie map criteria + game contract

Games (and agents) should generate maps from a **criteria profile**, not from a pile of density knobs.

## Files

| Path | Role |
|------|------|
| `profiles/*.json` | Criteria profiles (`genre` + layout + POIs + art + validation) |
| `docs/contracts/map-criteria.schema.json` | Schema for profiles |
| `docs/contracts/game-contract.schema.json` | Schema for playable `*.game.json` exports |
| `profiles/examples/lunacia_rift.game.json` | Reference contract matching Lunacia Rift hardcodes |

## Target CLI

```bash
tilemap-app map-gen --profile profiles/moba_3lane_lunacia.json --seed 77 --out maps/lunacia_rift
```

Emits (at minimum):

- `maps/lunacia_rift.txt` + `.legend.json`
- `build/lunacia_rift.tiled.json` + `.csv`
- `build/lunacia_rift.game.json`  ← **games load this for collision/lanes/POIs**
- preview PNG

## Layout engines

- `moba_lanes` — structured lanes → forest → gaps → POIs (see `moba_3lane_lunacia`)
- `open_world` — existing spawn/path/mine/shop generator
- `arena` — TBD

## Validation

Fail the job if continuous lanes, gap connectivity, required POIs, or canvas pixel size do not match the profile.

## Web API

Extend `MapRequest` with optional `profile` (path or id) and/or nested `layout`. Density fields remain overrides on top of the profile.
