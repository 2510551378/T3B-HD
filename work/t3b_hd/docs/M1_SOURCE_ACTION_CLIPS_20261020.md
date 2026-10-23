# M1 source action clip pairs

## Implemented contract

The source path loads the canonical reference from `assets/models/aya_source_skin.bin` and `assets/models/aya_source_weapon.bin`. The optional `assets/models/aya_source_clips.txt` has this grammar:

```text
T3BCLIPS1 N
label body_relative_path weapon_relative_path
```

`N` is 0 through 5. Supported unique labels are `reference`, `aim`, `fire`, `move`, and `approach_fire`. Paths are relative to `assets/models/`; paths already beginning with `assets/models/` are also accepted. Absolute paths, parent traversal, and duplicate or unknown labels are rejected. `approach_fire` is the explicit captured approach-plus-fire input sequence; it is not renamed as generic locomotion or strafe.

Every pair must have exactly equal sample-time arrays, start at time 0, and share `units` and `floor`. Body structure must be 44 bones, 106 packets, and 3,456 vertex records; weapon structure must be one bone and 243 vertex records. A clip must exactly match the canonical asset's parent indices, packet topology/material indices, vertex positions, UVs, normals, bone indices, weights, render flags, material count, units, and floor. Both members load the original common material manifests. A failed optional entry rejects the whole optional manifest and keeps the canonical reference. An invalid canonical pair takes the explicit legacy fallback.

## Playback

`R` locking selects `aim`; stationary `SPACE` and the shot window select `fire`; simultaneous `W/S` plus firing selects `approach_fire`; unlocked `W/S` alone still requests `move`; otherwise playback uses `reference`. Unavailable `fire` falls back to an available `aim`, and unavailable `approach_fire` falls back to `fire`, then `reference`. Lock aim takes priority over movement when no shot is active.

A selected pair switch resets its clock to 0. Body skinning, weapon rendering, and weapon-tip-derived muzzle queries share that pair and clock. Sparse captures interpolate at their stored sample times and clamp at the last sample. Holding `SPACE` now requests repeated shots through the existing cooldown. A held sparse firing clip consequently holds its last sample when exhausted; a loop is not inferred.

The muzzle is still a geometric candidate measured from the real weapon mesh, **not a recovered original muzzle socket**. Original matrices determine its transform.

The new source path no longer loads the old region OBJ, old source-36 timeline, or old `aya_albedo.bmp`. Those remain restricted to legacy fallback.

## Verification performed

Built `build/t3b_hd_clips.exe` with GCC `-Wall -Wextra -Werror`, with no diagnostics. Ran:

```powershell
.\build\t3b_hd_clips.exe --test-source-clips
```

This uses a hidden OpenGL window to validate real asset loading and a small selection/time-state check; it does not run gameplay or certify action identity. Current evidence in `build/m1_source_clip_check.txt`:

- Canonical pair loaded: body 44/106/3,456 and weapon 1/1/243, both 12 samples and 2.73588371 seconds.
- Optional manifest loads three synchronized pairs: `aim`, `fire`, and `approach_fire`; generic `move` remains unavailable.
- Five selector checks, eight transition checks, eight end-clamp checks: zero failures.
- Twelve pair-state checks: zero synchronization failures.
- Fallback frames are explicitly counted; no missing action is reported as recovered.

`--test` additionally writes availability/request/selection counts, switch/fallback counts, pair synchronization checks, and the active clip/time to `build/m1_source_skin_result.txt`.

## Next validation required

Export verified aim/fire captures using the same canonical geometry, units, and floor, add the real manifest, then rerun the asset check and actual preview/play checks. Inspect the full captured interval for hand/grip following, weapon direction, and muzzle-tip motion. The current check has not validated any newly named action capture or full gameplay.
