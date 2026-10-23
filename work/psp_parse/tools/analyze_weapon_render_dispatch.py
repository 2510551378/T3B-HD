"""Audit actual original renderer JALR and callback return from retained bytes.

Does not promote callback reachability to observed GE commands or visual meaning.
"""
import argparse
import collections
import json
import struct
from pathlib import Path

from analyze_weapon_marker_output import BASE, MODULE_SHA, GEOMETRY_SHA, check, sha, sidecar
from analyze_weapon_marker_state_output import code_blocks
from analyze_weapon_enqueue import window, u32, u16, live_pointer, SECTION_SHA, RESOURCE_SHA

ENTRY, DISPATCH, RETURN = 0x08B692F4, 0x08B694F4, 0x08B694FC
TYPES = {152:(0x08B9809C,0x3F0,32,7),155:(0x08B9A514,0x808,0x4C,0x20)}


def gun(weapon, handle):
    raw = weapon['identityRaw']
    def at(key,address,size):
        data = sidecar(raw[key]['raw'])
        check(raw[key]['address'] == address and len(data) == size,'render gun raw identity differs')
        return data
    actor = u32(at('primary',handle,4))
    check(actor == weapon['actor'],'render handle actor differs')
    fields = at('actorFields',actor+0x3C4,40)
    check(u32(fields) == weapon['sourceBase'] and u32(fields,0x24) == weapon['metadata'],'render gun source pointers differ')
    metadata = at('metadata',weapon['metadata'],64)
    draw = at('draw',weapon['drawTable'],16)
    check(u16(metadata,6) == 3 and u32(metadata,0x34) == weapon['drawTable'],'render gun metadata differs')
    check(u16(draw) == 1 and u16(draw,4) == 243 and draw[10]*2 == 16 and u32(draw,12) == 0x522,'render gun draw differs')
    geometry = sidecar(weapon['geometry'])
    check(len(geometry) == 243*16 and sha(struct.pack('<I',0x522)+geometry) == weapon['geometrySHA256'] == GEOMETRY_SHA,
          'render gun geometry differs')


def audit(path, section_path, producer_path=None, allow_empty=False, route='original', expected_bp_schedule=None):
    check(route in ('original','alternate'),'unknown explicit render route')
    if route == 'alternate':
        ENTRY,DISPATCH,RETURN,SIZE,WRAPPER,WRAPPER_SIZE,ENTRY_RA = (
            0x08B69B58,0x08B69D64,0x08B69D6C,0x258,0x08BBD828,0x3C,0x08BBD858)
    else:
        ENTRY,DISPATCH,RETURN,SIZE,WRAPPER,WRAPPER_SIZE,ENTRY_RA = (
            0x08B692F4,0x08B694F4,0x08B694FC,0x24C,0x08B69540,0x24,0x08B69558)
    raw = path.read_bytes()
    capture = json.loads(raw)
    check(capture['schema'] == 'weapon-marker-render-dispatch-capture/v1','wrong render schema')
    check(capture['failure'] is None and capture['inFlight'] is None,'failed/incomplete render capture')
    check(capture['entryPC'] == ENTRY and capture['dispatchPC'] == DISPATCH and capture['returnPC'] == RETURN,'render phases differ')
    check(capture['ownedBP'] is None and capture['semanticName'] is None and not capture['geDrawObserved'],'render scope overclaim')
    cleanup = capture['cleanup']
    check(not cleanup['errors'] and cleanup['buttonsReleased'] and cleanup['ownedBreakpointRemoved'],'render cleanup incomplete')
    module = Path(capture['module']['file']).read_bytes()
    check(sha(module) == capture['module']['sha256'] == MODULE_SHA,'render original module differs')
    if expected_bp_schedule is not None:
        check(route == 'alternate' and capture.get('probe') == 'cpu-ge-emit-v1',
              'extended schedule requires the explicit GE CPU-emission probe')
        geometry_paths = {152:(0x08B982B4,0x08B6270C,0x08BBA214),
                          155:(0x08B9A76C,0x08B6050C,0x08B5E3B0)}
        fixed = []
        for row in capture['rows']:
            typ = row['dispatch']['actualType']
            check(typ in geometry_paths,'unsupported extended render path')
            matrix_return,geometry,emit_return = geometry_paths[typ]
            fixed.extend((ENTRY,DISPATCH,0x08B66BB4,matrix_return,0x08C01088,
                          geometry,0x08BFFF98,emit_return,RETURN))
        check(expected_bp_schedule == fixed,'extended BP lifecycle differs from original-module paths')
    allowed_bps = set(expected_bp_schedule) if expected_bp_schedule is not None else {ENTRY,DISPATCH,RETURN}
    check(all(isinstance(pc,int) and pc%4 == 0 and BASE <= pc < BASE+len(module) for pc in allowed_bps),
          'explicit BP schedule contains a non-module instruction')
    producer = Path(producer_path or capture['producer']['file']).read_bytes()
    check(sha(producer) == capture['producer']['sha256'],'render producer differs')
    section = section_path.read_bytes()
    check(sha(section) == SECTION_SHA,'render original FEP differs')
    names = code_blocks(capture,module,required_ranges={(ENTRY,SIZE),(WRAPPER,WRAPPER_SIZE)})
    ranges = {(block['address'],block['size']) for block in capture['codeIdentity']['checks']}
    check(u32(module,DISPATCH-BASE) == 0x0140F809 and u32(module,DISPATCH+4-BASE) == 0x01003025,
          'original JALR t2/delay move a2,t0 differs')
    active = None
    for transition in capture['transitions']:
        op,pc = transition['operation'],transition['address']
        if op == 'add_requested':
            check(active is None and pc in allowed_bps,'concurrent/foreign render BP')
            active = pc
        elif op == 'add_acknowledged':check(active == pc,'render BP ACK differs')
        elif op == 'remove':
            check(active == pc,'removed unowned render BP')
            active = None
        else:raise ValueError('unknown render BP transition')
        check(transition['ownedActiveCount'] == int(active is not None),'render active count differs')
    check(active is None,'render BP remains')
    if not capture['rows'] and allow_empty:
        check(capture['entryStopCount'] == capture['dispatchStopCount'] == capture['returnStopCount'] ==
              capture['targetEntryCount'] == 0,'empty report has unaccounted render stops')
        check(capture['firstStopTicks'] is None and capture['lastStopTicks'] is None,
              'empty report claims stop ticks')
        check(capture['externalPauseSeen'] is False and capture['initialBreakpoints'] == [] and
              capture['rejections'] == {},'empty report has unexplained pauses/breakpoints/rejections')
        check(capture['transitions'] == [
            {'operation':'add_requested','address':ENTRY,'ownedActiveCount':1},
            {'operation':'add_acknowledged','address':ENTRY,'ownedActiveCount':1},
            {'operation':'remove','address':ENTRY,'ownedActiveCount':0}],
            'empty report did not arm and remove the entry breakpoint')
        check(capture['negativeScope'] is not None,'empty report lacks its negative scope')
        inputs = capture['inputs']
        check(len(inputs) >= 3 and all(item['acknowledged'] is True for item in inputs),
              'empty capture input ACKs incomplete')
        check(any(any(item['buttons'].values()) for item in inputs) and
              all(value is False for value in inputs[-1]['buttons'].values()),
              'empty capture held-input/release evidence incomplete')
        return {'schema':'weapon-render-dispatch-independent-audit/v1','passed':True,
                'classification':'bounded_no_render_stops','capture':str(path.resolve()),
                'capture_sha256':sha(raw),'producer_sha256':sha(producer),'rows_checked':0,
                'code_blocks_checked':len(names),'actual_handler_histogram':{},'rows':[],
                'actual_callback_invocation_return_verified':False,
                'guest_execution_progress_verified':False,'geDrawObserved':False,'semanticName':None,
                'limits':['Only code identity, armed breakpoint, input ACKs and cleanup are verified.',
                          'No breakpoint stops or guest-tick samples were retained; guest execution progress is unverified.',
                          'This does not establish absence of a render consumer or correctness of the selected entry path.']}
    check(capture['externalPauseSeen'] is False,'render capture includes an external pause')
    check(capture['targetEntryCount'] == len(capture['rows']) and
          capture['entryStopCount'] >= capture['targetEntryCount'],'render target/entry counters differ')
    # The GE-emit auditor supplies an independently constructed fixed schedule.
    # The CLI and ordinary captures retain the original strict three-stage cycle.
    expected_cycle = expected_bp_schedule if expected_bp_schedule is not None else [
        pc for _ in capture['rows'] for pc in (ENTRY,DISPATCH,RETURN)]
    check([t['address'] for t in capture['transitions'] if t['operation'] == 'add_requested'] == expected_cycle and
          [t['address'] for t in capture['transitions'] if t['operation'] == 'add_acknowledged'] == expected_cycle and
          [t['address'] for t in capture['transitions'] if t['operation'] == 'remove'] == expected_cycle,
          'render positive capture lacks complete three-phase BP lifecycle')
    results = []
    for row in capture['rows']:
        check(row['classification'] == 'observed_handler_invocation_return' and row['semanticName'] is None and
              not row['geDrawObserved'],'render row overclaims scope')
        c,p,n,d,q = (row[key] for key in ('C','P','N','D','entrySP'))
        g = row['entryGPR']
        check(len(g) == 32 and g[4:8] == [c,p,n,1] and row['entryArgs'] == {'C':c,'P':p,'N':n,'pass':1},'render entry args differ')
        check(g[29] == q and g[31] == row['entryRA'] == ENTRY_RA and row['entryPC'] == ENTRY,'render entry PC/SP/RA differs')
        entry = row['entry']
        window(entry['context'],c,0xA8)  # Shared context need not name P/N yet.
        state = window(entry['state'],p,0x1AC)
        node = window(entry['node'],n,0x64)
        window(entry['stack'],q,0x30)
        check(u32(node,0x40) == d,'render actual node D differs')
        gun(row['weapon'],u32(state,0x144))
        base,t1,record = (u32(state,at) for at in (0x190,0x194,0x198))
        resource = row['resource']
        check((resource['source190'],resource['source194'],resource['source198']) == (base,t1,record) and
              t1 == base+0xFB4 and record == base+0x48F0,'render state FEP identity differs')
        full = window(resource['record192'],record,0xC0)
        prefix = window(resource['prefix64'],record,64)
        check(full == section[0x48F0:0x49B0] and prefix == full[:64] and sha(prefix) == RESOURCE_SHA,'render FEP192 differs')
        descriptor = window(entry['descriptor'],d,0x48)
        offset = d-base
        check(offset in (0x10BA0,0x10BE8,0x10C30,0x10C78) and row['descriptorPath']['offset'] == offset,'render D source differs')
        check(descriptor[:0x1C] == section[offset:offset+0x1C],'render D immutable bytes differ')
        for at in range(0x1C,0x48,4):
            check(live_pointer(u32(descriptor,at),u32(section,offset+at),base),'render D pointer not live-relocated')
        render = row['renderList']
        count,lo,defs = section[offset+0x15],u32(section,offset+0x2C),u32(section,offset+0x1C)
        check(count == render['count'] == 1 and render['role'] == 'render','render list count differs')
        indices = window(render['list'],base+lo,4)
        index = u16(indices)
        check(index == u16(section,lo) and len(render['definitions']) == 1,'render selected index differs')
        bo = u32(section,defs+index*4)
        definition = render['definitions'][0]
        check(definition['index'] == index and definition['offset'] == bo,'render definition interpretation differs')
        check(live_pointer(u32(window(definition['pointer'],base+defs+index*4,4)),bo,base),'render definition pointer differs')
        source_b = window(definition['raw'],base+bo,12)
        check(source_b[:8] == section[bo:bo+8] and live_pointer(u32(source_b,8),u32(section,bo+8),base),'render B source bytes differ')
        dispatch = row['dispatch']
        dg = dispatch['gpr']
        check(dispatch['pc'] == DISPATCH and dispatch['sp'] == dg[29] == q-0x30 and
              dg[16] == c and dg[17] == n and dg[19] == d,'before-JALR SP/objects differ')
        check(dg[18] == 1 and dg[20] == 0 and dg[21] == base+lo and dg[22] == 0x08C3ACC0 and dg[23] == 0x08C3A820,
              'before-JALR pass/index/registry registers differ')
        local = window(dispatch['stack'],q-0x30,0x30)
        check(u32(local,0x24) == row['entryRA'],'dispatch saved caller RA differs')
        for register,at in zip(range(16,24),range(4,0x24,4)):
            check(u32(local,at) == g[register],'dispatch saved entry register differs')
        context = window(dispatch['context'],c,0xA8)
        dispatch_node = window(dispatch['node'],n,0x64)
        b = window(dispatch['definition'],base+bo,12)
        check(b == source_b and u32(context,0x8C) == p and u32(context,0x90) == n and u32(context,0x94) == base+bo and
              u32(dispatch_node,0x40) == d,'actual dispatch context/B/N differs')
        typ = u16(b)
        check(typ in TYPES and dispatch['actualType'] == typ and dispatch['definitionIndex'] == index and dispatch['currentB'] == base+bo,
              'actual callback type/definition differs')
        target,size,parameter_bytes,data_bytes = TYPES[typ]
        check((target,size) in ranges and dispatch['target'] == dg[10] == target,'actual target/code differs')
        registry = dispatch['registry']
        slot_address = 0x08C3A820+4*typ
        obj = u32(window(registry['slot'],slot_address,4))
        vtable = u32(window(registry['object'],obj,4))
        window(registry['vtable'],vtable,0x28)
        method = window(registry['method20'],vtable+0x20,8)
        adjustment = struct.unpack_from('<h',method)[0]
        check(obj == u32(module,slot_address-BASE) and vtable == u32(module,obj-BASE) and
              method == module[vtable+0x20-BASE:vtable+0x28-BASE] and u32(method,4) == target,'live registry differs from original')
        check(registry['thisAdjustment'] == adjustment and registry['target'] == target,'reported registry interpretation differs')
        filter_address = 0x08C3ACC0+typ
        filter_raw = window(registry['filter']['raw'],filter_address&~3,4)
        filter_byte = filter_raw[filter_address&3]
        check(registry['filter']['fieldAddress'] == filter_address and registry['filter']['byte'] == filter_byte and filter_byte&1 == 0,
              'actual render filter differs')
        check(dg[4] == (obj+adjustment)&0xFFFFFFFF and dg[5] == c and dg[6] == vtable+0x20,'pre-delay callback args differ')
        parameter = u32(window(dispatch['parameterSlot'],u32(dispatch_node,0x48)+4*index,4))
        mutable_base = u32(dispatch_node,0x44)
        mutable = mutable_base+u16(b,2)
        check(parameter == dg[8] == dispatch['parameterPointer'] == dispatch['expectedDelaySlotA2'] and
              mutable == dg[7] == dispatch['mutableDataPointer'] and dispatch['mutableDataBase'] == mutable_base,
              'callback parameter/mutable pointer provenance differs')
        check(u16(b,2)+data_bytes <= u16(descriptor,2),'callback mutable read exceeds original D allocation')
        parameter_before = window(dispatch['parameterBefore'],parameter,parameter_bytes)
        mutable_before = window(dispatch['mutableDataBefore'],mutable,data_bytes)
        returned = row['returned']
        rg = returned['gpr']
        check(returned['pc'] == RETURN and returned['sp'] == rg[29] == q-0x30 and returned['ra'] == rg[31] == RETURN,'callback return PC/SP/RA differs')
        check(all(rg[i] == dg[i] for i in (16,17,18,19,20,21,22,23,30)),'callback changed saved GPRs')
        returned_stack = window(returned['stack'],q-0x30,0x30)
        # +0..27 contains saved f20/GPR/RA; +28..2f is not assigned a
        # callee-preservation meaning by the original prologue.
        check(returned_stack[:0x28] == local[:0x28],'callback changed saved dispatcher frame')
        rc = window(returned['context'],c,0xA8)
        rp = window(returned['state'],p,0x1AC)
        rn = window(returned['node'],n,0x64)
        check([u32(rc,at) for at in (0x8C,0x90,0x94)] == [p,n,base+bo] and u32(rn,0x40) == d,'callback changed object identity')
        check([u32(rp,at) for at in (0x190,0x194,0x198)] == [base,t1,record],'callback changed FEP identity')
        gun(returned['weapon'],u32(rp,0x144))
        check(returned['weapon']['actor'] == row['weapon']['actor'],'callback changed exact weapon actor')
        check(window(returned['resourceRecord192'],record,0xC0) == full,'callback changed source record')
        parameter_after = window(returned['parameterAfter'],parameter,parameter_bytes)
        mutable_after = window(returned['mutableDataAfter'],mutable,data_bytes)
        check(row['entryTicks'] < dispatch['ticks'] < returned['ticks'],'render stages not time-ordered')
        results.append({'sample':row['sample'],'state':hex(p),'node':hex(n),'descriptor_section_offset':hex(offset),
                        'actual_type':typ,'actual_handler':hex(target),'parameter_bytes':parameter_bytes,'mutable_bytes':data_bytes,
                        'callback_ticks':returned['ticks']-dispatch['ticks'],
                        'parameter_changed':parameter_before != parameter_after,'mutable_data_changed':mutable_before != mutable_after,
                        'geDrawObserved':False,'semanticName':None})
    check(results and len(results) == capture['dispatchStopCount'] == capture['returnStopCount'],'render observation count differs')
    return {'schema':'weapon-render-dispatch-independent-audit/v1','passed':True,'capture':str(path.resolve()),
            'capture_sha256':sha(raw),'producer_sha256':sha(producer),'route':route,'rows_checked':len(results),'code_blocks_checked':len(names),
            'actual_handler_histogram':dict(collections.Counter(r['actual_handler'] for r in results)),
            'rows':results,'actual_callback_invocation_return_verified':True,'geDrawObserved':False,'semanticName':None,
            'limits':['Actual JALR target and callback return are observed; internal GE commands and final visual remain unobserved.',
                      'Type-specific mutable windows are bounded by original D allocation and actual handler reads.',
                      'No muzzle/particle/projectile semantic is assigned.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,required=True)
    parser.add_argument('--section',type=Path,required=True)
    parser.add_argument('--producer',type=Path)
    parser.add_argument('--route',choices=('original','alternate'),default='original',
                        help='Require the explicitly selected original-module entry/caller/delay-slot ABI.')
    parser.add_argument('--allow-empty',action='store_true',
                        help='Audit a zero-stop capture as bounded evidence, never as an observed callback.')
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    result = audit(args.capture,args.section,args.producer,args.allow_empty,args.route)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:result[key] for key in ('passed','rows_checked','actual_handler_histogram','geDrawObserved')}))


if __name__ == '__main__':
    main()
