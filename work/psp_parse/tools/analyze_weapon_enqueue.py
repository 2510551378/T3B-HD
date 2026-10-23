"""Independently audit an observed original weapon-associated queue submission.

Queue membership is distinct from an observed renderer or GE submission.
"""
import argparse
import collections
import json
import math
import struct
from pathlib import Path

from analyze_weapon_marker_output import BASE, MODULE_SHA, GEOMETRY_SHA, check, sha, sidecar
from analyze_weapon_marker_state_output import code_blocks

ENTRY, RETURN = 0x08BBDCE8, 0x08B935F0
HEADS, TAILS = 0x08CB1460, 0x08CB1960
RESOURCE_SHA = '04afeecb38df20d41a7c24da1686e31cf70a8e631aa51e48321c776ab21d89b6'
SECTION_SHA = '97443c71b1c1d644f323c6ff611afb740329cfe11a47a711f39dc59de06ec802'
REQUIRED = {(ENTRY,0x19C),(0x08B92FCC,0x63C),(0x08B68F14,0x118),
            (0x08B6902C,0x78),(0x08B69994,0xC0),(0x08B69DBC,0xC8C)}


def u32(data, offset=0):
    return struct.unpack_from('<I',data,offset)[0]


def u16(data, offset=0):
    return struct.unpack_from('<H',data,offset)[0]


def window(item, address=None, size=None):
    data = sidecar(item['raw'])
    check(item['size'] == len(data) and (size is None or len(data) == size), 'queue window size differs')
    check(address is None or item['address'] == address, 'queue window address differs')
    at = item['address']
    check(at % 4 == 0 and 0x08000000 <= at and at+len(data) <= 0x0C000000, 'queue window outside guest RAM')
    if 'f32' in item:
        check(len(data) == 64 and list(struct.unpack('<16f',data)) == item['f32'] and
              list(struct.unpack('<16I',data)) == item['words'], 'matrix JSON/raw differs')
        check(all(math.isfinite(value) for value in item['f32']), 'nonfinite queue matrix')
    return data


def relocated(actual, original, base):
    return actual == original or (original != 0 and actual == base+original)


def live_pointer(actual, original, base):
    return actual == (base+original if original else 0)


def audit(path, section_path, producer_path=None):
    raw = path.read_bytes()
    capture = json.loads(raw)
    check(capture['schema'] == 'weapon-marker-enqueue-capture/v1', 'wrong queue schema')
    check(capture['failure'] is None and capture['inFlight'] is None, 'failed/incomplete queue capture')
    check(capture['entryPC'] == ENTRY and capture['returnPC'] == RETURN, 'queue ABI differs')
    check(capture['ownedBP'] is None and capture['semanticName'] is None and not capture['geDrawObserved'],
          'queue evidence assigned unobserved semantics/draw')
    cleanup = capture['cleanup']
    check(not cleanup['errors'] and cleanup['buttonsReleased'] and cleanup['ownedBreakpointRemoved'], 'queue cleanup incomplete')
    module = Path(capture['module']['file']).read_bytes()
    check(sha(module) == capture['module']['sha256'] == MODULE_SHA, 'original module differs')
    producer = Path(producer_path or capture['producer']['file']).read_bytes()
    check(sha(producer) == capture['producer']['sha256'], 'queue producer identity differs')
    section = section_path.read_bytes()
    check(sha(section) == SECTION_SHA, 'selected original FEP differs')
    names = code_blocks(capture,module,required_ranges=REQUIRED)
    active = None
    for event in capture['transitions']:
        op,pc = event['operation'],event['address']
        if op == 'add_requested':
            check(active is None and pc in (ENTRY,RETURN), 'concurrent/foreign queue BP')
            active = pc
        elif op == 'add_acknowledged':
            check(active == pc,'queue BP ACK differs')
        elif op == 'remove':
            check(active == pc,'removed unowned queue BP')
            active = None
        else:
            raise ValueError('unknown queue BP transition')
        check(event['ownedActiveCount'] == int(active is not None),'queue owned count differs')
    check(active is None,'queue BP remains')
    results = []
    for row in capture['rows']:
        check(row['classification'] == 'observed_enqueue' and not row['geDrawObserved'] and row['semanticName'] is None,
              'queue row classification differs')
        e,c,p,n,q = (row[k] for k in ('E','C','P','N','entrySP'))
        g = row['entryGPR']
        check(len(g) == 32 and g[4:8] == [row['entryArgs'][k] for k in ('a0','a1','a2','a3')], 'queue entry args differ')
        check(g[4] == e and g[5] == c and g[29] == q and g[31] == row['entryRA'] == RETURN,
              'queue entry SP/RA/objects differ')
        check(row['entryPC'] == ENTRY, 'queue entry PC differs')
        stack = window(row['entryStack'],q,0xD0)
        returns = []
        for offset,expected in ((0x74,0x08B68FF0),(0xA0,0x08B69080),(0xB8,0x08B69A40),(0xC8,0x08B6A9E8)):
            value = u32(stack,offset)
            check(value == expected,'queue saved caller chain differs')
            returns.append({'offset':offset,'address':q+offset,'value':value})
        check(row['callerChain'] == {'entryRA':RETURN,'savedReturns':returns}, 'reported queue chain differs')
        entry = row['entry']
        context,state,node,before_e = (window(entry[k],at,size) for k,at,size in
                                     [('context',c,0xA8),('state',p,0x1AC),('node',n,0x64),('queueEntry',e,0x18)])
        check(u32(context,0x8C) == p and u32(context,0x90) == n and u32(node,0x3C) == e, 'queue object links differ')
        check(u16(state,0xE) == 0,'state excludes original enqueue path')
        weapon = row['weapon']
        identity = weapon['identityRaw']
        handle = u32(state,0x144)
        def identity_window(key,at,size):
            item = identity[key]
            check(item['address'] == at,'raw gun identity address differs')
            data = sidecar(item['raw'])
            check(len(data) == size,'raw gun identity size differs')
            return data
        actor = u32(identity_window('primary',handle,4))
        check(actor == weapon['actor'],'primary->gun actor differs')
        actor_fields = identity_window('actorFields',actor+0x3C4,40)
        check(u32(actor_fields) == weapon['sourceBase'] and u32(actor_fields,0x24) == weapon['metadata'],'gun source pointers differ')
        meta = identity_window('metadata',weapon['metadata'],64)
        draw = identity_window('draw',weapon['drawTable'],16)
        check(u16(meta,6) == 3 and u32(meta,0x34) == weapon['drawTable'],'gun metadata differs')
        check(u16(draw) == 1 and u16(draw,4) == 243 and draw[10]*2 == 16 and u32(draw,12) == 0x522,'gun draw layout differs')
        geometry = sidecar(weapon['geometry'])
        check(len(geometry) == 243*16 and sha(struct.pack('<I',0x522)+geometry) == weapon['geometrySHA256'] == GEOMETRY_SHA,
              'gun geometry identity differs')
        resource = row['resource']
        base,t1,record = (u32(state,i) for i in (0x190,0x194,0x198))
        check((resource['source190'],resource['source194'],resource['source198']) == (base,t1,record), 'state FEP pointers differ')
        check(t1 == base+0xFB4 and record == base+0x48F0, 'selected live FEP chain differs')
        header = window(resource['header'],base,0x50)
        check(header[:8] == section[:8] and u32(header,0x14) == len(section) and
              u16(header,0x1C) == u16(header,0x1E) == 93,'FEP header identity differs')
        for at in (8,0x28,0x2C):
            check(relocated(u32(header,at),u32(section,at),base),'FEP header relocation differs')
        slot = window(resource['table1Slot4'],base+u32(section,0x2C)+16,4)
        check(live_pointer(u32(slot),0xFB4,base),'FEP live slot4 differs')
        table_record = window(resource['table1Record4'],t1,0x34)
        full_record = window(resource['record192'],record,0xC0)
        prefix = window(resource['prefix64'],record,64)
        check(full_record == section[0x48F0:0x49B0] and prefix == full_record[:64] and sha(prefix) == RESOURCE_SHA,
              'selected resource original bytes differ')
        list_offset = u32(section,0xFB4+0x20)
        nested = window(resource['nestedList'],base+list_offset,16)
        check(u16(table_record,0x12) == 4 and live_pointer(u32(table_record,0x20),list_offset,base),'nested live descriptor chain differs')
        for i in range(4):
            check(live_pointer(u32(nested,i*4),u32(section,list_offset+i*4),base),'nested live descriptor pointer differs')
        descriptor = window(entry['descriptor'],u32(node,0x40),0x48)
        offset = entry['descriptor']['address']-base
        check(offset in [0x10BA0,0x10BE8,0x10C30,0x10C78] and row['descriptorPath']['offset'] == offset,
              'actual node descriptor not selected source candidate')
        check(descriptor[:0x1C] == section[offset:offset+0x1C],'descriptor immutable prefix differs')
        for at in range(0x1C,0x48,4):
            check(live_pointer(u32(descriptor,at),u32(section,offset+at),base),'descriptor live pointer relocation differs')
        render_types = []
        post_types = []
        for observed,(role,co,po) in zip(row['descriptorPath']['lists'],[('pre',0x19,0x3C),('post',0x14,0x28),('render',0x15,0x2C)]):
            count,lo,defs = section[offset+co],u32(section,offset+po),u32(section,offset+0x1C)
            check(observed['role'] == role and observed['count'] == count == descriptor[co] and count <= 32,'descriptor list counts differ')
            indices = window(observed['list'],base+lo,(count*2+3)&~3)
            check(indices[:count*2] == section[lo:lo+count*2] and len(observed['definitions']) == count,'descriptor indices differ')
            for j,definition in enumerate(observed['definitions']):
                index = u16(indices,j*2)
                bo = u32(section,defs+index*4)
                ptr = window(definition['pointer'],base+defs+index*4,4)
                data = window(definition['raw'],base+bo,12)
                check(live_pointer(u32(ptr),bo,base) and data[:8] == section[bo:bo+8] and
                      live_pointer(u32(data,8),u32(section,bo+8),base),'definition original bytes/live pointer differ')
                check(definition['ordinal'] == j and definition['index'] == index and definition['offset'] == bo and
                      definition['type'] == u16(data) and definition['mutableDataOffset'] == u16(data,2),'definition fields differ')
                if role == 'render':render_types.append(u16(data))
                if role == 'post':post_types.append((base+bo,u16(data)))
        check(len(row['descriptorPath']['lists']) == 3 and (u32(context,0x94),14) in post_types,
              'observed current post definition is not type14')
        for name,at in [('transform50',0x50),('transform54',0x54)]:
            matrix = entry['matrices'][name]
            if u32(node,at):window(matrix,u32(node,at),64)
            else:check(matrix is None,'null node matrix given data')
        for parent in entry['parents']:
            field = parent['nodeFieldOffset']
            check(field in (0x18,0x1C),'unexpected parent traversal')
            parent_node = window(parent['node'],u32(node,field),0x64)
            for key,matrix in parent['matrices'].items():
                at = int(key)
                check(at in (0x50,0x54),'unexpected parent matrix field')
                if u32(parent_node,at):window(matrix,u32(parent_node,at),64)
                else:check(matrix is None,'null parent matrix given data')
        returned = row['returned']
        pg = returned['gpr']
        check(returned['pc'] == RETURN and returned['sp'] == pg[29] == q and returned['ra'] == pg[31] == RETURN,
              'queue return PC/SP/RA differs')
        check(all(pg[i] == g[i] for i in (16,17,18,19,20,21,22,23,30)),'queue saved registers differ')
        check(row['entryTicks'] < returned['ticks'],'queue entry/return time not ordered')
        after_e = window(returned['queueEntry'],e,0x18)
        after_c = window(returned['context'],c,0xA8)
        after_p = window(returned['state'],p,0x1AC)
        after_n = window(returned['node'],n,0x64)
        check(after_p == state and u32(after_c,0x8C) == p and u32(after_c,0x90) == n and u32(after_n,0x3C) == e,
              'enqueue changed state/object identity')
        bucket = u16(after_e,0xA)
        check(bucket < 320 and bucket == returned['bucket'] == pg[2],'observed bucket/v0 differs')
        check(after_e[8] == 1 and [u32(after_e,i) for i in (0xC,0x10,0x14)] == [c,p,n], 'actual enqueue output differs')
        before_heads = window(row['bucketSources']['beforeHeads'],HEADS,0x500)
        before_tails = window(row['bucketSources']['beforeTails'],TAILS,0x500)
        window(row['bucketSources']['staticModeTables'],0x08C2DE70,0x220)
        head = u32(window(returned['head'],HEADS+4*bucket,4))
        tail = u32(window(returned['tail'],TAILS+4*bucket,4))
        old_head,old_tail = u32(before_heads,4*bucket),u32(before_tails,4*bucket)
        check(returned['oldHeadBefore'] == old_head and returned['oldTailBefore'] == old_tail,'reported pre-bucket differs')
        check(tail == e and u32(after_e) == old_tail and u32(after_e,4) == 0,'actual new-tail linkage differs')
        if old_tail:
            previous = window(returned['oldTailAfter'],old_tail,8)
            check(old_tail != e and old_head != 0 and head == old_head and u32(previous,4) == e,'actual previous-tail linkage differs')
        else:
            check(old_head == 0 and head == e and returned['oldTailAfter'] is None,'empty queue linkage differs')
        check(returned['linkValidation'] == {'validated':True,'emptyBucket':old_tail == 0},'reported link validation differs')
        results.append({'sample':row['sample'],'state':hex(p),'node':hex(n),'queue_entry':hex(e),
                        'descriptor_section_offset':hex(offset),'static_render_types':render_types,
                        'current_post_type':14,'bucket':bucket,'empty_bucket':old_tail == 0,
                        'selector':struct.unpack_from('<h',state,0x14C)[0],
                        'enqueue_ticks':returned['ticks']-row['entryTicks'],'state_bytes_unchanged':True,
                        'geDrawObserved':False,'semanticName':None})
    check(results and len(results) == capture['returnStopCount'],'no complete queue observations/count differs')
    return {'schema':'weapon-marker-enqueue-independent-audit/v1','passed':True,
            'capture':str(path.resolve()),'capture_sha256':sha(raw),'producer_sha256':sha(producer),
            'rows_checked':len(results),'code_blocks_checked':len(names),'rows':results,
            'descriptor_histogram':dict(collections.Counter(r['descriptor_section_offset'] for r in results)),
            'actual_queue_membership_verified':True,'geDrawObserved':False,'semanticName':None,
            'limits':['Type14 enqueue and its raw source descriptor are observed; renderer callback/GE execution remains unobserved.',
                      'Static render types are original resource reachability, not observed renderer invocations.',
                      'Queue bucket is verified against actual return v0 and list links, not a VFPU depth-helper replay.',
                      'No visual muzzle/FX/projectile meaning is assigned.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,required=True)
    parser.add_argument('--section',type=Path,required=True)
    parser.add_argument('--producer',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    result = audit(args.capture,args.section,args.producer)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:result[key] for key in ('passed','rows_checked','descriptor_histogram','geDrawObserved')}))


if __name__ == '__main__':
    main()
