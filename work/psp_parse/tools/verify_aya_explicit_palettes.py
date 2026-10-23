"""Cross-check metadata palettes against sequential PRIM-time GE state."""
import argparse
import hashlib
import json
import struct
from collections import Counter, defaultdict
from pathlib import Path
from extract_ge_timeline import read_ppdmp
from replay_ge_draws import iter_ge_draws


def verify(metadata_path, manifests):
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    by_hash = defaultdict(list)
    for packet in metadata["packets"]:
        by_hash[packet["vertex_sha256"]].append(packet)
    counters = Counter()
    rows = []
    sources_seen, packets_seen = set(), set()
    for manifest_path in manifests:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for frame in manifest["frames"]:
            path = manifest_path.parent / Path(frame["dump"]["file"]).name
            commands, push = read_ppdmp(str(path))
            source = {r["index"]: [w & 0xffffff for w in r["matrix"]] for r in frame["records"]}
            for draw in iter_ge_draws(commands, push):
                vt = draw["vtype"]
                if vt is None or not (vt >> 9) & 3:
                    continue
                pointer, size = draw["pointer"], draw["size"]
                digest = hashlib.sha256(struct.pack("<I", vt) + push[pointer:pointer + size]).hexdigest()
                matches = by_hash.get(digest, [])
                if not matches:
                    counters["other_geometry_draws"] += 1
                    continue
                counters["exact_geometry_draws"] += 1
                if len(matches) != 1:
                    counters["ambiguous_packet_draws"] += 1
                    continue
                packet = matches[0]
                packets_seen.add(packet["draw"])
                if draw["count"] != packet["vertex_count"] or draw["primitive"] != 3:
                    counters["primitive_count_mismatches"] += 1
                for slot in packet["active_palette_indices"]:
                    expected = packet["palette_state"][str(slot)]
                    payload = draw["palette_payloads"].get(slot)
                    candidates = [i for i, words in source.items() if words == payload]
                    status = "exact_expected_source" if expected in candidates else "different_source" if candidates else "no_same_pass_matrix_match"
                    counters[status] += 1
                    if status == "exact_expected_source":
                        sources_seen.add(expected)
                    rows.append({"capture": manifest_path.parent.name, "frame": frame["frame"],
                                 "ge_vertex_record": draw["draw"], "packet": packet["draw"], "palette_index": slot,
                                 "expected_source": expected, "exact_source_candidates": candidates, "status": status})
    missing_packets = sorted(set(p["draw"] for p in metadata["packets"]) - packets_seen)
    missing_sources = sorted(set(metadata["summary"]["active_source_indices"]) - sources_seen)
    return {"schema": "aya-explicit-palette-verification/v1", "metadata": str(metadata_path.resolve()),
            "manifests": [str(p.resolve()) for p in manifests], "counts": dict(counters),
            "verified_source_indices": sorted(sources_seen), "verified_packet_indices": sorted(packets_seen),
            "missing_packet_indices": missing_packets, "missing_source_indices": missing_sources,
            "limitations": ["Byte equality identifies geometry and checks the explicit source index; captures may span different simulation updates.",
                            "Only explicit GE writes are replayed; unknown INIT matrix state is not invented.",
                            "Original legacy reports that apply an entire following REGISTERS block to one draw have a state-ordering error."],
            "observations": rows}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("metadata", type=Path)
    ap.add_argument("manifests", nargs="+", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    result = verify(a.metadata, a.manifests)
    a.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {k: v for k, v in result.items() if k != "observations"}
    a.out.with_suffix(".md").write_text("# Aya 显式 palette 与 GE PRIM 时序交叉验证\n\n```json\n" + json.dumps(summary, ensure_ascii=False, indent=2) + "\n```\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    failures = ("different_source", "primitive_count_mismatches", "no_same_pass_matrix_match", "ambiguous_packet_draws")
    if any(result["counts"].get(k) for k in failures) or result["missing_packet_indices"] or result["missing_source_indices"]:
        raise SystemExit("GE/metadata conflict or incomplete verification; see report")


if __name__ == "__main__":
    main()
