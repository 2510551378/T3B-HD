"""Regression checks for original GE material semantics, not image-generation tests."""
import struct
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from exact_aya_materials import (CONTEXT_RANGES, decode_texture, initial_registers,
                                 iter_material_draws, unswizzle, unpack_color, write_rgba_bmp)


def record_stream(rows):
    commands, data = [], bytearray()
    for kind, raw in rows:
        commands.append((kind, len(raw), len(data)))
        data.extend(raw)
    return commands, bytes(data)


def regs(*words):
    return struct.pack("<%dI" % len(words), *words)


class ExactMaterialTests(unittest.TestCase):
    def test_prim_precedes_following_register_changes(self):
        # The next draw's VTYPE and alpha state may share the PRIM register record.
        commands, push = record_stream([(1, regs(0x12000522, 0xdbff0006)), (2, b"geometry"),
                                       (1, regs(0x04030003, 0x12004522, 0xdbff8004))])
        draws = list(iter_material_draws(commands, push))
        self.assertEqual(len(draws), 1)
        self.assertEqual(draws[0]["registers"][0x12], 0x522)
        self.assertEqual(draws[0]["registers"][0xdb], 0xff0006)

    def test_clut_load_is_partial_and_persistent(self):
        initial = bytes(range(256)) * 4
        commands, push = record_stream([(4, initial), (4, b"\xaa" * 32),
                                       (1, regs(0xc4000001)), (2, b"geometry"), (1, regs(0x04030003))])
        draw = list(iter_material_draws(commands, push))[0]
        self.assertEqual(draw["clut"][:32], b"\xaa" * 32)
        self.assertEqual(draw["clut"][32:1024], initial[32:])
        self.assertEqual([r["bytes"] for r in draw["clut_records"]], [1024, 32])

    def test_init_is_context_ranges_after_seventeen_words(self):
        context = bytearray(2048)
        at = 68
        for lo, hi in CONTEXT_RANGES:
            for cmd in range(lo, hi + 1):
                struct.pack_into("<I", context, at, (cmd << 24) | cmd)
                at += 4
        state = initial_registers(context)
        self.assertEqual(state[0xc5], 0xc5)
        self.assertNotIn(0xc4, state)
        self.assertEqual(state[0x12], 0x12)

    def test_swizzle_blocks_restore_row_stride(self):
        # Two adjacent 16x8 blocks; a whole linear first row must interleave them.
        raw = bytes([10]) * 128 + bytes([20]) * 128
        result = unswizzle(raw, 32, 8)
        self.assertEqual(result, (bytes([10]) * 16 + bytes([20]) * 16) * 8)
        with self.assertRaises(ValueError):
            unswizzle(raw, 17, 8)

    def test_palette_formats_and_clut_index_transform(self):
        self.assertEqual(unpack_color(0x3210, 2), bytes((0, 17, 34, 51)))
        self.assertEqual(unpack_color(0x00ff, 0), bytes((255, 28, 0, 255)))
        # CLUT4 low nibble first; shift=1,mask=1,start=16 -> indices 16,17.
        state = {0xc3: 4, 0xb8: 1, 0xa8: 2, 0xc2: 0, 0xc5: 3 | (1 << 2) | (1 << 8) | (1 << 16)}
        palette = bytearray(1024)
        palette[64:72] = bytes((1, 2, 3, 4, 5, 6, 7, 8))
        rgba, facts = decode_texture(bytes((0x20,)), state, palette, bytes([1]) * 1024)
        self.assertEqual(rgba, bytes((1, 2, 3, 4, 5, 6, 7, 8)))
        self.assertEqual(facts["used_clut_indices"], [16, 17])

    def test_unknown_clut_entry_is_not_guessed(self):
        state = {0xc3: 5, 0xb8: 0, 0xa8: 1, 0xc2: 0, 0xc5: 0xff03}
        with self.assertRaisesRegex(ValueError, "unrecorded CLUT entry"):
            decode_texture(b"\x00", state, bytes(1024), bytes(1024))

    def test_bmp_preserves_alpha_and_row_orientation(self):
        rgba = bytes((255, 0, 0, 2, 0, 255, 0, 128, 0, 0, 255, 255, 17, 23, 29, 0))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "alpha.bmp"
            write_rgba_bmp(path, 2, 2, rgba)
            raw = path.read_bytes()
            self.assertEqual(struct.unpack_from("<I", raw, 14)[0], 108)
            self.assertEqual(struct.unpack_from("<I", raw, 54 + 12)[0], 0xff000000)
            self.assertEqual(Image.open(path).convert("RGBA").tobytes(), rgba)


if __name__ == "__main__":
    unittest.main()
