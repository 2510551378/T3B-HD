"""Semantic checks for isolated clips, capture identity and canonical scene calibration."""
import contextlib
import copy
import hashlib
import io
import json
import shutil
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

import export_aya_actual_weapon as weapon
import export_aya_source_skin as body


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def identity(path):
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


class ClipIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.metadata = self.root / "metadata.json"
        self.manifest = self.root / "manifest.json"
        self.timing = self.root / "timing.json"
        self.canonical = self.root / "canonical.json"
        raw_identity = [1., 0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0.]
        words = [0x2b000000 | (struct.unpack("<I", struct.pack("<f", value))[0] >> 8) for value in raw_identity]
        rows = [{"index": i, "matrix": words} for i in range(44)]
        self.frames = [{"ticks": ticks, "records": rows} for ticks in (100, 50000100, 100000100)]
        metadata = {"bones": [{"matrix_80_words": [struct.unpack("<I", struct.pack("<f", 2.))[0]]}],
                    "packets": [{"vertices": [{"position_raw": [0, 16384, 0], "influences": [[0, 1.]]}]}]}
        write_json(self.metadata, metadata)
        write_json(self.manifest, {"frames": self.frames})
        write_json(self.timing, {"cpu_hz": 100000000})
        self.times = weapon.sample_times(self.frames, {"cpu_hz": 100000000})
        self.report = {"samples": 3, "sample_times_seconds": self.times.tolist(), "saved_cpu_hz": 100000000,
                       "pc_units_per_original_unit": .92, "reference_floor": .5, "actual_reference_floor": .5,
                       "reference_scale_calibration": None,
                       "inputs": {"metadata": identity(self.metadata), "manifest": identity(self.manifest), "timing": identity(self.timing)}}

    def validate(self, report=None):
        return weapon.validate_body_capture(self.report if report is None else report, self.metadata, self.manifest,
                                            self.timing, self.frames, self.times)

    def test_three_frame_non333mhz_capture_is_valid(self):
        self.assertEqual(self.times.tolist(), [0., .5, 1.])
        self.assertEqual(self.validate()[:3], (.92, .5, .5))

    def test_model_paths_are_relative_and_cannot_escape_runtime(self):
        target = body.resolve_output_model(self.root, Path("assets/models/aya_aim.bin"))
        self.assertEqual(target, self.root / "assets/models/aya_aim.bin")
        for invalid in (self.root / "absolute.bin", Path("../escaped.bin"), Path(".")):
            with self.subTest(path=invalid), self.assertRaises(ValueError):
                body.resolve_output_model(self.root, invalid)

    def test_reference_obj_default_is_legacy_or_custom_same_stem(self):
        reference = self.root / "assets/models/aya_source_skin.bin"
        custom = self.root / "assets/models/aya_aim.bin"
        self.assertEqual(body.reference_obj_path(self.root, reference).name, "aya_source_reference.obj")
        self.assertEqual(body.reference_obj_path(self.root, custom).name, "aya_aim_reference.obj")
        self.assertEqual(body.reference_obj_path(self.root, custom, Path("diagnostics/pose.obj")), self.root / "diagnostics/pose.obj")

    def test_different_capture_path_is_rejected_even_with_same_bytes(self):
        alternative = self.root / "other_manifest.json"
        alternative.write_bytes(self.manifest.read_bytes())
        report = copy.deepcopy(self.report)
        report["inputs"]["manifest"] = identity(alternative)
        with self.assertRaisesRegex(ValueError, "manifest identity"):
            self.validate(report)

    def test_changed_manifest_bytes_are_rejected_at_same_path(self):
        self.manifest.write_bytes(self.manifest.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "manifest identity"):
            self.validate()

    def test_sample_count_and_times_and_uncalibrated_floor_are_checked(self):
        for key, value in (("samples", 12), ("sample_times_seconds", [0., .6, 1.]),
                           ("reference_floor", -.25), ("pc_units_per_original_unit", 1.)):
            report = copy.deepcopy(self.report)
            report[key] = value
            with self.subTest(field=key), self.assertRaises(ValueError):
                self.validate(report)

    def calibrated_report(self):
        write_json(self.canonical, {"inputs": {"metadata": identity(self.metadata)},
                                   "pc_units_per_original_unit": .92, "reference_floor": -.25})
        units, floor, evidence = body.calibrated_scene_conversion(self.metadata, .92, .5, self.canonical)
        report = copy.deepcopy(self.report)
        report.update(pc_units_per_original_unit=units, reference_floor=floor, reference_scale_calibration=evidence)
        report["inputs"]["reference_scale_report"] = identity(self.canonical)
        return report

    def test_verified_calibration_preserves_actual_clip_floor_separately(self):
        report = self.calibrated_report()
        self.assertEqual(self.validate(report)[:3], (.92, -.25, .5))
        self.assertEqual(report["reference_scale_calibration"]["actual_clip_reference_floor"], .5)

    def test_changed_canonical_report_is_rejected(self):
        report = self.calibrated_report()
        self.canonical.write_bytes(self.canonical.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "canonical scale report SHA256 changed"):
            self.validate(report)

    def test_forged_calibration_declaration_is_rejected(self):
        report = self.calibrated_report()
        report["reference_scale_calibration"]["reference_floor"] = 100.
        with self.assertRaisesRegex(ValueError, "calibration declaration"):
            self.validate(report)

    def test_reference_geometry_and_scale_must_match(self):
        report = self.calibrated_report()
        canonical = json.loads(self.canonical.read_text(encoding="utf-8"))
        canonical["inputs"]["metadata"]["sha256"] = "wrong geometry"
        write_json(self.canonical, canonical)
        with self.assertRaisesRegex(ValueError, "different Aya geometry"):
            body.calibrated_scene_conversion(self.metadata, .92, .5, self.canonical)

    def test_duplicate_ticks_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "chronological"):
            weapon.sample_times([{"ticks": 100}, {"ticks": 100}], {"cpu_hz": 333000000})


class RealCaptureClipExportTests(unittest.TestCase):
    def test_default_exports_remain_byte_identical_to_reference_assets(self):
        parse_root = Path(__file__).resolve().parent.parent
        canonical_path = parse_root / "out/AYA_SOURCE_SKIN_EXPORT.json"
        reference_body = parse_root.parent / "t3b_hd/assets/models/aya_source_skin.bin"
        reference_weapon = parse_root.parent / "t3b_hd/assets/models/aya_source_weapon.bin"
        if not all(path.is_file() for path in (canonical_path, reference_body, reference_weapon)):
            self.skipTest("original local reference fixtures unavailable")
        canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            report = root / "body.json"
            with contextlib.redirect_stdout(io.StringIO()):
                body.main(["--metadata", canonical["inputs"]["metadata"]["path"],
                           "--manifest", canonical["inputs"]["manifest"]["path"],
                           "--timing", canonical["inputs"]["timing"]["path"],
                           "--completed-snapshot", canonical["matrix_convention_validation"]["snapshot"],
                           "--materials", canonical["inputs"]["materials"]["path"],
                           "--runtime-root", str(root / "runtime"), "--report", str(report)])
                weapon.main(["--metadata", canonical["inputs"]["metadata"]["path"],
                             "--manifest", canonical["inputs"]["manifest"]["path"],
                             "--timing", canonical["inputs"]["timing"]["path"],
                             "--body-report", str(report), "--runtime-root", str(root / "runtime"),
                             "--out", str(root / "weapon_export")])
            self.assertEqual((root / "runtime/assets/models/aya_source_skin.bin").read_bytes(), reference_body.read_bytes())
            self.assertEqual((root / "runtime/assets/models/aya_source_weapon.bin").read_bytes(), reference_weapon.read_bytes())
            self.assertTrue((root / "runtime/assets/models/aya_source_reference.obj").is_file())

    def test_three_frame_clip_uses_distinct_outputs_and_canonical_scale(self):
        parse_root = Path(__file__).resolve().parent.parent
        capture_root = parse_root / "out/AYA_BONE_GE_ACTIONS/manual_slot0_damage_probe"
        canonical_path = parse_root / "out/AYA_SOURCE_SKIN_EXPORT.json"
        required = [capture_root / "manifest.json", canonical_path,
                    parse_root / "out/AYA_SLOT0_SKELETON_METADATA.json",
                    parse_root / "out/AYA_SLOT0_CORE_TIMING.json", parse_root / "out/AYA_EXACT_MATERIALS/materials.json"]
        if not all(path.is_file() for path in required):
            self.skipTest("original local GE fixtures unavailable")
        canonical_bytes = canonical_path.read_bytes()
        canonical = json.loads(canonical_bytes)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            inputs = root / "new_capture"
            inputs.mkdir()
            manifest = json.loads(required[0].read_text(encoding="utf-8"))
            manifest["frames"] = manifest["frames"][1:4]
            for frame in manifest["frames"]:
                filename = Path(frame["dump"]["file"]).name
                shutil.copyfile(capture_root / filename, inputs / filename)
            manifest_path = inputs / "manifest.json"
            write_json(manifest_path, manifest)
            runtime = root / "runtime"
            models = runtime / "assets/models"
            models.mkdir(parents=True)
            reference_body, reference_weapon = models / "aya_source_skin.bin", models / "aya_source_weapon.bin"
            reference_body.write_bytes(b"body reference sentinel")
            reference_weapon.write_bytes(b"weapon reference sentinel")
            report = root / "reports/new_body.json"
            with contextlib.redirect_stdout(io.StringIO()):
                body.main(["--metadata", str(required[2]), "--manifest", str(manifest_path),
                           "--timing", str(required[3]), "--completed-snapshot", canonical["matrix_convention_validation"]["snapshot"],
                           "--materials", str(required[4]), "--runtime-root", str(runtime),
                           "--output-model", "assets/models/aya_aim_test.bin", "--report", str(report),
                           "--reference-scale-report", str(canonical_path)])
                weapon.main(["--metadata", str(required[2]), "--manifest", str(manifest_path),
                             "--timing", str(required[3]), "--body-report", str(report),
                             "--runtime-root", str(runtime), "--output-model", "assets/models/aya_weapon_aim_test.bin",
                             "--out", str(root / "weapon_export")])
            self.assertEqual(reference_body.read_bytes(), b"body reference sentinel")
            self.assertEqual(reference_weapon.read_bytes(), b"weapon reference sentinel")
            self.assertEqual(canonical_path.read_bytes(), canonical_bytes)
            self.assertTrue((models / "aya_aim_test_reference.obj").is_file())
            body_report = json.loads(report.read_text(encoding="utf-8"))
            weapon_report = json.loads((root / "weapon_export/weapon.json").read_text(encoding="utf-8"))
            self.assertEqual(body_report["samples"], 3)
            self.assertEqual(weapon_report["samples"], 3)
            self.assertEqual(body_report["sample_times_seconds"], weapon_report["sample_times_seconds"])
            self.assertEqual(body_report["reference_floor"], canonical["reference_floor"])
            self.assertEqual(weapon_report["reference_floor"], canonical["reference_floor"])
            self.assertEqual(body_report["actual_reference_floor"], weapon_report["actual_body_reference_floor"])
            raw = (models / "aya_weapon_aim_test.bin").read_bytes()
            self.assertEqual(len(raw), 76 + 24300 + 3 * 52)
            header = struct.unpack_from("<8s8I4f", raw)
            self.assertEqual(header[5], 3)
            self.assertTrue(weapon_report["binary_layout_readback_verified"])


if __name__ == "__main__":
    unittest.main()
