"""Independently audit staged assets and their original resource bindings."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from PIL import Image


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(runtime, project):
    data_root = project/"Content/SourceData"
    manifest_file = data_root/"manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if manifest["schema"] != "t3b-ue-source-bundle/v1":
        raise ValueError("unknown UE bundle schema")
    binaries = [(manifest["scene"]["binary"], "assets/scenes/original_street/original_street.bin"),
                ("models/aya_fire.bin", "assets/models/clips/aya_fire_reverse_capture.bin"),
                ("models/weapon_fire.bin", "assets/models/clips/weapon_fire_reverse_capture.bin"),
                ("models/twisted.bin", "assets/models/original_actor_source.bin")]
    for target, source in binaries:
        if (data_root/target).read_bytes() != (runtime/source).read_bytes():
            raise ValueError(f"staged original binary changed: {target}")
    resources = {item["file"]: item for item in manifest["textures"]}
    if len(resources) != 76:
        raise ValueError("expected73 street and3 actor RGBA resources")

    def pixels(material, original):
        resource = resources[material["texture"]]
        if resource["asset"] != material["texture_asset"]:
            raise ValueError("material does not bind its declared texture asset")
        with Image.open(runtime/original) as source, Image.open(data_root/resource["file"]) as output:
            if source.size != output.size or source.convert("RGBA").tobytes() != output.convert("RGBA").tobytes():
                raise ValueError(f"texture/alpha changed: {original}")

    lines = (runtime/"assets/scenes/original_street/original_street_materials.txt").read_text(encoding="utf-8").splitlines()[1:]
    if len(lines) != len(manifest["scene"]["materials"]) or len(lines) != 81:
        raise ValueError("street material coverage differs")
    unsupported = []
    for material, line in zip(manifest["scene"]["materials"], lines):
        path, blend, depth, cull = line.split()
        if [material[key] for key in ("blend", "depth_write", "cull")] != [int(blend), int(depth), int(cull)]:
            raise ValueError("source render state was silently changed")
        pixels(material, path)
        if int(blend) and int(depth):
            unsupported.append(material["asset"])
    expected_actors = {"Aya": (44, 106, 3456, "assets/materials/original_aya/aya_original_materials.txt"),
                       "Weapon": (1, 1, 243, "assets/materials/original_weapon/aya_original_weapon_materials.txt"),
                       "Twisted": (11, 28, 1800, "assets/materials/original_actor/original_actor_materials.txt")}
    times = {}
    if {a["name"] for a in manifest["actors"]} != set(expected_actors) or len(manifest["actors"]) != 3:
        raise ValueError("unexpected source actors")
    for actor in manifest["actors"]:
        payload = (data_root/actor["binary"]).read_bytes()
        h = struct.unpack_from("<8s8I4f", payload)
        expected = expected_actors[actor["name"]]
        if h[2:5] != expected[:3] or h[5] != 60 or actor["samples"] != 60 or actor["playback"] != "clamp":
            raise ValueError("source actor topology/timeline coverage changed")
        start = 56+h[2]*4+h[3]*16+h[4]*100
        times[actor["name"]] = payload[start:start+h[5]*4]
        original_materials = (runtime/expected[3]).read_text(encoding="utf-8").splitlines()[1:]
        if len(original_materials) != len(actor["materials"]):
            raise ValueError("actor material coverage changed")
        for item, row in zip(actor["materials"], original_materials):
            values = row.split()
            pixels(item, values[1])
            if [item[k] for k in ("su", "sv", "ou", "ov")] != list(map(float, values[4:8])) or [item[k] for k in ("wrap_s", "wrap_t")] != list(map(int, values[8:10])):
                raise ValueError("actor UV transform/sampler changed")
            if item["blend"] != bool(h[7] & 4) or item["rgb_scale"] != (2 if h[7] & 2 else 1):
                raise ValueError("actor source flags changed")
            if item["blend"] and item["depth_write"]:
                unsupported.append(item["asset"])
    if times["Aya"] != times["Weapon"]:
        raise ValueError("Aya and weapon no longer share stored times")
    if sorted(unsupported) != sorted(item["material"] for item in manifest["unsupported_render_states"]):
        raise ValueError("unsupported original render states were hidden")
    for entry in manifest["inputs"].values():
        if digest(Path(entry["path"])) != entry["sha256"]:
            raise ValueError("source identity changed after staging")
    for relative, entry in manifest["staged_outputs"].items():
        if digest(data_root/relative) != entry["sha256"]:
            raise ValueError("staged artifact identity changed")
    return {"schema": "t3b-ue-source-bundle-independent-verification/v1", "passed": True,
            "manifest_sha256": digest(manifest_file), "binary_copies_identical": 4,
            "RGBA_resources": len(resources), "material_bindings_checked": 84,
            "unsupported_material_states_preserved": len(unsupported),
            "source_render_states_equivalent_in_UE": False, "unreal_editor_executed": False,
            "scope": "exact source staging, textures, samplers, flags and paired timeline; no engine runtime acceptance"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, default=Path(__file__).resolve().parents[2]/"t3b_hd")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    report = check(args.runtime_root, args.project_root)
    output = args.project_root/"Validation/source_bundle_independent_verification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(report))
