"""draw_vtypes.py -- follow the GE state through the recording and tag each VERTICES block
with the vertex format in effect at that moment.

GEState::Save writes (cmd << 24) | value words, so a VTYPE write is simply any word whose
top byte is 0x12.
"""
import collections
import struct
import sys

sys.path.insert(0, r"work\psp_parse\archive")
from ppdmp2 import read  # noqa: E402


def vtype_str(v):
    tex = v & 3
    col = (v >> 2) & 3
    nrm = (v >> 4) & 3
    pos = (v >> 7) & 3
    wt = (v >> 9) & 3
    idx = (v >> 11) & 3
    tname = ["none", "u8", "u16", "f32"]
    cname = ["5650", "5551", "4444", "8888"]
    nname = ["none", "s8", "s16", "f32"]
    pname = ["s8", "s16", "f32", "?"]
    wname = ["none", "u8", "u16", "f32"]
    iname = ["none", "u8", "u16", "?"]
    return (f"tex={tname[tex]} col={cname[col]} nrm={nname[nrm]} pos={pname[pos]} "
            f"wt={wname[wt]} idx={iname[idx]}")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cmds, buf = read(sys.argv[1])
    cur = None
    draws = []
    for i, (t, sz, ptr) in enumerate(cmds):
        if ptr + sz > len(buf):
            continue
        if t == 1:
            w = struct.unpack_from(f"<{sz // 4}I", buf, ptr)
            for x in w:
                if (x >> 24) == 0x12:
                    cur = x & 0xFFFFFF
        elif t == 2:
            draws.append((i, sz, cur))
    print(f"{len(draws)} vertex blocks, {len(set(d[2] for d in draws))} distinct vtypes")
    by = collections.defaultdict(list)
    for i, sz, vt in draws:
        by[vt].append((sz, i))
    for vt, lst in sorted(by.items(), key=lambda kv: -len(kv[1])):
        total = sum(s for s, _ in lst)
        print(f"\nvtype 0x{vt:06x} x{len(lst):3}  bytes {total:>8}  {vtype_str(vt)}")
        print(f"   sizes: {sorted(set(s for s, _ in lst))[:8]}")


if __name__ == "__main__":
    main()
