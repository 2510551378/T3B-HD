"""proc_bone.py -- scan the PPSSPP process memory for the bone matrix array.

PPSSPP keeps GPUgstate (including boneMatrix, 8 x 12 floats) in its own heap, outside the
32 MiB guest mirror.  The GE debugger shows exactly this array.  A valid skeleton has, for
every 3x4 block, unit-length rows and translations that cluster within a couple of metres.

    python proc_bone.py [process_name]
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys

import numpy as np

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010


class MEMORY_BASIC_INFORMATION64(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_ulonglong),
        ("AllocationBase", ctypes.c_ulonglong),
        ("AllocationProtect", wt.DWORD),
        ("__alignment1", wt.DWORD),
        ("RegionSize", ctypes.c_ulonglong),
        ("State", wt.DWORD),
        ("Protect", wt.DWORD),
        ("Type", wt.DWORD),
        ("__alignment2", wt.DWORD),
    ]


def find_pid(name):
    import subprocess
    out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True)
    for line in out.stdout.splitlines():
        parts = [p.strip('"') for p in line.split(",")]
        if len(parts) > 1 and parts[0].lower().startswith(name.lower()):
            return int(parts[1])
    return None


def check(m):
    """A skinned bone set: 8 matrices whose rotation rows mostly share one scale factor.

    Real data has a scaled root bone plus rotation*S bones, so we require a dominant scale
    rather than a single one.
    """
    if not np.isfinite(m).all() or np.abs(m).max() > 1e4:
        return False
    rows = m.reshape(24, 4)[:, :3]
    lens = np.linalg.norm(rows, axis=1)
    if lens.min() <= 0:
        return False
    # modal length (rounded) and how many rows agree with it
    rounded = np.round(lens * 2) / 2
    vals, counts = np.unique(rounded, return_counts=True)
    k = int(np.argmax(counts))
    modal = float(vals[k])
    if modal < 20.0:
        return False
    agree = np.sum(np.abs(lens - modal) / modal < 0.05)
    return bool(agree >= 16)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    name = sys.argv[1] if len(sys.argv) > 1 else "PPSSPPWindows64"
    pid = find_pid(name)
    if not pid:
        print("process not found")
        return
    print("pid", pid)
    h = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not h:
        print("OpenProcess failed", ctypes.get_last_error())
        return

    mbi = MEMORY_BASIC_INFORMATION64()
    addr = 0
    hits = []
    scanned = 0
    while kernel32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi),
                                  ctypes.sizeof(mbi)):
        base, size, state, prot = mbi.BaseAddress, mbi.RegionSize, mbi.State, mbi.Protect
        if state == 0x1000 and (prot & 0xFF) in (0x02, 0x04, 0x08, 0x20, 0x40, 0x80) and size >= 4096:
            buf = ctypes.create_string_buffer(size)
            got = ctypes.c_size_t(0)
            if kernel32.ReadProcessMemory(h, ctypes.c_void_p(base), buf, size,
                                          ctypes.byref(got)):
                data = buf.raw[:got.value]
                scanned += len(data)
                n = len(data) // 4
                if n >= 96:
                    f = np.frombuffer(data[:n * 4], dtype="<f4")
                    for s in range(0, n - 96, 4):
                        m = f[s:s + 96].reshape(8, 3, 4)
                        if check(m):
                            t = m[:, :, 3]
                            spread = float(np.abs(t - t.mean(axis=0)).max())
                            if spread < 2.5:
                                hits.append((base + s * 4, spread, t.mean(axis=0), m.copy()))
        addr = base + size
        if addr > 0x7FFFFFFFFFFF:
            break
    kernel32.CloseHandle(h)
    print(f"scanned {scanned / 1048576:.0f} MB, {len(hits)} bone-array candidates")
    hits.sort(key=lambda h_: h_[1])
    for a, spread, centre, m in hits[:6]:
        print(f"\n  @0x{a:x} spread {spread:.3f} m  centre "
              f"({centre[0]:.2f},{centre[1]:.2f},{centre[2]:.2f})")
        for i in range(4):
            print("    bone%d  %7.3f %7.3f %7.3f | %7.3f" %
                  (i, m[i][0][0], m[i][0][1], m[i][0][2], m[i][0][3]))
        np.save(f"work/psp_parse/raw/bones_0x{a:x}.npy", m)


if __name__ == "__main__":
    main()
