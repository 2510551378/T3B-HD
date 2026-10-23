"""ppdmp2.py -- correct PPSSPP frame dump reader (GPU/Debugger/Record.cpp).

    Header (24B): "PPSSPPGE", u32 version, char gameID[9], u8 pad[3]
    u32 command_count
    u32 pushbuf_size
    u32 compressed_size_1 ; zstd block 1 = command_count * 9 bytes
    u32 compressed_size_2 ; zstd block 2 = pushbuf

    struct Command { u8 type; u32 sz; u32 ptr; }   // ptr = offset INTO pushbuf
"""
import collections
import struct
import subprocess
import sys
import tempfile
import os

NAMES = {0: "INIT", 1: "REGISTERS", 2: "VERTICES", 3: "INDICES", 4: "CLUT",
         5: "TRANSFERSRC", 6: "MEMSET", 7: "MEMCPYDEST", 8: "MEMCPYDATA",
         9: "DISPLAY", 10: "CLUTADDR", 11: "EDRAMTRANS"}
for i in range(8):
    NAMES[0x10 + i] = f"TEXTURE{i}"
for i in range(8):
    NAMES[0x18 + i] = f"FRAMEBUF{i}"

HERE = os.path.dirname(os.path.abspath(__file__))
NODE_HELPER = os.path.join(HERE, "..", "tools", "zstd_blob.js")
NODE_BIN = os.environ.get("NODE_BIN", "node")


def zstd(data):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zst") as f:
        f.write(data)
        src = f.name
    dst = src + ".out"
    r = subprocess.run([NODE_BIN, NODE_HELPER, src, dst], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "zstd failed").strip())
    out = open(dst, "rb").read()
    os.unlink(src)
    os.unlink(dst)
    return out


def read(path):
    blob = open(path, "rb").read()
    assert blob[:8] == b"PPSSPPGE", "not a ppdmp"
    version = struct.unpack_from("<I", blob, 8)[0]
    gameid = blob[12:21].split(b"\0")[0].decode("ascii", "replace")
    ncmd, bufsz = struct.unpack_from("<II", blob, 24)
    pos = 32
    csize1 = struct.unpack_from("<I", blob, pos)[0]
    pos += 4
    cmds_raw = zstd(blob[pos:pos + csize1])
    pos += csize1
    csize2 = struct.unpack_from("<I", blob, pos)[0]
    pos += 4
    buf = zstd(blob[pos:pos + csize2])
    print(f"{path}: v{version} {gameid} commands={ncmd} pushbuf={bufsz} "
          f"(decoded {len(cmds_raw)} / {len(buf)} bytes)")
    cmds = []
    for i in range(ncmd):
        t, sz, ptr = struct.unpack_from("<BII", cmds_raw, i * 9)
        cmds.append((t, sz, ptr))
    return cmds, buf


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cmds, buf = read(sys.argv[1])
    cnt = collections.Counter(c[0] for c in cmds)
    print("types:", {NAMES.get(k, hex(k)): v for k, v in sorted(cnt.items())})
    print("\nfirst 20 commands:")
    for i, (t, sz, ptr) in enumerate(cmds[:20]):
        print(f"  [{i:>4}] {NAMES.get(t, hex(t)):<11} sz={sz:<7} ptr=0x{ptr:06x}")
    big = [(sz, t, ptr) for t, sz, ptr in cmds if t == 1]
    print(f"\nREGISTERS blocks: {len(big)}, sizes {sorted(set(b[0] for b in big))}")


if __name__ == "__main__":
    main()
