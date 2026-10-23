"""Dense WORLD capture safety/identity regressions and original GE fixture checks."""
import contextlib
import copy
import io
import json
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

import export_aya_dense_weapon as dense


PARSE = Path(__file__).resolve().parent.parent
METADATA = PARSE / "out/AYA_SLOT0_SKELETON_METADATA.json"
REFERENCE = PARSE / "out/AYA_EXACT_WEAPON/weapon.json"
FIRE = PARSE / "out/AYA_BONE_GE_ACTIONS/slot0_fire_world_dense_verified/manifest_aligned.json"


class WorldPayloadTests(unittest.TestCase):
    def test_column_xyz_high24_preserves_translation_and_discards_low8(self):
        words = [0x3f8000ab, 0, 0, 0, 0, 0x3f8000ff, 0, 0,
                 0, 0, 0x3f800001, 0, 0x400000ee, 0x404000dd, 0x408000cc, 0x3f800000]
        expected = [0x3f8000, 0, 0, 0, 0x3f8000, 0, 0, 0, 0x3f8000, 0x400000, 0x404000, 0x408000]
        self.assertEqual(dense.world_payload(words), expected)

    def test_non_affine_and_nonfinite_world_are_rejected(self):
        for value in (0x3f000000, 0x7fc00000):
            words = [0] * 16
            words[0] = words[5] = words[10] = words[15] = 0x3f800000
            words[3] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                dense.world_payload(words)

    def test_two_distinct_ge_endpoints_are_required(self):
        with self.assertRaisesRegex(ValueError, "at least two"):
            dense.validate_alignment_source({"geAlignment": {"matches": [{"actual_source_sample": 0}]}})


class DenseFixtureTests(unittest.TestCase):
    def setUp(self):
        if not all(path.is_file() for path in (FIRE, METADATA, REFERENCE)):
            self.skipTest("original local dense WORLD fixtures unavailable")
        self.manifest = dense.load(FIRE)
        self.binding = dense.load(Path(self.manifest["worldSourceBinding"]["file"]))

    def test_aligned_manifest_cannot_change_runtime_words(self):
        altered = copy.deepcopy(self.manifest)
        altered["frames"][0]["worldSource"]["bodyWords"][0] ^= 1
        with self.assertRaisesRegex(ValueError, "changed runtime sample"):
            dense.validate_alignment_source(altered)

    def test_per_sample_geometry_and_quantization_are_checked(self):
        for field in ("geometry", "payload", "matrix_pointer"):
            frame = copy.deepcopy(self.manifest["frames"][0])
            if field == "geometry":
                frame["worldSource"]["weaponIdentity"]["geometry_sha256"] = "wrong"
            elif field == "payload":
                frame["worldSource"]["weaponPayload"][0] ^= 1
            else:
                frame["worldSource"]["weaponMatrixPointer"] += 4
            with self.subTest(field=field), self.assertRaises(ValueError):
                dense.validate_world_sample(frame, self.binding, FIRE.parent)

    def test_source_block_and_json_must_contain_identical_bone_payloads(self):
        frame = copy.deepcopy(self.manifest["frames"][0])
        source = FIRE.parent / Path(frame["sourceBlock"]["file"]).name
        with tempfile.TemporaryDirectory() as folder:
            altered = bytearray(source.read_bytes())
            altered[0xc0] ^= 1
            target = Path(folder) / source.name
            target.write_bytes(altered)
            with self.assertRaisesRegex(ValueError, "source block and JSON"):
                dense.validate_world_sample(frame, self.binding, target.parent)

    def test_canonical_binary_sha_is_verified_before_copying_geometry(self):
        reference = dense.load(REFERENCE)
        original = Path(reference["runtime_output"]).read_bytes()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            altered = bytearray(original)
            altered[80] ^= 1
            (root / "bad.bin").write_bytes(altered)
            reference["runtime_output"] = str(root / "bad.bin")
            (root / "bad.json").write_text(json.dumps(reference), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "canonical weapon binary SHA256"):
                dense.reference_weapon(root / "bad.json")

    def test_endpoint_replay_rejects_a_wrong_runtime_sample(self):
        canonical, _, _, raw = dense.reference_weapon(REFERENCE)
        first = self.manifest["geAlignment"]["matches"][0]
        frame = copy.deepcopy(next(f for f in self.manifest["frames"] if f["frame"] == first["actual_source_sample"]))
        frame["worldSource"]["weaponPayload"][0] ^= 1
        with self.assertRaisesRegex(ValueError, "WORLD does not exactly match"):
            dense.endpoint_check(frame, Path(first["dump"]), dense.load(METADATA), canonical, raw)

    def test_real_dense_aim_and_fire_preserve_canonical_geometry_and_every_frame_world(self):
        canonical = dense.load(REFERENCE)
        canonical_path = Path(canonical["runtime_output"])
        before = canonical_path.read_bytes()
        cases = [("fire", "slot0_fire_world_dense_verified", "AYA_FIRE_DENSE_SOURCE_SKIN_EXPORT.json", False),
                 ("aim", "slot0_aim_world_dense_verified", "AYA_AIM_DENSE_SOURCE_SKIN_EXPORT.json", False),
                 ("retreat", "slot0_fire_retreat90_world60", "AYA_FIRE_RETREAT_SOURCE_SKIN_EXPORT.json", True),
                 ("reverse", "slot0_fire_reverse120_world60", "AYA_FIRE_REVERSE_SOURCE_SKIN_EXPORT.json", True)]
        for label, capture_dir, body_name, actual_weapon_source in cases:
            manifest_path = PARSE / f"out/AYA_BONE_GE_ACTIONS/{capture_dir}/manifest_aligned.json"
            body_report = PARSE / "out" / body_name
            if not manifest_path.is_file() or not body_report.is_file():
                self.skipTest(f"{label} dense body fixture unavailable")
            with self.subTest(label=label), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                with contextlib.redirect_stdout(io.StringIO()):
                    report = dense.main(["--manifest", str(manifest_path), "--metadata", str(METADATA),
                                         "--timing", str(PARSE / "out/AYA_SLOT0_CORE_TIMING.json"),
                                         "--body-report", str(body_report), "--reference-weapon-report", str(REFERENCE),
                                         "--runtime-root", str(root / "runtime"), "--output-model", f"assets/models/clips/{label}.bin",
                                         "--out", str(root / "report")])
                binary = Path(report["runtime_output"]).read_bytes()
                h, _, geometry_end, times, matrices = dense.read_skin(binary)
                self.assertEqual(h[5], 60)
                self.assertEqual(binary[56:geometry_end], before[56:dense.GEOMETRY_END])
                self.assertEqual(len(binary), 27496)
                self.assertEqual([row["frame"] for row in report["exact_ge_endpoints"]], [1, 58])
                self.assertLess(report["position_validation"]["max_error_original_units"], 0.0001)
                self.assertTrue(report["binary_layout_readback_verified"])
                self.assertEqual(report["weapon_bone_observation"]["actual_record_samples"], 60 if actual_weapon_source else 0)
                self.assertEqual(times.tolist(), dense.load(body_report)["sample_times_seconds"])
                # Independent complete 4x4 decode from the captured F32 words, truncating low bits.
                manifest = dense.load(manifest_path)
                for i, frame in enumerate(manifest["frames"]):
                    bone = np.diag([59.2998046875] * 3 + [1.])
                    if actual_weapon_source:
                        words = np.asarray(frame["worldSource"]["weaponBoneSource"]["payload"], dtype="<u4") << 8
                        bone[:3] = words.view("<f4").reshape(3, 4, order="F")
                    full = []
                    for actor in ("body", "weapon"):
                        words = np.asarray(frame["worldSource"][actor + "Words"], dtype="<u4") & 0xffffff00
                        full.append(words.view("<f4").reshape(4, 4, order="F").astype(np.float64))
                    expected = np.asarray((np.linalg.inv(full[0]) @ full[1] @ bone)[:3], dtype="<f4")
                    self.assertTrue(np.array_equal(matrices[i, 0], expected))
                files = list((root / "runtime").rglob("*"))
                self.assertEqual([p for p in files if p.is_file()], [Path(report["runtime_output"])])
        self.assertEqual(canonical_path.read_bytes(), before)


class ActualWeaponSourceTests(unittest.TestCase):
    def setUp(self):
        self.capture = PARSE / "out/AYA_BONE_GE_ACTIONS/slot0_fire_reverse120_world60"
        if not (self.capture / "manifest_aligned.json").is_file():
            self.skipTest("original direct-weapon-source fixture unavailable")
        self.manifest = dense.load(self.capture / "manifest_aligned.json")

    def test_selected_source_and_full_skeleton_are_verified(self):
        frame = self.manifest["frames"][0]
        proof = dense.captured_weapon_bone(frame, self.capture)
        self.assertEqual(proof["index"], 0)
        self.assertEqual(proof["metadata_bone_count"], 3)
        self.assertEqual(proof["payload"], frame["worldSource"]["weaponBoneSource"]["payload"])
        self.assertIsNotNone(proof["full_skeleton_block"])

    def test_missing_source_or_wrong_metadata_or_raw_payload_is_rejected(self):
        for field in ("missing", "bone_count", "index", "address", "payload"):
            frame = copy.deepcopy(self.manifest["frames"][0])
            world = frame["worldSource"]
            if field == "missing":
                world.pop("weaponBoneSource")
            elif field == "bone_count":
                world["weaponIdentity"]["boneCount"] = 2
            elif field == "index":
                world["weaponIdentity"]["sourceIndex"] = 1
            elif field == "address":
                world["weaponBoneSource"]["address"] += 0x130
            else:
                world["weaponBoneSource"]["payload"][0] ^= 1
            with self.subTest(field=field), self.assertRaises(ValueError):
                dense.captured_weapon_bone(frame, self.capture)

    def test_full_skeleton_source0_slice_cannot_disagree(self):
        frame = self.manifest["frames"][0]
        source = frame["worldSource"]["weaponBoneSource"]
        skeleton = frame["worldSource"]["weaponSkeletonSource"]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / Path(source["file"]).name).write_bytes(Path(source["file"]).read_bytes())
            changed = bytearray(Path(skeleton["file"]).read_bytes())
            changed[0xc0] ^= 1
            (root / Path(skeleton["file"]).name).write_bytes(changed)
            with self.assertRaisesRegex(ValueError, "skeleton block disagrees"):
                dense.captured_weapon_bone(frame, root)

    def test_endpoint_ge_must_equal_actual_weapon_source_not_only_canonical(self):
        match = self.manifest["geAlignment"]["matches"][0]
        frame = copy.deepcopy(next(f for f in self.manifest["frames"] if f["frame"] == match["actual_source_sample"]))
        source = frame["worldSource"]["weaponBoneSource"]
        skeleton = frame["worldSource"]["weaponSkeletonSource"]
        canonical, _, _, raw_geometry = dense.reference_weapon(REFERENCE)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            changed = bytearray(Path(source["file"]).read_bytes())
            # A finite zero-translation bone can differ from the GE endpoint; that must be rejected.
            value = struct.unpack("<I", struct.pack("<f", 60.))[0] >> 8
            for component in (0, 4, 8):
                struct.pack_into("<I", changed, 0xc0 + component * 4, 0x2b000000 | value)
                source["payload"][component] = value
            (root / Path(source["file"]).name).write_bytes(changed)
            full = bytearray(Path(skeleton["file"]).read_bytes())
            full[:0x130] = changed
            (root / Path(skeleton["file"]).name).write_bytes(full)
            capture = root / "endpoint.ppdmp"
            capture.write_bytes(Path(match["dump"]).read_bytes())
            with self.assertRaisesRegex(ValueError, "actual captured selected weapon source"):
                dense.endpoint_check(frame, capture, dense.load(METADATA), canonical, raw_geometry)

    def test_three_bone_analysis_keeps_semantics_unassigned(self):
        canonical, _, _, _ = dense.reference_weapon(REFERENCE)
        analysis = dense.analyze_weapon_metadata(self.capture / "weapon_metadata_snapshot.json",
                                                 self.manifest["frames"], canonical, .01106623198148076)
        self.assertEqual(analysis["parents"], [-1, 0, 0])
        self.assertEqual(analysis["draw_palette_source_mapping"], [[0, 0]])
        self.assertEqual(analysis["dense_parent_pointer_checks"], 180)
        self.assertTrue(all(b["semantic_name"] is None for b in analysis["bones"]))
        self.assertEqual(analysis["bones"][1]["positive_z_dot_geometry_barrel_forward"], 1.)


if __name__ == "__main__":
    unittest.main()
