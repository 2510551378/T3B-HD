"""Independently audit original weapon-associated CPU display-list writes.

Raw memory/stack/code checks are separate from VFPU mathematics and GE execution.
No producer module is imported or executed by this auditor.
"""
import argparse
import collections
import json
import math
import struct
from pathlib import Path

from analyze_weapon_render_dispatch import audit as audit_callback
from analyze_weapon_marker_output import check, sha, sidecar
from analyze_weapon_marker_state_output import code_blocks
from analyze_weapon_enqueue import window, u32, u16

ENTRY, DISPATCH, RETURN = 0x08B69B58, 0x08B69D64, 0x08B69D6C
COMMON = {(ENTRY, 0x258), (0x08BBD828, 0x3C), (0x08B66BB4, 0x3B4),
          (0x08C01088, 0x268), (0x08BFFF98, 0xD0), (0x08BBB8D4, 0x5C),
          (0x08BFFF6C, 0x2C), (0x08C01E9C, 0x58), (0x08B6589C, 0x104)}
# Constants independently tied to the fixed original module's prologues/call sites.
PATHS = {
    152: dict(frame=0xD0, matrix_return=0x08B982B4, view_ra=0x08B982BC,
              geometry=0x08B6270C, geometry_ra=0x08B98410, table_field=0x38,
              container_field=0xA0, emit_delta=0x70, emit_return=0x08BBA214,
              saved_ra=0xCC, saved={16:0xB4,17:0xB8,18:0xBC,19:0xC0,20:0xC4,21:0xC8},
              chain={0:{0x08B5D53C,0x08B5D558},0x44:{0x08B5DDD4},
                     0x50:{0x08B6274C},0x60:{0x08B98410}},
              code={(0x08B6270C,0x4C),(0x08B5DDB0,0x30),
                    (0x08B5D258,0x350),(0x08BBA1FC,0x24)}),
    155: dict(frame=0x110, matrix_return=0x08B9A76C, view_ra=0x08B9A840,
              geometry=0x08B6050C, geometry_ra=0x08B9ACC0, table_field=0x34,
              container_field=0xA4, emit_delta=0x80, emit_return=0x08B5E3B0,
              saved_ra=0x104, saved={16:0xE0,17:0xE4,18:0xE8,19:0xEC,20:0xF0,
                                   21:0xF4,22:0xF8,23:0xFC,30:0x100},
              chain={0x10:{0x08B5EE08},0x50:{0x08B60558},0x70:{0x08B9ACC0}},
              code={(0x08B6050C,0x68),(0x08B5ECAC,0x1D4),(0x08B5E368,0x74)}),
}
SAVED = (16,17,18,19,20,21,22,23,30)


def words(raw):
    check(len(raw) % 4 == 0, 'non-word command stream')
    return list(struct.unpack('<%dI' % (len(raw)//4), raw))


def matrix(item, address):
    raw = window(item, address, 64)
    check(all(math.isfinite(v) for v in struct.unpack('<16f', raw)), 'nonfinite actual matrix')
    return raw


def registers(stage, pc, sp, ra):
    g = stage['gpr']
    check(len(g) == 32 and all(type(v) is int and 0 <= v <= 0xFFFFFFFF for v in g),
          'invalid stage register values')
    check(stage['pc'] == pc and stage['sp'] == g[29] == sp and stage['ra'] == g[31] == ra,
          'stage PC/SP/RA differs from original ABI')
    return g


def dl(item):
    address = u32(window(item['global'], 0x08CA31D8, 4))
    raw = window(item['context'], address, 0x20)
    cursor = u32(raw, 8)
    canonical = cursor-0x40000000 if 0x48000000 <= cursor < 0x4C000000 else cursor
    check(item['address'] == address and item['cursor'] == cursor and
          item['readCursor'] == canonical and cursor % 4 == 0 and
          0x08000000 <= canonical < 0x0C000000,
          'display-list pointer provenance differs')
    return address, cursor


def command_window(item, cpu_address, size):
    check(type(cpu_address) is int and cpu_address % 4 == 0 and 0 < size <= 0x20000 and size % 4 == 0,
          'invalid command-window extent/alignment')
    if 0x08000000 <= cpu_address and cpu_address+size <= 0x0C000000:
        read_address = cpu_address
    elif 0x48000000 <= cpu_address and cpu_address+size <= 0x4C000000:
        read_address = cpu_address-0x40000000
    else:
        raise ValueError('command window outside ordinary/uncached PSP RAM')
    raw = sidecar(item['raw'])
    check(item['address'] == cpu_address and item['readAddress'] == read_address and
          item['size'] == len(raw) == size, 'command CPU alias/canonical-read window differs')
    return raw


def stride(vtype):
    # Independent scalar-size layout, in PSP's weight/UV/color/normal/position order.
    check(0 < vtype <= 0xFFFFFF and ((vtype >> 11) & 3) == 0 and
          ((vtype >> 18) & 7) == 0 and ((vtype >> 7) & 3) != 0,
          'indexed/morphed/absent-position emission outside scope')
    size, alignment = 0, 1
    fields = [((vtype >> 9) & 3, ((vtype >> 14) & 7)+1, 'scalar'),
              (vtype & 3, 2, 'scalar'), ((vtype >> 2) & 7, 1, 'color'),
              ((vtype >> 5) & 3, 3, 'scalar'), ((vtype >> 7) & 3, 3, 'scalar')]
    for fmt, count, kind in fields:
        if not fmt:
            continue
        if kind == 'color':
            check(fmt in (4,5,6,7), 'illegal emitted color format')
            unit = 4 if fmt == 7 else 2
        else:
            unit = (0,1,2,4)[fmt]
        size = (size+unit-1)//unit*unit + unit*count
        alignment = max(alignment,unit)
    return (size+alignment-1)//alignment*alignment


def prim_words(g):
    # Literal SW/branch layout in original 08bfff98..08c00068.
    check(g[4] <= 7 and g[5] <= 0xFFFFFF and 1 <= g[6] <= 4096 and g[7] == 0,
          'unsupported CPU PRIM arguments')
    check(g[8] % 4 == 0 and 0x08000000 <= g[8] < 0x0C000000, 'invalid emitted vertex pointer')
    result = []
    if g[5]:
        result.append(0x12000000 | g[5])
    result += [0x10000000 | (((g[8] >> 24) & 15) << 16),
               0x01000000 | (g[8] & 0xFFFFFF), 0x04000000 | (g[4] << 16) | g[6]]
    return result


def audit(path, section_path, producer_path=None):
    capture = json.loads(path.read_bytes())
    check(capture.get('probe') == 'cpu-ge-emit-v1' and capture.get('route') == 'alternate69b58',
          'wrong CPU GE emission probe')
    check(capture['rows'] and capture['cpuCommandWriteObserved'] is True,
          'no completed actual CPU-emission observations')
    schedule, required = [], set(COMMON)
    for row in capture['rows']:
        p = PATHS[row['dispatch']['actualType']]
        schedule += [ENTRY,DISPATCH,0x08B66BB4,p['matrix_return'],0x08C01088,
                     p['geometry'],0x08BFFF98,p['emit_return'],RETURN]
        required |= p['code']
    base_report = audit_callback(path, section_path, producer_path, route='alternate',
                                 expected_bp_schedule=schedule)
    module = Path(capture['module']['file']).read_bytes()
    code = code_blocks(capture, module, required_ranges=required)
    section = section_path.read_bytes()
    n = len(capture['rows'])
    expected_counts = {name:n for name in ('dispatch','matrix_entry','matrix_return','view_entry',
                                          'geometry_entry','emit_entry','emit_return','callback_return')}
    expected_counts['entry'] = capture['entryStopCount']
    check(capture['stageStopCounts'] == expected_counts, 'nine-stage stop counters differ')
    check(capture['entryStopCount'] == n + sum(capture['rejections'].values()),
          'unaccounted target/foreign entry stop')
    check(sum(d['reads'] for d in capture['gprCategoryDiagnostics']) == sum(expected_counts.values()),
          'register read diagnostics differ from stage stops')
    check(capture['firstStopTicks'] <= capture['rows'][0]['entryTicks'] and
          capture['lastStopTicks'] == capture['rows'][-1]['returned']['ticks'],
          'first/last tick accounting differs')
    check(capture['inputs'] and all(i['acknowledged'] is True for i in capture['inputs']) and
          all(v is False for v in capture['inputs'][-1]['buttons'].values()),
          'input ACK/release accounting differs')
    results = []
    for row in capture['rows']:
        typ = row['dispatch']['actualType']
        p = PATHS[typ]
        c,node,state,b = row['C'],row['N'],row['P'],row['dispatch']['currentB']
        h = row['entrySP']-0x30-p['frame']
        check(row['handlerSP'] == h and row['cpuCommandWriteObserved'] is True and
              row['cpuEmissionClassification'] == 'observed_geometry_cpu_commands' and
              row['emitCoverage'] == 'first_matching_cpu_prim_per_handler', 'row CPU-emission scope differs')
        parameter = window(row['dispatch']['parameterBefore'])
        mutable = window(row['dispatch']['mutableDataBefore'])
        if typ == 152:
            check(u16(mutable,4) != 0xFFFF and mutable[6] == 0 and
                  parameter[0x1D] == parameter[0x1F] == 1, 'type152 path branch differs')
        else:
            check(parameter[0x48] == 0 and parameter[0x4B] == 1, 'type155 path branch differs')
        source = row['geometrySource']
        fep = row['resource']['source190']
        header = window(source['header'], fep, 0x50)
        index = struct.unpack_from('<i',parameter,0xC)[0]
        table_offset = u32(section,p['table_field'])
        check(0 <= index < 32 and source['index'] == index and
              source['sourceField'] == p['table_field'] and
              source['table'] == u32(header,p['table_field']) == fep+table_offset,
              'geometry source table/index provenance differs')
        offset = u32(section,table_offset+4*index)
        pointer = u32(window(source['slot'], fep+table_offset+4*index,4))
        check(pointer == source['source'] == fep+offset, 'geometry source record relocation differs')
        record = window(source['record'],pointer,0x18)
        runtime_id = struct.unpack_from('<i',record,0x10)[0]
        check(record[:12] == section[offset:offset+12] and
              u32(record,0xC) == fep+u32(section,offset+0xC) and
              record[0x14:] == section[offset+0x14:offset+0x18] and
              0 <= runtime_id <= 4095 and runtime_id == source['runtimeId'],
              'runtime geometry record/source bytes differ')
        context = window(source['context'],c,0xA8)
        container = u32(context,p['container_field'])
        container_raw = window(source['containerRaw'],container,0x24)
        objects = u32(container_raw)
        obj = u32(window(source['objectSlot'],objects+runtime_id*4,4))
        check(source['container'] == container and source['object'] == obj,
              'runtime ID to geometry-object chain differs')
        object_raw = window(source['objectRaw'],obj,0x20)

        me,mr = row['matrix']['entry'],row['matrix']['returned']
        mg = registers(me,0x08B66BB4,h,p['matrix_return'])
        mrg = registers(mr,p['matrix_return'],h,p['matrix_return'])
        check(all(mg[i] == mrg[i] for i in SAVED), 'matrix helper changed saved GPRs')
        nc = window(me['node'],node,0x64)
        pc = window(me['state'],state,0x1AC)
        cc = window(me['context'],c,0xA8)
        check([u32(cc,i) for i in (0x8C,0x90,0x94)] == [state,node,b] and u32(nc,0x1C) == 0,
              'matrix current context/parent path differs')
        frame = window(me['handlerStack'],h,p['frame'])
        check(u32(frame,p['saved_ra']) == RETURN and
              all(u32(frame,at) == row['dispatch']['gpr'][r] for r,at in p['saved'].items()),
              'matrix handler saved frame differs')
        check(mg[4:7] == [c,node,u32(nc,0x50)] and mg[8] == h+0x10 and
              me['inputPointer'] == mg[6] and me['outputPointer'] == mg[8] and me['mode'] == mg[7],
              'matrix actual input/output ABI differs')
        matrix(me['input'],mg[6]); matrix(me['p60'],state+0x60)
        check(window(me['p60']) == pc[0x60:0xA0], 'matrix P60 windows disagree at same stop')
        window(me['outputBefore'],h+0x10,64)  # uninitialized destination may contain nonfinite bits
        output = matrix(mr['output'],h+0x10)
        mode = me['modeSource']
        definition = window(row['dispatch']['definition'],b,12)
        indices = window(mode['indices'],u32(definition,8),4)
        mi = u16(indices,2)
        check(mi < 96 and mi == mode['index'], 'matrix mode component index differs')
        component = u32(window(mode['slot'],u32(nc,0x48)+mi*4,4))
        # Current schema explicitly separates a byte-structured pointer from aligned raw reads.
        check(mode['componentPointer'] == component and mode['fieldAddress'] == component+1 and
              mode['byteOffset'] == (component+1) & 3,
              'matrix mode byte-field pointer differs')
        field = component+1
        cb = window(mode['component'],field & ~3,4)
        check(0x08000000 <= component < 0x0C000000-1 and cb[field & 3] == mg[7],
              'actual matrix mode byte differs')
        all_regs = json.loads(sidecar(me['allRegisters']['raw']))
        check(all_regs['categories'][0]['uintValues'][:32] == mg,
              'complete register snapshot disagrees with stage GPRs')
        gm = u32(window(me['globalSlot'],0x08C3B58C,4))
        matrix(me['globalMatrix'],gm)

        ve,ge = row['view']['entry'],row['geometryHelper']['entry']
        vdl,vd = dl(ve['dl'])
        vg = registers(ve,0x08C01088,h-0x60,0x08BFFF8C)
        check(vg[4:7] == [vdl,1,h-0x50], 'VIEW context/kind/input ABI differs')
        stack = window(ve['stack'],h-0x60,0x60)
        check(u32(stack) == 0x08BBB924 and u32(stack,0x50) == p['view_ra'], 'VIEW wrapper/handler chain differs')
        view_input = matrix(ve['input'],h-0x50)
        matrix(ve['handlerMatrix'],h+0x10)
        global_ptr = u32(window(ve['globalSlot'],0x08C3B588,4))
        matrix(ve['globalMatrix'],global_ptr)
        command_window(ve['packetBefore'],vd,52)
        view_words = [0x3C000000] + [0x3D000000 | (u32(view_input,i*4) >> 8)
                                    for i in (0,1,2,4,5,6,8,9,10,12,13,14)]
        actual_view = command_window(row['view']['packetAtGeometry'],vd,52)
        check(words(actual_view) == row['view']['expectedWords'] == view_words,
              'actual VIEW command bytes differ from sampled writer input')
        gg = registers(ge,p['geometry'],h,p['geometry_ra'])
        gd, gc = dl(ge['dl'])
        check(gd == vdl and 52 <= gc-vd <= 0x1000 and (gc-vd) % 4 == 0,
              'VIEW-to-geometry command cursor extent differs')
        commands = command_window(row['view']['commandsThroughGeometry'],vd,gc-vd)
        check(commands[:52] == actual_view, 'retained VIEW command span differs')
        check(gg[5] == runtime_id and
              (gg[4] == c and gg[6] == 0 and gg[7] == h if typ == 152 else
               gg[4] == container and gg[6] == h), 'geometry helper arguments differ from resource provenance')
        gcc = window(ge['context'],c,0xA8)
        check(u32(gcc,p['container_field']) == container, 'geometry container changed')
        window(ge['auxiliaryVector'],h,16)

        ee,er = row['emit']['entry'],row['emit']['returned']
        eg = registers(ee,0x08BFFF98,h-p['emit_delta'],p['emit_return'])
        erg = registers(er,p['emit_return'],eg[29],p['emit_return'])
        check(all(eg[i] == erg[i] for i in SAVED), 'PRIM helper changed saved GPRs')
        es = window(ee['stack'],eg[29],0x1A0)
        check(all(u32(es,at) in allowed for at,allowed in p['chain'].items()) and
              u32(es,p['emit_delta']+p['saved_ra']) == RETURN, 'geometry-to-emitter saved call chain differs')
        if typ == 152:
            check([u32(es,at) for at in (0x10,0x14,0x18)] == [h,obj,u32(container_raw,0x20)],
                  'type152 actual emitter geometry-object/vector/auxiliary provenance differs')
        else:
            check([eg[20],eg[21]] == [obj,u32(container_raw,0x20)],
                  'type155 actual emitter geometry-object/auxiliary provenance differs')
        expected = prim_words(eg)
        vertex_stride = stride(eg[5])
        check(vertex_stride == ee['vertexStride'] and vertex_stride*eg[6] <= 0x20000,
              'emitted stride/extent differs')
        vertices = window(ee['vertices'],eg[8],vertex_stride*eg[6])
        if typ == 155:
            record = window(ee['drawRecord'],eg[19],16)
            check([u32(record,o) for o in (0,8,12)] == [eg[4],eg[6],eg[8]] and eg[17] == eg[5],
                  'type155 draw record/VTYPE differs')
        ed, ec = dl(ee['dl'])
        rd, rc = dl(er['dl'])
        check(ed == rd == gd and ec >= gc and rc == ec+4*len(expected),
              'CPU PRIM context/cursor delta differs')
        command_window(ee['packetBefore'],ec,4*len(expected))
        packet = command_window(er['packet'],ec,4*len(expected))
        check(words(packet) == row['emit']['expectedWords'] == expected,
              'actual PRIM command bytes differ from original emitter arguments')
        ticks = [row['entryTicks'],row['dispatch']['ticks'],me['ticks'],mr['ticks'],
                 ve['ticks'],ge['ticks'],ee['ticks'],er['ticks'],row['returned']['ticks']]
        check(all(a < b for a,b in zip(ticks,ticks[1:])), 'nine original stages not strictly guest-time ordered')
        results.append(dict(sample=row['sample'],actual_type=typ,mode=mg[7],runtime_geometry_id=runtime_id,
                            source_record_offset=hex(offset),geometry_object=hex(obj),
                            geometry_object_sha256=sha(object_raw),matrix_output_sha256=sha(output),
                            view_packet_bytes=len(actual_view),view_packet_words=view_words,
                            primitive=eg[4],vtype=hex(eg[5]),vertex_count=eg[6],vertex_stride=vertex_stride,
                            vertices_sha256=sha(vertices),prim_packet_words=expected,
                            prim_packet_bytes=len(packet),emit_ticks=er['ticks']-ee['ticks'],
                            callback_ticks=ticks[-1]-ticks[1],semanticName=None,geDrawObserved=False))
    return dict(schema='weapon-cpu-ge-emit-independent-audit/v1',passed=True,
                capture=str(path.resolve()),capture_sha256=sha(path.read_bytes()),
                producer_sha256=base_report['producer_sha256'],rows_checked=n,
                code_blocks_checked=len(code),actual_callback_invocation_return_verified=True,
                actual_cpu_VIEW_and_PRIM_writes_verified=True,rows=results,
                actual_type_histogram=dict(collections.Counter(r['actual_type'] for r in results)),
                geDrawObserved=False,semanticName=None,
                limits=['CPU commands are observed; GE execution and final pixels are unverified.',
                        'Only the first matching CPU PRIM per sampled handler is retained.',
                        'Exact weapon/resource association does not assign muzzle/FX semantics.',
                        'Matrix arithmetic and VFPU prefixes require a separate independent replay.',
                        'No production M1 socket or timeline is replaced by these observations.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,required=True)
    parser.add_argument('--section',type=Path,required=True)
    parser.add_argument('--producer',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    check(not args.out.exists(), 'refusing to overwrite audit')
    result = audit(args.capture,args.section,args.producer)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'rows_checked':result['rows_checked'],
                      'code_blocks_checked':result['code_blocks_checked']},ensure_ascii=False))


if __name__ == '__main__':
    main()
