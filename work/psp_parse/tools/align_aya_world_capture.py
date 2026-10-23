"""Assign asynchronous GE dumps only to exact body/source/weapon matches."""
import argparse
import hashlib
import json
from pathlib import Path
from extract_ge_timeline import read_ppdmp
from export_aya_actual_weapon import matrix_draws


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for arg in ("manifest", "metadata", "out"):
        ap.add_argument("--"+arg, type=Path, required=True)
    a = ap.parse_args()
    m = json.loads(a.manifest.read_text(encoding="utf-8"))
    meta = json.loads(a.metadata.read_text(encoding="utf-8"))
    packets = {p["vertex_sha256"]: p for p in meta["packets"]}
    aligned = []
    for capture in m["unassignedWorldGEDumps"]:
        path = a.manifest.parent / Path(capture["file"]).name
        commands, push = read_ppdmp(str(path))
        draws = list(matrix_draws(commands, push))
        body = [d for d in draws if d["sha256"] in packets]
        if len(body) != 106 or len({d["sha256"] for d in body}) != 106:
            raise ValueError("GE dump does not contain complete Aya geometry")
        candidates = []
        for f in m["frames"]:
            w = f["worldSource"]
            guns = [d for d in draws if d["sha256"] == w["weaponIdentity"]["geometry_sha256"]]
            if len(guns) != 1 or guns[0]["world"] != w["weaponPayload"]:
                continue
            if any(d["world"] != w["bodyPayload"] for d in body):
                continue
            sources = {r["index"]: [x & 0xffffff for x in r["matrix"]] for r in f["records"]}
            checks, mismatch = 0, False
            for draw in body:
                packet = packets[draw["sha256"]]
                for slot in packet["active_palette_indices"]:
                    index = packet["palette_state"][str(slot)]
                    checks += 1
                    if draw["bones"][slot*12:slot*12+12] != sources[index]:
                        mismatch = True
            if not mismatch:
                candidates.append((f, checks))
        if len(candidates) != 1:
            raise ValueError(f"GE dump lacks a unique exact source/WORLD sample: {path}, candidates={len(candidates)}")
        f, checks = candidates[0]
        if f.get("dump"):
            raise ValueError("multiple GE dumps map to one sample")
        f["dump"] = {"file": str(path.resolve()), "bytes": path.stat().st_size}
        aligned.append({"dump": str(path.resolve()), "requested_after_sample": capture["requestedAtSample"],
                        "actual_source_sample": f["frame"], "exact_active_influences": checks,
                        "body_world_exact_components": 12, "weapon_world_exact_components": 12})
    if len(aligned) < 2:
        raise ValueError("capture needs at least two exact GE cross-checks")
    m["geAlignment"] = {"source_manifest": str(a.manifest.resolve()),
                        "source_sha256": hashlib.sha256(a.manifest.read_bytes()).hexdigest(),
                        "method": "exact original packet palette/source plus body and weapon WORLD", "matches": aligned}
    a.out.write_text(json.dumps(m, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(aligned))


if __name__ == "__main__":
    main()
