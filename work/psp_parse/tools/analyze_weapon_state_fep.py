"""Verify retained FEP windows against their original ISO section offline."""
import argparse
import collections
import json
import struct
from pathlib import Path

from analyze_weapon_marker_output import check, sha, sidecar
from analyze_weapon_marker_state_output import audit as audit_state


def u32(data, at):
    return struct.unpack_from('<I', data, at)[0]


def changes(source, live, base, offset):
    check(len(source) == len(live) and len(live) % 4 == 0, 'word comparison lengths differ')
    counts, changed = collections.Counter(), []
    for at in range(0, len(live), 4):
        before, after = u32(source, at), u32(live, at)
        category = 'unchanged' if before == after else ('base_added' if after == base+before else 'other_mutation')
        counts[category] += 1
        if category != 'unchanged':
            changed.append({'section_offset': offset+at, 'source_word': before, 'live_word': after, 'category': category})
    return {'word_categories': dict(counts), 'changes': changed}


def audit(capture_path, source_match_path):
    capture_raw = capture_path.read_bytes()
    capture = json.loads(capture_raw)
    state_audit = audit_state(capture_path)
    match_raw = source_match_path.read_bytes()
    match = json.loads(match_raw)
    check(match['schema'] == 'weapon-state-data-original-source-match/v1' and match['passed'], 'source match invalid')
    check(match['full_iso_scanned'] and match['match_count'] == 1 and len(match['containing_sections']) == 1, 'source match is not unique')
    section = match['containing_sections'][0]
    source = Path(section['extracted_section']).read_bytes()
    check(len(source) == section['section_bytes'] and sha(source) == section['section_sha256'], 'extracted source changed')
    probe = capture['fepProbe']
    check(probe['enabled'] and probe['attempted'] and probe['status'] == 'captured' and probe['failure'] is None, 'FEP probe incomplete')
    check(probe['semanticName'] is None and len(probe['windows']) == 5, 'FEP scope differs')
    base = probe['sourceState190']
    expected = {'header_tables': (0, 0x400), 'type0_descriptor4': (0xAB8, 12),
                'pointer_list': (0x48E0, 16), 'table1_record4': (0xFB4, 64), 'record': (0x48F0, 0xC0)}
    windows, comparisons = {}, {}
    for item in probe['windows']:
        name = item['name']
        check(name in expected and name not in windows, 'unknown/duplicate FEP window')
        offset, length = expected[name]
        check(item['offset'] == offset and item['size'] == length and item['address'] == base+offset, 'window address/size differs')
        check(item['status'] == 'read', 'window read failed')
        live = sidecar(item['raw'])
        check(len(live) == length, 'raw window length differs')
        windows[name] = live
        comparisons[name] = changes(source[offset:offset+length], live, base, offset)
    check(set(windows) == set(expected), 'required windows missing')
    header = windows['header_tables']
    for at in (0, 4, 0x10, 0x14, 0x18, 0x1C, 0x20, 0x24, 0x48):
        check(u32(header, at) == u32(source, at), f'header scalar {at:x} differs')
    check(header[:4] == b'FEP\x07' and u32(header, 0x14) == len(source), 'wrong FEP source header')
    # These are actual relocated words, rather than an equality asserted by
    # the capture producer's permissive relative/relocated header gate.
    for at in (8, *range(0x28, 0x48, 4), 0x4C):
        check(u32(header, at) == base+u32(source, at), f'header offset {at:x} was not relocated as observed')
    table0, table1 = u32(source, 0x28), u32(source, 0x2C)
    descriptor_offset = u32(source, table0+4*4)
    check(descriptor_offset == 0xAB8 and u32(header, table0+4*4) == base+descriptor_offset, 'table0[4] link differs')
    descriptor = windows['type0_descriptor4']
    check(descriptor[:8] == source[descriptor_offset:descriptor_offset+8], 'descriptor identity changed')
    list_offset = u32(source, descriptor_offset+8)
    check(list_offset == 0x48E0 and u32(descriptor, 8) == base+list_offset, 'descriptor/list link differs')
    record_offset = u32(source, list_offset)
    check(record_offset == 0x48F0 and u32(windows['pointer_list'], 0) == base+record_offset, 'list/record link differs')
    record4_offset = u32(source, table1+4*4)
    check(record4_offset == 0xFB4 and u32(header, table1+4*4) == base+record4_offset, 'table1[4] link differs')
    check(probe['sourceState194'] == base+record4_offset and probe['sourceState198'] == base+record_offset, 'state/source linkage differs')
    check(windows['record'][:64] == bytes.fromhex(match['pattern_hex']), 'live record prefix differs from unique ISO match')
    for row in capture['rows']:
        entry = sidecar(row['entryState'])
        check((u32(entry, 0x190), u32(entry, 0x194), u32(entry, 0x198)) ==
              (base, base+record4_offset, base+record_offset), 'later row source identity changed')
        check(sidecar(row['resourceIdentity']['entry']['bytes']) == windows['record'][:64], 'entry record/window differs')
    other = [c for report in comparisons.values() for c in report['changes'] if c['category'] == 'other_mutation']
    return {'schema': 'weapon-state-live-fep-source-verification/v1', 'passed': True,
        'capture': str(capture_path.resolve()), 'capture_sha256': sha(capture_raw),
        'source_match': str(source_match_path.resolve()), 'source_match_sha256': sha(match_raw),
        'source_section_sha256': sha(source), 'source_section_iso_offset': section['section_iso_offset'],
        'runtime_base': base, 'state_rows_checked': state_audit['rows_checked'],
        'state_declared_source_base_verified_for_windows': True,
        'full_section_runtime_bytes_verified': False, 'selected_table0_index': 4,
        'selected_subrecord_index': 0, 'selected_record_section_offset': record_offset,
        'record_prefix64_exact': True, 'record_192_exact': windows['record'] == source[record_offset:record_offset+0xC0],
        'header_offset8_meaning': 'Relocated offset/pointer; a fixed header-length interpretation is contradicted by live bytes.',
        'window_comparisons': comparisons, 'other_mutations': other,
        'semanticName': None,
        'limits': ['Only the retained bounded windows are verified; this is not a complete loaded-section dump.',
            'Base-added word classification alone does not name every field as a pointer.',
            'Other runtime mutations are retained and are not interpreted as relocation.',
            'Source identity and transform state do not identify muzzle/FX semantics.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--source-match', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.capture, args.source_match)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('passed','state_rows_checked','runtime_base','record_192_exact','other_mutations')}))


if __name__ == '__main__':
    main()
