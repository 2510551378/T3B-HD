"""Independently audit bounded sequential queue-entry observations.

No exact-weapon selection, callback completion, GE or muzzle semantics inferred.
"""
import argparse
import collections
import json
from pathlib import Path
import struct

from analyze_weapon_marker_output import MODULE_SHA, check, sha, sidecar
from analyze_weapon_marker_state_output import code_blocks

PHASES = [('enqueue',0x08BBDCE8,0x19C),('range_draw',0x08BBDA68,0xB8),
          ('range_alt',0x08BBDB20,0xB8),('entry_callback',0x08BBD7F0,0x38),
          ('entry_callback_alt',0x08BBD828,0x3C),('controller_dispatch',0x08B5AC60,0x258),
          ('enqueue_control',0x08BBDCE8,0x19C)]


def u32(data, offset=0):
    return struct.unpack_from('<I',data,offset)[0]


def pointer(value, size):
    return isinstance(value,int) and value%4 == 0 and 0x08000000 <= value and value+size <= 0x0C000000


def audit(path, producer_path):
    raw = path.read_bytes()
    capture = json.loads(raw)
    check(capture['schema'] == 'weapon-queue-route-capture/v1','wrong queue route schema')
    check(capture['failure'] is None and capture['externalPause'] is False,'capture failed or externally paused')
    check(capture['errors'] == [] and capture['ownedBP'] is None,'queue debugger errors or unremoved BP')
    check(capture['semanticName'] is None and all(capture[k] is False for k in
          ('exactWeaponSelection','muzzleProven','GEConsumerProven')),'queue route scope overclaim')
    cleanup = capture['cleanup']
    check(cleanup['errors'] == [] and cleanup['buttonsReleased'] and cleanup['ownedBreakpointRemoved'] and
          cleanup['unconsumedOwnStops'] == [],'queue route cleanup incomplete')
    producer = producer_path.read_bytes()
    check(sha(producer) == capture['producer']['sha256'],'sampled producer differs')
    module = Path(capture['module']['file']).read_bytes()
    check(sha(module) == capture['module']['sha256'] == MODULE_SHA,'original module differs')
    check(sha(Path(capture['map']['file']).read_bytes()) == capture['map']['sha256'],'original function map differs')
    names = code_blocks(capture,module,required_ranges={(pc,size) for _,pc,size in PHASES})
    check(capture['phaseOrder'] == [{'name':name,'pc':pc,'size':size} for name,pc,size in PHASES],
          'queue phase order differs')
    check(len(capture['phases']) == len(PHASES),'incomplete phase sequence')
    active = None
    armed = []
    removed = []
    for transition in capture['transitions']:
        operation,pc = transition['operation'],transition['address']
        if operation == 'add_requested':
            check(active is None and pc in {item[1] for item in PHASES},'concurrent/foreign BP')
            active = pc
        elif operation == 'add_acknowledged':
            check(active == pc,'BP ACK identity differs')
            armed.append(pc)
        elif operation == 'remove':
            check(active == pc,'unowned BP removal')
            removed.append(pc)
            active = None
        else:
            raise ValueError('unknown BP transition')
    check(active is None and armed == removed == [pc for _,pc,_ in PHASES],'queue BP sequence incomplete')
    rpc_by_ticket = {}
    for item in capture['rpcLog']:
        check('ack' in item and 'timeoutAt' not in item,'queue RPC missing ACK')
        check(item['ack']['event'] == item['request']['event'] and
              item['ack']['ticket'] == item['request']['ticket'],'queue RPC response identity differs')
        check(item['wallAcknowledged'] >= item['wallRequested'],'queue RPC wall ordering differs')
        ticket = item['request']['ticket']
        check(ticket not in rpc_by_ticket,'duplicate queue RPC ticket')
        rpc_by_ticket[ticket] = item
    for item in capture['resumes']:
        check(item.get('ack',{}).get('event') == 'cpu.resume' and 'error' not in item and 'timeoutAt' not in item,
              'own resume not acknowledged')
        ack = item['ack']
        check(item['wallRequested'] <= item['wallAcknowledged'],'own resume ACK wall precedes request')
        check((item['ackKind'] == 'ticketed' and ack.get('ticket') == item['ticket']) or
              (item['ackKind'] == 'unticketed' and not ack.get('ticket')),'own resume ACK ticket differs')
        check(any(event['kind'] == 'resume_notification' and event['wall'] == item['wallAcknowledged'] and
                  event['raw'] == ack for event in capture['events']),'resume ACK not retained as notification')
    results = []
    last_ticks = None
    observed_stop_keys = []
    controllers = collections.Counter()
    for index,(phase,(name,pc,size)) in enumerate(zip(capture['phases'],PHASES)):
        check((phase['index'],phase['name'],phase['pc'],phase['size']) == (index,name,pc,size),
              'queue phase identity differs')
        check(not any(k in phase for k in ('failure','settleError','endStatusError','tickRegression','pausedAtEnd')),
              'phase contains failure/pause/tick regression')
        check(phase['ownStops'] == len(phase['rows']),'phase stop count differs')
        check(phase['wallStarted'] <= phase['armedAt'] <= phase['bpRemovedAt'] <= phase['wallFinished'],
              'phase armed wall interval differs')
        check(phase['deadline'] == phase['armedAt']+capture['bounds']['phaseMs'],'phase deadline differs')
        before,after = phase['statusSamples']
        check(before['label'] == 'before' and after['label'] == 'after','phase status inventory differs')
        for status in (before,after):
            ack = status['ack']
            rpc = rpc_by_ticket.get(ack.get('ticket'))
            check(rpc is not None and rpc['request']['event'] == 'cpu.status' and rpc['ack'] == ack,
                  'phase status differs from complete raw RPC ACK')
            check(status['wallRequested'] <= rpc['wallRequested'] <= rpc['wallAcknowledged'] <= status['wallAcknowledged'],
                  'phase status/raw RPC wall ordering differs')
        a,b = before['ack'],after['ack']
        check(all(s['event'] == 'cpu.status' and not s['paused'] and not s['stepping'] and
                  isinstance(s['ticks'],int) and s['ticks'] >= 0 for s in (a,b)),
              'phase status does not show running guest')
        check(a['ticks'] <= b['ticks'] and (last_ticks is None or last_ticks <= a['ticks']),
              'phase guest tick regression')
        last_ticks = b['ticks']
        rows = []
        for row in phase['rows']:
            check(row['pc'] == pc and row['status'] == 'read' and row['semanticName'] is None,
                  'incomplete/wrong-PC queue stop')
            check(a['ticks'] <= row['ticks'] <= b['ticks'],'stop ticks outside phase status interval')
            check(phase['wallStarted'] <= row['wallStopReceived'] <= phase['bpRemovedAt'],
                  'stop receipt outside recorded phase')
            reply = json.loads(sidecar(row['registerReply']))
            rpc = rpc_by_ticket.get(reply.get('ticket'))
            check(rpc is not None and rpc['request']['event'] == 'cpu.getAllRegs' and rpc['ack'] == reply,
                  'register sidecar differs from complete raw RPC ACK')
            values = reply['categories'][0]['uintValues']
            check(len(values) == row['gprCategoryLength'] and values[:32] == row['gpr'] and
                  len(values) >= 32,'raw GPRs disagree with summary')
            if len(values) >= 35:
                check(values[32] == pc,'raw GPR PC differs')
            g = row['gpr']
            check(row['args'] == dict(zip(('a0','a1','a2'),g[4:7])),'queue raw args differ')
            stack = row['stack']
            check(stack['address'] == g[29] and stack['size'] == len(sidecar(stack['raw'])) == 256,
                  'queue raw stack differs')
            control = row['controller']
            global_raw = sidecar(control['globalRaw'])
            check(control['globalAddress'] == 0x08C3A680 and len(global_raw) == 4 and
                  u32(global_raw) == control['address'],'controller global raw identity differs')
            c = control['address']
            detail = {'args':row['args'],'pc':hex(pc),'ticks':row['ticks'],'caller_ra':hex(g[31])}
            if pointer(c,0x30):
                data = sidecar(control['raw'])
                check(control['status'] == 'read_at_own_stop' and len(data) == 0x30 and
                      data[0x2E] == control['rawByte2e'] and data[0x2F] == control['rawByte2f'],
                      'controller byte summary differs from raw')
                controllers[(c,data[0x2E],data[0x2F])] += 1
                detail.update(controller=hex(c),controller_byte2e=data[0x2E],controller_byte2f=data[0x2F])
            else:
                check(control['status'] == 'invalid_pointer_unfollowed' and 'raw' not in control,
                      'invalid controller dereferenced')
            if name == 'controller_dispatch':
                check(c == g[4],'dispatch a0 is not the captured global controller')
                detail['mode_signed'] = g[5] if g[5] < 0x80000000 else g[5]-0x100000000
            if name in ('range_draw','range_alt'):
                start,count = g[5:7]
                # Both functions divert a0==3 to 08bbd9e8, ignoring a1/a2.
                # Its original helper processes only bucket265 on the A path.
                special = g[4] == 3
                if not special:
                    check(start <= 320 and count <= 320 and start+count <= 320,'range exceeds original 320 buckets')
                detail.update(range_start=start,range_count=count,
                              range_semantics='static_special_bucket265_helper' if special else 'static_requested_half_open_range',
                              contains_buckets_200_203=False if special else
                              all(start <= x < start+count for x in (200,203)))
            if name.startswith('entry_callback'):
                entry = row['callbackEntry']
                check(entry['address'] == g[4] and entry['size'] == 24,'callback E summary differs')
                if pointer(g[4],24):
                    e = sidecar(entry['raw'])
                    check(entry['status'] == 'read' and len(e) == 24,'callback E raw differs')
                    detail['entry_kind_byte8'] = e[8]
                    detail['entry_bucket_u16_a'] = struct.unpack_from('<H',e,10)[0]
                    for key,offset,length in [('C',12,64),('P',16,420),('N',20,64)]:
                        field = entry['fields'][key]
                        check((field['sourceOffset'],field['address'],field['size']) ==
                              (offset,u32(e,offset),length),'callback field provenance differs')
                        if pointer(field['address'],length):
                            check(field['status'] == 'read' and len(sidecar(field['raw'])) == length,
                                  'callback pointed raw window differs')
            observed_stop_keys.append((pc,row['ticks']))
            rows.append(detail)
        results.append({'name':name,'own_stops':len(rows),'before_ticks':a['ticks'],'after_ticks':b['ticks'],
                        'guest_ticks_advanced':b['ticks']-a['ticks'],'rows':rows})
    check(sorted(observed_stop_keys) == sorted((r['ownStopPC'],r['ownStopTicks']) for r in capture['resumes']),
          'observed own stops do not pair with resumes')
    return {'schema':'weapon-queue-route-independent-audit/v1','passed':True,'capture':str(path.resolve()),
            'capture_sha256':sha(raw),'producer_sha256':sha(producer),'code_blocks_checked':len(names),
            'phases':results,'stop_count':len(observed_stop_keys),
            'controllers':[{'address':hex(c),'byte2e':e,'byte2f':f,'stops':n} for (c,e,f),n in controllers.items()],
            'guest_execution_progress_verified':any(p['guest_ticks_advanced'] > 0 for p in results),
            'exact_weapon_selected':False,'actual_callback_return_verified':False,'geDrawObserved':False,
            'semanticName':None,'limits':['Sequential phase windows are not simultaneous route coverage.',
            'Only entry observations and raw controller/range data are established.',
            'No exact weapon/resource filtering, render-handler return, or GE/visual proof.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,required=True)
    parser.add_argument('--producer',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    result = audit(args.capture,args.producer)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'stops':result['stop_count'],'controllers':result['controllers'],
                      'phases':[{k:p[k] for k in ('name','own_stops','guest_ticks_advanced')} for p in result['phases']]}))


if __name__ == '__main__':
    main()
