"""dump_mesh.py -- export and render the meshes embedded in a PPSSPP frame dump.

A .ppdmp carries the vertex pages the frame actually used, so the character that was on
screen is in here.  Each run is exported as its own OBJ, auto-rotated so the longest axis
is vertical, and rendered front + side into one contact sheet.
"""
import os
import struct
import subprocess
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "..", "tools")
SCALE = 3.125 / 32768.0


def runs(blob):
    marks = [o for o in range(0, len(blob) - 20, 2) if blob[o + 10:o + 12] == b"\xcc\xcc"]
    out = []
    if not marks:
        return out
    cur = [marks[0]]
    for o in marks[1:]:
        if o - cur[-1] == 20:
            cur.append(o)
        else:
            out.append(cur)
            cur = [o]
    out.append(cur)
    return [r for r in out if len(r) >= 3]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    src, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    for f in os.listdir(outdir):
        if f.endswith((".obj", ".png")):
            os.remove(os.path.join(outdir, f))
    blob = open(src, "rb").read()
    rs = runs(blob)
    print(f"{src}: {len(rs)} runs")

    items = []
    for r in rs:
        V = []
        for o in r:
            x, y, z = struct.unpack_from("<3h", blob, o + 4)
            V.append((x * SCALE, y * SCALE, z * SCALE))
        xs = [p[0] for p in V]
        ys = [p[1] for p in V]
        zs = [p[2] for p in V]
        ext = sorted([max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)], reverse=True)
        items.append((len(r), r, ext))
    items.sort(key=lambda t: -t[0])

    picked = items[:12]
    print(f"{'#':>2} {'verts':>6}  dims (sorted)      person?")
    keep = []
    for i, (n, r, ext) in enumerate(picked):
        big, mid, small = ext
        person = 1.2 <= big <= 2.2 and 0.15 <= small and mid <= 1.2 and big >= 1.5 * mid
        print(f"{i:>2} {n:>6}  {big:6.2f} x {mid:5.2f} x {small:5.2f} m   {'YES' if person else ''}")
        keep.append((i, n, r, ext, person))

    for i, n, r, ext, person in keep:
        V = []
        for o in r:
            x, y, z = struct.unpack_from("<3h", blob, o + 4)
            V.append((x * SCALE, y * SCALE, z * SCALE))
        xs = [p[0] for p in V]
        ys = [p[1] for p in V]
        zs = [p[2] for p in V]
        e = [max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)]
        up = max(range(3), key=lambda k: e[k])
        horiz = [k for k in range(3) if k != up]
        W = [(p[horiz[0]], p[up], p[horiz[1]]) for p in V]
        path = os.path.join(outdir, f"d{i:02d}_{n}v_{ext[0]:.2f}m.obj")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"# {n} verts {ext[0]:.2f}x{ext[1]:.2f}x{ext[2]:.2f} m\n")
            for p in W:
                fh.write("v %.4f %.4f %.4f\n" % p)
            for k in range(0, n - 2, 3):
                fh.write(f"f {k+1} {k+2} {k+3}\n")

    files = sorted(f for f in os.listdir(outdir) if f.endswith(".obj"))
    TW, TH = 250, 330
    cols = 6
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new("RGB", (TW * cols, TH * rows + 24), (16, 17, 20))
    dr = ImageDraw.Draw(sheet)
    dr.text((8, 5), f"frame dump meshes ({len(files)})", fill=(235, 235, 235))
    for k, fn in enumerate(files):
        png = os.path.join(outdir, f"{k}.png")
        subprocess.run([sys.executable, os.path.join(TOOLS, "render_obj.py"),
                        os.path.join(outdir, fn), png, "--view", "front", "--size", str(TW)],
                       capture_output=True)
        if os.path.exists(png):
            im = Image.open(png).convert("RGB").resize((TW, TH))
            x, y = (k % cols) * TW, 24 + (k // cols) * TH
            sheet.paste(im, (x, y))
            dr.text((x + 4, y + 3), fn[:30], fill=(225, 225, 225))
    outp = os.path.join(HERE, "..", "out", "preview", "dumpmeshes.png")
    sheet.save(outp)
    print("->", outp)


if __name__ == "__main__":
    main()
