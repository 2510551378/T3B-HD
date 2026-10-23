"""Replay GE state up to each PRIM; a REGISTERS record is not a snapshot.

Record.cpp::EmitPrim appends PRIM after emitting vertex data, and subsequent
state changes may share that same REGISTERS block. Applying its entire block
to the preceding VERTICES incorrectly uses the next draw's palette/VTYPE.
INIT state is deliberately not guessed; matrices are valid only after all
twelve components have been observed in explicit GE writes.
"""
import struct


def iter_ge_draws(commands, push):
    vtype = None
    bone_cursor = 0
    bones = [None] * 96
    vertices = None
    for ordinal, (kind, size, pointer) in enumerate(commands):
        if pointer + size > len(push):
            raise ValueError(f"record {ordinal} is outside push buffer")
        if kind == 2:
            vertices = (ordinal, size, pointer)
        elif kind == 1:
            if size % 4:
                raise ValueError("unaligned REGISTERS record")
            for offset in range(0, size, 4):
                word = struct.unpack_from("<I", push, pointer + offset)[0]
                cmd, payload = word >> 24, word & 0xffffff
                if cmd == 0x12:
                    vtype = payload
                elif cmd == 0x2a:
                    bone_cursor = payload & 0x7f
                elif cmd == 0x2b:
                    if bone_cursor < 96:
                        bones[bone_cursor] = payload
                    bone_cursor = (bone_cursor + 1) & 0x7f
                elif cmd == 4 and vertices is not None:
                    draw, vertex_size, vertex_pointer = vertices
                    yield {"draw": draw, "size": vertex_size, "pointer": vertex_pointer,
                           "vtype": vtype, "primitive": (payload >> 16) & 7, "count": payload & 0xffff,
                           "register_record": ordinal, "register_word": offset // 4,
                           "palette_payloads": {i // 12: list(bones[i:i + 12]) for i in range(0, 96, 12)
                                                if all(v is not None for v in bones[i:i + 12])}}
