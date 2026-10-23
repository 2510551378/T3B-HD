"""Audit retained original marker -> generic -> final-state bytes offline."""
import argparse
import collections
import json
import math
import struct
from pathlib import Path

from analyze_weapon_marker_output import BASE, ENTRY, RETURN, GEOMETRY_SHA, MODULE_SHA
from analyze_weapon_marker_output import check, sha, sidecar, matrix, multiply, errors

GENERIC = 0x08B630DC
STATE_RETURNS = {0x08B63550, 0x08B6379C}
OUTER_RETURNS = {0x08B639C8, 0x08B69AEC, 0x08B69F00}


def f32(data, offset=0):
    return struct.unpack_from('<16f', data, offset)


def predict_common_state(marker, actor_basis, local, offset50, flags, position10):
    """F64 algebra for the observed low-flag paths, not a VFPU emulator.

    Derivation: selected module 08b632cc..08b63494. PPSSPP v1.20.4
    Int_Vmmul/Int_Vtfm and register layouts independently resolve the VFPU ops.
    High-basis and external Y-adjustment branches remain unsupported.
    """
    if flags & (0x00200000 | 0x10):
        return None
    rotation_basis = actor_basis if flags & 0x20 else marker
    translation_basis = actor_basis if flags & 0x40 else marker
    # 08b63470 reads P+10 only when both low flags are clear. Other paths
    # read P+90. Their equality in constructors is not assumed here.
    local_position = local[12:15] if flags & 0x60 else position10[:3]
    result = [0.0] * 16
    for column in range(3):
        for row in range(3):
            result[column*4 + row] = sum(rotation_basis[k*4 + row]*local[column*4 + k] for k in range(3))
    for row in range(3):
        result[12 + row] = (sum(translation_basis[k*4 + row]*local_position[k] for k in range(3))
                            + marker[12 + row] + offset50[row])
    result[15] = 1.0
    return result


def code_blocks(capture, module, required_ranges=None):
    names = []
    ranges = set()
    for block in capture['codeIdentity']['checks']:
        start, size = block['address'], block['size']
        expected = module[start - BASE:start - BASE + size]
        check(len(expected) == size, 'code range outside module')
        for key in ('expected', 'original', 'decoded'):
            check(sidecar(block[key]) == expected, f'{key} differs from selected module')
        sidecar(block['raw'])
        lines = json.loads(sidecar(block['disasm']))['lines']
        seen = {}
        for line in lines:
            at, count = line['address'], line['addressSize']
            if at >= start + size or at + count <= start:
                continue
            check(line['type'] in ('opcode', 'macro') and count >= 4 and count % 4 == 0, 'invalid disassembly')
            values = [line['encoding']] if count == 4 else line['macroEncoding']
            check(len(values) == count // 4 and values[0] == line['encoding'], 'macro coverage differs')
            for i, word in enumerate(values):
                address = at + i*4
                if start <= address < start + size:
                    check(address not in seen, 'overlapping code words')
                    seen[address] = word
        rebuilt = b''.join(struct.pack('<I', seen[pc]) for pc in range(start, start + size, 4))
        check(rebuilt == expected and block['verified'], 'independently rebuilt original code differs')
        names.append(block['name'])
        ranges.add((start, size))
    check(capture['codeIdentity']['verified'], 'code identity not verified')
    required = required_ranges if required_ranges is not None else {(ENTRY, 0x210), (0x08B3E610, 0x12C), (0x08BBC93C, 0x43C),
                (0x08B62E98, 0x654), (0x08B634EC, 0x438), (0x08BFD23C, 0x44)}
    check(required <= ranges, 'full helper/wrapper/generic/state/parent/copy64 identity coverage missing')
    return names


def audit(path):
    raw = path.read_bytes()
    capture = json.loads(raw)
    check(capture['schema'] == 'weapon-marker-state-output-capture/v1', 'capture schema differs')
    check(capture['failure'] is None and capture['inFlight'] is None, 'failed/incomplete capture')
    check(capture['semanticName'] is None and capture['ownedBP'] is None, 'semantic/BP contract differs')
    cleanup = capture['cleanup']
    check(not cleanup['errors'] and cleanup['buttonsReleased'] and cleanup['ownedBreakpointRemoved'], 'cleanup failed')
    module = Path(capture['module']['file']).read_bytes()
    check(sha(module) == capture['module']['sha256'] == MODULE_SHA, 'selected module differs')
    names = code_blocks(capture, module)
    active = None
    targets = {ENTRY, RETURN, GENERIC, *STATE_RETURNS}
    for transition in capture['transitions']:
        op, pc = transition['operation'], transition['address']
        if op == 'add_requested':
            check(active is None and pc in targets, 'simultaneous/foreign owned BP')
            active = pc
        elif op == 'add_acknowledged':
            check(active == pc, 'BP acknowledgement differs')
        elif op == 'remove':
            check(active == pc, 'removed unowned BP')
            active = None
        else:
            raise ValueError(f'unknown transition {op}')
    check(active is None, 'owned BP not removed')
    results = []
    for row in capture['rows']:
        h, p = row['sp'], row['statePointer']
        check(row['index'] == 1 and row['ra'] == RETURN and row['output'] == h + 0x40, 'helper entry differs')
        check(row['entryGPR'][29] == h and row['entryGPR'][31] == RETURN, 'entry SP/RA differs')
        check(row['entryGPR'][4] == h+0x40 and row['entryGPR'][5] == row['actor'], 'entry arguments differ')
        check(row['returnGPR'][29] == h and row['returnGPR'][31] == RETURN, 'helper return SP/RA differs')
        check(all(row['entryGPR'][i] == row['returnGPR'][i] for i in (16, 17, 18)), 'helper saved GPR differs')
        geometry = sidecar(row['geometry'])
        check(len(geometry) == 243*16 and sha(struct.pack('<I', 0x522)+geometry) == GEOMETRY_SHA, 'actual geometry differs')
        stack = sidecar(row['entryStack'])
        check(len(stack) >= 0x3AC, 'extended stack missing')
        u32 = lambda at: struct.unpack_from('<I', stack, at)[0]
        check(u32(0x84) == 0x08BBCCD0 and u32(0x20C) == GENERIC, 'selected caller chain differs')
        check(p == u32(0x200) == row['entryGPR'][20]-0x10 == row['entryGPR'][21]-0x90, 'state pointer crosschecks differ')
        state_ra, outer_ra = u32(0x360), u32(0x3A8)
        check(state_ra in STATE_RETURNS and outer_ra in OUTER_RETURNS, 'unknown upper caller')
        check(row['stateRA'] == state_ra and row['outerRA'] == outer_ra, 'saved RA interpretation differs')
        for phase in ('helper_return', 'generic_return', 'state_return'):
            check(f"{phase}_{row['sample']:04d}" in names, 'selected return opcode check missing')
        states = {name: sidecar(row[name]) for name in ('entryState', 'stateAfterHelper', 'stateAfterGeneric', 'stateAfterReturn')}
        check(all(len(data) == 0x1A4 for data in states.values()), 'state snapshot length differs')
        actual, generic = matrix(row['actualOutput']), matrix(row['genericOutput'])
        pre_all, post_all = sidecar(row['preSourcesAll']), sidecar(row['postSourcesAll'])
        check(len(pre_all) == len(post_all) == 3*0x130, 'dense source length differs')
        check(pre_all[0x130:0x260] == sidecar(row['preSource']), 'pre source1 slice differs')
        check(post_all[0x130:0x260] == sidecar(row['postSource']), 'post source1 slice differs')
        check(post_all[0x170:0x1B0] == sidecar(row['postSource40']), 'post source40 slice differs')
        check(sidecar(row['actualOutput']) == sidecar(row['genericOutput']), 'generic output not identical to helper')
        context = sidecar(row['genericContext'])
        check(len(context) == 0x160 and context[:64] == sidecar(row['genericOutput']), 'generic context differs')
        flags = struct.unpack_from('<I', context, 0x128)[0]
        check(flags == u32(0x338), 'saved flags changed before generic return')
        check(flags == struct.unpack_from('<I', states['entryState'], 0x154)[0], 'entry live/saved flags differ')
        gr, sr = row['genericReturn'], row['stateReturn']
        check(gr['pc'] == GENERIC and gr['sp'] == h+0x210 and gr['gpr'][29] == h+0x210, 'generic return SP/PC differs')
        check(gr['ra'] == GENERIC == gr['gpr'][31], 'generic return RA differs')
        check(sr['pc'] == state_ra and sr['sp'] == h+0x370 and sr['gpr'][29] == h+0x370, 'state return SP/PC differs')
        check(sr['ra'] == state_ra and sr['gpr'][31] == state_ra and sr['gpr'][16] == p, 'state epilogue differs')
        check(row['entryTicks'] < row['returnTicks'] < gr['ticks'] < sr['ticks'], 'return ticks are not ordered')
        final = matrix(row['stateFinal'])
        before = matrix(row['stateBefore'])
        check(sidecar(row['stateFinal']) == states['stateAfterReturn'][0x60:0xA0], 'final state slice differs')
        check(sidecar(row['stateBefore']) == states['stateAfterGeneric'][0x60:0xA0], 'before state slice differs')
        position10 = f32(states['stateAfterGeneric'], 0x10)
        prediction = predict_common_state(actual, f32(context, 0x40), before, f32(states['stateAfterGeneric'], 0x50), flags, position10)
        resources = {}
        resource_hashes = {}
        for name, snapshot_name in (('entry','entryState'), ('helperReturn','stateAfterHelper'),
                                    ('genericReturn','stateAfterGeneric'), ('stateReturn','stateAfterReturn')):
            resources[name] = struct.unpack_from('<I', states[snapshot_name], 0x198)[0]
            identity = row['resourceIdentity'][name]
            check(identity['address'] == resources[name] and identity['fieldAddress'] == p+0x198, 'resource pointer interpretation differs')
            check(identity['semanticName'] is None, 'resource given an unconfirmed semantic name')
            if identity['status'] == 'read':
                resource_bytes = sidecar(identity['bytes'])
                check(len(resource_bytes) == 64, 'resource snapshot length differs')
                resource_hashes[name] = sha(resource_bytes)
            else:
                resource_hashes[name] = None
        results.append({'sample': row['sample'], 'flags': flags, 'flags_hex': hex(flags),
            'state': p, 'state_return': hex(state_ra), 'outer_return': hex(outer_ra), 'resource_pointers': resources,
            'resource_sha256': resource_hashes,
            'helper_generic_byte_identical': True,
            'helper_final_difference': errors(final, actual),
            'common_formula_supported': prediction is not None,
            'common_formula_difference': errors(final, prediction) if prediction is not None else None,
            'position10_vs_local_translation_max_abs': max(abs(position10[i]-before[12+i]) for i in range(3)),
            'state_before_origin': list(before[12:15]), 'helper_origin': list(actual[12:15]),
            'final_state_origin': list(final[12:15]), 'semanticName': None})
    check(results, 'no complete three-return observations')
    return {'schema': 'weapon-marker-final-state-audit/v1', 'passed': True,
        'capture': str(path.resolve()), 'capture_sha256': sha(raw), 'rows_checked': len(results),
        'code_blocks_checked': len(names), 'flags_histogram': dict(collections.Counter(r['flags_hex'] for r in results)),
        'outer_return_histogram': dict(collections.Counter(r['outer_return'] for r in results)),
        'rows': results, 'semanticName': None,
        'limits': ['passed describes raw evidence/ABI consistency; numerical formula errors are reported separately.',
            'F64 common-path algebra does not certify VFPU instruction rounding identity.',
            'Resource pointers and transformed state do not identify a specific muzzle/FX consumer.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.capture)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('passed','rows_checked','flags_histogram','outer_return_histogram')}))


if __name__ == '__main__':
    main()
