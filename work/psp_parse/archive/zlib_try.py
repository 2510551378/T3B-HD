"""Try zlib/deflate and common LZ headers on SEDB / pack payloads (patch authors may have used zlib)."""
import glob
import os
import sys
import zlib

SEQ = os.path.join(os.path.dirname(__file__), "extract", "sedb")


def try_zlib(blob, base=0):
    for off in range(0, min(len(blob), 4096)):
        if blob[off] != 0x78:
            continue
        for wbits in (15, -15, 47):
            try:
                d = zlib.decompressobj(wbits)
                out = d.decompress(blob[off:off + 4 * 1024 * 1024])
                if len(out) > 512:
                    return off + base, wbits, out
            except Exception:
                pass
    return None


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    files = sorted(glob.glob(os.path.join(SEQ, "sedb_*.bin")))
    hits = 0
    for p in files:
        blob = open(p, "rb").read()
        r = try_zlib(blob)
        if r:
            off, wbits, out = r
            print(f"  {os.path.basename(p)}: zlib @0x{off:x} wbits={wbits} -> {len(out):,} bytes")
            print("    ", out[:120])
            hits += 1
            if hits > 4:
                break
    print(f"zlib hits: {hits}")

    # also try the whole pkg's high-entropy SEDB bodies directly
    print("\nchecking biggest SEDB bodies for deflate markers:")
    for p in files:
        blob = open(p, "rb").read()
        n = blob.count(b"\x78\x9c") + blob.count(b"\x78\xda") + blob.count(b"\x78\x01")
        if n > 0 and len(blob) > 400000:
            print(f"  {os.path.basename(p)}: markers={n}")


if __name__ == "__main__":
    main()
