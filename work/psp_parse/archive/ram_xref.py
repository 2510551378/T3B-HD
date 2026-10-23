"""ram_xref.py -- find who calls the GE submission stubs, using the symbol map + RAM image.

Guest addressing: PPSSPP savestate RAM starts at guest 0x08000000, so
    guest = file_offset + 0x08000000
The map gives module-relative offsets (module base 0x08804000).
"""
import bisect
import struct
import sys

GUEST_BASE = 0x08000000
MODULE_BASE = 0x08804000

STUBS = {
    "sceGeListEnQueue": 0x08C18BFC,
    "sceGeListEnQueueHead": 0x08C18BDC,
    "sceGeListUpdateStallAddr": 0x08C18C14,
    "sceGeDrawSync": 0x08C18C04,
    "sceGeListSync": 0x08C18BCC,
    "sceGeBreak": 0x08C18C0C,
    "sceGeContinue": 0x08C18BEC,
}


def load_map(path):
    funcs = []
    for ln in open(path, encoding="utf-8", errors="replace"):
        p = ln.split()
        if len(p) < 5 or p[0].startswith("."):
            continue
        try:
            off = int(p[0], 16)
            size = int(p[1], 16)
        except ValueError:
            continue
        funcs.append((MODULE_BASE + off, size, p[4]))
    funcs.sort()
    return funcs


def owner(funcs, starts, addr):
    i = bisect.bisect_right(starts, addr) - 1
    if i < 0:
        return None
    g, size, name = funcs[i]
    return (g, size, name) if g <= addr < g + size else (g, size, name)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ram = open(sys.argv[1], "rb").read()
    funcs = load_map(sys.argv[2])
    starts = [f[0] for f in funcs]
    print(f"RAM {len(ram):,} bytes, {len(funcs)} symbols, "
          f"module guest 0x{MODULE_BASE:08x}..0x{MODULE_BASE + 0x4AF000:08x}")

    lo = MODULE_BASE - GUEST_BASE
    hi = min(len(ram), lo + 0x4AF000)
    print(f"scanning file 0x{lo:08x}..0x{hi:08x} for JAL to GE stubs")

    hits = {}
    n = (hi - lo) // 4
    words = struct.unpack_from(f"<{n}I", ram, lo)
    targets = {v: k for k, v in STUBS.items()}
    for i, w in enumerate(words):
        if (w >> 26) != 3:            # JAL
            continue
        tgt = ((lo + i * 4 + GUEST_BASE + 4) & 0xF0000000) | ((w & 0x03FFFFFF) << 2)
        name = targets.get(tgt)
        if not name:
            continue
        pc = lo + i * 4 + GUEST_BASE
        o = owner(funcs, starts, pc)
        key = (name, o[2] if o else "?")
        hits.setdefault(key, []).append(pc)

    print(f"\n{sum(len(v) for v in hits.values())} call sites in {len(hits)} (stub, function) pairs")
    for (stub, fn), pcs in sorted(hits.items(), key=lambda kv: -len(kv[1])):
        print(f"  {stub:<26} <- {fn:<24} x{len(pcs):>4}  first @0x{pcs[0]:08x}")


if __name__ == "__main__":
    main()
