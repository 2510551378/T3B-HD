"""Recover hierarchy and explicit draw palettes from ULJM05798 guest memory.

No anatomical naming, bind-pose convention, or world-unit scale is guessed.
Inputs are preserved. Invalid bounds, parent cycles, and undefined active
palette slots stop the export instead of silently producing a plausible rig.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import struct
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Memory:
    def __init__(self, segments):
        self.segments = segments

    def read(self, address, size):
        for base, data in self.segments:
            offset = address - base
            if offset >= 0 and offset + size <= len(data):
                return data[offset:offset + size]
        raise ValueError(f"unmapped range {address:#x}+{size:#x}")

    def unpack(self, fmt, address):
        return struct.unpack(fmt, self.read(address, struct.calcsize(fmt)))


def packed_words(words):
    return struct.pack(f"<{len(words)}I", *words)


def vertex_layout(vtype):
    # GE interleaved vertex fields, in order: weights, UV, color, normal, position.
    fields = [("weights", (vtype >> 9) & 3, (0, 1, 2, 4), (0, 1, 2, 4), ((vtype >> 14) & 7) + 1),
              ("uv", vtype & 3, (0, 1, 2, 4), (0, 2, 4, 8), 1),
              ("color", (vtype >> 2) & 7, (0, 0, 0, 0, 2, 2, 2, 4), (0, 0, 0, 0, 2, 2, 2, 4), 1),
              ("normal", (vtype >> 5) & 3, (0, 1, 2, 4), (0, 3, 6, 12), 1),
              ("position", (vtype >> 7) & 3, (0, 1, 2, 4), (0, 3, 6, 12), 1)]
    offset = 0
    alignment = 1
    result = {}
    if (vtype >> 11) & 3 or (vtype >> 18) & 7:
        raise ValueError(f"indexed/morphed vertex format unsupported: {vtype:#x}")
    for name, kind, aligns, sizes, count in fields:
        if not kind:
            continue
        a, size = aligns[kind], sizes[kind] * count
        if not a or not size:
            raise ValueError(f"unsupported {name} kind {kind}")
        offset = (offset + a - 1) // a * a
        result[name] = (offset, kind)
        offset += size
        alignment = max(alignment, a)
    return (offset + alignment - 1) // alignment * alignment, result


def recover(mem, metadata, source_base):
    count = mem.unpack("<h", metadata + 6)[0]
    if count != 44:
        raise ValueError(f"expected selected 44-bone object, got {count}")
    descriptors = mem.unpack("<I", metadata + 0x18)[0]
    table = mem.unpack("<I", metadata + 0x34)[0]
    descriptor_bytes = mem.read(descriptors, count * 16)
    bones = []
    for i in range(count):
        raw = struct.unpack_from("<8h", descriptor_bytes, i * 16)
        parent = raw[7]
        if not -1 <= parent < count or parent == i:
            raise ValueError(f"bone {i}: invalid parent {parent}")
        address = source_base + i * 0x130
        actual = mem.unpack("<I", address + 0x124)[0]
        expected = source_base + parent * 0x130 if parent >= 0 else 0
        if actual != expected:
            raise ValueError(f"bone {i}: runtime parent {actual:#x} != descriptor parent {expected:#x}")
        bones.append({"index": i, "parent": parent, "descriptor_address": descriptors + i * 16,
                      "descriptor_signed16": list(raw), "record_address": address,
                      "runtime_parent_pointer": actual, "children": [],
                      "matrix_40_words": list(mem.unpack("<16I", address + 0x40)),
                      "matrix_80_words": list(mem.unpack("<16I", address + 0x80))})
    for bone in bones:
        seen = {bone["index"]}
        p = bone["parent"]
        while p >= 0:
            if p in seen:
                raise ValueError("parent cycle")
            seen.add(p)
            p = bones[p]["parent"]
        if bone["parent"] >= 0:
            bones[bone["parent"]]["children"].append(bone["index"])

    draw_count = mem.unpack("<h", table)[0]
    if not 0 < draw_count < 2000:
        raise ValueError(f"invalid draw count {draw_count}")
    cursor = table + 4
    palette = {}
    packets = []
    active_sources = set()
    declared_sources = set()
    weight_sum_range = [math.inf, -math.inf]
    for draw in range(draw_count):
        vertex_count, transform_index, flag4, update_count, stride_halfwords, flag7, vtype = mem.unpack("<Hh4BI", cursor)
        if update_count > 8 or not vertex_count or vertex_count > 65535:
            raise ValueError(f"invalid packet {draw}")
        stride, layout = vertex_layout(vtype)
        if stride != stride_halfwords * 2:
            raise ValueError(f"draw {draw}: GE stride {stride} != packet stride {stride_halfwords * 2}")
        p = cursor + 12
        updates = []
        for _ in range(update_count):
            slot, source = mem.unpack("<hh", p)
            p += 4
            if not 0 <= slot < 8 or not 0 <= source < count:
                raise ValueError(f"draw {draw}: invalid palette entry {(slot, source)}")
            palette[slot] = source
            declared_sources.add(source)
            updates.append({"palette_index": slot, "source_index": source})
        payload = mem.read(p, vertex_count * stride)
        nw = ((vtype >> 14) & 7) + 1
        vertices = []
        active_slots = set()
        for j in range(vertex_count):
            base = j * stride
            weights = []
            if "weights" in layout:
                offset, kind = layout["weights"]
                code, divisor = {1: ("B", 128), 2: ("H", 32768), 3: ("f", 1)}[kind]
                values = struct.unpack_from(f"<{nw}{code}", payload, base + offset)
                total = sum(values) / divisor
                if not math.isfinite(total) or any(w < 0 for w in values):
                    raise ValueError(f"draw {draw}, vertex {j}: invalid weights")
                weight_sum_range = [min(weight_sum_range[0], total), max(weight_sum_range[1], total)]
                for slot, weight in enumerate(values):
                    if not weight:
                        continue
                    if slot not in palette:
                        raise ValueError(f"draw {draw}: active palette slot {slot} has no source")
                    active_slots.add(slot)
                    active_sources.add(palette[slot])
                    weights.append([palette[slot], weight / divisor])
            vertex = {"influences": weights}
            for field in ("position", "normal", "uv"):
                if field in layout:
                    offset, kind = layout[field]
                    code = ({1: "B", 2: "H", 3: "f"} if field == "uv" else {1: "b", 2: "h", 3: "f"})[kind]
                    components = 2 if field == "uv" else 3
                    vertex[field + "_raw"] = list(struct.unpack_from(f"<{components}{code}", payload, base + offset))
            vertices.append(vertex)
        end = (p + len(payload) + 3) & ~3
        packets.append({"draw": draw, "address": cursor, "relative_offset": cursor - table,
                        "vertex_address": p, "vertex_count": vertex_count, "stride": stride,
                        "transform_index_raw": transform_index, "flags_raw": [flag4, flag7], "vtype": vtype,
                        "palette_updates": updates, "palette_state": {str(k): v for k, v in sorted(palette.items())},
                        "active_palette_indices": sorted(active_slots), "vertex_sha256": sha(struct.pack("<I", vtype) + payload),
                        "vertices": vertices})
        cursor = end
    active = sorted(active_sources)
    absent = sorted(set(range(count)) - active_sources)
    ancestors = set()
    for index in active:
        p = bones[index]["parent"]
        while p >= 0:
            ancestors.add(p)
            p = bones[p]["parent"]
    summary = {"bone_count": count, "parent_pointer_matches": count,
               "roots": [b["index"] for b in bones if b["parent"] == -1],
               "draw_count": draw_count, "draw_table_bytes": cursor - table,
               "vertex_count": sum(p["vertex_count"] for p in packets),
               "active_source_indices": active, "palette_declared_source_indices": sorted(declared_sources),
               "not_directly_weighted_indices": absent,
               "nonweighted_ancestors_of_weighted_bones": sorted(set(absent) & ancestors),
               "other_nonweighted_indices": sorted(set(absent) - ancestors),
               "vertex_weight_sum_range": weight_sum_range,
               "descriptor_sha256": sha(descriptor_bytes), "draw_table_sha256": sha(mem.read(table, cursor - table))}
    return {"schema": "aya-original-skeleton-draw-metadata/v1", "metadata_address": metadata,
            "source_base": source_base, "descriptor_table": descriptors, "draw_table": table,
            "summary": summary, "bones": bones, "packets": packets,
            "limitations": ["44-bone object identity inherits the selected Aya capture; bone count alone is not a universal actor identifier.",
                            "No anatomical labels are assigned to individual indices.",
                            "Descriptor first seven s16 fields remain raw; rotation convention and translation scale need verification.",
                            "Matrix +0x40/+0x80 words are preserved without assuming an inverse-bind convention; a bone-0 breakpoint does not make all records one completed animation update.",
                            "Positions, normals and UVs remain in original storage units; topology and material/CLUT are not exported here.",
                            "Palette state persists between packets; update_count is not the vertex influence count."]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    inputs = ap.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--ram", type=Path)
    inputs.add_argument("--snapshot", type=Path)
    ap.add_argument("--metadata", type=lambda x: int(x, 0))
    ap.add_argument("--source-base", type=lambda x: int(x, 0))
    ap.add_argument("--ram-prefix", type=lambda x: int(x, 0), default=0x48)
    ap.add_argument("--compare", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    source = args.snapshot or args.ram
    data = source.read_bytes()
    if args.snapshot:
        snap = json.loads(data)
        if snap["schema"] != "aya-metadata-snapshot/v1":
            raise ValueError("unsupported snapshot")
        metadata, source_base = snap["metadata"], snap["sourceBase"]
        segments = [(metadata, packed_words(snap["header"])),
                    (snap["descriptors"], packed_words(snap["descriptorWords"])),
                    (snap["drawTable"], packed_words(snap["drawWords"]))]
        segments += [(source_base + row["index"] * 0x130, packed_words(row["words"])) for row in snap["records"]]
    else:
        if args.metadata is None or args.source_base is None:
            ap.error("--ram requires --metadata and --source-base")
        metadata, source_base = args.metadata, args.source_base
        segments = [(0x08000000, data[args.ram_prefix:])]
    result = recover(Memory(segments), metadata, source_base)
    result["input"] = {"path": str(source.resolve()), "sha256": sha(data), "ram_prefix": args.ram_prefix if args.ram else None}
    if args.compare:
        other = json.loads(args.compare.read_text(encoding="utf-8"))
        result["comparison"] = {"path": str(args.compare.resolve()),
                                "same_parents": [b["parent"] for b in result["bones"]] == [b["parent"] for b in other["bones"]],
                                "same_descriptors": result["summary"]["descriptor_sha256"] == other["summary"]["descriptor_sha256"],
                                "same_draw_table": result["summary"]["draw_table_sha256"] == other["summary"]["draw_table_sha256"],
                                "same_active_sources": result["summary"]["active_source_indices"] == other["summary"]["active_source_indices"]}
        if not all(v for k, v in result["comparison"].items() if k != "path"):
            raise ValueError(f"cross-capture metadata mismatch: {result['comparison']}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    small = {k: v for k, v in result.items() if k not in ("packets", "bones")}
    lines = ["# Aya 原版骨骼层级与 draw palette 解析", "", "本报告来自原版 guest-memory 字节解析；所有导出前都检查父指针、无环层级、顶点 stride 和非零权重的 palette 来源。", "", "```json", json.dumps(small, ensure_ascii=False, indent=2), "```", "", "| Source index | Parent | Children |", "|---:|---:|---|"]
    lines += [f"| {b['index']} | {b['parent']} | {', '.join(map(str, b['children'])) or '—'} |" for b in result["bones"]]
    args.out.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), "summary": result["summary"], "comparison": result.get("comparison")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
