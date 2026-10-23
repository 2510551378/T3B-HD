"""map_syms.py -- load the PPSSPP symbol map and list the named (non z_un_) functions."""
import sys


def load(path):
    syms = []
    for ln in open(path, encoding="utf-8", errors="replace"):
        p = ln.split()
        if len(p) < 5 or p[0].startswith("."):
            continue
        try:
            off = int(p[0], 16)
            size = int(p[1], 16)
        except ValueError:
            continue
        syms.append((off, size, p[4]))
    return syms


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    syms = load(sys.argv[1])
    print(f"{len(syms)} symbols")
    named = [s for s in syms if not s[2].startswith("z_un_")]
    print(f"named: {len(named)}")
    pats = sys.argv[2:] or ["Gu", "Draw", "Prim", "Mesh", "Model", "Load", "Read", "File"]
    seen = set()
    for pat in pats:
        m = [s for s in named if pat.lower() in s[2].lower()]
        if not m:
            continue
        print(f"== {pat}: {len(m)}")
        for off, size, n in m[:14]:
            key = (off, n)
            if key in seen:
                continue
            seen.add(key)
            print(f"   0x{off:06x} guest 0x{0x08804000 + off:08x} size 0x{size:<6x} {n}")


if __name__ == "__main__":
    main()
