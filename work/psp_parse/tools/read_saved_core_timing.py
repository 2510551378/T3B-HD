"""Read PPSSPP v1.20.4 CoreTiming section; do not assume a CPU frequency.

Reference: Core/CoreTiming.cpp::DoState, section v3; Serializer linked lists
serialize a u8 presence flag followed by time/u64, userdata/u64, type/u32.
"""
import argparse
import ctypes
import hashlib
import json
import struct
from pathlib import Path


def decompress_state(data):
    from extract_runtime_character import lib, dec
    lib.ZSTD_getFrameContentSize.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    lib.ZSTD_getFrameContentSize.restype = ctypes.c_uint64
    parts = []
    start = 0
    while True:
        start = data.find(b"\x28\xb5\x2f\xfd", start)
        if start < 0:
            break
        compressed = data[start:]
        source = ctypes.create_string_buffer(compressed)
        size = lib.ZSTD_getFrameContentSize(source, len(compressed))
        if 0 < size < 256 * 1024 * 1024:
            try:
                parts.append(dec(compressed, size))
            except RuntimeError:
                pass
        start += 4
    if len(parts) != 1:
        raise ValueError(f"expected one valid zstd state frame, found {len(parts)}")
    return parts[0]


def read_timing(data):
    marker = b"CoreTiming".ljust(16, b"\0")
    at = data.find(marker)
    if at < 0 or data.find(marker, at + 1) >= 0:
        raise ValueError("CoreTiming section is absent or ambiguous")
    version, registered = struct.unpack_from("<II", data, at + 16)
    if version != 3 or not 0 < registered < 10000:
        raise ValueError("only observed v3 serialization is supported")
    p = at + 24
    events = []
    for queue in range(2):
        n = 0
        while data[p]:
            if data[p] != 1 or n >= 10000:
                raise ValueError("invalid linked-list node flag")
            p += 1
            time, user, kind = struct.unpack_from("<QQI", data, p)
            p += 20
            n += 1
            if queue == 0:
                events.append({"ticks": time, "userdata": user, "event_type": kind})
        p += 1
    hz, slice_length, global_ticks, idle_ticks, last_ticks, last_us = struct.unpack_from("<IIQQQQ", data, p)
    if not 1000000 <= hz <= 1000000000 or struct.unpack_from("<I", data, p + 40)[0] != 0x42:
        raise ValueError("invalid frequency or section end marker")
    return {"section_offset": at, "version": version, "cpu_hz": hz, "slice_length": slice_length,
            "global_ticks": global_ticks, "idle_ticks": idle_ticks, "last_frequency_change_ticks": last_ticks,
            "last_frequency_change_us": last_us, "events": events}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=Path)
    ap.add_argument("--compressed", action="store_true")
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    raw = a.input.read_bytes()
    data = decompress_state(raw) if a.compressed else raw
    result = read_timing(data)
    result.update(schema="ppsspp-saved-core-timing/v1", input=str(a.input.resolve()), input_sha256=hashlib.sha256(raw).hexdigest(),
                  reference="https://github.com/hrydgard/ppsspp/blob/v1.20.4/Core/CoreTiming.cpp#L459-L501",
                  limitation="Saved frequency is verified at the save instant; changes during later captures require separate observation.")
    a.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "events"}))


if __name__ == "__main__":
    main()
