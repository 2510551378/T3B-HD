"""Regression: state changes after a PRIM must not affect that draw."""
import struct
import unittest
from replay_ge_draws import iter_ge_draws


class ReplayTests(unittest.TestCase):
    def test_shared_register_block_and_inherited_palette(self):
        push = bytearray()
        commands = []

        def record(kind, data):
            commands.append((kind, len(data), len(push)))
            push.extend(data)

        def registers(words):
            record(1, struct.pack(f"<{len(words)}I", *words))

        first = list(range(12))
        second = list(range(100, 112))
        registers([0x12000522, 0x2a000000] + [0x2b000000 | x for x in first])
        record(2, b"old_vertex_buffer")
        # This one record contains the first draw AND preparation for the next.
        registers([0x04030003, 0x2a000000] + [0x2b000000 | x for x in second] + [0x12004522])
        record(2, b"next_vertex_buffer")
        registers([0x04030006])
        record(2, b"third_vertex_buffer")
        registers([0x04030009])
        draws = list(iter_ge_draws(commands, push))
        self.assertEqual([d["vtype"] for d in draws], [0x522, 0x4522, 0x4522])
        self.assertEqual([d["count"] for d in draws], [3, 6, 9])
        self.assertEqual([d["palette_payloads"][0] for d in draws], [first, second, second])
        self.assertEqual([d["draw"] for d in draws], [1, 3, 5])

    def test_partial_matrix_is_unknown(self):
        words = [0x12000522, 0x2a000000, 0x2b3f8000, 0x04030003]
        data = struct.pack("<4I", *words)
        draws = list(iter_ge_draws([(2, 0, 0), (1, len(data), 0)], data))
        self.assertEqual(draws[0]["palette_payloads"], {})


if __name__ == "__main__":
    unittest.main()
