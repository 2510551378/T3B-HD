"""Recover Aya materials by exact geometry identity and PRIM-time GE replay.

This decodes recorded original bytes, never synthesizes/repaints texture detail.
Record.cpp flushes registers before RAM records and appends PRIM after VERTICES.
CLUT records are raw bytes; CLUTFORMAT controls their actual palette format.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from collections import defaultdict
from pathlib import Path

from PIL import Image

from extract_runtime_character import read_ppdmp


# GPUState.cpp::contextCmdRanges; INIT is a saved context, not cmdmem[256].
CONTEXT_RANGES = [(0, 2), (0x10, 0x10), (0x12, 0x28), (0x2c, 0x33),
                  (0x36, 0x38), (0x42, 0x4d), (0x50, 0x51), (0x53, 0x58),
                  (0x5b, 0xb5), (0xb8, 0xc3), (0xc5, 0xd0), (0xd2, 0xe9),
                  (0xeb, 0xec), (0xee, 0xee), (0xf0, 0xf6), (0xf8, 0xf9)]
FORMAT_NAMES = {0: "BGR5650", 1: "ABGR5551", 2: "ABGR4444", 3: "ABGR8888",
                4: "CLUT4", 5: "CLUT8", 6: "CLUT16", 7: "CLUT32"}
BITS = {0: 16, 1: 16, 2: 16, 3: 32, 4: 4, 5: 8, 6: 16, 7: 32}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def f24(payload):
    return struct.unpack("<f", struct.pack("<I", (payload & 0xffffff) << 8))[0]


def initial_registers(raw):
    if len(raw) < 2048:
        raise ValueError("truncated saved GE context")
    registers = {}
    at = 17 * 4
    for lo, hi in CONTEXT_RANGES:
        for cmd in range(lo, hi + 1):
            word = struct.unpack_from("<I", raw, at)[0]
            # Uninitialized nop/vaddr/iaddr slots can legitimately be zero.
            if word >> 24 != cmd and not (cmd <= 2 and word == 0):
                raise ValueError(f"saved context mismatch at command {cmd:02x}: {word:08x}")
            registers[cmd] = word & 0xffffff
            at += 4
    return registers


def iter_material_draws(commands, push):
    """Yield exact state at PRIM, with persistent CLUT RAM and explicit provenance."""
    registers, textures = {}, {}
    vertices = pending_clut = None
    clut = bytearray(2048)
    clut_known = bytearray(2048)
    clut_records = []
    initial_clut = True
    for ordinal, (kind, size, pointer) in enumerate(commands):
        if pointer + size > len(push):
            raise ValueError(f"record {ordinal} exceeds push buffer")
        raw = push[pointer:pointer + size]
        if kind == 0:
            registers = initial_registers(raw)
        elif kind == 4:
            record = {"record": ordinal, "bytes": size, "sha256": sha(raw)}
            if initial_clut:
                if size != 1024:
                    raise ValueError("initial current CLUT must be 1024 bytes")
                clut[:size], clut_known[:size] = raw, b"\x01" * size
                clut_records = [record]
                initial_clut = False
            else:
                if pending_clut is not None:
                    raise ValueError("unconsumed recorded CLUT before next CLUT")
                pending_clut = raw, record
        elif 0x10 <= kind <= 0x17:
            textures[kind - 0x10] = {"record": ordinal, "bytes": size,
                                     "sha256": sha(raw), "raw": raw, "framebuffer": False}
        elif 0x18 <= kind <= 0x1f:
            # Keep unresolved framebuffer backing explicit instead of guessing its orientation.
            textures[kind - 0x18] = {"record": ordinal, "bytes": size,
                                     "sha256": sha(raw), "raw": raw, "framebuffer": True}
        elif kind == 2:
            vertices = {"record": ordinal, "bytes": size, "pointer": pointer}
        elif kind == 1:
            if size % 4:
                raise ValueError("unaligned register record")
            for offset in range(0, size, 4):
                word = struct.unpack_from("<I", raw, offset)[0]
                cmd, payload = word >> 24, word & 0xffffff
                registers[cmd] = payload
                if cmd == 0xc4:
                    blocks = 64 if payload & 127 == 64 else payload & 63
                    if blocks and pending_clut is not None:
                        data, record = pending_clut
                        if len(data) > blocks * 32:
                            raise ValueError("CLUT record exceeds LOADCLUT byte count")
                        clut[:len(data)] = data
                        clut_known[:len(data)] = b"\x01" * len(data)
                        clut_records = [record] if len(data) >= 1024 else clut_records + [record]
                        pending_clut = None
                    elif blocks:
                        raise ValueError("LOADCLUT has no preceding raw CLUT record")
                elif cmd == 4 and vertices is not None:
                    yield {"vertices": dict(vertices), "register_record": ordinal,
                           "register_word": offset // 4, "registers": dict(registers),
                           "primitive": (payload >> 16) & 7, "count": payload & 0xffff,
                           "texture0": textures.get(0), "clut": bytes(clut),
                           "clut_known": bytes(clut_known), "clut_records": list(clut_records)}


def unswizzle(raw, row_bytes, height):
    """PSP 16-byte x 8-row blocks; reject shapes that need an unproven padding rule."""
    if row_bytes % 16 or height % 8:
        raise ValueError("swizzled shape is not a full 16-byte x 8-row block grid")
    required = row_bytes * height
    if len(raw) < required:
        raise ValueError("texture bytes truncated")
    out = bytearray(required)
    blocks_x = row_bytes // 16
    for y in range(height):
        for bx in range(blocks_x):
            src = ((y // 8) * blocks_x + bx) * 128 + (y & 7) * 16
            dst = y * row_bytes + bx * 16
            out[dst:dst + 16] = raw[src:src + 16]
    return bytes(out)


def unpack_color(value, fmt):
    if fmt == 0:
        r, g, b = value & 31, (value >> 5) & 63, (value >> 11) & 31
        return bytes(((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2), 255))
    if fmt == 1:
        r, g, b = value & 31, (value >> 5) & 31, (value >> 10) & 31
        return bytes(((r << 3) | (r >> 2), (g << 3) | (g >> 2), (b << 3) | (b >> 2), 255 if value & 32768 else 0))
    if fmt == 2:
        return bytes(((value >> n) & 15) * 17 for n in (0, 4, 8, 12))
    if fmt == 3:
        return struct.pack("<I", value)
    raise ValueError(f"unsupported palette format {fmt}")


def decode_texture(raw, registers, clut, known):
    """Return RGBA top-left rows and facts derived from the original GE state."""
    r = registers
    fmt = r[0xc3] & 15
    if fmt not in BITS:
        raise ValueError(f"texture format {fmt} (compressed/unknown) is unresolved")
    width, height = 1 << (r[0xb8] & 15), 1 << ((r[0xb8] >> 8) & 15)
    # The observed Aya row width is exactly 256; no guessed width from payload length.
    bufw = r[0xa8] & 0x7ff
    if bufw < width or (bufw * BITS[fmt]) % 8:
        raise ValueError("TEXBUFW smaller than dimensions or sub-byte row padding unresolved")
    row_bytes = bufw * BITS[fmt] // 8
    if len(raw) < row_bytes * height:
        raise ValueError("texture record shorter than declared stride x height")
    linear = unswizzle(raw, row_bytes, height) if r[0xc2] & 1 else raw
    palette_fmt = r[0xc5] & 3
    shift, mask = (r[0xc5] >> 2) & 31, (r[0xc5] >> 8) & 255
    start = ((r[0xc5] >> 16) & 31) << 4
    entry_bytes = 4 if palette_fmt == 3 else 2
    used_indices = set()
    pixels = bytearray()
    for y in range(height):
        row = linear[y * row_bytes:(y + 1) * row_bytes]
        for x in range(width):
            if fmt == 4:
                value = (row[x // 2] >> (4 * (x & 1))) & 15
            elif BITS[fmt] == 8:
                value = row[x]
            elif BITS[fmt] == 16:
                value = struct.unpack_from("<H", row, x * 2)[0]
            else:
                value = struct.unpack_from("<I", row, x * 4)[0]
            if fmt & 4:
                index = ((value >> shift) & mask) | (start & (255 if palette_fmt == 3 else 511))
                at = index * entry_bytes
                if at + entry_bytes > len(clut) or not all(known[at:at + entry_bytes]):
                    raise ValueError(f"unrecorded CLUT entry {index}")
                value = int.from_bytes(clut[at:at + entry_bytes], "little")
                used_indices.add(index)
                pixels.extend(unpack_color(value, palette_fmt))
            else:
                pixels.extend(unpack_color(value, fmt))
    facts = {"width": width, "height": height, "buffer_width": bufw,
             "row_bytes": row_bytes, "format": FORMAT_NAMES[fmt], "format_id": fmt,
             "swizzled": bool(r[0xc2] & 1), "mip_max_level": (r[0xc2] >> 16) & 7,
             "clut_format": FORMAT_NAMES[palette_fmt], "clut_format_id": palette_fmt,
             "clut_shift": shift, "clut_mask": mask, "clut_start": start,
             "used_clut_indices": sorted(used_indices), "rgba_sha256": sha(pixels),
             "alpha_min": min(pixels[3::4]), "alpha_max": max(pixels[3::4]),
             "alpha_nonopaque_pixels": sum(a != 255 for a in pixels[3::4]),
             "orientation": "top-left rows; UV uses original PSP coordinates; no PNG flip"}
    return bytes(pixels), facts


def material_parameters(r):
    tc = r[0x12] & 3
    # Through-mode coordinates use texture pixel units; this Aya mesh is non-through U16.
    through = bool(r[0x12] & (1 << 23))
    return {"texture_enabled": bool(r[0x1e] & 1), "uv_map_mode": r[0xc0] & 3,
            "uv_storage_type": tc, "uv_through_mode": through,
            "uv_raw_denominator": None if through else {1: 128, 2: 32768, 3: 1}.get(tc),
            "uv_scale": [f24(r[0x48]), f24(r[0x49])],
            "uv_offset": [f24(r[0x4a]), f24(r[0x4b])],
            "uv_formula": "uv_raw / uv_raw_denominator * uv_scale + uv_offset" if not through else "unresolved through-mode UV",
            "texture_function": r[0xc9] & 7, "texture_alpha_used": bool(r[0xc9] & 256),
            "color_double": bool(r[0xc9] & 65536),
            "wrap_u": "clamp" if r[0xc7] & 1 else "repeat",
            "wrap_v": "clamp" if r[0xc7] & 256 else "repeat",
            "min_filter_raw": r[0xc6] & 7, "mag_filter_raw": (r[0xc6] >> 8) & 1,
            "alpha_test_enabled": bool(r[0x22] & 1), "alpha_test_raw": r[0xdb],
            "alpha_test_function": r[0xdb] & 7, "alpha_test_ref": (r[0xdb] >> 8) & 255,
            "alpha_test_mask": (r[0xdb] >> 16) & 255,
            "alpha_blend_enabled": bool(r[0x21] & 1), "blend_raw": r[0xdf],
            "blend_src_factor": r[0xdf] & 15, "blend_dst_factor": (r[0xdf] >> 4) & 15,
            "blend_equation": (r[0xdf] >> 8) & 7,
            "cull_enabled": bool(r[0x1d] & 1), "cull_mode_raw": r[0x9b]}


def write_rgba_bmp(path, width, height, rgba):
    """BITMAPV4 + explicit alpha mask; BI_RGB BMP loaders often discard alpha."""
    if len(rgba) != width * height * 4:
        raise ValueError("RGBA byte size mismatch")
    pixels = bytearray()
    for y in range(height - 1, -1, -1):
        for x in range(width):
            at = (y * width + x) * 4
            red, green, blue, alpha = rgba[at:at + 4]
            pixels.extend((blue, green, red, alpha))
    header = struct.pack("<2sIHHI", b"BM", 122 + len(pixels), 0, 0, 122)
    dib = struct.pack("<IiiHHIIiiII", 108, width, height, 1, 32, 3, len(pixels), 0, 0, 0, 0)
    dib += struct.pack("<5I", 0x00ff0000, 0x0000ff00, 0x000000ff, 0xff000000, 0x73524742)
    dib += b"\0" * 48
    assert len(dib) == 108
    path.write_bytes(header + dib + pixels)
    check = Image.open(path).convert("RGBA")
    if check.tobytes() != rgba:
        raise ValueError("BMP RGBA round-trip mismatch")


def recover(metadata_path, captures, out_dir):
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    by_hash = defaultdict(list)
    for packet in metadata["packets"]:
        by_hash[packet["vertex_sha256"]].append(packet)
    out_dir.mkdir(parents=True, exist_ok=True)
    resources, observations, capture_summaries = {}, [], []
    for capture in captures:
        commands, push = read_ppdmp(str(capture))
        packets_seen, unresolved = set(), []
        capture_key = f"{capture.parent.name}/{capture.name}"
        for draw in iter_material_draws(commands, push):
            r, v = draw["registers"], draw["vertices"]
            if 0x12 not in r:
                continue
            digest = sha(struct.pack("<I", r[0x12]) + push[v["pointer"]:v["pointer"] + v["bytes"]])
            matches = by_hash.get(digest, [])
            if not matches:
                continue
            if len(matches) != 1:
                raise ValueError("ambiguous Aya geometry digest")
            packet = matches[0]
            if draw["count"] != packet["vertex_count"] or draw["primitive"] != 3:
                raise ValueError("Aya original primitive/count mismatch")
            index = packet["draw"]
            packets_seen.add(index)
            tex = draw["texture0"]
            row = {"capture": capture_key, "packet": index, "vertex_sha256": digest,
                   "vertex_record": v["record"], "register_record": draw["register_record"],
                   "register_word": draw["register_word"], "vtype": r[0x12],
                   "primitive": draw["primitive"], "vertex_count": draw["count"],
                   "register_payloads": {f"0x{k:02x}": value for k, value in sorted(r.items())},
                   "texture_record": None if tex is None else tex["record"],
                   "texture_guest_address": (r[0xa0] & 0xfffff0) | ((r[0xa8] << 8) & 0x0f000000),
                   "clut_guest_address": (r[0xb0] & 0xfffff0) | ((r[0xb1] << 8) & 0x0f000000),
                   "clut_records": draw["clut_records"], "status": "unresolved"}
            try:
                if tex is None or tex["framebuffer"]:
                    raise ValueError("no ordinary recorded TEXTURE0 bytes")
                pixels, facts = decode_texture(tex["raw"], r, draw["clut"], draw["clut_known"])
                params = material_parameters(r)
                if params["uv_map_mode"] != 0 or params["uv_through_mode"]:
                    raise ValueError("non-direct UV generation needs additional matrix/light state")
                # VTYPE width changes across packets, but the material itself is the same.
                stable_params = {k: v for k, v in params.items() if k not in ("uv_storage_type", "uv_raw_denominator", "uv_formula")}
                identity = {"texture_sha256": tex["sha256"], "clut_ram_sha256": sha(draw["clut"][:1024]),
                            "format": facts["format_id"], "clut_format": facts["clut_format_id"],
                            "clut_shift": facts["clut_shift"], "clut_mask": facts["clut_mask"],
                            "clut_start": facts["clut_start"], "rgba_sha256": facts["rgba_sha256"],
                            "parameters": stable_params}
                material_id = sha(json.dumps(identity, sort_keys=True).encode())
                if material_id not in resources:
                    stem = f"aya_{material_id[:16]}"
                    png = out_dir / (stem + ".png")
                    Image.frombytes("RGBA", (facts["width"], facts["height"]), pixels).save(png)
                    bmp = out_dir / (stem + ".bmp")
                    write_rgba_bmp(bmp, facts["width"], facts["height"], pixels)
                    texture_bin, clut_bin = out_dir / (stem + ".texture.bin"), out_dir / (stem + ".clut.bin")
                    texture_bin.write_bytes(tex["raw"])
                    clut_bin.write_bytes(draw["clut"][:1024])
                    resources[material_id] = {"material_id": material_id, **identity, **facts,
                                              "texture_bytes": tex["bytes"], "clut_ram_bytes": 1024,
                                              "png": str(png.resolve()), "png_sha256": sha(png.read_bytes()),
                                              "bmp": str(bmp.resolve()), "bmp_sha256": sha(bmp.read_bytes()),
                                              "bmp_encoding": "BITMAPV4HEADER, BGRA32 bottom-up, BI_BITFIELDS explicit RGBA masks",
                                              "texture_bin": str(texture_bin.resolve()), "clut_bin": str(clut_bin.resolve())}
                row.update(status="exact_runtime_binding", material_id=material_id,
                           texture_sha256=tex["sha256"], clut_ram_sha256=identity["clut_ram_sha256"],
                           uv_transform=params)
            except (ValueError, KeyError) as error:
                row["reason"] = str(error)
                unresolved.append({"packet": index, "reason": str(error)})
            observations.append(row)
        capture_summaries.append({"key": capture_key, "path": str(capture.resolve()),
                                  "sha256": sha(capture.read_bytes()), "packets_seen": sorted(packets_seen),
                                  "missing_packets": sorted(set(range(len(metadata["packets"]))) - packets_seen),
                                  "unresolved": unresolved})
    material_indices = {key: i for i, key in enumerate(sorted(resources))}
    for key, resource in resources.items():
        resource["runtime_material_index"] = material_indices[key]
    packet_rows = []
    for packet in metadata["packets"]:
        rows = [r for r in observations if r["packet"] == packet["draw"]]
        material_ids = sorted({r["material_id"] for r in rows if "material_id" in r})
        packet_rows.append({"packet": packet["draw"], "vertex_sha256": packet["vertex_sha256"],
                            "vertex_count": packet["vertex_count"], "material_ids": material_ids,
                            "runtime_material_indices": [material_indices[key] for key in material_ids],
                            "observations": len(rows), "all_observations_decoded": bool(rows) and all("material_id" in r for r in rows),
                            "consistent_across_captures": len(material_ids) == 1 and len(rows) == len(captures),
                            "uv_storage_type": packet["vtype"] & 3,
                            "uv_raw_denominator": {1: 128, 2: 32768, 3: 1}.get(packet["vtype"] & 3)})
    raw_dir = Path(__file__).resolve().parent.parent / "raw"
    source_evidence = [{"path": str((raw_dir / name).resolve()), "sha256": sha((raw_dir / name).read_bytes())}
                       for name in ("Record.cpp", "RecordFormat.h", "GPUState.h", "GPUState.cpp", "VertexDecoderCommon.cpp")]
    result = {"schema": "aya-exact-runtime-materials/v1", "metadata": str(metadata_path.resolve()),
              "metadata_sha256": sha(metadata_path.read_bytes()), "captures": capture_summaries,
              "source_evidence": source_evidence,
              "enum_reference": "https://github.com/hrydgard/ppsspp/blob/master/GPU/ge_constants.h (read 2026-10-20)",
              "summary": {"packet_count": len(packet_rows), "capture_count": len(captures),
                          "observations": len(observations), "decoded_observations": sum("material_id" in r for r in observations),
                          "material_count": len(resources), "all_packets_consistent": all(p["consistent_across_captures"] for p in packet_rows)},
              "materials": list(resources.values()), "packets": packet_rows, "observations": observations,
              "limitations": ["Binding covers this exact 106-packet Aya mesh and supplied recorded poses; other costumes/LODs/actors are not inferred.",
                              "PNG contains original RGBA; material texture function/color doubling, lighting and alpha state still need equivalent runtime shader behavior.",
                              "No sharpening or generative upscaling is applied. Alpha bytes are preserved.",
                              "Texture dimensions/CLUT bindings do not establish original pack asset identifiers.",
                              "Unsupported framebuffer/compressed textures and non-direct UV generation remain unresolved, never guessed."]}
    output = out_dir / "materials.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = [f"T3BMAT1 {len(resources)}"]
    for key in sorted(resources):
        resource = resources[key]
        params = resource["parameters"]
        # This deliberately small interchange format cannot encode arbitrary GE alpha state.
        if (params["alpha_test_function"] != 6 or params["alpha_test_mask"] != 255
                or params["blend_src_factor"] != 2 or params["blend_dst_factor"] != 3
                or params["blend_equation"] != 0):
            raise ValueError("runtime text manifest cannot express this GE alpha/blend state")
        bitmap = "assets/materials/original_aya/" + Path(resource["bmp"]).name
        values = [material_indices[key], bitmap, params["alpha_test_ref"], int(params["alpha_blend_enabled"]),
                  *params["uv_scale"], *params["uv_offset"], int(params["wrap_u"] == "clamp"), int(params["wrap_v"] == "clamp")]
        manifest.append(" ".join(map(str, values)))
    (out_dir / "aya_original_materials.txt").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False))
    if any(c["missing_packets"] or c["unresolved"] for c in capture_summaries):
        raise SystemExit("Incomplete material recovery; see materials.json")
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--metadata", type=Path, required=True)
    ap.add_argument("--capture", action="append", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    recover(a.metadata, a.capture, a.out)


if __name__ == "__main__":
    main()
