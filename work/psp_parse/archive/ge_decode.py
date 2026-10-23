"""ge_decode.py -- decode a RAM range as a PSP GE display list.

Command word = (opcode << 24) | arg.  We print a readable command trace so draw calls
(PRIM + VTYPE + VADDR) become visible.
"""
import struct
import sys

OPS = {
    0x00: "NOP", 0x01: "VADDR", 0x02: "IADDR", 0x03: "PRIM3D?", 0x04: "PRIM",
    0x05: "BEZIER", 0x06: "SPLINE", 0x07: "BOUNDINGBOX", 0x08: "JUMP", 0x09: "BJUMP",
    0x0A: "CALL", 0x0B: "RET", 0x0C: "END", 0x0D: "SIGNAL", 0x0E: "FINISH", 0x0F: "BASE",
    0x10: "VTYPE", 0x11: "?,", 0x12: "VTYPE?", 0x13: "REGION1", 0x14: "REGION2",
    0x15: "LIGHTING", 0x16: "LIGHT0", 0x17: "LIGHT1", 0x18: "LIGHT2", 0x19: "LIGHT3",
    0x1A: "CLUT", 0x1B: "TEXSIZE", 0x1C: "TEXADDR0", 0x1D: "TEXADDR1",
    0x1E: "TEXADDR2", 0x1F: "TEXADDR3", 0x20: "TEXSTRIDE", 0x21: "TEXMODE",
    0x22: "TEXFORMAT", 0x23: "TEXFILTER", 0x24: "TEXWRAP", 0x25: "TEXLEVEL",
    0x26: "TEXFUNC", 0x27: "TEXENVCOLOR", 0x28: "TEXFLUSH",
    0x2A: "TEXSYNC", 0x2B: "FOG1", 0x2C: "FOG2", 0x2D: "CLEARMODE", 0x2E: "SCISSOR1",
    0x2F: "SCISSOR2", 0x30: "MINZ", 0x31: "MAXZ", 0x32: "CULL", 0x33: "COLORTEST",
    0x34: "ALPHATEST", 0x35: "STENCILTEST", 0x36: "STENCILOP", 0x37: "ZTEST",
    0x38: "BLEND", 0x39: "BLENDCOL", 0x3A: "BLENDFIXA", 0x3B: "BLENDFIXB",
    0x3C: "DITHER", 0x3D: "ALPHAMODE", 0x3E: "COLORMASK", 0x3F: "ALPHAMASK",
    0x40: "TRANSFERSRC", 0x41: "TRANSFERDST", 0x42: "TRANSFERSRCSIZE",
    0x43: "TRANSFERDSTSIZE", 0x44: "TRANSFERSTART", 0x45: "TRANSFERSYNC",
    0x46: "TEXBASE", 0x47: "FRAMEBUF", 0x48: "OFFSET",
}


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    path = sys.argv[1]
    off = int(sys.argv[2], 0)
    count = int(sys.argv[3]) if len(sys.argv) > 3 else 96
    blob = open(path, "rb").read()
    words = struct.unpack_from(f"<{count}I", blob, off)
    print(f"{path} @0x{off:08x} guest 0x{0x08000000 + off:08x}")
    for i, w in enumerate(words):
        op = (w >> 24) & 0xFF
        arg = w & 0xFFFFFF
        name = OPS.get(op, f"0x{op:02x}")
        extra = ""
        if op == 0x12:                      # VTYPE
            extra = f"   vtype=0x{arg:06x}"
        elif op == 0x01:                    # VADDR
            extra = f"   ptr=0x{arg:06x}"
        elif op == 0x02:
            extra = f"   iptr=0x{arg:06x}"
        elif op == 0x04:
            extra = f"   prim={(arg >> 16) & 7} count={arg & 0xFFFF}"
        print(f"  [{i:03d}] 0x{w:08x}  {name:<12}{extra}")


if __name__ == "__main__":
    main()
