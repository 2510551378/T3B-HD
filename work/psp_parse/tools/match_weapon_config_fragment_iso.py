"""Exact full-ISO search for retained config+0x8c fragments; offline only.

Uses original ISO9660 and pack-directory bytes to resolve the legacy relative
CSV inventory. An exact fragment match is a candidate, not a config schema or
a confirmed live section base. No project auditor/parser is imported.
"""
import argparse
import csv
import hashlib
import io
import json
import mmap
from pathlib import Path
import struct
import sys

ISO_SHA = '448a90acdc7698270344ec14dd943da293084446ca5793acb0e2e8b1b68a15bc'
EXPECTED = bytes.fromhex('010000000100000016022800ef030000')
SECTOR = 2048


def check(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def integer(s):
    return int(s, 16) if s.lower().startswith('0x') else int(s, 10)


def bounded(source, at, size):
    check(isinstance(at, int) and isinstance(size, int) and at >= 0 and size >= 0 and
          at <= len(source) and size <= len(source)-at, f'out-of-range source window {at}/{size}')
    return bytes(source[at:at+size])


def sidecar(meta, capture_parent):
    p = Path(meta['file']).resolve()
    check(p.parent == capture_parent.resolve(), 'sidecar outside selected capture directory')
    raw = p.read_bytes()
    check(len(raw) == meta['bytes'] and sha(raw) == meta['sha256'], 'sidecar identity differs')
    return raw


def capture_fragment(capture_path, audit_path):
    raw = capture_path.read_bytes()
    c = json.loads(raw)
    audit_raw = audit_path.read_bytes()
    audit = json.loads(audit_raw)
    check(c['schema'] == 'weapon-marker-selector-writer-capture/v1' and c['failure'] is None and
          c['inFlight'] is None and c['ownedBP'] is None and c['bounds']['bindingProbe'] is True,
          'capture is not a complete binding-probe observation')
    check(c['cleanup']['errors'] == [] and c['cleanup']['buttonsReleased'] and
          c['cleanup']['ownedBreakpointRemoved'], 'capture cleanup incomplete')
    check(audit['schema'] == 'weapon-marker-selector-writer-independent-audit/v1' and audit['passed'] and
          audit['capture_sha256'] == sha(raw) and audit['producer_sha256'] == c['producer']['sha256'],
          'retained independent audit does not bind this capture')
    check(len(c['rows']) == audit['rows_checked'] == 4 and len(audit['rows']) == 4,
          'expected exactly four independently audited rows')
    rows = []
    for row, audited in zip(c['rows'], audit['rows']):
        check(row['actualWriteObserved'] is True and row['classification'] == 'observed_selector_write',
              'row is not an observed selector write')
        b = row['bindingProvenance']
        check(b['schema'] == 'weapon-binding-source-provenance/v1' and b['status'] == 'read',
              'binding window unavailable')
        w = b['windows']['config_8c']
        check(w['size'] == 16 and w['address'] == b['config']+0x8c, 'config window offset differs')
        value = sidecar(w['raw'], capture_path.parent)
        check(value == EXPECTED, 'not all four original config fragments equal the selected pattern')
        fields = struct.unpack('<4I', value)
        check(fields[1] == b['selector'] == row['newSelector'] and
              fields[2] == b['requestedID']['config94'], 'raw selector/requested-ID observation differs')
        check(audited['sample'] == row['sample'] and integer(audited['binding_source']['config']) == b['config'],
              'independent audit row/config association differs')
        rows.append(dict(sample=row['sample'], entry_ticks=row['entryTicks'],
                         config_runtime_address=b['config'], fragment_runtime_address=w['address'],
                         fragment_relative_to_config=0x8c, raw=w['raw'], raw_hex=value.hex(),
                         raw_u32=list(fields), selector=b['selector'], semantic_name=None))
    return EXPECTED, rows, dict(path=str(capture_path.resolve()), sha256=sha(raw),
        producer_sha256=c['producer']['sha256'], independent_audit=str(audit_path.resolve()),
        independent_audit_sha256=sha(audit_raw), independent_audit_reexecuted=False)


def iso_file(source, components):
    pvd = bounded(source, 16*SECTOR, SECTOR)
    check(pvd[:7] == b'\x01CD001\x01', 'selected ISO primary volume descriptor differs')
    check(struct.unpack_from('<H', pvd, 128)[0] == struct.unpack_from('>H', pvd, 130)[0] == SECTOR,
          'unsupported ISO logical block size')

    def record(raw, at):
        check(len(raw) >= 34 and raw[0] == len(raw) and 33+raw[32] <= len(raw), 'bad ISO directory record')
        lba, size = struct.unpack_from('<I', raw, 2)[0], struct.unpack_from('<I', raw, 10)[0]
        check(lba == struct.unpack_from('>I', raw, 6)[0] and
              size == struct.unpack_from('>I', raw, 14)[0], 'ISO dual-endian record differs')
        check(raw[1] == 0 and not raw[25] & 0x80 and raw[26:28] == b'\0\0',
              'unsupported ISO extended-attribute/multi-extent/interleaved record')
        check(lba*SECTOR+size <= len(source), 'ISO file extent outside image')
        return dict(record_iso_offset=at, raw_record_hex=raw.hex(), lba=lba,
                    iso_offset=lba*SECTOR, bytes=size, flags=raw[25],
                    name=raw[33:33+raw[32]].decode('ascii'))

    current = record(pvd[156:156+pvd[156]], 16*SECTOR+156)
    chain = [current]
    for name in components:
        check(current['flags'] & 2, 'ISO path component is not a directory')
        start, size = current['iso_offset'], current['bytes']
        check(size <= 16*1024*1024, 'ISO directory exceeds bounded parser size')
        at = start
        matches = []
        while at < start+size:
            n = source[at]
            if n == 0:
                at = (at//SECTOR+1)*SECTOR
                continue
            check(at+n <= start+size and at//SECTOR == (at+n-1)//SECTOR,
                  'ISO directory record crosses extent/sector')
            entry = record(bounded(source, at, n), at)
            if entry['name'].split(';')[0].casefold() == name.casefold():
                matches.append(entry)
            at += n
        check(len(matches) == 1, f'ISO path component {name} not unique')
        current = matches[0]
        chain.append(current)
    check(not current['flags'] & 2, 'ISO selected member is a directory')
    return dict(path='/'.join(components), pvd_iso_offset=16*SECTOR,
                pvd_sha256=sha(pvd), directory_chain=chain, **current)


def sections_from_csv(source, csv_raw, pkg):
    reader = csv.DictReader(io.StringIO(csv_raw.decode('utf-8-sig')))
    check(reader.fieldnames == ['pack','type','section','sec_off','size','kind'],
          'CSV is not the selected legacy pack-relative schema')
    rows = list(reader)
    cache, sections = {}, []
    for row_number, row in enumerate(rows, 2):
        relative = integer(row['pack'])
        check(0 <= relative < pkg['bytes'], 'CSV pack outside 3rd.pkg')
        pack_at = pkg['iso_offset']+relative
        if pack_at not in cache:
            prefix = bounded(source, pack_at, 16)
            check(prefix[:4] == b'pack', 'CSV relative pack position lacks actual magic')
            kind, first_size, header_bytes = struct.unpack_from('<3I', prefix, 4)
            check(16 <= header_bytes <= 0x20000 and header_bytes % 4 == 0,
                  'unsupported pack directory length')
            header = bounded(source, pack_at, header_bytes)
            count = (header_bytes-8)//8
            entries = []
            for slot in range(count):
                size, offset = struct.unpack_from('<2I', header, 8+slot*8)
                if size == 0 or offset == 0:
                    continue
                check(offset >= header_bytes and relative+offset+size <= pkg['bytes'],
                      'actual pack section outside 3rd.pkg')
                entries.append(dict(directory_slot=slot, size=size, rel_offset=offset,
                                    directory_entry_hex=header[8+slot*8:16+slot*8].hex()))
            check(entries and entries[0]['size'] == first_size, 'pack first directory entry differs')
            cache[pack_at] = dict(pack_type=kind, header_bytes=header_bytes,
                                  header_raw_hex=header.hex(), header_sha256=sha(header), entries=entries)
        actual = cache[pack_at]
        ordinal = integer(row['section'])
        check(0 <= ordinal < len(actual['entries']), 'CSV nonempty-section ordinal out of actual directory')
        entry = actual['entries'][ordinal]
        check(integer(row['type']) == actual['pack_type'] and integer(row['size']) == entry['size'] and
              integer(row['sec_off']) == entry['rel_offset'], 'CSV/actual pack directory differs')
        sections.append(dict(csv_row_number=row_number,csv_raw_fields=row,pack_iso_offset=pack_at,
            pack_offset_relative_to_pkg=relative,pack_type=actual['pack_type'],
            pack_header_bytes=actual['header_bytes'],pack_header_raw_hex=actual['header_raw_hex'],
            pack_header_sha256=actual['header_sha256'],csv_section_nonempty_ordinal=ordinal,
            section_directory_slot=entry['directory_slot'],directory_entry_hex=entry['directory_entry_hex'],
            section_iso_offset=pack_at+entry['rel_offset'],section_bytes=entry['size'],
            section_offset_relative_to_pack=entry['rel_offset']))
    return sections, dict(rows_checked=len(rows),unique_pack_headers_checked=len(cache),
        csv_pack_coordinate='relative to original ISO9660 PSP_GAME/USRDIR/3rd.pkg',
        csv_section_coordinate='ordinal among nonempty directory entries, not assumed raw slot',
        conversion='pack_iso_offset = ISO9660(3rd.pkg).iso_offset + int(csv.pack)',
        every_csv_row_matched_actual_pack_directory=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture',type=Path,required=True)
    p.add_argument('--audit',type=Path,required=True)
    p.add_argument('--iso',type=Path,required=True)
    p.add_argument('--sections',type=Path,required=True)
    p.add_argument('--out-dir',type=Path,required=True)
    args=p.parse_args()
    pattern, observations, capture_identity = capture_fragment(args.capture,args.audit)
    csv_raw=args.sections.read_bytes()
    with args.iso.open('rb') as stream, mmap.mmap(stream.fileno(),0,access=mmap.ACCESS_READ) as source:
        iso_sha=sha(source)
        check(iso_sha==ISO_SHA,'original ISO SHA256 differs')
        pkg=iso_file(source,['PSP_GAME','USRDIR','3rd.pkg'])
        sections,csv_check=sections_from_csv(source,csv_raw,pkg)
        matches=[]
        start=0
        while True:
            at=source.find(pattern,start)
            if at<0:
                break
            matches.append(at)
            start=at+1  # Include overlapping matches, with no alignment filter.
        mapped=[]
        extracted={}
        for i,at in enumerate(matches):
            containers=[]
            for section in sections:
                begin,size=section['section_iso_offset'],section['section_bytes']
                if begin<=at and at+len(pattern)<=begin+size:
                    block=bounded(source,begin,size)
                    extracted[begin]=block
                    offset=at-begin
                    check(block[offset:offset+16]==pattern,'mapped fragment differs')
                    item=dict(section,section_sha256=sha(block),section_magic_hex=block[:16].hex(),
                              section_header_window_bytes=min(256,size),section_header_256_hex=block[:256].hex(),
                              fragment_offset_in_section=offset,fragment_offset_in_pack=at-section['pack_iso_offset'],
                              fragment_plus8c_config_origin_hypothesis=None)
                    item['original_iso_section_blob']=f'iso_section_{begin:08x}.bin'
                    if size>=8:
                        n,stride,origin=struct.unpack_from('<HHI',block)
                        item['raw_first8_interpretation_candidate']=dict(
                            raw_hex=block[:8].hex(),u16_at0=n,u16_at2=stride,u32_at4=origin,
                            exact_size_equation=(origin+n*stride==size),
                            complete_record_format_recovered=False)
                    if offset>=0x8c:
                        item['fragment_plus8c_config_origin_hypothesis']=dict(
                            candidate_config_origin_offset_in_section=offset-0x8c,
                            equation='source section offset(candidate config origin)+0x8c = matched fragment offset',
                            candidate_runtime_section_bases=[dict(sample=row['sample'],
                                candidate_base=row['fragment_runtime_address']-offset) for row in observations],
                            live_base_confirmed=False,complete_config_record_verified=False)
                        if size>=8 and stride>0 and origin+n*stride==size:
                            relative=offset-0x8c-origin
                            item['fragment_plus8c_config_origin_hypothesis']['candidate_regular_array_index']=(
                                relative//stride if relative>=0 and relative%stride==0 and relative//stride<n else None)
                    containers.append(item)
            mapped.append(dict(iso_offset=at,exact_match_bytes=16,containing_sections=containers,
                               candidate_only=True))
        report=dict(schema='weapon-config-fragment-original-iso-match/v1',passed=True,
            capture=capture_identity,observations=observations,all_four_raw_fragments_equal=True,
            pattern_hex=pattern.hex(),pattern_bytes=len(pattern),pattern_sha256=sha(pattern),
            iso=dict(path=str(args.iso.resolve()),bytes=len(source),sha256=iso_sha),
            full_iso_scanned=True,search_range=[0,len(source)],search_alignment_filter=None,
            overlapping_matches_included=True,match_count=len(matches),matches=mapped,
            unique_fragment_match=len(matches)==1,complete_config_record_verified=False,
            unique_containing_section_count=len(extracted),
            unique_containing_pack_count=len({x['pack_iso_offset'] for m in mapped for x in m['containing_sections']}),
            live_section_base_confirmed=False,semantic_name=None,iso9660_pkg=pkg,
            section_inventory=dict(path=str(args.sections.resolve()),sha256=sha(csv_raw),**csv_check),
            producer=dict(script=str(Path(__file__).resolve()),sha256=sha(Path(__file__).read_bytes()),
                          command=[sys.executable,'-X','utf8',*sys.argv],cwd=str(Path.cwd())),
            limits=['A 16-byte exact match, even unique, is only a source-fragment candidate.',
                    'No complete config extent/schema, loader identity, or live section base was verified.',
                    'Only the fixed original ISO was searched; no RAM scan/dump, PPSSPP, UI, or savestate IO.',
                    'Pack mapping uses the supplied CSV inventory checked against original directory bytes; unmapped matches remain unmapped.',
                    'A missing exact match would not establish compression, encryption, or another format.',
                    'No FX/muzzle/action semantic name is assigned.'])
    args.out_dir.mkdir(parents=True,exist_ok=True)
    (args.out_dir/'config_8c_fragment.bin').write_bytes(pattern)
    for at,block in extracted.items():
        target=args.out_dir/f'iso_section_{at:08x}.bin'
        target.write_bytes(block)
        check(target.read_bytes()==block,'extracted original ISO section differs')
    (args.out_dir/'source_match.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    print(json.dumps(dict(passed=True,rows=len(observations),full_iso_scanned=True,match_count=len(matches),
        containing_section_associations=sum(len(x['containing_sections']) for x in mapped),
        pkg_iso_offset=pkg['iso_offset'],inventory_rows=csv_check['rows_checked'],
        unique_pack_headers=csv_check['unique_pack_headers_checked']),ensure_ascii=False))


if __name__=='__main__':
    main()
