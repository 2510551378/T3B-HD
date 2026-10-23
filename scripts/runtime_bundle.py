"""Create, verify and install the private runtime ZIP; never uploads assets."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tempfile
import zipfile

from asset_manifest import ASSET_ROOTS, ROOT, digest, reject_link

SCHEMA = "t3b-private-runtime-bundle/v1"
MANIFEST_NAME = "bundle_manifest.json"
EXTRAS = {
    "work/t3b_hd/t3b_hd.exe", "work/t3b_hd/SDL2.dll",
    "work/t3b_unreal/Binaries/Win64/UnrealEditor-T3BRemake.dll",
    "work/t3b_unreal/Binaries/Win64/UnrealEditor.modules",
    "build/runtime_bundle/SDL2-LICENSE.txt",
    "build/runtime_bundle/runtime_asset_manifest.json",
    "build/runtime_bundle/README.txt",
}
MAX_BYTES = 512 * 1024 * 1024


def safe_name(value: str) -> str:
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or "\\" in value or ":" in value
            or any(part in ("", ".", "..") for part in value.split("/"))
            or any(part.endswith((".", " ")) for part in path.parts)):
        raise ValueError(f"Unsafe bundle path: {value}")
    # These names alias device objects on Windows, including names with extensions.
    devices = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
               *(f"LPT{i}" for i in range(1, 10))}
    if any(part.split(".")[0].upper() in devices for part in path.parts):
        raise ValueError(f"Reserved Windows path: {value}")
    if not (value in EXTRAS or any(value.startswith(root + "/") for root in ASSET_ROOTS)):
        raise ValueError(f"Unexpected runtime destination: {value}")
    return value


def destination(root: Path, relative: str) -> Path:
    safe_name(relative)
    current = root
    reject_link(current)
    for part in PurePosixPath(relative).parts:
        current /= part
        if current.exists() or current.is_symlink():
            reject_link(current)
    return current


def encoded(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def pack(args) -> None:
    output = args.output.resolve()
    sidecar = output.with_suffix(output.suffix + ".sha256")
    if output.exists() or sidecar.exists():
        raise ValueError("Output already exists; choose a new versioned bundle name")
    asset_manifest = ROOT / "docs/runtime_asset_manifest.json"
    assets = json.loads(asset_manifest.read_text(encoding="utf-8"))
    sources = {}
    for row in assets["files"]:
        name = safe_name(row["path"])
        source = destination(ROOT, name)
        if source.stat().st_size != row["bytes"] or digest(source) != row["sha256"]:
            raise ValueError(f"Asset differs from committed identity: {name}")
        sources[name] = source
    sources["work/t3b_hd/t3b_hd.exe"] = ROOT / "work/t3b_hd/t3b_hd.exe"
    sources["work/t3b_hd/SDL2.dll"] = ROOT / "work/t3b_hd/SDL2.dll"
    sources["build/runtime_bundle/SDL2-LICENSE.txt"] = args.sdl_license.resolve(strict=True)
    engine = json.loads((args.engine_root / "Engine/Build/Build.version").read_text(encoding="utf-8"))
    engine_modules = json.loads((args.engine_root / "Engine/Binaries/Win64/UnrealEditor.modules").read_text(encoding="utf-8"))
    binary_root = args.ue_binary_root.resolve(strict=True)
    module = json.loads((binary_root / "Binaries/Win64/UnrealEditor.modules").read_text(encoding="utf-8"))
    if module["BuildId"] != engine_modules["BuildId"]:
        raise ValueError("Precompiled project module does not match engine BuildId")
    # Verify that the reusable DLL was built beside exactly the delivered sources.
    required_sources = {}
    project = ROOT / "work/t3b_unreal"
    for directory in ("Source", "Shaders"):
        for path in sorted((project / directory).rglob("*")):
            if path.is_file():
                reject_link(path)
                relative = path.relative_to(project)
                if digest(path) != digest(binary_root / relative):
                    raise ValueError(f"Build-copy source differs: {relative}")
                required_sources[path.relative_to(ROOT).as_posix()] = digest(path)
    for name in ("UnrealEditor-T3BRemake.dll", "UnrealEditor.modules"):
        sources[f"work/t3b_unreal/Binaries/Win64/{name}"] = binary_root / "Binaries/Win64" / name
    payloads = {
        "build/runtime_bundle/runtime_asset_manifest.json": asset_manifest.read_bytes(),
        "build/runtime_bundle/README.txt": (ROOT / "docs/RUNTIME_BUNDLE_README.txt").read_bytes(),
    }
    entries = []
    for name, source in sources.items():
        reject_link(source)
        entries.append({"path": name, "bytes": source.stat().st_size, "sha256": digest(source)})
    for name, data in payloads.items():
        entries.append({"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    entries.sort(key=lambda row: row["path"])
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    manifest = {"schema": SCHEMA, "source_commit": commit,
                "asset_manifest_sha256": digest(asset_manifest),
                "engine": {key: engine[key] for key in ("MajorVersion", "MinorVersion", "PatchVersion", "Changelist")},
                "engine_build_id": module["BuildId"], "required_module_sources": required_sources,
                "file_count": len(entries), "total_bytes": sum(row["bytes"] for row in entries),
                "files": entries, "scope": "Private runtime handoff; no ISO, saves, engine, SDK or raw captures"}
    if manifest["total_bytes"] > MAX_BYTES:
        raise ValueError("Runtime bundle exceeds expected size bound")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="t3b-pack-", dir=output.parent) as temporary:
        staged = Path(temporary) / "bundle.zip"
        with zipfile.ZipFile(staged, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr(MANIFEST_NAME, encoded(manifest))
            for row in entries:
                name = row["path"]
                if name in payloads:
                    archive.writestr(name, payloads[name])
                else:
                    archive.write(sources[name], name)
        staged.rename(output)
    checksum = digest(output)
    sidecar.write_text(f"{checksum}  {output.name}\n", encoding="ascii")
    print(json.dumps({"bundle": str(output), "sha256": checksum,
                      "compressed_bytes": output.stat().st_size, "files": len(entries)}, indent=2))


def read_bundle(archive: zipfile.ZipFile):
    infos = archive.infolist()
    names = [entry.filename for entry in infos]
    if len(names) != len(set(name.casefold() for name in names)):
        raise ValueError("Duplicate/case-alias ZIP entries")
    if sum(entry.file_size for entry in infos) > MAX_BYTES or len(infos) > 2000:
        raise ValueError("Unexpected ZIP size/count")
    if MANIFEST_NAME not in names or archive.getinfo(MANIFEST_NAME).file_size > 1024 * 1024:
        raise ValueError("Missing/oversized bundle manifest")
    manifest = json.loads(archive.read(MANIFEST_NAME))
    if manifest["schema"] != SCHEMA:
        raise ValueError("Unexpected bundle schema")
    rows = manifest["files"]
    expected = {safe_name(row["path"]) for row in rows}
    if (len(expected) != len(rows) or manifest["file_count"] != len(rows)
            or manifest["total_bytes"] != sum(row["bytes"] for row in rows)
            or set(names) != expected | {MANIFEST_NAME}):
        raise ValueError("ZIP/manifest inventory mismatch")
    for row in rows:
        info = archive.getinfo(row["path"])
        if info.file_size != row["bytes"] or stat.S_ISLNK(info.external_attr >> 16):
            raise ValueError(f"Invalid ZIP member: {row['path']}")
        with archive.open(info) as stream:
            value = hashlib.sha256()
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                value.update(block)
        if value.hexdigest() != row["sha256"]:
            raise ValueError(f"Payload hash mismatch: {row['path']}")
    return manifest


def inspect_or_install(args) -> None:
    bundle = args.bundle.resolve(strict=True)
    if args.sha256 and digest(bundle) != args.sha256.lower():
        raise ValueError("Outer ZIP SHA-256 mismatch")
    with zipfile.ZipFile(bundle) as archive:
        manifest = read_bundle(archive)  # Verify every byte before changing the clone.
        if args.mode == "verify":
            print(f"bundle_verification=passed; files={manifest['file_count']}")
            return
        project_root = args.project_root.resolve(strict=True)
        if not (project_root / "work/t3b_unreal/T3BRemake.uproject").is_file():
            raise ValueError("Destination must be a cloned T3B-HD repository")
        local_manifest = project_root / "docs/runtime_asset_manifest.json"
        if digest(local_manifest) != manifest["asset_manifest_sha256"]:
            raise ValueError("Clone uses a different asset manifest; use the matching source revision")
        plans = []
        conflicts = []
        for row in manifest["files"]:
            target = destination(project_root, row["path"])
            identical = target.is_file() and target.stat().st_size == row["bytes"] and digest(target) == row["sha256"]
            if target.exists() and not identical:
                conflicts.append(row["path"])
            if not identical:
                plans.append((row, target))
        if conflicts and not args.replace_existing:
            raise ValueError("Changed local files would be replaced; back up and use --replace-existing:\n" + "\n".join(conflicts[:20]))
        # Stage decompression first; existing identical assets are left untouched.
        with tempfile.TemporaryDirectory(prefix="t3b-install-", dir=project_root) as temporary:
            staging = Path(temporary)
            for index, (row, _) in enumerate(plans):
                with archive.open(row["path"]) as source, (staging / str(index)).open("wb") as target:
                    shutil.copyfileobj(source, target)
            for index, (row, target) in enumerate(plans):
                destination(project_root, row["path"])
                target.parent.mkdir(parents=True, exist_ok=True)
                (staging / str(index)).replace(target)
        installed = destination(project_root, "build/runtime_bundle/README.txt").parent / "installed_manifest.json"
        if installed.exists() or installed.is_symlink():
            reject_link(installed)
        installed.write_bytes(encoded(manifest))
    print(f"bundle_installation=passed; files={manifest['file_count']}; written={len(plans)}; root={project_root}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    create = commands.add_parser("pack")
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--ue-binary-root", type=Path, required=True)
    create.add_argument("--engine-root", type=Path, required=True)
    create.add_argument("--sdl-license", type=Path, required=True)
    for mode in ("verify", "install"):
        command = commands.add_parser(mode)
        command.add_argument("bundle", type=Path)
        command.add_argument("--sha256")
        if mode == "install":
            command.add_argument("--project-root", type=Path, default=ROOT)
            command.add_argument("--replace-existing", action="store_true")
    args = parser.parse_args()
    if args.mode == "pack":
        pack(args)
    else:
        inspect_or_install(args)


if __name__ == "__main__":
    main()
