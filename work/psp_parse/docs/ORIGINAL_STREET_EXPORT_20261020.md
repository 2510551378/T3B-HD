# Original battle street: observed geometry export

The original main-camera street is exported from two existing GE captures. This is the camera-visible stable geometry, not a claim to a complete level or recovered original collision/navigation.

## Assets and evidence

- `work/t3b_hd/assets/scenes/original_street/original_street.bin`: T3BSCN1 v1, 140 ordered draws, 31,656 vertices, 10,552 triangles, 81 material states. SHA256 `08f7e9617f41910f45c32fd54a34eb8c2ae0d6199d1845044dcb76b2b705fcba`.
- `original_street_materials.txt`: T3BSCNM1, 81 entries, original blend/depth-write/cull enables and 73 unique BMP V4 RGBA textures.
- `original_street.json`: every original draw WORLD/VIEW/PROJ, exact PRIM-time registers, geometry/texture/CLUT identities and unsupported state.
- `work/psp_parse/out/ORIGINAL_STREET_EXPORT.json` and `ORIGINAL_STREET_VERIFICATION.json`: input/artifact SHA identities and deterministic verification results.

Source captures are `slot0_fire_world_dense_verified/world_ge_0.ppdmp` (SHA256 `bf6a35337c3177cbcb66a2590ca402fcabc402758e3b7d11d33305620f06208c`) and `slot0_aim_world_dense_verified/world_ge_0.ppdmp` (SHA256 `1b5abba1fa42337356d0e96e1a22058eae381e12b4c9e7bd534313940f87ffc8`) under `work/psp_parse/out/AYA_BONE_GE_ACTIONS/`.

## Format and coordinates

Header `<8s4I8f`, 56 bytes: `T3BSCN1\0`, version, draw/vertex/material counts, player x/z/yaw, enemy x/z/yaw, canonical units, canonical floor. Draws `<3I`: first vertex, vertex count, material index. Vertices `<5f4B`, 24 bytes: PC position xyz, original float32 UV, original RGBA bytes. Total file size 761,480 bytes.

`PC = units * (inverse(reference Aya WORLD) * original draw WORLD * (POS16 / 32768) - [0,floor,0])`.

Units `0.01106623198148076` and floor `-0.15446150302886963` come from the canonical Aya source export. No scene centering or independent height scale is applied. Player spawn is `[0,0,0]`; enemy `[x,z,yawRadians]` is `[2.666991517166828,0.02244852098917704,-1.579219303342358]`. Enemy yaw-only rotation residual is `1.525902185051109e-5`; determinant `1.0000158690601273`; relative source vertical translation `-4.252089399399341e-5`. These are within explicit float24 tolerances.

## Verified facts

- All selected geometry is original unindexed triangle-list VTYPE `0x11f`, stride20: F32 UV offset0, RGBA8 offset8, signed16 position offset12. Original order is preserved.
- Both raw captures have equal multisets of geometry + WORLD + material signatures for the 140 selected draws.
- Every packed position is independently recomputed from raw POS16 and original matrices. Maximum PC float32 rounding error is `7.6130925776851655e-6`.
- All 31,656 UV pairs are bit-identical and all vertex RGBA bytes match their raw GE source. UV coordinates outside 0..1 remain intact.
- Every material is decoded again directly from its original texture and effective CLUT. All PNG/BMP RGBA pixels and alpha are exact; 81 states bind 73 unique decoded textures.
- Draws4..9 (source vertex records36/41/46/51/56/61) contain the base road near Aya. Base-road Y is `[0.0017058637458831072,0.001712751341983676]` in canonical PC units. Near-horizontal triangle cross products point +Y; WORLD/reference inverse/positive unit conversion preserve handedness. Standard RH OpenGL view/projection can retain CCW front faces.
- Canonical Aya frame0 skin minimum is approximately zero after its source floor conversion, 0.001706..0.001713 PC units below the original base road. Same-capture Aya106 draw/3456 vertex GE skin minimum is `-0.011720483008245169`, 0.013426..0.013433 below the road. This preserves captured pose/quantization; it is not a proven anatomical foot contact and no additional vertical correction is applied.
- Captured camera position in scene PC space is `[-4.580237933894363,1.7645407272680271,0.724811439691848]`, above the road.

The manifest deliberately covers the agreed renderer contract: original texture times smooth vertex RGBA, alpha GREATER0, linear/repeat, standard depth test, and per-material blend/depth-write/cull. Original fog/stencil and PSP reverse-depth details remain in JSON; T3BSCNM1 does not reproduce them. Invisible, culled or off-camera level geometry and original collision/triggers are not recovered by this export.

## Reproduction

Run from the workspace root in PowerShell. Both scripts only read captures and write their own assets/reports; they do not start PPSSPP or the C runtime.

```powershell
& 'C:\Users\25105\AppData\Local\Programs\Python\Python313\python.exe' -X utf8 '.\work\psp_parse\tools\export_original_scene.py' --inventory '.\work\psp_parse\out\ORIGINAL_SCENE_INVENTORY_20261020.json' --canonical-aya-report '.\work\psp_parse\out\AYA_SOURCE_SKIN_EXPORT.json' --runtime-root '.\work\t3b_hd' --output-directory 'assets/scenes/original_street' --report '.\work\psp_parse\out\ORIGINAL_STREET_EXPORT.json'
& 'C:\Users\25105\AppData\Local\Programs\Python\Python313\python.exe' -X utf8 '.\work\psp_parse\tools\verify_original_scene.py' --export-report '.\work\psp_parse\out\ORIGINAL_STREET_EXPORT.json' --runtime-root '.\work\t3b_hd' --out '.\work\psp_parse\out\ORIGINAL_STREET_VERIFICATION.json'
```

Runtime rendering, gameplay collision and ray tests are a separate integration check, not covered by the Python asset verification.
