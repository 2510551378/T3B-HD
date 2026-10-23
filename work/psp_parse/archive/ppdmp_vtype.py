"""ppdmp_vtype.py -- read the GE register writes from a frame dump and report the vertex
format words (command 0x12 = VTYPE) plus the vertex-address registers.

GEState::Save layout (GPU/GPUState.cpp):
    word[5] = vertexAddr, word[6] = indexAddr, word[7] = offsetAddr
    then, from word 17, a stream of (cmd << 24) | value words.
"""
import collections
import struct
import sys

sys.path.insert(0, __file__.rsplit("\\", 1)[0])
from ppdmp2 import read, NAMES  # noqa: E402


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cmds, buf = read(sys.argv[1])
    print(f"{len(cmds)} commands, pushbuf {len(buf):,}")

    vt = []
    vaddr = []
    for i, (t, sz, ptr) in enumerate(cmds):
        if t != 1 or ptr + sz > len(buf):
            continue
        words = struct.unpack_from(f"<{sz // 4}I", buf, ptr)
        if len(words) >= 8:
            vaddr.append((words[5], words[6], words[7]))
        for w in words[17:]:
            if (w >> 24) == 0x12:
                vt.append(w & 0xFFFFFF)
    print(f"vertexAddr registers seen: {len(vaddr)}, first few: "
          f"{[hex(v[0]) for v in vaddr[:6]]}")
    print(f"VTYPE words: {len(vt)}")
    for a, c in collections.Counter(vt).most_common(12):
        print(f"   vtype 0x{a:06x} x{c}   bits: tex={a & 3} col={(a >> 2) & 3} "
              f"nrm={(a >> 4) & 3} pos={(a >> 6) & 3} wt={(a >> 8) & 3} idx={(a >> 10) & 3}")

    # vertex block sizes
    sizes = collections.Counter(sz for t, sz, _ in cmds if t == 2)
    print(f"\nVERTICES blocks: {sum(sizes.values())}, distinct sizes: "
          f"{sorted(sizes)[:10]}{'...' if len(sizes) > 10 else ''}")
    print("top sizes:", sizes.most_common(8))


if __name__ == "__main__":
    main()
