"""Snapshot or verify local runtime assets without copying or publishing them."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat

ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOTS = (
    "work/t3b_hd/assets",
    "work/t3b_unreal/Content/SourceData",
    "work/t3b_unreal/Content/T3B",
)
MANIFEST = ROOT / "docs/runtime_asset_manifest.json"


def reject_link(path: Path) -> None:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError(f"Symlink/reparse point is not an asset file: {path}")


def checked_path(relative: str) -> Path:
    posix = PurePosixPath(relative)
    if posix.is_absolute() or ".." in posix.parts or "\\" in relative or ":" in relative:
        raise ValueError(f"Invalid relative asset path: {relative}")
    if not any(relative.startswith(root + "/") for root in ASSET_ROOTS):
        raise ValueError(f"Path outside asset roots: {relative}")
    current = ROOT
    for part in posix.parts:
        current /= part
        reject_link(current)
    if not current.is_file():
        raise ValueError(f"Not an asset file: {relative}")
    return current


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else _digest(stream)


def _digest(stream) -> str:
    value = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        value.update(block)
    return value.hexdigest()


def walk(path: Path):
    reject_link(path)
    for entry in sorted(path.iterdir()):
        reject_link(entry)
        if entry.is_dir():
            yield from walk(entry)
        elif entry.is_file():
            yield entry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("snapshot", "verify"))
    args = parser.parse_args()
    if args.mode == "snapshot":
        files = []
        for relative in ASSET_ROOTS:
            path = ROOT
            for part in PurePosixPath(relative).parts:
                path /= part
                reject_link(path)
            for asset in walk(path):
                files.append({"path": asset.relative_to(ROOT).as_posix(),
                              "bytes": asset.stat().st_size, "sha256": digest(asset)})
        document = {"schema": "t3b-private-runtime-asset-manifest/v1",
                    "scope": "Local runtime handoff only; no asset payloads or download URLs",
                    "roots": list(ASSET_ROOTS), "file_count": len(files),
                    "total_bytes": sum(row["bytes"] for row in files), "files": files}
        MANIFEST.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"snapshot_files={len(files)}; manifest={MANIFEST.relative_to(ROOT)}")
        return
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if data["schema"] != "t3b-private-runtime-asset-manifest/v1" or data["roots"] != list(ASSET_ROOTS):
        raise ValueError("Unexpected asset manifest contract")
    files = data["files"]
    if (data["file_count"] != len(files) or len({r["path"].casefold() for r in files}) != len(files)
            or data["total_bytes"] != sum(r["bytes"] for r in files)):
        raise ValueError("Invalid asset manifest counts or duplicate paths")
    errors = []
    for row in files:
        try:
            path = checked_path(row["path"])
            if path.stat().st_size != row["bytes"] or digest(path) != row["sha256"]:
                errors.append(f"identity mismatch: {row['path']}")
        except (OSError, ValueError) as error:
            errors.append(f"{row['path']}: {error}")
    if errors:
        print("\n".join(errors[:20]))
        raise SystemExit(f"asset_verification=failed; errors={len(errors)}")
    print(f"asset_verification=passed; files={len(files)}; bytes={data['total_bytes']}")


if __name__ == "__main__":
    main()
