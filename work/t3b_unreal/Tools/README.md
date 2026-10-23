# Source data core: standalone verification

`Source/T3BRemake/Private/T3BSourceData.h/.cpp` has no Unreal Engine dependency. Loaders take byte vectors and throw `T3BSource::FormatError` for rejected input. The UE module therefore enables C++ exceptions.

## Coordinate and matrix contract

- `LoadScene` preserves original ordered draw sections, raw float32 UVs and RGBA bytes. Scene positions are already in PC world units. `units`/`floor` are metadata and must not be applied a second time.
- `LoadSkin` preserves source indices, weights and arbitrary row-major affine matrices. Matrix storage is `[(sample*bones+bone)*12 + row*4+column]`.
- `PoseOriginal` interpolates affine components at stored sample times and returns original-unit positions. It clamps to the first/final sample and does not infer a loop. It expects an unchanged, valid `LoadSkin` result and finite time.
- `ToPC` applies the original C runtime's scale, floor and actor x/z/yaw transform. `ToUE` returns `(PC.z, -PC.x, PC.y)*100` in centimeters (one negated axis converts the right-handed PC frame to left-handed UE without mirroring or reversing winding).
- No matrix is decomposed into `FTransform`. Weights remain quantized source values and are not normalized. Allowed active weight sum is `[.95,1.01]`, matching the C reader; inactive weights must be zero.

Both loaders reject wrong magic/version, wrong or trailing byte counts, invalid bounded counts, incomplete/noncontiguous packet coverage, out-of-range materials, and non-finite floats. Skin validation additionally rejects parent cycles/ranges, invalid influences/weights, nonzero reserved fields, and invalid/non-increasing times. Standalone builds disable floating-point contraction; the implementation also requests precise/no-contraction behavior under MSVC and Clang.

## Run

From `work/t3b_unreal`, with local `g++` and Python on PATH:

```powershell
python -X utf8 Tools/verify_source_core.py
```

This rebuilds the two independent C++17 executables with `-O2 -Wall -Wextra -Werror -ffp-contract=off`, runs 57 unit checks, exports all stored source samples, and writes `Tools/source_core_verification.json` with source, input, executable and output hashes.

Individual probes:

```powershell
.\Tools\source_probe.exe --scene ../t3b_hd/assets/scenes/original_street/original_street.bin --out Tools/scene_probe.csv
.\Tools\source_probe.exe --skin ../t3b_hd/assets/models/clips/aya_fire_reverse_capture.bin --out Tools/aya_fire_probe.csv
```

Skin CSV `x/y/z` fields are original-unit positions and directly comparable to frozen C probes. `pc_x/y/z` and `ue_x/y/z` use actor x/z/yaw of zero. Scene `x/y/z` and `pc_x/y/z` both preserve the stored PC positions; integer bit columns preserve exact source float32 values.

## Observed verification

- 57 checks passed: 10 numerical/preservation checks, 45 malformed-file rejection cases, and 2 invalid-time/coordinate rejection cases.
- All 31,656 scene vertices retain exact position/UV/RGBA bits and draw/material association.
- Aya fire: 60 samples × 3,456 vertices = 207,360 points compared with frozen C results; zero component bit mismatches.
- Weapon fire: 60 × 243 = 14,580 points; zero component bit mismatches.
- Original actor: 60 × 1,800 = 108,000 points; zero component bit mismatches.
- PC scale/floor and UE coordinate conversions pass bit comparisons at all exported points. Explicit non-rigid shear/reflection, between-sample interpolation, clamp, actor translation and yaw cases pass separate unit checks.

These results verify the shared source core on the available standalone compiler. They do not establish UE module compilation, GPU/material correctness, collision or gameplay. The separate engine replay probe is still required when a compatible Unreal Engine installation is available.
