"""Locate retained state+198 data bytes in the original ISO, without live IO."""
import argparse
import csv
import hashlib
import json
import mmap
import struct
from pathlib import Path

from analyze_weapon_marker_output import check, sidecar, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--iso', type=Path, required=True)
    parser.add_argument('--sections', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    raw_capture = args.capture.read_bytes()
    capture = json.loads(raw_capture)
    check(capture['schema'] == 'weapon-marker-state-output-capture/v1', 'wrong capture schema')
    check(capture['failure'] is None and capture['rows'], 'no complete successful observations')
    identity = capture['rows'][0]['resourceIdentity']['stateReturn']
    check(identity['status'] == 'read', 'selected identity data was not read')
    pattern = sidecar(identity['bytes'])
    check(len(pattern) == 64, 'expected bounded 64byte identity record')
    # Verify this selected capture really observed the same bytes and pointer
    # at all four stages, rather than generalizing from the first row alone.
    for row in capture['rows']:
        for stage in ('entry', 'helperReturn', 'genericReturn', 'stateReturn'):
            observed = row['resourceIdentity'][stage]
            check(observed['status'] == 'read' and observed['address'] == identity['address'], 'identity pointer changed')
            check(sidecar(observed['bytes']) == pattern, 'identity record bytes changed')
    sections = list(csv.DictReader(args.sections.open(encoding='utf-8-sig')))
    matches = []
    with args.iso.open('rb') as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as source:
        iso_sha = hashlib.sha256(source).hexdigest()
        check(iso_sha == '448a90acdc7698270344ec14dd943da293084446ca5793acb0e2e8b1b68a15bc', 'selected original ISO differs')
        start = 0
        while True:
            found = source.find(pattern, start)
            if found < 0:
                break
            matches.append(found)
            check(len(matches) <= 100000, 'pattern too common for bounded identity analysis')
            start = found+1
        containers = []
        for found in matches:
            # pack_sections.py writes ABSOLUTE ISO offsets. No PKG_BASE addition.
            for section in sections:
                pack = int(section['pack_offset'], 0)
                relative, size = int(section['rel_offset'], 0), int(section['size'], 0)
                begin = pack + relative
                if begin <= found and found+len(pattern) <= begin+size:
                    check(source[pack:pack+4] == b'pack', 'CSV container magic differs')
                    check(struct.unpack_from('<I', source, pack+4)[0] == int(section['type']), 'CSV type differs')
                    slot = int(section['section'])
                    actual_size, actual_relative = struct.unpack_from('<II', source, pack+8+slot*8)
                    check((actual_size, actual_relative) == (size, relative), 'CSV section directory differs')
                    block = source[begin:begin+size]
                    offset = found-begin
                    item = {'iso_match_offset': found, 'pack_iso_offset': pack, 'pack_type': int(section['type']),
                        'section_slot': slot, 'section_iso_offset': begin, 'section_bytes': size,
                        'section_sha256': sha(block), 'section_magic_hex': block[:4].hex(),
                        'section_header_256_hex': block[:256].hex(), 'pattern_offset_in_section': offset,
                        'candidate_runtime_section_base': identity['address']-offset,
                        'candidate_runtime_base_confirmed': False}
                    if len(matches) == 1:
                        args.out.parent.mkdir(parents=True, exist_ok=True)
                        target = args.out.with_name(args.out.stem+'_section.bin')
                        if target.exists():
                            check(target.read_bytes() == block, 'refusing to replace different extracted section')
                        else:
                            target.write_bytes(block)
                        item['extracted_section'] = str(target.resolve())
                    containers.append(item)
        result = {'schema': 'weapon-state-data-original-source-match/v1', 'passed': True,
            'capture': str(args.capture.resolve()), 'capture_sha256': sha(raw_capture),
            'capture_rows_same_identity': len(capture['rows']), 'runtime_record_address': identity['address'],
            'pattern_sha256': sha(pattern), 'pattern_hex': pattern.hex(), 'pattern_bytes': len(pattern),
            'iso': str(args.iso.resolve()), 'iso_bytes': len(source), 'iso_sha256': iso_sha,
            'full_iso_scanned': True, 'matches': matches, 'match_count': len(matches),
            'containing_sections': containers, 'semanticName': None,
            'limits': ['Unique byte match and a source container are not proof of live section base or FX semantics.',
                'A live header/block fingerprint or loader evidence is needed before treating the candidate base as confirmed.',
                'Record content may be a transform descriptor rather than an asset root.']}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'matches': len(matches), 'containing_sections': containers}, ensure_ascii=False))


if __name__ == '__main__':
    main()
