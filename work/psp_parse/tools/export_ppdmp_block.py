"""Export one VERTICES block from a PPSSPP frame dump for inspection."""
import argparse, struct
from pathlib import Path

from extract_runtime_character import layout, read_ppdmp, SCALE, decode_uv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("command", type=int)
    ap.add_argument("out")
    a = ap.parse_args()
    cmds, push = read_ppdmp(a.dump)
    cur = 0
    for i, (typ, size, ptr) in enumerate(cmds):
        if typ == 1 and ptr + size <= len(push):
            for word in struct.unpack_from(f"<{size // 4}I", push, ptr):
                if word >> 24 == 0x12:
                    cur = word & 0xFFFFFF
        if i != a.command or typ != 2:
            continue
        stride, offs = layout(cur)
        po, ps = offs["pos"]
        raw = push[ptr:ptr + size]
        count = (len(raw) - po) // stride
        verts = []
        uvs = []
        for k in range(count):
            rec = raw[k * stride:(k + 1) * stride]
            if ps == 6:
                x, y, z = struct.unpack_from("<3h", rec, po)
                verts.append((x * SCALE, y * SCALE, z * SCALE))
            elif ps == 12:
                verts.append(struct.unpack_from("<3f", rec, po))
            else:
                raise SystemExit(f"unsupported position size {ps}")
            if "uv" in offs:
                uvs.append(decode_uv(rec, offs["uv"][0], cur & 3))
            else:
                uvs.append((0.0, 0.0))
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            f.write(f"# command {i} vtype 0x{cur:x} stride {stride}\n")
            for x, y, z in verts:
                f.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")
            for u, v in uvs:
                f.write(f"vt {u:.6f} {v:.6f}\n")
            for k in range(0, count - 2, 3):
                f.write(f"f {k+1}/{k+1} {k+2}/{k+2} {k+3}/{k+3}\n")
        print(f"command {i}: {count} vertices -> {out}")
        return
    raise SystemExit(f"VERTICES command {a.command} not found")


if __name__ == "__main__":
    main()
