"""ppdmp_parse.py -- parse a PPSSPP frame dump (GPU/Debugger/RecordFormat.h).

Layout, after the 24-byte file header:
    struct Command { u8 type; u32 sz; u32 ptr; }   // 9 bytes, packed
    followed by sz bytes of payload.

type: 0 INIT, 1 REGISTERS, 2 VERTICES, 3 INDICES, 4 CLUT, 5 TRANSFERSRC,
      6 MEMSET, 7 MEMCPYDEST, 8 MEMCPYDATA, 9 DISPLAY, 10 CLUTADDR, 11 EDRAMTRANS,
      0x10..0x17 TEXTURE0..7, 0x18..0x1F FRAMEBUF0..7
"""
import struct
import sys

NAMES = {
    0: "INIT", 1: "REGISTERS", 2: "VERTICES", 3: "INDICES", 4: "CLUT",
    5: "TRANSFERSRC", 6: "MEMSET", 7: "MEMCPYDEST", 8: "MEMCPYDATA", 9: "DISPLAY",
    10: "CLUTADDR", 11: "EDRAMTRANS",
}
for i in range(8):
    NAMES[0x10 + i] = f"TEXTURE{i}"
for i in range(8):
    NAMES[0x18 + i] = f"FRAMEBUF{i}"


def parse(blob, limit=None):
    pos = 0
    out = []
    while pos + 9 <= len(blob):
        t = blob[pos]
        sz, ptr = struct.unpack_from("<II", blob, pos + 1)
        if sz > len(blob):
            break
        out.append((t, sz, ptr, pos + 9))
        pos += 9 + sz
        if limit and len(out) >= limit:
            break
    return out, pos


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    blob = open(sys.argv[1], "rb").read()
    recs, consumed = parse(blob)
    print(f"{sys.argv[1]}: {len(blob):,} bytes")
    print(f"parsed {len(recs)} records, consumed {consumed:,} bytes "
          f"({consumed * 100.0 / len(blob):.1f}%)")
    import collections
    cnt = collections.Counter(r[0] for r in recs)
    print("types:", {NAMES.get(k, hex(k)): v for k, v in sorted(cnt.items())})
    print("\nfirst 24 records:")
    for t, sz, ptr, off in recs[:24]:
        print(f"  @0x{off - 9 - 0:08x}  {NAMES.get(t, hex(t)):<11} sz={sz:<8} ptr=0x{ptr:08x}")


if __name__ == "__main__":
    main()
