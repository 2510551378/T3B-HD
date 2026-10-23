"""region_obj.py -- dump a RAM range as an OBJ under several stride hypotheses."""
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

SCALE = 9.5367431640625e-05
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "..", "tools")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    path = sys.argv[1]
    off = int(sys.argv[2], 0)
    size = int(sys.argv[3], 0)
    outdir = sys.argv[4]
    os.makedirs(outdir, exist_ok=True)
    blob = open(path, "rb").read()[off:off + size]
    print(f"{path} @0x{off:08x} {size} bytes")

    made = []
    for stride, dt in ((12, "h"), (16, "h"), (20, "h"), (12, "f"), (16, "f"), (32, "f")):
        sz = 2 if dt == "h" else 4
        n = len(blob) // stride
        raw = np.frombuffer(blob[: n * stride], dtype="<i2" if dt == "h" else "<f4")
        step = stride // sz
        v = raw[: n * step].reshape(n, step)[:, :3].astype(np.float64)
        if dt == "h":
            v *= SCALE
        if not np.isfinite(v).all():
            continue
        if np.abs(v).max() > 200:
            continue
        span = np.linalg.norm(v.max(axis=0) - v.min(axis=0))
        if span < 0.2:
            continue
        d = np.linalg.norm(np.diff(v, axis=0), axis=1)
        med = float(np.median(d))
        if med > 0.4:
            continue
        name = f"r_{stride}{dt}_{span:.1f}m.obj"
        p = os.path.join(outdir, name)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(f"# {n} verts stride {stride} {dt} span {span:.2f}\n")
            for q in v:
                fh.write("v %.4f %.4f %.4f\n" % tuple(q))
            for k in range(0, n - 2, 3):
                fh.write(f"f {k+1} {k+2} {k+3}\n")
        made.append((name, n, span, med))
        print(f"  {name:<24} {n:>5}v span={span:6.2f} m  median step {med:.3f}")

    if not made:
        return
    W, H = 260, 320
    sheet = Image.new("RGB", (W * len(made), H + 24), (16, 17, 20))
    dr = ImageDraw.Draw(sheet)
    dr.text((8, 5), f"0x{off:08x} under different stride hypotheses", fill=(235, 235, 235))
    for i, (name, n, span, med) in enumerate(made):
        png = os.path.join(outdir, f"{i}.png")
        subprocess.run([sys.executable, os.path.join(TOOLS, "render_obj.py"),
                        os.path.join(outdir, name), png, "--view", "front", "--size", str(W)],
                       capture_output=True)
        if os.path.exists(png):
            im = Image.open(png).convert("RGB").resize((W, H))
            sheet.paste(im, (i * W, 24))
            dr.text((i * W + 4, 28), name[:28], fill=(220, 220, 220))
    outp = os.path.join(HERE, "..", "out", "preview", "region.png")
    sheet.save(outp)
    print("->", outp)


if __name__ == "__main__":
    main()
