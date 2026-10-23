"""Corrupt independent evidence constraints of the actual queue-route capture."""
import copy
import hashlib
import json
from pathlib import Path

from analyze_weapon_queue_routes import audit


def main():
    root = Path(__file__).resolve().parents[1]
    source = root/'out/AYA_BONE_GE_ACTIONS/slot0_weapon_queue_routes_fire6/queue_routes.json'
    producer = root/'out/WEAPON_QUEUE_ROUTES_RUNTIME_20261020/trace_weapon_queue_routes_sampled.js'
    output = root/'out/WEAPON_QUEUE_ROUTES_RUNTIME_20261020/audit_negative_cases'
    output.mkdir(exist_ok=True)
    original = json.loads(source.read_text(encoding='utf-8'))
    assert audit(source,producer)['stop_count'] == 30
    def raw_controller(c):
        item = c['phases'][0]['rows'][0]['controller']['raw']
        raw = bytearray(Path(item['file']).read_bytes())
        raw[0x2e] = 1
        target = output/'valid_hash_wrong_controller.bin'
        target.write_bytes(raw)
        item.update(file=str(target),sha256=hashlib.sha256(raw).hexdigest())
    def inconsistent_status_ack(c):
        for item in c['rpcLog']:
            if item['request']['event'] == 'cpu.status':
                item['ack'].update(paused=True,stepping=True,ticks=0)
    cases = [
        ('controller_summary',lambda c:c['phases'][0]['rows'][0]['controller'].update(rawByte2e=1)),
        ('valid_hash_controller_raw',raw_controller),
        ('gpr_summary',lambda c:c['phases'][0]['rows'][0]['gpr'].__setitem__(4,0)),
        ('raw_stack_address',lambda c:c['phases'][0]['rows'][0]['stack'].update(address=0x09ff0000)),
        ('status_tick_regression',lambda c:c['phases'][0]['statusSamples'][1]['ack'].update(ticks=0)),
        ('missing_resume_ack',lambda c:c['resumes'][0].pop('ack')),
        ('ge_overclaim',lambda c:c.update(GEConsumerProven=True)),
        ('weapon_overclaim',lambda c:c.update(exactWeaponSelection=True)),
        ('concurrent_breakpoints',lambda c:c['transitions'].insert(1,copy.deepcopy(c['transitions'][0]))),
        ('incomplete_phase_sequence',lambda c:c['phases'].pop()),
        ('phase_status_not_bound_to_rpc',inconsistent_status_ack),
        ('unrelated_resume_ticket',lambda c:c['resumes'][0].update(
            ackKind='ticketed',ack={'event':'cpu.resume','ticket':'unrelated'})),
        ('resume_wall_before_request',lambda c:c['resumes'][0].update(wallAcknowledged=0)),
    ]
    results = []
    for name,mutate in cases:
        data = copy.deepcopy(original)
        mutate(data)
        target = output/(name+'.json')
        target.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
        try:
            audit(target,producer)
        except (ValueError,AssertionError) as error:
            results.append({'case':name,'rejected':True,'reason':str(error)})
        else:
            raise AssertionError('Invalid queue-route evidence accepted: '+name)
    # This is internally consistent synthetic evidence, not a new runtime capture.
    # Verify that ignored a1/a2 no longer imply consumption of buckets200/203.
    special = copy.deepcopy(original)
    row = special['phases'][2]['rows'][0]
    reply = json.loads(Path(row['registerReply']['file']).read_text(encoding='utf-8'))
    reply['categories'][0]['uintValues'][4] = row['gpr'][4] = row['args']['a0'] = 3
    data = (json.dumps(reply)+'\n').encode('utf-8')
    target = output/'synthetic_mode3_regs.json'
    target.write_bytes(data)
    row['registerReply'].update(file=str(target),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
    for item in special['rpcLog']:
        if item['request']['ticket'] == reply['ticket']:
            item['ack'] = reply
    target = output/'synthetic_mode3.json'
    target.write_text(json.dumps(special,indent=2)+'\n',encoding='utf-8')
    result = audit(target,producer)['phases'][2]['rows'][0]
    assert result['range_semantics'] == 'static_special_bucket265_helper'
    assert result['contains_buckets_200_203'] is False
    report = {'passed':True,'valid_actual_capture_checked':True,'rejected_cases':len(results),
              'synthetic_mode3_scope_classification_verified':True,'cases':results}
    (output/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'rejected_cases':len(results)}))


if __name__ == '__main__':
    main()
