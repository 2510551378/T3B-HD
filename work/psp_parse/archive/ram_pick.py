"""ram_pick.py -- export the person-shaped RAM runs, auto-rotated so the long axis is up,
then render a contact sheet."""
import os
import struct
import subprocess
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "..", "tools")
sys.path.insert(0, TOOLS)
from pack_export import find_runs, SCALE  # noqa: E402


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    blob = open(r"work\psp_parse\raw\ram.bin", "rb").read()
    outdir = os.path.join(HERE, "..", "out", "dump", "bodies")
    os.makedirs(outdir, exist_ok=True)
    for f in os.listdir(outdir):
        if f.endswith(".obj") or f.endswith(".png"):
            os.remove(os.path.join(outdir, f))

    runs = [r for r in find_runs(blob) if len(r) >= 100]
    picks = []
    for r in runs:
        V = []
        for o in r:
            x, y, z = struct.unpack_from("<3h", blob, o + 4)
            V.append((x * SCALE, y * SCALE, z * SCALE))
        xs = [p[0] for p in V]
        ys = [p[1] for p in V]
        zs = [p[2] for p in V]
        ext = [max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)]
        order = sorted(range(3), key=lambda i: -ext[i])
        big, mid, small = ext[order[0]], ext[order[1]], ext[order[2]]
        if not (1.2 <= big <= 2.2 and 0.15 <= small and mid <= 1.2 and big >= 1.5 * mid):
            continue
        picks.append((len(r), r, order, big, mid, small))
    picks.sort(key=lambda p: -p[0])
    print(f"{len(picks)} person-shaped runs")

    files = []
    for i, (n, r, order, big, mid, small) in enumerate(picks[:6]):
        up = order[0]
        horiz = [a for a in range(3) if a != up]
        # map: up -> Y, other two -> X, Z
        V = []
        for o in r:
            x, y, z = struct.unpack_from("<3h", blob, o + 4)
            p = (x * SCALE, y * SCALE, z * SCALE)
            V.append((p[horiz[0]], p[up], p[horiz[1]]))
        path = os.path.join(outdir, f"body{i}_{n}v_{big:.2f}m.obj")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"# {n} verts, {big:.2f} x {mid:.2f} x {small:.2f} m\n")
            for p in V:
                fh.write("v %.4f %.4f %.4f\n" % p)
            for k in range(0, n - 2, 3):
                fh.write(f"f {k+1} {k+2} {k+3}\n")
        files.append(path)
        print(f"  body{i}: {n}v {big:.2f} x {mid:.2f} x {small:.2f} m -> {os.path.basename(path)}")

    # contact sheet: front + side of each
    W, H = 240, 340
    rows = len(files)
    sheet = Image.new("RGB", (W * 2 * rows, H + 26), (16, 17, 20))
    dr = ImageDraw.Draw(sheet)
    dr.text((8, 6), "person-shaped runs from savestate RAM (left: front, right: side)", fill=(235, 235, 235))
    for i, path in enumerate(files):
        for j, view in enumerate(("front", "side")):
            png = os.path.join(outdir, f"v{i}_{view}.png")
            subprocess.run([sys.executable, os.path.join(TOOLS, "render_obj.py"), path, png,
                            "--view", view, "--size", str(W)], capture_output=True)
            if os.path.exists(png):
                im = Image.open(png).convert("RGB").resize((W, H))
                x = (i * 2 + j) * W
                sheet.paste(im, (x, 26))
                dr.text((x + 4, 30), os.path.basename(path)[:26], fill=(220, 220, 220))
    outp = os.path.join(HERE, "..", "out", "preview", "bodies.png")
    sheet.save(outp)
    print("->", outp, sheet.size)


if __name__ == "__main__":
    main()
