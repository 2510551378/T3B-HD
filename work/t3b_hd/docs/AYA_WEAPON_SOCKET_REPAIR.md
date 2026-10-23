# Aya weapon socket repair

- Idle path no longer uses the old static GE `bone4` fallback.
- Idle weapon pose uses the calibrated hand-local frame.
- Shooting path uses the recovered 44-bone source record index `36` through the 24-frame true hand timeline.
- The true timeline now stores the per-frame right-hand draw center and rotation. The weapon transform maps the local grip directly to that center, then applies the source rotation to the weapon and muzzle offsets; the legacy `155°` yaw correction is bypassed for the true source path.
- The rendered Aya right-hand region now consumes the same interpolated center/rotation as the weapon. It no longer uses the old `0.35` blend or the fixed `.95,1.90,0` pivot, so the palm, grip, and muzzle stay rigidly coincident through the full 24-frame shot loop (idle uses frame 0).
- Across all 24 source frames, grip error is `0.000000` in the recovered local frame and muzzle-vs-hand-forward error is below `1.3e-6°` after float24 decode.

Preview: `build/m1_weapon_idle_refit.png`; continuous-shot capture path: `t3b_hd.exe build/empty_scene.obj --preview` (writes `build/m1_preview_fire_a.ppm` and `build/m1_preview_fire_b.ppm`).
