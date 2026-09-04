# newski citadel wall art

Source art for the citadel wall/tower/gate pieces that `scripts/` composites into
the gotchiverse-2d chunk maps.

This directory exists because the art was previously reachable only through
`/tmp/newski_layers` (an Aseprite export target that macOS has since purged) and
`build/` (gitignored). Every copy of it was one `rm -rf` away from being gone.
No `.aseprite` master file for these pieces exists anywhere on disk — `source/`
below is the earliest surviving form.

## `source/`

19 per-layer PNGs at native 8px-tile resolution, exported from Aseprite on
2026-08-27. This is the input to the pipeline:

```
scripts/newski_legend_pipeline.py <layer>   # source/<layer>.png -> build/newski_legend_<layer>.{png,json} + build/newski_<layer>_64.png
scripts/slice_and_pack_newski.py            # -> gotchiverse sprites sheets + build/newski_pack_meta.json
scripts/write_wall_chunks.py                # -> stamps GIDs into gotchiverse chunk TMJs
```

`scripts/newski_legend_pipeline.py` and `scripts/build_newski_tower_sheet.py`
both read this directory via their `NEWski_LAYERS` constant.

Regeneration is deterministic: re-running the legend pipeline over `source/`
reproduces 14 of the 15 derived layers **byte-identically**. The exception is
documented below.

## `prebuilt/`

Derived artifacts committed because they **cannot** be reproduced from `source/`.
Do not delete these assuming the pipeline can rebuild them.

### `newski_topleftcorner_64.png` + its legend pair — source diverges

`source/topleftcorner.png` (2026-08-27) is a **later revision** than the derived
art the citadel chunks were actually stamped with (2026-08-21). Regenerating from
source changes 1.63% of pixels, confined to the north edge (tiles x95-153, y0-12):
the corner tower moves right and the parapet is extended along the top run.

Which one is intended has not been decided. The files here are the **2026-08-21**
version — the one matching what is currently written into the live gotchiverse
chunks. If the Aug 27 revision is the wanted one, regenerating is not enough:
`newski_pack_meta.json` must be rebuilt and the affected chunks re-stamped via
`scripts/write_wall_chunks.py`, because tile GIDs will shift.

### `newski_leftmidsmall_64.png` + its legend pair — no source layer

There is no `source/leftmidsmall.png`. This layer predates the Aug 27 export
(dated 2026-08-19) and appears to be an early experiment; its only consumer is
`scripts/tower2_newski_overlay.py:109`, which is itself currently unrunnable.
Retained rather than deleted because it cannot be recreated.

### `newski_pack_meta.json` — GID allocation is load-bearing

Maps each wall piece to its `firstgid` and local tile ids in the packed
spritesheets, and is consumed directly by `scripts/write_wall_chunks.py`.
The allocation it records is **already baked into the chunk TMJs** in
gotchiverse-2d. Regenerating it from a different set of inputs would renumber
tiles and silently invalidate every chunk already stamped, so the working
allocation is pinned here.

## Note on `build/`

`build/` remains gitignored and holds the regenerable derivatives. Nothing in
`build/newski_*` should be treated as a source of truth; if it disappears, run
the legend pipeline over `source/` and restore the three pinned exceptions above
from `prebuilt/`.
