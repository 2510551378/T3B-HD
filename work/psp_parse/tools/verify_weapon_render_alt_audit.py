"""Check independently constrained raw evidence in the actual alternate capture."""
import copy
import hashlib
import json
from pathlib import Path

from analyze_weapon_render_dispatch import audit


def main():
    root = Path(__file__).resolve().parents[1]
    source = root/'out/AYA_BONE_GE_ACTIONS/slot0_weapon_render_alt_fire6/marker_render_dispatch.json'
    section = root/'out/WEAPON_MARKER_STATE_20261020/original_source_match_section.bin'
    producer = root/'out/WEAPON_QUEUE_ROUTES_RUNTIME_20261020/trace_weapon_marker_render_alt_sampled.js'
    output = root/'out/WEAPON_QUEUE_ROUTES_RUNTIME_20261020/render_alt_audit_cases'
    output.mkdir(exist_ok=True)
    original = json.loads(source.read_text(encoding='utf-8'))
    assert audit(source,section,producer,route='alternate')['rows_checked'] == 6
    def raw_method(c):
        item = c['rows'][0]['dispatch']['registry']['method20']['raw']
        raw = bytearray(Path(item['file']).read_bytes())
        raw[4] ^= 4
        target = output/'valid_hash_wrong_method_target.bin'
        target.write_bytes(raw)
        item.update(file=str(target),sha256=hashlib.sha256(raw).hexdigest())
    def raw_frame(c):
        item = c['rows'][0]['returned']['stack']['raw']
        raw = bytearray(Path(item['file']).read_bytes())
        raw[0x24] ^= 4
        target = output/'valid_hash_wrong_saved_RA.bin'
        target.write_bytes(raw)
        item.update(file=str(target),sha256=hashlib.sha256(raw).hexdigest())
    cases = [
        ('wrong_explicit_route',None,'original'),
        ('wrong_target_summary',lambda c:c['rows'][0]['dispatch'].update(target=0x08b9a514),'alternate'),
        ('pre_delay_a2_confused_with_parameter',lambda c:c['rows'][0]['dispatch']['gpr'].__setitem__(6,c['rows'][0]['dispatch']['parameterPointer']),'alternate'),
        ('wrong_entry_caller',lambda c:c['rows'][0]['entryGPR'].__setitem__(31,0x08b69558),'alternate'),
        ('valid_hash_wrong_method_target',raw_method,'alternate'),
        ('valid_hash_wrong_saved_RA',raw_frame,'alternate'),
        ('oversized_mutable_window',lambda c:c['rows'][0]['dispatch']['mutableDataBefore'].update(size=64),'alternate'),
        ('unordered_return_ticks',lambda c:c['rows'][0]['returned'].update(ticks=c['rows'][0]['entryTicks']),'alternate'),
        ('invented_muzzle_semantics',lambda c:c['rows'][0].update(semanticName='muzzle'),'alternate'),
        ('ge_overclaim',lambda c:c.update(geDrawObserved=True),'alternate'),
        ('missing_BP_lifecycle',lambda c:c.update(transitions=[]),'alternate'),
        ('wrong_target_entry_count',lambda c:c.update(targetEntryCount=0),'alternate'),
        ('external_pause_unreported_as_failure',lambda c:c.update(externalPauseSeen=True),'alternate'),
    ]
    results = []
    for name,mutate,route in cases:
        data = copy.deepcopy(original)
        if mutate:
            mutate(data)
        target = output/(name+'.json')
        target.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
        try:
            audit(target,section,producer,route=route)
        except (ValueError,AssertionError) as error:
            results.append({'case':name,'rejected':True,'reason':str(error)})
        else:
            raise AssertionError('Invalid render evidence accepted: '+name)
    report = {'passed':True,'valid_actual_rows_checked':6,'rejected_cases':len(results),'cases':results}
    (output/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'rejected_cases':len(results)}))


if __name__ == '__main__':
    main()
