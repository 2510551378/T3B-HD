"""Verify all captured C skinning samples and preserve their probe evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from verify_source_skin_runtime import verify_clip


def identity(path):
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runtime-root", type=Path, required=True)
    ap.add_argument("--clip", nargs=3, action="append", required=True, metavar=("LABEL", "BODY_REPORT", "WEAPON_REPORT"))
    ap.add_argument("--probe-archive", type=Path, required=True)
    ap.add_argument("--inspection-manifest", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    results = {label: verify_clip(a.runtime_root, label, Path(b), Path(w), all_samples=True) for label, b, w in a.clip}
    a.probe_archive.mkdir(parents=True, exist_ok=True)
    probes = {}
    for label, _, _ in a.clip:
        for mesh in ("aya", "weapon"):
            name = f"{mesh}_{label}_cpu_probe.csv"
            original = a.runtime_root / "build" / name
            output = a.probe_archive / name
            shutil.copyfile(original, output)
            probes[f"{label}/{mesh}"] = identity(output)
    archived_exe=a.probe_archive / "t3b_hd_dense_capture_verified.exe"
    shutil.copyfile(a.runtime_root / "t3b_hd.exe", archived_exe)
    report = {"schema": "aya-dense-C-runtime-all-samples/v2", "passed": True,
              "scope": "separate capture inspection manifest; no gameplay clip activation",
              "executable": identity(archived_exe),
              "inspection_manifest": identity(a.inspection_manifest), "preserved_probes": probes,
              "clips": results, "limits": ["Captured combat poses may include contact/action transitions; no pure recoil-cycle claim.",
                                            "C samples verify original source and exported weapon affine data; GE cross-check scope is recorded in export reports."]}
    a.out.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({label: {mesh: result["max_cpu_position_error_original_units"] for mesh, result in values.items()} for label, values in results.items()}))


if __name__ == "__main__":
    main()
