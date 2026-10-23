"""Bind WORLD uploader inputs by exact original draw geometry and payloads."""
import argparse
import hashlib
import json
from pathlib import Path
from extract_ge_timeline import read_ppdmp
from export_aya_actual_weapon import matrix_draws

WEAPON = "168578abca4c4f5d22d5994ebced6b93a25d5167428bfd47f1a1150a8d42e65a"
SELECT = [0, 1, 2, 4, 5, 6, 8, 9, 10, 12, 13, 14]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trace", type=Path, required=True)
    ap.add_argument("--metadata", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    trace = json.loads(a.trace.read_text(encoding="utf-8"))
    meta = json.loads(a.metadata.read_text(encoding="utf-8"))
    commands, push = read_ppdmp(str(a.trace.parent / Path(trace["dumps"][0]["file"]).name))
    draws = list(matrix_draws(commands, push))
    signatures = {p["vertex_sha256"] for p in meta["packets"]}
    body = [d for d in draws if d["sha256"] in signatures]
    gun = [d for d in draws if d["sha256"] == WEAPON]
    if len(body) != 106 or len({d["sha256"] for d in body}) != 106 or len(gun) != 1:
        raise ValueError("expected complete original Aya and exactly one original rifle")
    if any(d["world"] != body[0]["world"] for d in body):
        raise ValueError("Aya WORLD varies within its mesh packets")
    matches = {}
    for label, draw in (("aya", body[0]), ("weapon", gun[0])):
        rows = []
        for row in trace["worlds"]:
            if row["kind"] != "writer":
                continue
            packed = [(row["sourceMatrix"][i] >> 8) & 0xffffff for i in SELECT]
            if packed == draw["world"]:
                if row["ra"] != 0x08bfff8c or row["savedCallerRa"]-8 != 0x08b526b4:
                    raise ValueError("matching matrix has an unverified caller contract")
                if row["matrixPointer"] != row["gpr"][17]+0x220:
                    raise ValueError("WORLD input is not the observed object's +220 matrix")
                rows.append({"trace_index": row["index"], "ticks": row["ticks"], "object": row["gpr"][17],
                             "matrix_pointer": row["matrixPointer"], "renderer_list_cursor_s0": row["gpr"][16],
                             "caller": row["savedCallerRa"]-8, "float32_words": row["sourceMatrix"]})
        if not rows or len({r["object"] for r in rows}) != 1:
            raise ValueError(f"{label} WORLD lacks a unique runtime object")
        matches[label] = rows
    aya_object = matches["aya"][0]["object"]
    if not any(s["object"] == aya_object for s in trace["samples"]):
        raise ValueError("WORLD object not tied to the observed 44-bone Aya source object")
    report = {"schema": "aya-weapon-world-source-binding/v1", "passed": True,
              "aya_object": aya_object, "weapon_object": matches["weapon"][0]["object"],
              "weapon_matrix_pointer": matches["weapon"][0]["matrix_pointer"],
              "world_uploader": 0x08c01088, "world_selector": 2, "wrapper_ra": 0x08bfff8c,
              "caller": 0x08b526b4, "object_matrix_offset": 0x220,
              "weapon_geometry_sha256": WEAPON, "exact_matches": matches,
              "inputs": {"trace": {"path": str(a.trace.resolve()), "sha256": hashlib.sha256(a.trace.read_bytes()).hexdigest()},
                         "metadata": {"path": str(a.metadata.resolve()), "sha256": hashlib.sha256(a.metadata.read_bytes()).hexdigest()}},
              "limits": ["Guest pointers are specific to this backup/runtime allocation and must be revalidated in each capture.",
                         "Exact WORLD attribution does not establish anatomical socket or muzzle metadata."]}
    a.out.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("passed", "aya_object", "weapon_object", "weapon_matrix_pointer", "caller")}))


if __name__ == "__main__":
    main()
