from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[2] / "t3b_unreal/Content/SourceData"
OUT = Path(__file__).resolve().parents[2] / "t3b_unreal/Validation/source_bundle_manifest_v1.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_relative(value: str) -> Path:
    path = Path(value.replace("\\", "/"))
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError(f"unsafe source-bundle path: {value}")
    return path


def main() -> None:
    manifest_path = ROOT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == "t3b-ue-source-bundle/v1"
    report = {
        "schema": "t3b-ue-source-bundle-manifest/v1",
        "status": "passed",
        "manifest_sha256": sha(manifest_path),
        "staged_outputs": [],
        "textures": [],
        "actors": [],
        "scene": {},
        "provenance_inputs": len(manifest.get("inputs", [])),
    }

    for value in manifest["staged_outputs"]:
        rel = safe_relative(value)
        path = ROOT / rel
        if not path.is_file():
            raise ValueError(f"missing staged output: {value}")
        report["staged_outputs"].append({"file": value, "bytes": path.stat().st_size, "sha256": sha(path)})

    for item in manifest["textures"]:
        rel = safe_relative(item["file"])
        path = ROOT / rel
        if not path.is_file():
            raise ValueError(f"missing texture: {item['file']}")
        with Image.open(path) as image:
            rgba = image.convert("RGBA")
            width, height = rgba.size
            rgba_hash = hashlib.sha256(rgba.tobytes()).hexdigest()
        if [width, height] != [item["width"], item["height"]]:
            raise ValueError(f"texture dimensions differ: {item['file']}")
        if item["container"]["sha256"] != sha(path) or item["rgba_sha256"] != rgba_hash:
            raise ValueError(f"texture hash differs: {item['file']}")
        report["textures"].append({"file": item["file"], "width": width, "height": height, "png_sha256": sha(path), "rgba_sha256": rgba_hash})

    scene_rel = safe_relative(manifest["scene"]["binary"])
    scene_path = ROOT / scene_rel
    scene = scene_path.read_bytes()
    magic, version, draws, vertices, materials = struct.unpack_from("<8s4I", scene, 0)
    if magic != b"T3BSCN1\0" or version != 1:
        raise ValueError("scene binary header differs")
    expected = {"draws": draws, "vertices": vertices, "materials": materials}
    if expected != {"draws": manifest["scene"]["draws"], "vertices": manifest["scene"]["vertices"], "materials": len(manifest["scene"]["materials"])}:
        raise ValueError("scene manifest counts differ")
    report["scene"] = {"file": manifest["scene"]["binary"], **expected, "bytes": len(scene), "sha256": sha(scene_path)}

    for actor in manifest["actors"]:
        rel = safe_relative(actor["binary"])
        path = ROOT / rel
        data = path.read_bytes()
        magic, version, bones, packets, vertices, samples, materials, flags = struct.unpack_from("<8s7I", data, 0)
        if magic != b"T3BSKN2\0" or version != 2:
            raise ValueError(f"actor binary header differs: {actor['name']}")
        actual = {"bones": bones, "packets": packets, "vertices": vertices, "samples": samples, "materials": materials, "flags": flags}
        expected = {"bones": actor["bones"], "packets": actor["packets"], "vertices": actor["vertices"], "samples": actor["samples"], "materials": len(actor["materials"]), "flags": actor["flags"]}
        if actual != expected:
            raise ValueError(f"actor manifest counts differ: {actor['name']}")
        report["actors"].append({"name": actor["name"], "file": actor["binary"], **actual, "bytes": len(data), "sha256": sha(path)})

    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
