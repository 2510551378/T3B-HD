"""Offline identity/byte-contract tests; no emulator or network use."""
import copy
import json
import unittest
from pathlib import Path
import analyze_weapon_marker_state_consumer as a
from disasm_aya_eboot import load_symbols


class ConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.module = (root / "raw/ULJM05798_module_08804000.bin").read_bytes()
        cls.section = (root / "out/WEAPON_MARKER_STATE_20261020/original_source_match_section.bin").read_bytes()
        cls.symbols = load_symbols(root / "map.ppmap.txt")
        cls.capture = json.loads((root / "out/AYA_BONE_GE_ACTIONS/slot0_weapon_marker_state_fep6_v2/marker_state_output.json").read_text(encoding="utf-8"))

    def run_analysis(self, module=None, section=None, symbols=None, capture=None):
        return a.analyze(self.module if module is None else module,
                         self.section if section is None else section,
                         self.symbols if symbols is None else symbols,
                         self.capture if capture is None else capture,
                         lambda name, raw: {"bytes": len(raw), "sha256": a.sha(raw)})

    def test_original_bound_chain(self):
        j = self.run_analysis()
        self.assertEqual(len(j["functions"]), 39)
        self.assertEqual(len(j["retained_live_state_rows"]), 6)
        self.assertTrue(all(x["record_byte6"] == 0 and x["node_bank1"] != 0
                            and not x["downstream_observed"] for x in j["retained_live_state_rows"]))
        renders = [d["lists"][2]["items"] for d in j["nested_descriptors"]]
        self.assertEqual([[x["type"] for x in xs] for xs in renders], [[152], [152], [155], [155]])
        for r in j["registries"]:
            if r["type"] in (152, 155):
                self.assertEqual(r["draw_pass_filter_byte"], 0)
                target = next(m["target"] for m in r["methods"] if m["vtable_offset"] == 0x20)
                self.assertEqual(target, {152: 0x08B9809C, 155: 0x08B9A514}[r["type"]])
        self.assertIsNone(j["semanticName"])

    def test_module_identity(self):
        with self.assertRaisesRegex(ValueError, "module identity"):
            self.run_analysis(module=b"bad")

    def test_section_identity(self):
        with self.assertRaisesRegex(ValueError, "FEP identity"):
            self.run_analysis(section=self.section[:-1])

    def test_function_map_boundary_required(self):
        with self.assertRaisesRegex(ValueError, "unique map"):
            self.run_analysis(symbols=[s for s in self.symbols if s[0] != 0x08B66BB4])

    def test_failed_capture(self):
        c = copy.deepcopy(self.capture)
        c["failure"] = "timeout"
        with self.assertRaisesRegex(ValueError, "capture failed"):
            self.run_analysis(capture=c)

    def test_outer_ra(self):
        c = copy.deepcopy(self.capture)
        c["rows"][0]["outerRA"] = 0
        with self.assertRaisesRegex(ValueError, "updater outer RA"):
            self.run_analysis(capture=c)

    def test_saved_sidecar_sha(self):
        c = copy.deepcopy(self.capture)
        c["rows"][0]["stateFinal"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "sidecar identity"):
            self.run_analysis(capture=c)

    def test_actual_matrix_equality(self):
        c = copy.deepcopy(self.capture)
        c["rows"][0]["actualOutput"] = c["rows"][0]["helperOutputBefore"]
        with self.assertRaisesRegex(ValueError, "bytes differ"):
            self.run_analysis(capture=c)

    def test_bounds(self):
        for offset, size in [(-1, 1), (0, -1), (4, 1), (3, 2)]:
            with self.assertRaises(ValueError):
                a.bounded(b"1234", offset, size)
        self.assertEqual(a.bounded(b"1234", 4, 0), b"")


if __name__ == "__main__":
    unittest.main()
