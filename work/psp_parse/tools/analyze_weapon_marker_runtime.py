"""Audit retained helper-entry captures without connecting to an emulator."""
import argparse
import collections
import hashlib
import json
import struct
from pathlib import Path


BASE = 0x08804000
WEAPON_SHA = '168578abca4c4f5d22d5994ebced6b93a25d5167428bfd47f1a1150a8d42e65a'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check(condition, message):
    if not condition:
        raise ValueError(message)


def audit(path, hz):
    raw = path.read_bytes()
    report = json.loads(raw)
    module = Path(report['module']['file']).read_bytes()
    check(sha(module) == report['module']['sha256'], 'selected module SHA differs')
    check(report['codeIdentity']['verified'] and not report['failure'], 'probe identity/failure')
    check(not report['cleanup']['errors'] and report['cleanup']['buttonsReleased'] and report['cleanup']['breakpointRemoved'], 'probe cleanup incomplete')
    check(report['expectedGeometrySHA256'] == WEAPON_SHA, 'geometry identity differs')
    checks = []
    for block in report['codeIdentity']['blocks']:
        expected = module[block['address'] - BASE:block['address'] - BASE + block['bytes']]
        check(len(expected) == block['bytes'], 'code block outside module')
        check(Path(block['expectedFile']).read_bytes() == expected, 'expected sidecar differs from module')
        for key, digest in [('originalFile', 'originalSHA256'), ('decodedFile', 'decodedSHA256')]:
            data = Path(block[key]).read_bytes()
            check(data == expected and sha(data) == block[digest], f'{key} differs from original module')
        disasm = json.loads(Path(block['disasmFile']).read_text(encoding='utf-8'))
        encoded = {}
        for line in disasm['lines']:
            at, size = line['address'], line['addressSize']
            if at >= block['address'] + block['bytes'] or at + size <= block['address']:
                continue
            check(line['type'] in ('opcode', 'macro') and size >= 4 and size % 4 == 0, 'non-opcode line')
            values = [line['encoding']] if size == 4 else line['macroEncoding']
            check(len(values) == size // 4 and values[0] == line['encoding'], 'invalid macro')
            for i, word in enumerate(values):
                address = at + 4 * i
                if block['address'] <= address < block['address'] + block['bytes']:
                    check(address not in encoded, 'overlapping opcode')
                    encoded[address] = word
        rebuilt = b''.join(struct.pack('<I', encoded[a]) for a in range(block['address'], block['address'] + block['bytes'], 4))
        check(rebuilt == expected, 'disassembly independently reconstructed original words differ')
        checks.append({'address': block['address'], 'bytes': len(expected), 'sha256': sha(expected), 'raw_difference_count': len(block['differences'])})

    indices, chains, states, source_shas, actors = collections.Counter(), collections.Counter(), {}, collections.Counter(), set()
    ticks = []
    for row in report['rows']:
        check(row['pc'] == 0x08b44580 and row['a2_index'] in (1, 2), 'entry/index mismatch')
        check(row['geometrySHA256'] == WEAPON_SHA, 'retained row weapon geometry differs')
        source = Path(row['sourceFile']).read_bytes()
        check(len(source) == 0x130 and sha(source) == row['sourceSHA256'], 'source sidecar mismatch')
        check(row['sourceAddress'] == row['sourceBase'] + row['a2_index'] * 0x130, 'source indexing mismatch')
        check(list(struct.unpack_from('<16I', source, 0x40)) == row['sourceMatrix40Words'], '+40 words differ')
        stack = Path(row['stackFile']).read_bytes()
        check(sha(stack) == row['stackSHA256'], 'stack sidecar SHA differs')
        check(row['ra'] == 0x08b3e62c, 'different wrapper chain; classify separately before extending this audit')
        outer = struct.unpack_from('<I', stack, 0x84)[0]
        layouts = {0x08bbc688: (0xfc, 0xf0), 0x08bbca40: (0x17c, 0x170), 0x08bbccd0: (0x17c, 0x170), 0x08bbce3c: (0xfc, 0xf0)}
        check(outer in layouts, 'unknown attachment frame')
        ra_offset, s1_offset = layouts[outer]
        parent = struct.unpack_from('<I', stack, 0x90 + ra_offset)[0]
        state = row['attachmentStateCandidate']
        check(state is not None and state['address'] == struct.unpack_from('<I', stack, 0x90 + s1_offset)[0], 'state stack identity differs')
        primary, secondary = state['raw140'][1:3]
        check(row['wrapperActorHandle']['firstWordEqualsActor'] and primary == row['wrapperActorHandle']['address'], 'primary +144 is not verified actor handle')
        # Legacy captures named only +148; classify from preserved raw140.
        check(primary == state.get('primaryActorHandle144', primary), '+144 field differs')
        check(secondary == state.get('secondaryActorHandle148', state.get('actorHandle148', secondary)), '+148 field differs')
        indices[row['a2_index']] += 1
        chains[f'{row["ra"]:08x}->{outer:08x}->{parent:08x}'] += 1
        states[str(state['address'])] = {'address': state['address'], 'primaryActorHandle144': primary,
            'secondaryActorHandle148': secondary, 'selector14c': state['selector14c'], 'selector14e': state['selector14e'],
            'primaryHandleMatchesVerifiedWrapperHandle': True}
        source_shas[row['sourceSHA256']] += 1
        actors.add(row['a1_drawable'])
        ticks.append(row['ticks'])
    check(all(a <= b for a, b in zip(ticks, ticks[1:])), 'non-monotonic ticks')
    first_stop, last_stop = report.get('firstStopTicks'), report.get('lastStopTicks')
    if first_stop is not None or last_stop is not None:
        check(isinstance(first_stop, int) and isinstance(last_stop, int) and first_stop <= last_stop, 'invalid all-helper stop clock')
    return {'capture': str(path.resolve()), 'capture_sha256': sha(raw), 'version': report['version'],
        'stopCount': report['stopCount'], 'globalIndexCounts': report['indexCounts'], 'retained_weapon_rows': len(ticks),
        'firstStopTicks': first_stop, 'lastStopTicks': last_stop,
        'all_helper_span_seconds': (last_stop-first_stop)/hz if first_stop is not None else None,
        'retained_weapon_indices': dict(indices), 'chains': dict(chains), 'states': list(states.values()), 'actors': sorted(actors),
        'ticks_first': ticks[0] if ticks else None, 'ticks_last': ticks[-1] if ticks else None,
        'retained_span_ticks': ticks[-1] - ticks[0] if ticks else 0,
        'retained_span_seconds': (ticks[-1] - ticks[0]) / hz if ticks else 0,
        'source_sha_counts': dict(source_shas), 'code_identity_independent_checks': checks,
        'inputs': report['inputEvents'], 'cleanup': report['cleanup'], 'semanticName': None,
        'limits': ['Geometry identity is recorded by the producer; geometry bytes were not retained in this helper-entry capture.',
            'Source and WORLD are pre-lazy-update entry snapshots; no output matrix was captured.',
            'Row-count/time bounds truncate observation; no source2 row is not proof of absence.',
            'Caller state transformation is confirmed; specific FX/muzzle identity remains unresolved.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, action='append', required=True)
    parser.add_argument('--cpu-hz', type=float, default=333000000.0)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    check(args.cpu_hz > 0, 'invalid clock')
    results = [audit(path, args.cpu_hz) for path in args.capture]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({'schema': 'weapon-marker-retained-runtime-audit/v1', 'cpu_hz': args.cpu_hz,
        'captures': results, 'semanticName': None}, indent=2), encoding='utf-8')
    print(json.dumps({'out': str(args.out.resolve()), 'captures': len(results), 'rows': [r['retained_weapon_rows'] for r in results]}))


if __name__ == '__main__':
    main()
