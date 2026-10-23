"""Coverage map of 3rd.pkg: which 32 MiB windows contain which known structures."""
import os
import sys

ROOT = r"C:\Users\25105\Documents\寄生前夜第四日"
ISO = os.path.join(ROOT, r"PSP\The_3rd_birthday_cn_full_v101.iso")
SEC = 2048
PKG_LBA, PKG_SIZE = 59600, 1344292864
WIN = 32 * 1024 * 1024

SIGS = [
    (b"\x89PNG\r\n\x1a\n", "PNG"),
    (b"PSMF", "PSMF"),
    (b"SEDBSSCF", "SEDB"),
    (b"pack", "pack"),
    (b"RIFF", "RIFF"),
]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    nwin = (PKG_SIZE + WIN - 1) // WIN
    counts = {tag: [0] * nwin for _, tag in SIGS}
    with open(ISO, "rb") as f:
        f.seek(PKG_LBA * SEC)
        pos, left = 0, PKG_SIZE
        CH = 1 << 23
        carry = b""
        keep = max(len(s) for s, _ in SIGS) - 1
        while left > 0:
            chunk = f.read(min(CH, left))
            if not chunk:
                break
            left -= len(chunk)
            buf = carry + chunk
            base = pos - len(carry)
            for sig, tag in SIGS:
                i = 0
                while True:
                    i = buf.find(sig, i)
                    if i < 0:
                        break
                    counts[tag][(base + i) // WIN] += 1
                    i += 1
            carry = buf[-keep:]
            pos += len(chunk)

    print(f"{'win':>3} {'offset':>12} " + " ".join(f"{t:>5}" for _, t in SIGS))
    for w in range(nwin):
        row = " ".join(f"{counts[t][w]:>5}" for _, t in SIGS)
        print(f"{w:>3} {w * WIN:>12,} {row}")
    print("\ntotals:", {t: sum(counts[t]) for _, t in SIGS})


if __name__ == "__main__":
    main()
