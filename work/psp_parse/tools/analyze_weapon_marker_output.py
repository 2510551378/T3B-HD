"""Independently audit retained helper entry/return bytes; no emulator connection."""
import argparse
import hashlib
import json
import math
import struct
from pathlib import Path

BASE = 0x08804000
ENTRY, RETURN = 0x08B44580, 0x08B3E62C
GEOMETRY_SHA = '168578abca4c4f5d22d5994ebced6b93a25d5167428bfd47f1a1150a8d42e65a'
MODULE_SHA = 'b5fc590366fc610f2cdd60104a4a28851bacd402c4600a4c296776e1dea0869f'


def check(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sidecar(item):
    data = Path(item['file']).read_bytes()
    check(len(data) == item['bytes'] and sha(data) == item['sha256'], 'sidecar size/hash differs')
    return data


def matrix(item):
    data = sidecar(item)
    check(len(data) == 64, 'matrix must contain 16 F32 values')
    values = struct.unpack('<16f', data)
    check(list(struct.unpack('<16I', data)) == item['words'], 'matrix words differ')
    check(all(math.isfinite(v) for v in values), 'nonfinite matrix')
    check(list(values) == item['f32'], 'JSON float matrix differs from retained bytes')
    return values


def multiply(a, b):
    # Explicit row/column indexing independent of the JS linear-index implementation.
    result = [0.0] * 16
    for column in range(4):
        for row in range(4):
            result[column * 4 + row] = sum(a[k * 4 + row] * b[column * 4 + k] for k in range(4))
    return result


def errors(actual, predicted):
    delta = [x - y for x, y in zip(actual, predicted)]
    return {'max_abs': max(map(abs, delta)), 'rms': math.sqrt(sum(x*x for x in delta) / 16)}


def audit(path):
    capture_bytes = path.read_bytes()
    capture = json.loads(capture_bytes)
    check(capture['schema'] == 'weapon-marker-helper-output-capture/v1', 'wrong capture schema')
    check(capture['failure'] is None and capture['inFlight'] is None, 'failed/incomplete capture')
    check(capture['entryPC'] == ENTRY and capture['returnPC'] == RETURN, 'wrong helper ABI')
    check(capture['expectedGeometrySHA256'] == GEOMETRY_SHA, 'wrong selected geometry')
    cleanup = capture['cleanup']
    check(not cleanup['errors'] and cleanup['buttonsReleased'] and cleanup['ownedBreakpointRemoved'], 'cleanup incomplete')
    check(capture['ownedBP'] is None and capture['semanticName'] is None, 'ownership/semantic contract differs')
    module = Path(capture['module']['file']).read_bytes()
    check(sha(module) == capture['module']['sha256'] == MODULE_SHA, 'selected ULJM05798 module hash differs')
    names = []
    for block in capture['codeIdentity']['checks']:
        address, size = block['address'], block['size']
        expected = module[address - BASE:address - BASE + size]
        check(len(expected) == size and sidecar(block['expected']) == expected, 'expected module bytes differ')
        for field in ('original', 'decoded'):
            check(sidecar(block[field]) == expected, f'{field} code does not match module')
        sidecar(block['raw'])
        disassembly = json.loads(sidecar(block['disasm']))
        words = {}
        for line in disassembly['lines']:
            at, count = line['address'], line['addressSize']
            if at >= address + size or at + count <= address:
                continue
            check(line['type'] in ('opcode', 'macro') and count >= 4 and count % 4 == 0, 'invalid code line')
            encoded = [line['encoding']] if count == 4 else line['macroEncoding']
            check(len(encoded) == count // 4 and encoded[0] == line['encoding'], 'invalid macro coverage')
            for index, value in enumerate(encoded):
                pc = at + 4 * index
                if address <= pc < address + size:
                    check(pc not in words, 'overlapping disassembly')
                    words[pc] = value
        rebuilt = b''.join(struct.pack('<I', words[pc]) for pc in range(address, address + size, 4))
        check(rebuilt == expected and block['verified'], 'independent code reconstruction differs')
        names.append(block['name'])
    check(capture['codeIdentity']['verified'] and {'helper_full', 'wrapper_full'} <= set(names), 'full code identity missing')
    active = None
    for transition in capture['transitions']:
        operation = transition['operation']
        if operation == 'add_requested':
            check(active is None and transition['address'] in (ENTRY, RETURN), 'simultaneous/foreign owned BP')
            active = transition['address']
        elif operation == 'add_acknowledged':
            check(active == transition['address'], 'BP acknowledgement differs')
        elif operation == 'remove':
            check(active == transition['address'], 'removed an unowned BP')
            active = None
        else:
            raise ValueError(f'unknown BP transition: {operation}')
    check(active is None, 'owned BP not removed')
    rows = []
    for row in capture['rows']:
        check(row['entryPC'] == ENTRY and row['returnPC'] == RETURN and row['index'] == 1, 'wrong paired helper')
        check(row['entryTicks'] < row['returnTicks'], 'invalid entry/return time')
        check(row['entryGPR'][29] == row['sp'] == row['returnGPR'][29], 'return SP differs')
        check(row['entryGPR'][31] == row['ra'] == RETURN == row['returnGPR'][31], 'return RA differs')
        check(row['entryGPR'][4] == row['output'] == row['sp'] + 0x40, 'original output pointer differs')
        check(row['entryGPR'][5] == row['actor'] and row['entryGPR'][6] == 1, 'actor/index differs')
        check(all(row['entryGPR'][i] == row['returnGPR'][i] for i in (16, 17, 18)), 'callee-saved register differs')
        check(f"return_{row['sample']:04d}" in names, 'return opcode check missing')
        geometry = sidecar(row['geometry'])
        check(len(geometry) == 243*16 and sha(struct.pack('<I', 0x522) + geometry) == GEOMETRY_SHA, 'retained geometry differs')
        pre_source, post_source = sidecar(row['preSource']), sidecar(row['postSource'])
        check(len(pre_source) == len(post_source) == 0x130, 'source record size differs')
        check(pre_source[0x40:0x80] == sidecar(row['preSource40']), 'pre +40 slice differs')
        check(post_source[0x40:0x80] == sidecar(row['postSource40']), 'post +40 slice differs')
        actual, world, source = matrix(row['actualOutput']), matrix(row['postWorld']), matrix(row['postSource40'])
        pre_world, pre_local = matrix(row['preWorld']), matrix(row['preSource40'])
        stack = sidecar(row['entryStack'])
        outer = struct.unpack_from('<I', stack, 0x84)[0]
        frames = {0x08BBC688: 0xFC, 0x08BBCA40: 0x17C, 0x08BBCCD0: 0x17C, 0x08BBCE3C: 0xFC}
        check(outer in frames, 'unknown wrapper caller; classify before extending audit')
        parent = struct.unpack_from('<I', stack, 0x90 + frames[outer])[0]
        products = {'world_times_source40': multiply(world, source), 'source40_times_world': multiply(source, world)}
        measured = {key: errors(actual, value) for key, value in products.items()}
        for key, value in measured.items():
            check(abs(value['max_abs'] - row['comparison'][key]['max_abs']) < 1e-10, 'producer error calculation differs')
        rows.append({'sample': row['sample'], 'entry_ticks': row['entryTicks'], 'return_ticks': row['returnTicks'],
            'helper_duration_ticks': row['returnTicks'] - row['entryTicks'],
            'actor': row['actor'], 'chain': [RETURN, outer, parent], 'comparison': measured,
            'pre_world_times_source40': errors(actual, multiply(pre_world, pre_local)),
            'source_record_changed_during_call': pre_source != post_source,
            'world_changed_during_call': sidecar(row['preWorld']) != sidecar(row['postWorld']),
            'world_origin': list(actual[12:15]), 'world_forward_z': list(actual[8:11]), 'semanticName': None})
    check(rows, 'no actual output rows; audit cannot prove a transform relationship')
    check(all(a['return_ticks'] < b['entry_ticks'] for a, b in zip(rows, rows[1:])), 'overlapping/nonmonotonic pairs')
    return {'capture': str(path.resolve()), 'capture_sha256': sha(capture_bytes), 'rows_checked': len(rows),
        'helper_stops': capture['helperStopCount'], 'return_stops': capture['returnStopCount'],
        'all_owned_breakpoints_removed': True, 'code_blocks_checked': len(names), 'rows': rows,
        'max_world_times_source40_error': max(r['comparison']['world_times_source40']['max_abs'] for r in rows),
        'semanticName': None, 'limits': ['F64 comparison does not certify VFPU rounding identity.',
            'This proves helper output bytes/ABI and numerical comparisons, not a specific muzzle or FX consumer.',
            'Entry BP is disarmed while waiting for selected return; helper coverage is not exhaustive.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = {'schema': 'weapon-marker-helper-output-audit/v1', 'passed': True, **audit(args.capture)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('passed', 'rows_checked', 'max_world_times_source40_error')}))


if __name__ == '__main__':
    main()
