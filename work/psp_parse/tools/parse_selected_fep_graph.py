"""Bounded, lossless inventory of the selected original FEP07 table0/table1 graph.

No emulator access and no import of other project parsers. Unknown payloads are
retained by offset/length into a byte-identical source.bin, never semantically named.
"""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import struct
import sys


SECTION_SHA = '97443c71b1c1d644f323c6ff611afb740329cfe11a47a711f39dc59de06ec802'
MODULE_SHA = 'b5fc590366fc610f2cdd60104a4a28851bacd402c4600a4c296776e1dea0869f'
MODULE_BASE = 0x08804000


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


class Reader:
    def __init__(self, data):
        self.data = data

    def bounded(self, at, size, label):
        require(isinstance(at, int) and isinstance(size, int) and at >= 0 and
                size >= 0 and at <= len(self.data) and size <= len(self.data)-at,
                f'{label}: out of section range offset={at:#x} bytes={size}')
        return self.data[at:at+size]

    def u16(self, at):
        return struct.unpack('<H', self.bounded(at, 2, 'u16'))[0]

    def u32(self, at):
        return struct.unpack('<I', self.bounded(at, 4, 'u32'))[0]


def parse_graph(data):
    r = Reader(data)
    require(r.bounded(0, 4, 'magic') == b'FEP\x07', 'not FEP07')
    r.bounded(0, 0x50, 'header observation window')
    require(r.u32(0x14) == len(data), 'declared section bytes differs')
    counts = [r.u16(0x1c), r.u16(0x1e)]
    tables = [r.u32(0x28), r.u32(0x2c)]
    require(all(0 < n <= 65535 for n in counts), 'empty table count')
    nodes, edges = {}, []

    def add(at, size, kind, status, source=None):
        require(at % 4 == 0, f'{kind}: unaligned offset {at:#x}')
        raw = r.bounded(at, size, kind)
        key = f'{kind}:{at:08x}'
        if key in nodes:
            require(nodes[key]['minimum_bytes'] == size, 'shared node size differs')
        else:
            nodes[key] = dict(id=key, kind=kind, offset=at,
                              minimum_bytes=size, evidence_status=status,
                              raw_hex=raw.hex(), raw_sha256=sha(raw), incoming=[])
        if source is not None:
            edges.append(dict(source=source, target=key, target_offset=at))
            nodes[key]['incoming'].append(source)
        return key

    add(0, 0x50, 'header_window', 'raw window; not a declared header length')
    table_keys = []
    offsets = []
    for j, (table, count) in enumerate(zip(tables, counts)):
        tk = add(table, count*4, f'table{j}_offsets', 'header count/offset, bounded')
        table_keys.append(tk)
        entries = [r.u32(table+4*i) for i in range(count)]
        require(all(x != 0 for x in entries), 'null top-level table entry unsupported')
        offsets.append(entries)
    t0, t1 = [], []
    for i, at in enumerate(offsets[0]):
        key = add(at, 12, 'table0_descriptor', 'selector directly reads offsets 0,+4,+6,+8',
                  f'{table_keys[0]}[{i}]')
        index, count, target = r.u16(at+4), r.u16(at+6), r.u32(at+8)
        require(index < counts[1], f'descriptor {i}: table1 index out of range')
        require(count > 0, f'descriptor {i}: empty list unsupported')
        lk = add(target, count*4, 'table0_pointer_list', 'selector loops +6 count in 4-byte steps', key+'+8')
        records = []
        for j in range(count):
            record = r.u32(target+4*j)
            rk = add(record, 192, 'table0_record_candidate192',
                     '192 bytes live-confirmed only for selected 0x48f0; extent candidate elsewhere',
                     f'{lk}[{j}]')
            word = r.u32(record)
            records.append(dict(index=j, offset=record, node=rk, raw_word0=word,
                                selector_low9=word & 0x1ff,
                                descriptor_minus_record_word0=r.u32(at)-word))
        edges.append(dict(source=key+'+4:u16', target=f'table1_record:{offsets[1][index]:08x}',
                          target_offset=offsets[1][index], relation='table1 index'))
        t0.append(dict(index=i, offset=at, node=key,
                       raw_words=[r.u32(at+k) for k in (0, 4, 8)],
                       selector_masked_group=(r.u32(at) & 0x1fc00) >> 10,
                       table1_index_u16_at4=index, list_count_u16_at6=count,
                       list_offset=target, list_node=lk, records=records,
                       within_list_record_deltas=[b['offset']-a['offset'] for a, b in zip(records, records[1:])]))

    # All six words were observed relocated for the live index4 window. Other
    # records are offline structural matches, not additional live observations.
    for i, at in enumerate(offsets[1]):
        key = add(at, 52, 'table1_record', '52-byte stride observed across selected file',
                  f'{table_keys[1]}[{i}]')
        p = [r.u32(at+j) for j in range(0x1c, 0x34, 4)]
        c = [r.u16(at+0x10), r.u16(at+0x12), r.u16(at+0x14), r.u16(at+0x16), r.u32(at+0x18)]
        logical = [4*c[0], 4*c[1], 2*c[2], 4*c[3], 4*c[4]]
        allocated = logical.copy()
        allocated[2] = (allocated[2]+3) & ~3
        require(all(x <= y for x, y in zip(p, p[1:])), f'table1 {i}: descending subarray offsets')
        require([b-a for a, b in zip(p, p[1:])] == allocated,
                f'table1 {i}: candidate count/span relation failed')
        arrays = []
        for j in range(5):
            ak = add(p[j], logical[j], f'table1_array{j}_candidate',
                     'count/width candidate; +14 u16 loop is constructor-proven', key+f'+{0x1c+j*4:#x}')
            array = dict(index=j, node=ak, offset=p[j], count_candidate=c[j],
                         element_bytes_candidate=2 if j == 2 else 4,
                         logical_bytes=logical[j], allocated_bytes=allocated[j],
                         alignment_bytes_hex=r.bounded(p[j]+logical[j], allocated[j]-logical[j], 'array padding').hex())
            if j == 2:
                array['raw_u16'] = [r.u16(p[j]+2*k) for k in range(c[j])]
            else:
                values = [r.u32(p[j]+4*k) for k in range(c[j])]
                array['offset_candidates'] = values
                array['targets'] = []
                for k, value in enumerate(values):
                    # One aligned word establishes a bounded target, never an
                    # invented struct length. Later next-start windows retain it.
                    target_key = add(value, 4, 'table1_payload_opaque',
                                     'in-section offset candidate; no semantic/type claim', f'{ak}[{k}]')
                    array['targets'].append(target_key)
            arrays.append(array)
        p5 = add(p[5], 4, 'table1_payload_opaque',
                 'sixth table1 offset, live-relocated at selected index4', key+'+0x30')
        t1.append(dict(index=i, offset=at, node=key,
                       raw_words=[r.u32(at+j) for j in range(0, 52, 4)],
                       candidate_count_fields=dict(zip(['u16_10','u16_12','u16_14','u16_16','u32_18'], c)),
                       offsets_at_1c_to30=p, arrays=arrays, sixth_target=p5))

    # Structural views must not overlap, except for intentional same-start
    # references (reported through incoming edges). A candidate record cannot
    # silently consume the following list, descriptor, or another record.
    intervals = sorted((v['offset'], v['offset']+v['minimum_bytes'], k) for k, v in nodes.items())
    for (a, z, k), (b, _, q) in zip(intervals, intervals[1:]):
        require(z <= b or a == b, f'overlapping minimum ranges: {k} / {q}')
    starts = sorted({0, len(data), *(n['offset'] for n in nodes.values())})
    next_start = dict(zip(starts, starts[1:]))
    for node in nodes.values():
        end = next_start[node['offset']]
        require(end >= node['offset']+node['minimum_bytes'], 'candidate next-start span too short')
        node['next_observed_start_span'] = dict(offset=node['offset'], bytes=end-node['offset'],
                                               sha256=sha(data[node['offset']:end]),
                                               status='bounded window, not declared object extent')
    # Every byte has a lossless owner in this partition, including the unknown
    # remainder after the final known prefix. No bytes are replaced or dropped.
    boundaries = sorted({0, len(data), *(x for a, z, _ in intervals for x in (a, z))})
    partition = []
    cursor = 0
    for a, z in zip(boundaries, boundaries[1:]):
        require(a == cursor and z > a, 'invalid source partition')
        owners = [k for x, y, k in intervals if x <= a and z <= y]
        partition.append(dict(offset=a, bytes=z-a, owners=owners,
                              kind='parsed_or_candidate_prefix' if owners else 'opaque_preserved',
                              sha256=sha(data[a:z])))
        cursor = z
    require(cursor == len(data), 'partition incomplete')
    for e in edges:
        require(e['target'] in nodes, 'dangling graph edge')
    incoming = collections.defaultdict(list)
    for e in edges:
        incoming[e['target_offset']].append(e['source'])
    by_id = {n['id']: n for n in nodes.values()}
    for node in nodes.values():
        node['incoming'] = []
    for e in edges:
        by_id[e['target']]['incoming'].append(e['source'])
    shared = [dict(offset=k, references=v) for k, v in sorted(incoming.items()) if len(v) > 1]
    record_deltas = collections.Counter(d for x in t0 for d in x['within_list_record_deltas'])
    opaque_hist = collections.Counter(v['next_observed_start_span']['bytes'] for v in nodes.values()
                                      if v['kind'] == 'table1_payload_opaque')
    summary = dict(table0_entries=counts[0], table1_entries=counts[1],
                   table0_unique_descriptors=len(set(offsets[0])), table1_unique_records=len(set(offsets[1])),
                   table0_list_references=len(t0), table0_unique_lists=len({x['list_offset'] for x in t0}),
                   table0_record_references=sum(len(x['records']) for x in t0),
                   table0_unique_record_candidates=len({q['offset'] for x in t0 for q in x['records']}),
                   table0_list_count_histogram=dict(sorted(collections.Counter(x['list_count_u16_at6'] for x in t0).items())),
                   table0_within_list_record_delta_histogram=dict(sorted(record_deltas.items())),
                   table0_descriptor_stride_histogram=dict(collections.Counter(b-a for a,b in zip(offsets[0], offsets[0][1:]))),
                   table1_record_stride_histogram=dict(collections.Counter(b-a for a,b in zip(offsets[1], offsets[1][1:]))),
                   table1_opaque_target_count=sum(v['kind']=='table1_payload_opaque' for v in nodes.values()),
                   table1_array_count_totals=[sum(x['arrays'][j]['count_candidate'] for x in t1) for j in range(5)],
                   table1_array0_first_target_aliases_sixth_offset=sum(
                       x['arrays'][0]['offset_candidates'][0] == x['offsets_at_1c_to30'][5]
                       for x in t1 if x['arrays'][0]['count_candidate']),
                   table1_opaque_next_start_span_histogram=dict(sorted(opaque_hist.items())),
                   graph_nodes=len(nodes), graph_edges=len(edges), shared_target_addresses=len(shared),
                   full_source_bytes_preserved=len(data),
                   parsed_or_candidate_prefix_bytes=sum(x['bytes'] for x in partition if x['owners']),
                   opaque_preserved_bytes=sum(x['bytes'] for x in partition if not x['owners']))
    return dict(schema='selected-fep07-bounded-graph/v1', passed=True, semantic_name=None,
                header=dict(observed_window_bytes=0x50, raw_hex=data[:0x50].hex(),
                            raw_u32=[r.u32(i) for i in range(0,0x50,4)],
                            declared_section_bytes=r.u32(0x14), table_counts=counts, table_offsets=tables,
                            offset8_warning='Live-relocated word; do not call this header size.'),
                table0=t0, table1=t1, nodes=list(nodes.values()), edges=edges,
                shared_references=shared, lossless_partition=partition, summary=summary)


def code_evidence(module):
    require(sha(module) == MODULE_SHA, 'module SHA differs')
    # Literal instruction anchors independently decoded from the original MIPS.
    anchors = [(0x08b642d8,0x94a9001c,'lhu t1,0x1c(a1): table0 count'),
               (0x08b642f4,0x8ca50028,'lw a1,0x28(a1): table0 offsets'),
               (0x08b64310,0x95460006,'lhu a2,6(t2): descriptor list count'),
               (0x08b64324,0x8d470008,'lw a3,8(t2): descriptor list'),
               (0x08b64328,0x8ce80000,'lw t0,0(a3): list target'),
               (0x08b64344,0x24e70004,'addiu a3,a3,4: pointer-list stride'),
               (0x08b64378,0x95460004,'lhu a2,4(t2): table1 index passed to constructor'),
               (0x08b63a74,0x8e24002c,'lw a0,0x2c(s1): table1 offsets'),
               (0x08b63a78,0x00122880,'sll a1,s2,2: table1 slot stride'),
               (0x08b63a88,0x8c950000,'lw s5,0(a0): table1 record'),
               (0x08b63ce8,0x96a40014,'lhu a0,0x14(s5): table1 u16 list count'),
               (0x08b63d08,0x8ea40024,'lw a0,0x24(s5): table1 u16 list'),
               (0x08b63d10,0x94840000,'lhu a0,0(a0): u16 element'),
               (0x08b63d54,0x26310002,'addiu s1,s1,2: u16 stride')]
    out=[]
    for pc, word, meaning in anchors:
        actual=struct.unpack_from('<I',module,pc-MODULE_BASE)[0]
        require(actual==word, f'MIPS anchor differs {pc:#x}')
        out.append(dict(address=pc, word=word, little_endian_hex=struct.pack('<I',word).hex(), meaning=meaning))
    return dict(module_base=MODULE_BASE, module_sha256=sha(module), instruction_anchors=out,
                boundary='Only table0/table1 reader paths; no analysis of 0x08b651fc writer.')


def self_tests(original):
    tests=[]
    def reject(name, changed):
        try:
            parse_graph(bytes(changed))
        except (ValueError, struct.error) as error:
            tests.append(dict(name=name, rejected=True, reason=str(error)))
        else:
            raise ValueError('mutation accepted: '+name)
    reject('truncated_header',original[:20])
    reject('truncated_payload',original[:-1])
    for name,at,value,fmt in [
        ('bad_magic',0,0,'<I'),('declared_size',0x14,1,'<I'),
        ('empty_count',0x1c,0,'<H'),('table_outside',0x28,len(original),'<I'),
        ('table_unaligned',0x28,0x51,'<I'),('descriptor_outside',0x50,len(original)-4,'<I'),
        ('table1_index_outside',0xab8+4,93,'<H'),('empty_list',0xab8+6,0,'<H'),
        ('list_count_overflow',0xab8+6,65535,'<H'),('list_outside',0xab8+8,len(original),'<I'),
        ('record_outside',0x48e0,len(original)-4,'<I'),('record_overlap_next',0x48e0,0x49a0,'<I'),
        ('table1_subarray_outside',0xfb4+0x30,len(original),'<I'),
        ('table1_count_relation',0xfb4+0x12,0xffff,'<H'),
        ('nested_target_outside',0x10b34,len(original),'<I')]:
        changed=bytearray(original);struct.pack_into(fmt,changed,at,value);reject(name,changed)
    return dict(passed=True, rejected_mutations=len(tests), cases=tests)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--section',type=Path,required=True)
    parser.add_argument('--module',type=Path,required=True)
    parser.add_argument('--live-verification',type=Path,required=True)
    parser.add_argument('--out-dir',type=Path,required=True)
    args=parser.parse_args()
    data=args.section.read_bytes()
    require(sha(data)==SECTION_SHA and len(data)==778816,'selected section identity differs')
    graph=parse_graph(data)
    graph['code_evidence']=code_evidence(args.module.read_bytes())
    live_raw=args.live_verification.read_bytes();live=json.loads(live_raw)
    require(live['schema']=='weapon-state-live-fep-source-verification/v1' and live['passed'] and
            live['source_section_sha256']==sha(data) and live['record_192_exact'] and
            live['selected_table0_index']==4 and live['selected_record_section_offset']==0x48f0,
            'retained live verification differs')
    selected=graph['table0'][4]
    require(selected['offset']==0xab8 and selected['list_offset']==0x48e0 and
            selected['records'][0]['offset']==0x48f0 and graph['table1'][4]['offset']==0xfb4,
            'selected chain differs')
    graph['retained_live_scope']=dict(report=str(args.live_verification.resolve()),sha256=sha(live_raw),
        record192_exact=True,selected_table0_index=4,selected_subrecord_index=0,
        full_section_runtime_bytes_verified=False,
        warning='Uses the retained verifier report; this script performs no new runtime capture.')
    graph['self_tests']=self_tests(data)
    graph['source']=dict(path=str(args.section.resolve()),bytes=len(data),sha256=sha(data),
                          retained_blob='source.bin',offsets='all section-relative, little-endian')
    graph['producer']=dict(script=str(Path(__file__).resolve()),sha256=sha(Path(__file__).read_bytes()),
                            command=[sys.executable,'-X','utf8',*sys.argv],cwd=str(Path.cwd()))
    graph['limits']=[
        'All 93+93 top-level entries inventoried offline, not all source objects live-tested.',
        'Record192 is an extent candidate except selected live-matched 0x48f0.',
        'Table1 count/span candidates fit all 93 entries; no universal format claim.',
        'Next-observed-start spans are bounded raw windows, never declared object sizes.',
        'Nested table1 offset candidates stop at opaque targets; arbitrary words are not recursively guessed as pointers.',
        'Other header tables and all uncovered bytes remain opaque in the full byte-identical source.bin.',
        'No recovered names, FX/muzzle/action identity, playback engine, or constructor behavior is claimed.']
    args.out_dir.mkdir(parents=True,exist_ok=True)
    blob=args.out_dir/'source.bin';blob.write_bytes(data)
    require(blob.read_bytes()==data,'retained blob mismatch')
    graph['lossless_blob_verified']=True
    graph_path=args.out_dir/'graph.json'
    graph_path.write_text(json.dumps(graph,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    # Read the published representations back; downstream PC readers use exactly
    # these ranges, not a private in-memory interpretation.
    published=json.loads(graph_path.read_text(encoding='utf8'))
    retained=blob.read_bytes()
    rebuilt=[]
    for span in published['lossless_partition']:
        raw=retained[span['offset']:span['offset']+span['bytes']]
        require(sha(raw)==span['sha256'],'published partition hash differs')
        rebuilt.append(raw)
    require(b''.join(rebuilt)==data,'published partition roundtrip differs')
    for node in published['nodes']:
        raw=retained[node['offset']:node['offset']+node['minimum_bytes']]
        require(raw.hex()==node['raw_hex'] and sha(raw)==node['raw_sha256'],
                'published node bytes differ')
    for filename, rows in [('table0.csv',graph['table0']),('table1.csv',graph['table1'])]:
        with (args.out_dir/filename).open('w',encoding='utf8',newline='') as stream:
            writer=csv.writer(stream)
            if filename=='table0.csv':
                writer.writerow(['index','descriptor_offset','raw_word0','table1_index','list_count','list_offset','record_offsets'])
                for x in rows:
                    writer.writerow([x['index'],hex(x['offset']),hex(x['raw_words'][0]),x['table1_index_u16_at4'],
                                     x['list_count_u16_at6'],hex(x['list_offset']),
                                     ' '.join(hex(z['offset']) for z in x['records'])])
            else:
                writer.writerow(['index','record_offset','raw_13_u32','candidate_5_counts','six_offsets'])
                for x in rows:
                    writer.writerow([x['index'],hex(x['offset']), ' '.join(hex(z) for z in x['raw_words']),
                                     ' '.join(str(z) for z in x['candidate_count_fields'].values()),
                                     ' '.join(hex(z) for z in x['offsets_at_1c_to30'])])
    verification=dict(schema='selected-fep07-graph-verification/v1',passed=True,
        source_sha256=sha(retained),module_sha256=MODULE_SHA,graph_sha256=sha(graph_path.read_bytes()),
        summary=graph['summary'],self_tests=graph['self_tests'],
        published_blob_exact=True,published_node_raw_bytes_checked=len(published['nodes']),
        partition_roundtrip_exact=True,selected_live_record192_report_bound=True,
        full_section_live_verified=False,producer=graph['producer'])
    (args.out_dir/'verification.json').write_text(json.dumps(verification,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    print(json.dumps(dict(passed=True,**graph['summary'],rejected_mutations=graph['self_tests']['rejected_mutations'])))


if __name__=='__main__':
    main()
