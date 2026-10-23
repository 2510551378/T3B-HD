"""Offline, opcode-driven replay of observed matrix modes0/1 and VIEW.

No producer/predictor import, emulator connection, threshold-based equivalence,
or muzzle semantics. Unknown opcodes, unretained reads and unsupported modes
fail closed. Default-prefix consistency is distinguished from observed-prefix
bit equivalence. All inputs/outputs are retained raw little-endian float32.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = 0x08804000
MODULE_SHA = "b5fc590366fc610f2cdd60104a4a28851bacd402c4600a4c296776e1dea0869f"
REFERENCE_SHA = {
    "MIPSIntVFPU.cpp": "9a5f53df3b5f8c0a1b48424eae8430c729a89b89fab1d8926e553226dfcab876",
    "MIPSDisVFPU.cpp": "059adb5403b88b8fc22f4b85b3d3e1d1d58b5f9aa6e2798c1c17dd7a4d139f88",
    "MIPSVFPUUtils.cpp": "33c419ce793f5fc2db2cd825626541d823ce975c81784d67cd87fee53d115525",
    "MIPSVFPUUtils.h": "262d77fcc9dda7d63d56ff12cf93338d86bd4373f8fa57eb073c55a6b6cfc7e9",
    "MIPSTables.cpp": "960cdfcb001780ff8eb629eb8d0d1cd911dd96c3aa654bc3ad6c2860b5cca637",
}
REGISTER_REFERENCE_SHA = {
    'CPUCoreSubscriber.cpp': 'f5275602c205dc44e5090be0f46ad717274cd15e48d37acd5e9da5ed49c6fb96',
    'MIPSDebugInterface.cpp': '9169792b8ead5a1c7748b9d29b094c19eb7769974f3adc7ab62adb822ec7aee3',
    'MIPSDebugInterface.h': '47f50d1bfb176a21b35891dc2f29443135d9c39d019f5373888b4ec036ba3b9e',
}
FUNCTIONS = ((0x08B66BB4, 0x3B4), (0x08B657F8, 0xA4), (0x08B6589C, 0x104), (0x08BBB8D4, 0x5C))
DEFAULT_PREFIX = (0xE4, 0xE4, 0)


def check(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def words(raw: bytes) -> list[int]:
    check(len(raw) % 4 == 0, "unaligned raw byte extent")
    return list(struct.unpack('<' + 'I' * (len(raw) // 4), raw))


def u2f(value: int) -> float:
    result = struct.unpack('<f', struct.pack('<I', value))[0]
    check(math.isfinite(result), "nonfinite VFPU data is unsupported")
    return result


def f2u(value: float) -> int:
    check(math.isfinite(value), "nonfinite VFPU result is unsupported")
    return struct.unpack('<I', struct.pack('<f', value))[0]


def f32(value: float) -> float:
    return u2f(f2u(value))


def sidecar(item: dict) -> bytes:
    raw = Path(item['file']).read_bytes()
    check(len(raw) == item['bytes'] and sha(raw) == item['sha256'], "raw sidecar identity mismatch")
    return raw


def window(item: dict, size: int | None = None, address: int | None = None) -> bytes:
    check(isinstance(item['address'], int) and item['address'] % 4 == 0, "unaligned window address")
    raw = sidecar(item['raw'])
    check(len(raw) == item['size'], "window extent mismatch")
    check(size is None or len(raw) == size, "unexpected window size")
    check(address is None or item['address'] == address, "unexpected raw window address")
    return raw


def vindices(reg: int, size: int) -> list[int]:
    m, col = ((reg >> 2) & 7) * 16, reg & 3
    if size == 1:
        return [m + col * 4 + ((reg >> 5) & 3)]
    check(size in (2, 3, 4), "unsupported vector size")
    row = ((reg >> 6) & 1) if size == 3 else ((reg >> 5) & 2)
    return [m + col + ((row + i) & 3) * 4 if reg & 32 else m + col * 4 + ((row + i) & 3) for i in range(size)]


def mindices(reg: int, size: int) -> list[tuple[int, int]]:
    check(size in (3, 4), "unsupported matrix size")
    m, col = ((reg >> 2) & 7) * 16, reg & 3
    row = ((reg >> 6) & 1) if size == 3 else ((reg >> 5) & 2)
    return [(j * 4 + i, m + (((row + i) & 3) * 4 + ((col + j) & 3) if reg & 32 else ((col + j) & 3) * 4 + ((row + i) & 3))) for j in range(size) for i in range(size)]


class Machine:
    """Bounded subset; physical VFPU registers are explicit and uninitialized."""
    def __init__(self, module: bytes, gpr: list[int], prefix: tuple[int, int, int] = DEFAULT_PREFIX):
        check(len(gpr) == 32 and gpr[0] == 0 and all(type(x) is int and 0 <= x <= 0xffffffff for x in gpr), "bad GPR input")
        check(tuple(prefix) == DEFAULT_PREFIX, "non-default active VFPU prefix is unsupported")
        self.module, self.r, self.prefix = module, list(gpr), tuple(prefix)
        self.mem: dict[int, int] = {}
        self.writable: list[tuple[int, int]] = []
        self.v: list[float | None] = [None] * 128
        self.f: list[int | None] = [None] * 32
        self.cc: bool | None = None
        self.trace: list[dict] = []

    def retain(self, address: int, raw: bytes, write: bool = False) -> None:
        check(address % 4 == 0, "unaligned retained memory")
        for i, value in enumerate(words(raw)):
            at = address + 4 * i
            check(at not in self.mem or self.mem[at] == value, "contradictory same-stage raw windows")
            self.mem[at] = value
        if write:
            self.writable.append((address, address + len(raw)))

    def read(self, address: int) -> int:
        check(address in self.mem, f'unretained read {address:#x}')
        return self.mem[address]

    def write(self, address: int, value: int) -> None:
        check(address % 4 == 0 and any(a <= address and address + 4 <= b for a, b in self.writable), f'unbounded write {address:#x}')
        self.mem[address] = value

    def reg(self, index: int) -> float:
        check(self.v[index] is not None, f'uninitialized VFPU register {index}')
        return float(self.v[index])

    def matrix(self, reg: int, size: int) -> list[float]:
        out = [0.] * 16
        for logical, physical in mindices(reg, size):
            out[logical] = self.reg(physical)
        return out

    def instruction(self, pc: int) -> int:
        check(any(a <= pc < a + n for a, n in FUNCTIONS), f'unsupported control flow {pc:#x}')
        return struct.unpack_from('<I', self.module, pc - BASE)[0]

    def vfpu(self, w: int) -> str:
        check(self.prefix == DEFAULT_PREFIX, "unsupported VFPU prefix")
        vd, vs, vt = w & 127, (w >> 8) & 127, (w >> 16) & 127
        n = 1 + ((w >> 7) & 1) + 2 * ((w >> 15) & 1)
        if w in (0xF004A088, 0xF010AC14, 0xF00CA490):
            s, t, out = self.matrix(vs, n), self.matrix(vt, n), [0.] * 16
            for a in range(n):
                for b in range(n):
                    total = 0.
                    for k in range(4 if a == b == n - 1 else n):
                        total = f32(total + f32(s[b * 4 + k] * t[a * 4 + k]))
                    out[a * 4 + b] = total
            for logical, physical in mindices(vd, n):
                self.v[physical] = out[logical]
            name = f'vmmul.{n} vd={vd:#x} vs={vs:#x} vt={vt:#x}'
        elif w == 0xF193A497:
            s = self.matrix(vs, 4)
            t = [self.reg(i) for i in vindices(vt, 4)]
            out = []
            for a in range(4):
                total = f32(s[a * 4] * t[0])
                for k in range(1, 4):
                    total = f32(total + f32(s[a * 4 + k] * t[k]))
                out.append(total)
            for i, value in zip(vindices(vd, 4), out):
                self.v[i] = value
            name = 'vtfm4.q C530,E100,C430'
        elif w in (0x65098010, 0x65298111, 0x65498212, 0x65088090, 0x65088191, 0x65088292, 0x65099010, 0x65299111, 0x65499212, 0x6508808C, 0x6508818D, 0x6508828E):
            s, t = [self.reg(i) for i in vindices(vs, n)], self.reg(vindices(vt, 1)[0])
            for i, value in zip(vindices(vd, n), s):
                self.v[i] = f32(value * t)
            name = f'vscl.{n} vd={vd:#x} vs={vs:#x} scalar={vt:#x}'
        elif w in (0xD0060074, 0xD0060075, 0xD0060076):
            self.v[vindices(vd, 1)[0]] = 0.
            name = f'vzero.s {vd:#x}'
        else:
            raise ValueError(f'unsupported VFPU opcode {w:#010x}')
        self.prefix = DEFAULT_PREFIX
        return name

    def execute(self, pc: int) -> int | None:
        w = self.instruction(pc)
        op, rs, rt = w >> 26, (w >> 21) & 31, (w >> 16) & 31
        imm = w & 0xffff
        signed = imm - 0x10000 if imm & 0x8000 else imm
        target = None
        if w == 0:
            name = 'nop'
        elif op == 9:
            self.r[rt] = (self.r[rs] + signed) & 0xffffffff; name = 'addiu'
        elif op == 15:
            self.r[rt] = imm << 16; name = 'lui'
        elif op == 13:
            self.r[rt] = self.r[rs] | imm; name = 'ori'
        elif op == 11:
            self.r[rt] = int(self.r[rs] < (signed & 0xffffffff)); name = 'sltiu'
        elif op == 0 and w & 63 == 37:
            self.r[(w >> 11) & 31] = self.r[rs] | self.r[rt]; name = 'or/move'
        elif op == 35:
            self.r[rt] = self.read((self.r[rs] + signed) & 0xffffffff); name = 'lw'
        elif op == 43:
            self.write((self.r[rs] + signed) & 0xffffffff, self.r[rt]); name = 'sw'
        elif op == 17 and rs == 4:
            self.f[(w >> 11) & 31] = self.r[rt]; name = 'mtc1'
        elif op == 17 and rs == 0:
            x = self.f[(w >> 11) & 31]; check(x is not None, 'uninitialized FPR'); self.r[rt] = x; name = 'mfc1'
        elif w == 0x460D6032:
            check(self.f[12] is not None and self.f[13] is not None, 'f12/f13 not retained')
            self.cc = u2f(self.f[12]) == u2f(self.f[13]); name = 'c.eq.s f12,f13'
        elif op in (54, 62):
            vreg = rt | ((w & 1) << 5)
            offset = w & 0xfffc; offset -= 0x10000 if offset & 0x8000 else 0
            address = (self.r[rs] + offset) & 0xffffffff
            for component, i in enumerate(vindices(vreg, 4)):
                if op == 54:
                    self.v[i] = u2f(self.read(address + 4 * component))
                else:
                    self.write(address + 4 * component, f2u(self.reg(i)))
            name = 'lv.q' if op == 54 else 'sv.q'
        elif w == 0x48E80008:
            self.v[vindices(8, 1)[0]] = u2f(self.r[8]); name = 'mtv t0,S200'
        elif op == 3:
            self.r[31] = pc + 8; target = ((pc + 4) & 0xf0000000) | ((w & 0x3ffffff) << 2); name = 'jal'
        elif op == 0 and w & 63 == 8:
            target = self.r[rs]; name = 'jr'
        elif op in (4, 5, 20):
            take = self.r[rs] == self.r[rt]
            if op == 5: take = not take
            target = pc + 4 + signed * 4 if take else pc + 8
            if op == 20 and not take: target = -(pc + 8)
            name = 'beql' if op == 20 else 'beq/bne'
        elif op == 17 and rs == 8 and rt == 0:
            check(self.cc is not None, 'uninitialized FPU condition')
            target = pc + 4 + signed * 4 if not self.cc else pc + 8; name = 'bc1f'
        else:
            try:
                name = self.vfpu(w)
            except ValueError as error:
                raise ValueError(f'{error} at {pc:#010x}') from error
        check(self.r[0] == 0, 'write to zero GPR')
        self.trace.append({'pc': f'0x{pc:08x}', 'word': f'0x{w:08x}', 'instruction': name})
        return target

    def run(self, start: int, stop: int) -> None:
        pc = start
        while pc != stop:
            check(len(self.trace) < 512, 'instruction bound exceeded')
            target = self.execute(pc)
            if target is None:
                pc += 4
            elif target < 0:
                pc = -target
            else:
                check(self.execute(pc + 4) is None, 'branch in delay slot')
                pc = target

    def extract(self, at: int, size: int = 64) -> bytes:
        return b''.join(struct.pack('<I', self.read(at + i)) for i in range(0, size, 4))


def comparison(predicted: bytes, actual: bytes) -> dict:
    p, a = words(predicted), words(actual)
    check(len(p) == len(a), 'output comparison size mismatch')
    diffs = [{'index': i, 'predicted_word': f'0x{x:08x}', 'actual_word': f'0x{y:08x}', 'absolute_error': abs(u2f(x) - u2f(y))} for i, (x, y) in enumerate(zip(p, a)) if x != y]
    return {'bit_equal': not diffs, 'differing_f32_words': len(diffs), 'different_bits': sum((x ^ y).bit_count() for x, y in zip(p, a)),
            'max_absolute_error': max((abs(u2f(x) - u2f(y)) for x, y in zip(p, a)), default=0.),
            'predicted_hex': predicted.hex(), 'actual_hex': actual.hex(), 'differences': diffs}


def verify_code(capture: dict, module: bytes, address: int, size: int, required: bool = True) -> bool:
    matches = [x for x in capture['codeIdentity']['checks'] if x['address'] == address and x['size'] == size]
    check(matches or not required, f'full runtime code identity missing {address:#x}/{size:#x}')
    expected = module[address - BASE:address - BASE + size]
    for block in matches:
        check(block['verified'] and sidecar(block['expected']) == expected, 'runtime expected code mismatch')
        # Live raw may contain the one owned BREAK; the decoded window must
        # restore it, independently of producer's verified boolean.
        check('decoded' in block and sidecar(block['decoded']) == expected, 'runtime decoded original code mismatch')
        check(sidecar(block['original']) == expected, 'runtime unmodified original code mismatch')
        raw_words = words(sidecar(block['raw']))
        check(len(raw_words) == size // 4, 'runtime raw code extent mismatch')
        # PPSSPP may retain 0x68xxxxxx execution-cache replacements in its
        # physical RAM view. Never execute these as guest original opcodes.
        # Both separately retained original/decoded byte views above must
        # independently equal the pinned module over the full function.
        check(all(x == y or x & 0xfc00003f == 0x0000000d or x & 0xfc000000 == 0x68000000 for x, y in zip(raw_words, words(expected))), 'unknown physical code replacement')
    return bool(matches)


def decode_registers(entry: dict) -> dict:
    raw = sidecar(entry['allRegisters']['raw'])
    r = json.loads(raw)
    check(r['event'] == 'cpu.getAllRegs', 'raw register response event mismatch')
    cats = r['categories']
    check(len(cats) == 3, 'unsupported runtime register category count')
    for index, name, count in ((0, 'GPR', 35), (1, 'FPU', 32), (2, 'VFPU', 128)):
        c = cats[index]
        check(c['id'] == index and c['name'] == name and len(c['uintValues']) == len(c['registerNames']) == count, 'unknown register category shape/name/id')
        check(all(type(x) is int and 0 <= x <= 0xffffffff for x in c['uintValues']), 'invalid register uint bits')
    check(cats[1]['registerNames'] == ['f' + str(i) for i in range(32)], 'unknown FPU register naming')
    check(cats[0]['uintValues'][:32] == entry['gpr'] and cats[0]['registerNames'][32:] == ['pc', 'hi', 'lo'] and cats[0]['uintValues'][32] == entry['pc'], 'same-stage GPR/PC raw mismatch')
    f12 = cats[1]['uintValues'][cats[1]['registerNames'].index('f12')]
    return {'raw_sha256': sha(raw), 'categories': [{'id': x['id'], 'name': x['name'], 'register_count': len(x['uintValues'])} for x in cats],
            'f12_uint': f12, 'f12_hex': f'0x{f12:08x}', 'f12_float': u2f(f12), 'prefixes_observed': False,
            'prefix_boundary': 'Official getAllRegs exports 32 GPR+PC/HI/LO, 32 FPR, 128 VFPU data; no VFPU S/T/D controls.'}


def verify_matrix_row(row: dict, module: bytes) -> dict:
    entry, returned = row['matrix']['entry'], row['matrix']['returned']
    check(entry['pc'] == 0x08b66bb4 and entry['mode'] == entry['gpr'][7] and entry['mode'] in (0, 1), 'only observed matrix modes0/1 are supported')
    g = entry['gpr']
    check(entry['sp'] == g[29] and entry['ra'] == g[31] == returned['pc'] and returned['sp'] == g[29], 'matrix entry/return ABI mismatch')
    check(type(entry['ticks']) is int and type(returned['ticks']) is int and 0 <= entry['ticks'] < returned['ticks'], 'matrix guest progress is unknown/nonpositive')
    check(entry['inputPointer'] == g[6] and entry['outputPointer'] == g[8], 'matrix input/output pointer mismatch')
    context = window(entry['context'], address=g[4]); node = window(entry['node'], address=g[5])
    p = struct.unpack_from('<I', context, 0x8c)[0]
    check(struct.unpack_from('<I', context, 0x90)[0] == g[5] and struct.unpack_from('<I', node, 0x1c)[0] == 0, 'unsupported parent/context path')
    check(struct.unpack_from('<I', node, 0x50)[0] == g[6], 'node input pointer mismatch')
    window(entry['state'], address=p)
    window(entry['p60'], 64, p + 0x60); window(entry['input'], 64, g[6]); window(entry['outputBefore'], 64, g[8])
    global_ptr = words(window(entry['globalSlot'], 4, 0x08c3b58c))[0]
    window(entry['globalMatrix'], 64, global_ptr)
    mode = entry['modeSource']
    indices = window(mode['indices'], 4)
    index = struct.unpack_from('<H', indices, 2)[0]
    check(index == mode['index'] and index < 96, 'mode component index mismatch')
    slots = struct.unpack_from('<I', node, 0x48)[0]
    pointer = words(window(mode['slot'], 4, slots + 4 * index))[0]
    address = pointer + 1
    check(mode['componentPointer'] == pointer and mode['fieldAddress'] == address and mode['byteOffset'] == address % 4, 'component byte address mismatch')
    component = window(mode['component'], 4, address & ~3)
    check(component[address % 4] == entry['mode'], 'raw component does not select observed mode')
    regs = decode_registers(entry)
    m = Machine(module, g)
    m.f[12] = regs['f12_uint']
    for key in ('context', 'node', 'state', 'handlerStack', 'globalSlot', 'globalMatrix', 'input', 'p60', 'outputBefore'):
        item = entry[key]
        m.retain(item['address'], window(item), write=key in ('handlerStack', 'outputBefore'))
    m.writable.append((g[29] - 0xf0, g[29]))
    m.run(entry['pc'], returned['pc'])
    check(m.r == returned['gpr'], 'replayed 32 returned GPR values differ')
    predicted = m.extract(g[8]); actual = window(returned['output'], 64, g[8])
    return {'status': 'raw_output_compared_under_default_entry_prefix', 'mode': entry['mode'], 'node_parent1c': 0, 'registers': regs,
            'comparison': comparison(predicted, actual), 'all32_returned_GPR_exact': True, 'executed_instruction_count': len(m.trace),
            'opcode_trace': m.trace, 'entry_ticks': entry['ticks'], 'return_ticks': returned['ticks'],
            'prefix_assumption': list(DEFAULT_PREFIX), 'prefix_assumption_observed': False, 'muzzle_semantics_verified': False}


def verify_view_row(row: dict, module: bytes) -> dict:
    view = row['view']['entry']
    h = row['matrix']['entry']['sp']
    check(view['pc'] == 0x08c01088 and view['sp'] == view['gpr'][29] == h - 0x60, 'VIEW writer ABI/SP mismatch')
    check(type(view['ticks']) is int and view['ticks'] > row['matrix']['returned']['ticks'], 'VIEW guest progress is unknown/nonpositive')
    check(view['gpr'][5] == 1 and view['gpr'][6] == h - 0x50, 'VIEW kind/input ABI mismatch')
    handler = window(view['handlerMatrix'], 64, h + 0x10)
    actual = window(view['input'], 64, h - 0x50)
    slot = window(view['globalSlot'], 4, 0x08c3b588)
    ptr = words(slot)[0]
    glob = window(view['globalMatrix'], 64, ptr)
    # Mode1 branches end with vzero.s; mode0 ends with vmmul. Both EatPrefixes.
    # The original handler152/155 path from its matrix
    # return to BBB8D4 has no VFPU/prefix operation (155 may do COP1 math).
    # This proves default VIEW-entry prefixes independently of missing entry
    # prefix controls. We use the retained handler matrix, not assume that
    # handler155 kept the matrix return translation unchanged.
    g = [0] * 32; g[4] = h + 0x10; g[29] = h
    stack = window(view['stack'], 0x60, h - 0x60)
    check(words(stack)[0] == 0x08bbb924, 'VIEW wrapper saved RA mismatch')
    g[31] = struct.unpack_from('<I', stack, 0x50)[0]
    expected_ra = {152: 0x08b982bc, 155: 0x08b9a840}[row['dispatch']['actualType']]
    check(g[31] == expected_ra, 'handler VIEW caller RA mismatch')
    m = Machine(module, g)
    m.retain(h + 0x10, handler); m.retain(0x08c3b588, slot); m.retain(ptr, glob)
    m.writable.append((h - 0x50, h))
    m.run(0x08bbb8d4, 0x08bfff6c)
    check(m.r[29] == h - 0x50 and m.r[4] == 1 and m.r[5] == h - 0x50, 'replayed VIEW wrapper ABI mismatch')
    return {'status': 'actual_VIEW_input_compared', 'comparison': comparison(m.extract(h - 0x50), actual),
            'matrix_return_matches_view_handler': window(row['matrix']['returned']['output'], 64) == handler,
            'entry_prefix_provenance': 'Mode1 final vzero.s / mode0 final vmmul resets all prefixes; verified handler152/155 continuation contains no VFPU/prefix operation before VIEW compose.',
            'executed_instruction_count': len(m.trace), 'opcode_trace': m.trace, 'muzzle_semantics_verified': False}


def verify_capture(path: Path, module: bytes, include_inflight: bool) -> dict:
    raw = path.read_bytes(); capture = json.loads(raw)
    check(capture['schema'] == 'weapon-marker-render-dispatch-capture/v1' and capture['probe'] == 'cpu-ge-emit-v1', 'unknown capture schema/probe')
    check(capture['module']['sha256'] == MODULE_SHA and sha(Path(capture['module']['file']).read_bytes()) == MODULE_SHA, 'capture module differs')
    for address, size in ((0x08b66bb4, 0x3b4), (0x08bbb8d4, 0x5c)): verify_code(capture, module, address, size)
    rows = [(x, False) for x in capture['rows']]
    if include_inflight and capture['inFlight'] is not None:
        rows.append((capture['inFlight'], True))
    check(rows, 'no selected rows to verify')
    output = []
    for row, partial in rows:
        typ = row['dispatch']['actualType']
        check(typ in (152, 155), 'unsupported handler type')
        verify_code(capture, module, {152: 0x08b9809c, 155: 0x08b9a514}[typ], {152: 0x3f0, 155: 0x808}[typ])
        item = {'sample': row['sample'], 'handler_type': typ, 'partial_inflight': partial}
        if 'returned' in row.get('matrix', {}):
            item['matrix'] = verify_matrix_row(row, module)
            helper_address, helper_size = (0x08b6589c, 0x104) if item['matrix']['mode'] == 1 else (0x08b657f8, 0xa4)
            helper_live = verify_code(capture, module, helper_address, helper_size, required=False)
            item['matrix']['selected_helper'] = {'address': helper_address, 'bytes': helper_size, 'runtime_full_code_identity_present': helper_live,
                                                'module_sha256': MODULE_SHA, 'boundary': None if helper_live else 'Replay uses fixed-module helper bytes; this capture lacks the full live original/decoded helper window.'}
        elif partial:
            item['matrix'] = {'status': 'incomplete_no_actual_return_output', 'bit_equal': None}
        else:
            raise ValueError('complete row lacks matrix return')
        if 'input' in row.get('view', {}).get('entry', {}):
            check('comparison' in item['matrix'], 'VIEW lacks complete supported-mode provenance')
            item['view'] = verify_view_row(row, module)
        elif not partial:
            raise ValueError('complete row lacks actual VIEW input')
        else:
            item['view'] = {'status': 'incomplete_no_actual_VIEW_input'}
        output.append(item)
    comparisons = [item[stage]['comparison'] for item in output for stage in ('matrix', 'view') if 'comparison' in item[stage]]
    return {'file': str(path.resolve()), 'sha256': sha(raw), 'capture_failure': capture['failure'], 'capture_inflight_present': capture['inFlight'] is not None,
            'capture_complete': capture['failure'] is None and capture['inFlight'] is None,
            'rows': output, 'compared_stage_count': len(comparisons), 'all_compared_raw_outputs_bit_exact': bool(comparisons) and all(x['bit_equal'] for x in comparisons),
            'all_prefix_controls_observed': False, 'all_selected_helpers_full_runtime_code_identity_present': all(x.get('matrix', {}).get('selected_helper', {}).get('runtime_full_code_identity_present', False) for x in output),
            'semanticName': None, 'muzzle_semantics_verified': False}


def static_evidence(module: bytes, out: Path) -> dict:
    source_dir = ROOT / 'raw/ppsspp_v1.20.4_vfpu_reference'
    sources = json.loads((source_dir / 'sources.json').read_text(encoding='utf-8'))
    for item in sources['files']:
        check(item['name'] in REFERENCE_SHA and item['sha256'] == REFERENCE_SHA[item['name']], 'reference manifest changed')
        check(sha((source_dir / item['name']).read_bytes()) == REFERENCE_SHA[item['name']], 'pinned reference differs')
    reg_dir = ROOT / 'out/WEAPON_GE_MATRIX_MATH_20261020/reference'
    register_sources = json.loads((reg_dir / 'sources.json').read_text(encoding='utf-8'))
    for item in register_sources:
        check(Path(item['file']).name in REGISTER_REFERENCE_SHA and item['sha256'] == REGISTER_REFERENCE_SHA[Path(item['file']).name], 'register source manifest changed')
        check(sha(Path(item['file']).read_bytes()) == item['sha256'], 'pinned register source differs')
    funcs = []
    for address, size in FUNCTIONS:
        raw = module[address - BASE:address - BASE + size]
        existing = ROOT / f'out/WEAPON_GE_EMIT_STATIC_20261020/function_{address:08x}.bin'
        if existing.exists(): check(existing.read_bytes() == raw, 'frozen original function differs')
        target = out / f'function_{address:08x}.bin'; target.write_bytes(raw)
        funcs.append({'address': address, 'bytes': size, 'sha256': sha(raw), 'file': str(target),
                      'words': [{'pc': f'0x{address + i * 4:08x}', 'word': f'0x{w:08x}'} for i, w in enumerate(words(raw))]})
    return {'module_sha256': MODULE_SHA, 'official_reference_sources': sources, 'official_register_sources': register_sources, 'functions': funcs,
            'memory_layout': '16 little-endian f32 values, column-major; translation at byte0x30',
            'mode_dispatch_after_unsigned_subtract_one': {'1': '08b6589c', '2': '08b659a0 (not replayed)', '3': '08b6589c plus translation transform (not replayed)', '4': '08b6589c plus two translation transforms (not replayed)', '5': '08b65ac4 (not replayed)', '6': '08b657f8 plus subtract global translation (not replayed)', 'other': '08b657f8 (not replayed)'},
            'mode1_equation': 'Output basis = global58c.basis * columns(input.basis scaled by P+30.xyz); if f12 != 1 input basis is first multiplied by f12 with separate f32 rounding. Output translation4 = effectiveParent64 * input.translation4; output first3 bottom-row elements forced +0. effectiveParent = P+60 if node+1c==0, otherwise [nodeParent+54].',
            'mode0_equation': 'Output = effectiveParent4x4 * input4x4 with the first3 full input columns scaled by f12 if f12 != 1. Translation column remains unscaled. Original mode0 takes unsigned-default branch after subtracting1.',
            'view_equation': 'Output = global588_4x4 * handlerMatrix_4x4; raw VS=0x20 transposes physical M000 in vmmul.q; no affine row is discarded in this function.',
            'precision_model': 'Finite f32 multiply then f32 add in opcode order, non-fused pinned PPSSPP interpreter path; runtime JIT/MoreAccurateVMMUL may differ. No numerical tolerance establishes equivalence.',
            'unsupported': ['matrix modes other than0/1', 'nondefault entry S/T/D prefix', 'nonfinite arithmetic', 'unretained memory/opcode/control flow'],
            'semanticName': None, 'muzzle_semantics_verified': False}


def selftest(module: bytes) -> dict:
    """Small synthetic opcode/shape checks; explicitly not runtime evidence."""
    passed = []
    c, p, n, inp, output, global_matrix, sp, ret = (0x09001000, 0x09002000, 0x09003000, 0x09004000, 0x09005000, 0x09006000, 0x09fff000, 0x08b982b4)
    def pack(values: list[float]) -> bytes:
        return struct.pack('<16f', *values)
    def setup(scale: float) -> tuple[Machine, list[float], list[float], list[float], list[float]]:
        r = [0] * 32; r[4:9] = [c, n, inp, 1, output]; r[29], r[31] = sp, ret
        m = Machine(module, r); m.f[12] = f2u(scale)
        m.retain(c + 0x8c, struct.pack('<I', p)); m.retain(n + 0x1c, bytes(4))
        original = [1., 2., 3., 0., -4., 5., -6., 0., 7., -8., 9., 0., 11., -12., 13., 1.]
        parent = [0., 1., 2., 0., 3., 4., 5., 0., 6., 7., 8., 0., 9., 10., 11., 1.]
        glob = [1., 3., 5., 0., 2., 4., 6., 0., 7., 8., 10., 0., 90., 100., 110., 1.]
        factors = [2., 3., 4., 1.]
        m.retain(inp, pack(original)); m.retain(p + 0x60, pack(parent)); m.retain(p + 0x30, struct.pack('<4f', *factors))
        m.retain(0x08c3b58c, struct.pack('<I', global_matrix)); m.retain(global_matrix, pack(glob))
        m.retain(output, bytes(64), True); m.writable.append((sp - 0xf0, sp))
        return m, original, parent, glob, factors
    for scale in (1., .625):
        m, i, l, g, factors = setup(scale)
        m.run(0x08b66bb4, ret)
        expected = [0.] * 16
        for col in range(3):
            scaled = [f32(f32(i[col * 4 + k] * scale) * factors[col]) for k in range(3)]
            for row in range(3):
                value = 0.
                for k in range(3): value = f32(value + f32(g[k * 4 + row] * scaled[k]))
                expected[col * 4 + row] = value
        for row in range(4):
            value = f32(l[row] * i[12])
            for k in range(1, 4): value = f32(value + f32(l[k * 4 + row] * i[12 + k]))
            expected[12 + row] = value
        check(m.extract(output) == pack(expected), 'synthetic mode1 opcode/direct-equation mismatch')
        passed.append(f'mode1_noncommutative_nonsymmetric_scale_{scale}')
    for scale in (1., .625):
        m, i, l, _, _ = setup(scale); m.r[7] = 0
        # Non-affine bottom rows test that mode0 scales all four components
        # of each basis column and performs the complete 4x4 operation.
        i[3], i[7], i[11] = .5, -.25, .75
        l[3], l[7], l[11], l[15] = .25, -.5, .125, 2.
        for address, values in ((inp, i), (p + 0x60, l)):
            for index, value in enumerate(words(pack(values))): m.mem[address + 4 * index] = value
        m.run(0x08b66bb4, ret)
        expected = [0.] * 16
        for col in range(4):
            scaled = [f32(i[col * 4 + k] * scale) if col < 3 and scale != 1. else i[col * 4 + k] for k in range(4)]
            for row in range(4):
                value = 0.
                for k in range(4): value = f32(value + f32(l[k * 4 + row] * scaled[k]))
                expected[col * 4 + row] = value
        check(m.extract(output) == pack(expected), 'synthetic mode0 full4x4 mismatch')
        passed.append(f'mode0_nonaffine_full4x4_scale_{scale}')
    # VIEW independently executes original loads, transposed VS vmmul and stores.
    r = [0] * 32; r[4], r[29] = inp, sp
    m = Machine(module, r); m.retain(inp, pack(i)); m.retain(global_matrix, pack(g)); m.retain(0x08c3b588, struct.pack('<I', global_matrix)); m.writable.append((sp - 0x50, sp))
    m.run(0x08bbb8d4, 0x08bfff6c)
    expected = [0.] * 16
    for col in range(4):
        for row in range(4):
            value = 0.
            for k in range(4): value = f32(value + f32(g[k * 4 + row] * i[col * 4 + k]))
            expected[col * 4 + row] = value
    check(m.extract(sp - 0x50) == pack(expected), 'synthetic VIEW product order mismatch')
    passed.append('view_nonsymmetric_global_times_input')
    def reject(name, action):
        try: action()
        except ValueError: passed.append(name)
        else: raise ValueError('negative selftest accepted: ' + name)
    reject('unretained_read_rejected', lambda: Machine(module, [0] * 32).read(0x9000000))
    reject('unbounded_write_rejected', lambda: Machine(module, [0] * 32).write(0x9000000, 0))
    reject('nondefault_prefix_rejected', lambda: Machine(module, [0] * 32, (0, 0xe4, 0)))
    reject('unknown_vfpu_rejected', lambda: Machine(module, [0] * 32).vfpu(0xffffffff))
    reject('uninitialized_vfpu_rejected', lambda: Machine(module, [0] * 32).vfpu(0xf004a088))
    reject('nonfinite_rejected', lambda: u2f(0x7f800000))
    reject('unsupported_control_flow_rejected', lambda: Machine(module, [0] * 32).instruction(0x08b659a0))
    zero_difference = comparison(struct.pack('<I', 0), struct.pack('<I', 0x80000000))
    check(not zero_difference['bit_equal'] and zero_difference['different_bits'] == 1 and zero_difference['max_absolute_error'] == 0., 'signed zero was incorrectly called bit-equivalent')
    passed.append('signed_zero_numeric_equality_is_not_bit_equivalence')
    return {'passed': True, 'cases': passed, 'count': len(passed), 'runtime_evidence': False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, action='append', default=[])
    parser.add_argument('--include-inflight', action='store_true', help='Explicitly inspect retained partial stages; does not assert capture completion')
    parser.add_argument('--out', type=Path, default=ROOT / 'out/WEAPON_GE_MATRIX_MATH_20261020')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    module = (ROOT / 'raw/ULJM05798_module_08804000.bin').read_bytes()
    check(sha(module) == MODULE_SHA, 'fixed original module SHA mismatch')
    source = Path(__file__).read_bytes(); frozen = args.out / 'verify_weapon_ge_matrix_math_frozen.py'
    frozen.write_bytes(source)
    result = {'schema': 't3b-weapon-ge-matrix-math/v1', 'verifier_sha256': sha(source),
              'verifier_frozen_source': {'file': str(frozen.resolve()), 'bytes': len(source), 'sha256': sha(source), 'scope': 'Frozen source identity; ROOT still refers to the original tools-location layout when executed.'},
              'static': static_evidence(module, args.out), 'selftest': selftest(module), 'captures': [], 'actual_runtime_math_verified': False}
    result['captures'] = [verify_capture(p, module, args.include_inflight) for p in args.capture]
    result['status'] = 'actual_retained_stages_compared' if args.capture else 'static_recovered_awaiting_complete_runtime_capture'
    result['actual_sample_outputs_bit_exact'] = bool(result['captures']) and all(x['all_compared_raw_outputs_bit_exact'] for x in result['captures'])
    result['entry_prefix_controls_observed'] = False
    result['unconditional_all_mode_equivalence_verified'] = False
    result['actual_runtime_math_verified'] = False
    path = args.out / 'matrix_math_verification.json'
    path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'report': str(path), 'status': result['status']}))
    return int(bool(args.capture) and not result['actual_sample_outputs_bit_exact'])


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, OSError, OverflowError) as error:
        print(f'REJECTED: {error}', file=sys.stderr)
        raise SystemExit(1)
