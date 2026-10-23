"""Targeted PPSSPP native-heap scan for contiguous 8x3x4 bone matrices.

The scan is deliberately restricted to the native heap range observed in the
instrumentation captures. It looks for eight 3x4 float matrices with bounded
translations, unit-ish rotation rows, and near-orthogonal rows.
"""
import argparse, ctypes, ctypes.wintypes as wt, json, os, struct
from pathlib import Path

import numpy as np

K = ctypes.WinDLL("kernel32", use_last_error=True)
class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_ulonglong), ("AllocationBase", ctypes.c_ulonglong),
                ("AllocationProtect", wt.DWORD), ("_a1", wt.DWORD), ("RegionSize", ctypes.c_ulonglong),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD), ("_a2", wt.DWORD)]

READ = 0x0010
QUERY = 0x0400

def pid_for(prefix):
    import subprocess
    for line in subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout.splitlines():
        p = [x.strip('"') for x in line.split(",")]
        if len(p) > 1 and p[0].lower().startswith(prefix.lower()):
            return int(p[1])
    return None

def readable(prot):
    return (prot & 0xFF) in (0x02, 0x04, 0x08, 0x20, 0x40, 0x80)

def score_windows(f, base, max_hits=16):
    if len(f) < 96:
        return []
    hits = []
    # Bone arrays are 16-byte aligned in PPSSPP's GPU state.
    view = np.lib.stride_tricks.sliding_window_view(f, 96)[::4]
    finite = np.isfinite(view).all(axis=1)
    bounded = np.max(np.abs(view), axis=1) < 100.0
    keep = finite & bounded
    if not keep.any():
        return []
    v = view[keep].reshape(-1, 8, 3, 4)
    r = v[:, :, :, :3]
    t = v[:, :, :, 3]
    lens = np.linalg.norm(r, axis=3)
    row_ok = (lens > 0.35) & (lens < 3.5)
    dots = np.stack([np.sum(r[:, :, 0] * r[:, :, 1], axis=2),
                     np.sum(r[:, :, 0] * r[:, :, 2], axis=2),
                     np.sum(r[:, :, 1] * r[:, :, 2], axis=2)], axis=2)
    orth = np.max(np.abs(dots), axis=(1, 2))
    good = row_ok.sum(axis=(1, 2)) >= 18
    good &= orth < 0.35
    good &= np.max(np.abs(t), axis=(1, 2)) < 20.0
    idx = np.flatnonzero(good)
    for k in idx[:max_hits]:
        # Recover the file-relative start by searching the retained view row.
        raw = v[k]
        centre = raw[:, :, 3].mean(axis=0)
        hits.append({"offset": int(base), "centre": centre.tolist(), "orth_error": float(orth[k]), "matrix": raw.tolist()})
    return hits

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--process", default="PPSSPPWindows64")
    ap.add_argument("--min-addr", type=lambda x: int(x, 0), default=0x26600000000)
    ap.add_argument("--max-addr", type=lambda x: int(x, 0), default=0x26800000000)
    ap.add_argument("--out", default=r"work\psp_parse\raw\runtime_matrix_scan.json")
    args = ap.parse_args()
    pid = pid_for(args.process)
    if not pid:
        raise SystemExit("PPSSPP process not found")
    h = K.OpenProcess(QUERY | READ, False, pid)
    if not h:
        raise SystemExit(f"OpenProcess failed: {ctypes.get_last_error()}")
    mbi = MBI(); addr = 0; hits = []; scanned = 0; regions = 0
    while K.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
        base, size = int(mbi.BaseAddress), int(mbi.RegionSize)
        if base < args.min_addr or base >= args.max_addr:
            addr = base + size
            if addr <= base: break
            continue
        if mbi.State == 0x1000 and readable(mbi.Protect) and 0x100000 <= size <= 0x5000000:
            regions += 1
            raw = ctypes.create_string_buffer(size); got = ctypes.c_size_t(0)
            if K.ReadProcessMemory(h, ctypes.c_void_p(base), raw, size, ctypes.byref(got)):
                data = raw.raw[:got.value]; scanned += len(data)
                f = np.frombuffer(data[:len(data) - (len(data) % 4)], dtype="<f4")
                # Chunking keeps the strided window view bounded.
                step = 250_000
                for off in range(0, max(0, len(f) - 96), step):
                    chunk = f[off:min(len(f), off + step + 96)]
                    hs = score_windows(chunk, base + off * 4)
                    for x in hs:
                        x["offset"] = base + off * 4
                    hits.extend(hs)
        addr = base + size
        if addr <= base: break
    K.CloseHandle(h)
    # Deduplicate nearby hits; retain the best orthogonality score.
    hits.sort(key=lambda x: x["orth_error"])
    uniq = []
    for x in hits:
        if all(abs(x["offset"] - y["offset"]) > 256 for y in uniq):
            uniq.append(x)
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"pid": pid, "regions": regions, "scanned_bytes": scanned, "hits": uniq[:64]}, indent=2), encoding="utf-8")
    print(f"pid={pid} regions={regions} scanned={scanned:,} hits={len(uniq)} -> {out}")
    for x in uniq[:8]:
        print(f"  0x{x['offset']:x} orth={x['orth_error']:.4f} centre={np.round(x['centre'],3)}")

if __name__ == "__main__":
    main()
