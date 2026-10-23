"""render_candidates.py -- render a folder of OBJs side by side so a human can judge them."""
import glob
import os
import subprocess
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "..", "tools")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    src = sys.argv[1]
    out = sys.argv[2]
    files = sorted(glob.glob(os.path.join(src, "*.obj")))[:10]
    if not files:
        print("no obj")
        return
    tmp = os.path.join(os.path.dirname(os.path.abspath(out)), "_cand")
    os.makedirs(tmp, exist_ok=True)
    W, H = 300, 360
    cols = min(5, len(files))
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new("RGB", (W * cols, H * rows + 30), (16, 17, 20))
    dr = ImageDraw.Draw(sheet)
    dr.text((8, 6), f"{len(files)} candidates from {os.path.basename(src)}", fill=(235, 235, 235))
    for i, fn in enumerate(files):
        png = os.path.join(tmp, f"{i:02d}.png")
        subprocess.run([sys.executable, os.path.join(TOOLS, "render_obj.py"), fn, png,
                        "--view", "front", "--size", str(W)], capture_output=True)
        if not os.path.exists(png):
            continue
        im = Image.open(png).convert("RGB").resize((W, H))
        x = (i % cols) * W
        y = 30 + (i // cols) * H
        sheet.paste(im, (x, y))
        dr.text((x + 4, y + 4), os.path.basename(fn)[:34], fill=(225, 225, 225))
        dr.rectangle([x, y, x + W - 1, y + H - 1], outline=(55, 58, 66))
    sheet.save(out)
    print("->", out, sheet.size)


if __name__ == "__main__":
    main()
