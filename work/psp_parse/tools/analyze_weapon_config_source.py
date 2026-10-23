"""Audit raw full config/manager windows, then compare every original record.

No emulator connection; an exact record match is distinct from a verified live
section base or proof of which getter branch executed.
"""
import argparse
import collections
import json
import struct
from pathlib import Path

from analyze_weapon_marker_output import check, sha, sidecar
from analyze_weapon_selector_writer import audit as writer_audit

SECTION_SHA = '7411909bb4e848af75628d4c305bccc1d25361cdf91e79831984900f12e866f3'
STRIDE = 0xE4


def u32(data, offset=0):
    return struct.unpack_from('<I', data, offset)[0]


def window(item, address, size):
    data = sidecar(item['raw'])
    check(item['address'] == address and item['size'] == size == len(data), 'config raw window address/size differs')
    check(address % 4 == 0 and 0x08000000 <= address and address+size <= 0x0C000000,
          'config raw window outside bounded guest RAM')
    return data


def audit(capture_path, section_path, producer_path=None):
    baseline = writer_audit(capture_path, producer_path)
    capture = json.loads(capture_path.read_bytes())
    check(capture['bounds'].get('configProbe'), 'capture did not request full config provenance')
    ranges = {(item['address'],item['size']) for item in capture['codeIdentity']['checks']}
    check({(0x0896C5FC,0x10),(0x08AC288C,0x40),(0x08AC28CC,0x34),(0x0896CE9C,0x30)} <= ranges,
          'full config getter runtime code coverage missing')
    section = section_path.read_bytes()
    check(sha(section) == SECTION_SHA, 'original type34 section identity differs')
    count, stride, offset = struct.unpack_from('<HHI', section)
    check(count == 108 and stride == STRIDE and offset == 8 and len(section) == offset+count*stride,
          'selected original record layout differs')
    original_records = [section[offset+i*stride:offset+(i+1)*stride] for i in range(count)]
    results = []
    for row in capture['rows']:
        provenance = row['configProvenance']
        check(provenance['schema'] == 'weapon-config-source-provenance/v1', 'wrong config provenance schema')
        check(provenance['status'] == 'read' and provenance['semanticName'] is None and
              provenance['branchExecuted'] is None and not provenance['sourceHeaderCaptured'], 'config provenance overclaims semantics/branch/header')
        binding = row['bindingProvenance']
        config = binding['config']
        windows = provenance['windows']
        record = window(windows['config_record'], config, STRIDE)
        previous = sidecar(binding['windows']['config_8c']['raw'])
        check(record[0x8C:0x9C] == previous, 'full config does not contain prior same-stop fragment')
        root_pointer = u32(window(windows['manager_global'], 0x08C3BC0C, 4))
        manager = root_pointer+0x340
        fields = window(windows['manager_fields'], manager+0x8BE0, 12)
        base, table, live_count = struct.unpack('<3I', fields)
        check(1 <= live_count <= 108, 'live manager count outside explicit bound')
        check(base % 4 == 0 and 0x08000000 <= base and base+live_count*STRIDE <= 0x0C000000,
              'continuous table range outside guest RAM')
        pointers = window(windows['pointer_table'], table, live_count*4)
        values = struct.unpack('<'+'I'*live_count, pointers)
        # These bytes were retained, not followed. Null/sentinel entries need
        # not be valid pointers to be faithfully retained and classified.
        classes = collections.Counter('null' if value == 0 else 'guest_pointer' if
                                      value % 4 == 0 and 0x08000000 <= value < 0x0C000000 else 'other_word'
                                      for value in values)
        delta = config-base
        continuous_index = delta//STRIDE if delta >= 0 and delta % STRIDE == 0 and delta//STRIDE < live_count else None
        aliases = [i for i,value in enumerate(values) if value == config]
        check(provenance['config'] == config and provenance['recordBytes'] == STRIDE and provenance['maxCount'] == 108,
              'reported config identity/bounds differ')
        check((provenance['globalObject'],provenance['manager'],provenance['contiguousBase'],
               provenance['pointerTableBase'],provenance['count']) == (root_pointer,manager,base,table,live_count),
              'reported manager fields differ from raw')
        continuous = provenance['contiguousMembership']
        check(continuous['matched'] == (continuous_index is not None) and continuous['index'] == continuous_index and
              continuous['deltaBytes'] == delta, 'reported continuous membership differs')
        pointer = provenance['pointerMembership']
        expected_classes = ['null' if value == 0 else 'bounded_record_candidate' if value % 4 == 0 and
                            0x08000000 <= value and value+STRIDE <= 0x0C000000 else 'unfollowed_non_RAM_or_unaligned_value'
                            for value in values]
        check(pointer['matched'] == bool(aliases) and pointer['indices'] == aliases and
              pointer['rawSlotValues'] == list(values) and pointer['slotValueClasses'] == expected_classes and
              pointer['slotAddresses'] == [table+4*i for i in aliases] and not pointer['payloadsRead'],
              'reported pointer membership differs from raw')
        expected_layout = ('both' if aliases else 'contiguous_only') if continuous_index is not None else ('pointer_only' if aliases else 'unmatched')
        check(provenance['layoutMembership'] == expected_layout, 'reported table membership layout differs')
        matches = [i for i,original in enumerate(original_records) if original == record]
        differences = []
        for i,original in enumerate(original_records):
            changed = [j for j,(a,b) in enumerate(zip(original,record)) if a != b]
            differences.append({'source_index':i,'different_bytes':len(changed)})
        differences.sort(key=lambda item:(item['different_bytes'],item['source_index']))
        results.append({'sample':row['sample'],'config':hex(config),'config_sha256':sha(record),
                        'manager_root':hex(root_pointer),'manager':hex(manager),'record_table_base':hex(base),
                        'pointer_table_base':hex(table),'live_count':live_count,
                        'continuous_index':continuous_index,'pointer_table_alias_indices':aliases,
                        'pointer_table_word_classes':dict(classes),'original_exact_record_indices':matches,
                        'full_record_exact_match_count':len(matches),'unique_full_record_match':len(matches) == 1,
                        'continuous_index_agrees_with_unique_source':continuous_index == matches[0] if len(matches) == 1 else None,
                        'nearest_source_candidates_by_byte_difference':differences[:5],
                        'selector90':u32(record,0x90),'requested_resource94':hex(u32(record,0x94)),
                        'live_section_base_confirmed':False,'executed_getter_branch_confirmed':False,'semanticName':None})
    check(results and len(results) == baseline['rows_checked'], 'full config observations incomplete')
    return {'schema':'weapon-config-full-source-independent-audit/v1','passed':True,
            'capture':str(capture_path.resolve()),'capture_sha256':sha(capture_path.read_bytes()),
            'writer_audit_passed':baseline['passed'],'producer_sha256':baseline['producer_sha256'],
            'source_section':str(section_path.resolve()),'source_section_sha256':sha(section),
            'source_section_iso_offset':0x0757111C,'source_records_checked_per_row':108,
            'source_stride':STRIDE,'rows_checked':len(results),'rows':results,
            'all_rows_unique_full_record_match':all(row['unique_full_record_match'] for row in results),
            'live_section_base_confirmed':False,'executed_getter_branch_confirmed':False,'semanticName':None,
            'limits':['A raw exact record/manager membership match does not prove which getter branch last assigned config.',
                      'No live section header/full section dump was requested; the live section base is not certified.',
                      'All pointer-table words are retained, but unselected entries are not dereferenced.',
                      'Requested resource IDs and selector fields retain their data-flow meanings, not visual FX names.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,required=True)
    parser.add_argument('--producer',type=Path)
    parser.add_argument('--section',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    result = audit(args.capture,args.section,args.producer)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:result[key] for key in ['passed','rows_checked','all_rows_unique_full_record_match']}))


if __name__ == '__main__':
    main()
