"""Decode a recorded CLUT/TEXTURE0 pair into a PNG for material matching."""
import argparse, ctypes, struct
from pathlib import Path
from PIL import Image

from extract_runtime_character import read_ppdmp


def unswizzle8(src, w, h):
    out = bytearray(w * h)
    bw, bh = 16, 8
    nbx = w // bw
    for by in range(0, h, bh):
        for bx in range(0, w, bw):
            base = ((by // bh) * nbx + (bx // bw)) * (bw * bh)
            for y in range(bh):
                o = (by + y) * w + bx
                out[o:o + bw] = src[base + y * bw:base + y * bw + bw]
    return bytes(out)


def rgba_from_clut(raw):
    # PPSSPP record stores palette entries as RGBA8888 bytes.
    return [tuple(raw[i:i + 4]) for i in range(0, len(raw) - 3, 4)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("--clut", type=int, default=834)
    ap.add_argument("--texture", type=int, default=836)
    ap.add_argument("--width", type=int, default=256)
    ap.add_argument("--height", type=int, default=256)
    ap.add_argument("out")
    a = ap.parse_args()
    cmds, push = read_ppdmp(a.dump)
    ct, cs, cp = cmds[a.clut]
    tt, ts, tp = cmds[a.texture]
    palette = rgba_from_clut(push[cp:cp + cs])
    pixels = unswizzle8(push[tp:tp + ts], a.width, a.height)
    if len(palette) < 256 or len(pixels) < a.width * a.height:
        raise SystemExit(f"pair is too small: palette={len(palette)} pixels={len(pixels)}")
    rgba = bytearray(a.width * a.height * 4)
    for i, idx in enumerate(pixels[:a.width * a.height]):
        rgba[i * 4:i * 4 + 4] = bytes(palette[idx])
    Image.frombytes("RGBA", (a.width, a.height), bytes(rgba)).save(a.out)
    print(f"{a.dump}: CLUT[{a.clut}] + TEXTURE0[{a.texture}] -> {a.out}")


if __name__ == "__main__":
    main()
