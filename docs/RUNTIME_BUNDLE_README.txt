T3B-HD M1 v4 runtime asset bundle

1. Clone/update https://github.com/2510551378/T3B-HD into C:\src\T3B-HD.
2. Download the ZIP and .sha256 from this versioned Release after publication:
   https://github.com/2510551378/T3B-HD/releases/tag/runtime-assets-20261023-v4
   Do not add binary assets to Git history.
3. From the clone root, install with the checksum printed in the sidecar:
   python -X utf8 scripts/runtime_bundle.py install C:\Transfer\T3B-HD-runtime-assets-20261023-v4.zip --sha256 <SHA256>
4. Verify the original asset identities:
   python -X utf8 scripts/asset_manifest.py verify
5. Install Unreal Engine 5.8.4 (CL 58902052, module BuildId 55116800).
   powershell -ExecutionPolicy Bypass -File scripts/run_unreal.ps1 -Game
   Add -ReplayOnly for the original-source Spectator/probe mode.
   A different engine build or changed module sources require -Build and MSVC/SDK.
6. The C/SDL2 comparison prototype remains available without a compiler:
   powershell -ExecutionPolicy Bypass -File scripts/run_m1.ps1
   Add -HDSampling for optional 4x atlas sampling.

UE M1 controls:
WASD move; Shift run; Mouse view; RMB / Tab lock; LMB continuous fire;
R reload; E Overdive camera; Backspace restart; Esc release mouse;
left-click recaptures the mouse. The reticle projects the actual barrel ray.
Mouse pitch adjusts the view only, preserving the recovered source pose pitch.

The ZIP contains model/texture data, saved UE Content, the C prototype executable,
SDL2.dll plus its license, and our precompiled UE project module. It does not
contain Unreal Engine, SDKs, original ISO, saves, RAM/GE dumps or shader caches.
The first UE launch may compile shaders. It requires an Unreal Editor host;
it is not a cooked standalone game or a completed HD remake.

Install checks every member before writing and skips identical files. Unedited
files from a previously installed bundle can upgrade automatically. User-edited
files are protected; back them up before using --replace-existing explicitly.

M1 v4 adds capsule/scene collision, a shoulder camera, lock-on source-muzzle
shooting with scene/posed-target nearest-hit selection, enemy chase/melee,
health/damage/hit/death feedback, reload and an Overdive camera round trip.
Collision and combat rules are PC adapters. Overdive is not the original host
transfer system. Aya and weapon share a 120 ms loop seam adapter; the original
full animation/event scheduler remains unrecovered. See docs/UE_M1_V4.md.
