"""matrices.py -- pull the GE matrices out of the recorded register blocks.

Inside a REGISTERS block the matrix data are stored as (cmd << 24) | float24 words, where
float24 is the top 24 bits of an IEEE float32 (0x3F8000 == 1.0).

    cmd 0x0B = BONEMATRIXDATA   8 x 12 values
    cmd 0x0D = WORLDMATRIXDATA    12 values
    cmd 0x0F = VIEWMATRIXDATA     12 values
    cmd 0x11 = PROJMATRIXDATA     16 values
"""
import struct
import sys

import numpy as np

sys.path.insert(0, r"work\psp_parse\archive")
from ppdmp2 import read  # noqa: E402

MTX_CMDS = {0x0B: ("bone", 96), 0x0D: ("world", 12), 0x0F: ("view", 12),
            0x11: ("proj", 16), 0x15: ("tgen", 12)}


def f24(bits):
    return struct.unpack("<f", struct.pack("<I", (bits & 0xFFFFFF) << 8))[0]


def matrices_of(blk):
    n = len(blk) // 4
    w = struct.unpack_from("<%dI" % n, blk, 0)
    out = {name: [] for name, _ in MTX_CMDS.values()}
    for x in w:
        cmd = (x >> 24) & 0xFF
        if cmd in MTX_CMDS:
            out[MTX_CMDS[cmd][0]].append(f24(x))
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cmds, buf = read(sys.argv[1])
    found = 0
    for i, (t, sz, ptr) in enumerate(cmds):
        if t != 1 or sz < 200 or ptr + sz > len(buf):
            continue
        m = matrices_of(buf[ptr:ptr + sz])
        if len(m["world"]) >= 12:
            found += 1
            if found <= 4:
                world = np.array(m["world"][:12]).reshape(4, 3) if len(m["world"]) >= 12 else None
                print(f"\ncmd[{i}] sz={sz}  world values={len(m['world'])} "
                      f"bone={len(m['bone'])} view={len(m['view'])} "
                      f"proj={len(m['proj'])} tgen={len(m['tgen'])}")
                print("  world 4x3:")
                for row in world:
                    print("    %9.4f %9.4f %9.4f" % tuple(row))
    print(f"\nblocks carrying a world matrix: {found}")


if __name__ == "__main__":
    main()
