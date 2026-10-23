"""Create a per-draw CLUT/TEXTURE binding manifest from a PPSSPP frame dump."""
import argparse, hashlib, json, struct
from pathlib import Path

import numpy as np

from extract_runtime_character import SCALE, layout, read_ppdmp, decode_uv


def digest(data):
    return hashlib.sha1(data).hexdigest()[:12]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("out")
    a = ap.parse_args()
    cmds, push = read_ppdmp(a.dump)
    cur = 0
    clut_cmd = texture_cmd = None
    records = []
    for i, (typ, size, ptr) in enumerate(cmds):
        if ptr + size > len(push):
            continue
        payload = push[ptr:ptr + size]
        if typ == 1:
            for word in struct.unpack_from(f"<{size // 4}I", payload):
                if word >> 24 == 0x12:
                    cur = word & 0xFFFFFF
        elif typ == 4:
            clut_cmd = (i, digest(payload), size)
        elif typ == 0x10:
            texture_cmd = (i, digest(payload), size)
        elif typ == 2 and cur:
            stride, offs = layout(cur)
            if "pos" not in offs or stride <= 0:
                continue
            po, ps = offs["pos"]
            count = (size - po) // stride
            if count < 3:
                continue
            if ps == 6:
                arr = np.frombuffer(payload[po:po + count * stride], dtype="<i2").reshape(count, stride // 2)[:, :3] * SCALE
            elif ps == 12:
                arr = np.frombuffer(payload[po:po + count * stride], dtype="<f4").reshape(count, stride // 4)[:, :3]
            else:
                continue
            lo, hi = arr.min(0), arr.max(0)
            uv_lo = uv_hi = None
            if "uv" in offs:
                uoff, _ = offs["uv"]
                uv = np.asarray([decode_uv(payload[k * stride:(k + 1) * stride], uoff, cur & 3) for k in range(count)])
                uv_lo, uv_hi = uv.min(0), uv.max(0)
            records.append({
                "command": i,
                "vtype": f"0x{cur:x}",
                "stride": stride,
                "vertices": count,
                "weighted": bool((cur >> 9) & 3),
                "bbox": {"min": lo.round(6).tolist(), "max": hi.round(6).tolist()},
                "uv_bbox": None if uv_lo is None else {"min": uv_lo.round(6).tolist(), "max": uv_hi.round(6).tolist()},
                "clut": None if clut_cmd is None else {"command": clut_cmd[0], "sha1": clut_cmd[1], "bytes": clut_cmd[2]},
                "texture0": None if texture_cmd is None else {"command": texture_cmd[0], "sha1": texture_cmd[1], "bytes": texture_cmd[2]},
            })
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"dump": str(a.dump), "draws": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(records)} draw records -> {out}")


if __name__ == "__main__":
    main()
