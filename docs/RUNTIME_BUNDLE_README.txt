T3B-HD private runtime bundle

1. Clone/update https://github.com/2510551378/T3B-HD into C:\src\T3B-HD.
2. Transfer the ZIP and its .sha256 sidecar privately. Do not commit the ZIP.
3. From the clone root, install with the checksum printed in the sidecar:
   python -X utf8 scripts/runtime_bundle.py install C:\Transfer\T3B-HD-runtime-assets-20261023-v2.zip --sha256 <SHA256>
4. Verify the original asset identities:
   python -X utf8 scripts/asset_manifest.py verify
5. Run the Windows C/SDL2 prototype (no compiler required):
   powershell -ExecutionPolicy Bypass -File scripts/run_m1.ps1
   Add -HDSampling for optional 4x atlas sampling.
6. Install Unreal Engine 5.8.4 (CL 58902052, module BuildId 55116800).
   powershell -ExecutionPolicy Bypass -File scripts/run_unreal.ps1
   Add -Game to open the original-source replay directly.
   A different engine build or changed module sources require -Build and MSVC/SDK.

The ZIP contains model/texture data, saved UE Content, the C prototype executable,
SDL2.dll plus its license, and our precompiled UE project module. It does not
contain Unreal Engine, SDKs, original ISO, saves, RAM/GE dumps or shader caches.
The first UE launch may compile shaders. This is a development source replay,
not a cooked standalone Unreal game or a completed HD remake.

Install checks every member before writing, skips identical files, and refuses
to replace differing local assets unless --replace-existing is explicitly used.
Back up edited assets before replacing them. See docs/ASSET_HANDOFF.md in Git.
