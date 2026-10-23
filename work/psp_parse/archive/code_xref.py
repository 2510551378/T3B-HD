"""code_xref.py -- find code that materialises the address of a known vertex array.

A 32-bit constant on MIPS is built with `lui rt, hi` followed by `addiu rt, rt, lo`.
So instead of hunting the 4-byte pointer (which never appears), we look for that pair and
check whether it adds up to one of the vertex arrays we recovered from RAM.
"""
import struct
import sys

GUEST_BASE = 0x08000000
MOD_LO = 0x00804000      # file offset of the module's guest base 0x08804000
MOD_HI = MOD_LO + 0x4AF000


def runs_of(blob):
    marks = [o for o in range(0, len(blob) - 20, 2) if blob[o + 10:o + 12] == b"\xcc\xcc"]
    out = []
    cur = [marks[0]] if marks else []
    for o in marks[1:]:
        if o - cur[-1] == 20:
            cur.append(o)
        else:
            out.append(cur)
            cur = [o]
    if cur:
        out.append(cur)
    return [r for r in out if len(r) >= 3]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    blob = open(sys.argv[1], "rb").read()
    runs = runs_of(blob)
    targets = set(GUEST_BASE + r[0] for r in runs)
    print(f"{len(runs)} vertex arrays recovered; scanning code for their addresses")

    n = (min(len(blob), MOD_HI) - MOD_LO) // 4
    words = struct.unpack_from(f"<{n}I", blob, MOD_LO)
    hits = []
    for i in range(n - 6):
        w = words[i]
        if (w >> 26) != 0x0F:                 # lui
            continue
        rt = (w >> 16) & 0x1F
        hi = w & 0xFFFF
        for k in range(1, 5):
            w2 = words[i + k]
            if (w2 >> 26) != 0x09:            # addiu
                continue
            rs = (w2 >> 21) & 0x1F
            rt2 = (w2 >> 16) & 0x1F
            if rs != rt or rt2 != rt:
                continue
            lo = w2 & 0xFFFF
            if lo & 0x8000:
                lo -= 0x10000
            val = ((hi << 16) + lo) & 0xFFFFFFFF
            if val in targets:
                pc = GUEST_BASE + MOD_LO + i * 4
                hits.append((pc, val, i))
    print(f"{len(hits)} lui/addiu pairs pointing at recovered vertex arrays")
    for pc, val, i in hits[:20]:
        ctx = words[max(0, i - 4): i + 8]
        print(f"  code 0x{pc:08x} -> 0x{val:08x}  "
              + " ".join(f"{x:08x}" for x in ctx))


if __name__ == "__main__":
    main()
