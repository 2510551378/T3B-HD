"""Check that the retained zero-stop capture cannot become callback evidence."""
import copy
import json
from pathlib import Path

from analyze_weapon_render_dispatch import audit


def main():
    root = Path(__file__).resolve().parents[1]
    capture = root/'out/AYA_BONE_GE_ACTIONS/slot0_weapon_render_fire6/marker_render_dispatch.json'
    section = root/'out/WEAPON_MARKER_STATE_20261020/original_source_match_section.bin'
    producer = root/'out/WEAPON_MARKER_STATE_CONSUMER_20261020/trace_weapon_marker_render_dispatch_sampled.js'
    output = root/'out/WEAPON_MARKER_STATE_CONSUMER_20261020/render_empty_audit_cases'
    output.mkdir(exist_ok=True)
    original = json.loads(capture.read_text(encoding='utf-8'))
    valid = audit(capture,section,producer,allow_empty=True)
    assert valid['passed'] and valid['rows_checked'] == 0
    assert valid['actual_callback_invocation_return_verified'] is False
    assert valid['guest_execution_progress_verified'] is False
    cases = [
        ('default_refuses_empty',None,False),
        ('invented_entry_count',lambda c:c.update(entryStopCount=1),True),
        ('invented_guest_ticks',lambda c:c.update(firstStopTicks=100,lastStopTicks=200),True),
        ('ge_draw_overclaim',lambda c:c.update(geDrawObserved=True),True),
        ('missing_entry_ack',lambda c:c['transitions'].pop(1),True),
        ('missing_input_ack',lambda c:c['inputs'][1].update(acknowledged=False),True),
        ('unreleased_input',lambda c:c['inputs'][-1]['buttons'].update(square=True),True),
        ('external_pause',lambda c:c.update(externalPauseSeen=True),True),
        ('incomplete_cleanup',lambda c:c['cleanup'].update(ownedBreakpointRemoved=False),True),
    ]
    results = []
    for name,mutate,allow_empty in cases:
        data = copy.deepcopy(original)
        if mutate:
            mutate(data)
        path = output/(name+'.json')
        path.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
        try:
            audit(path,section,producer,allow_empty=allow_empty)
        except (ValueError,AssertionError) as error:
            results.append({'case':name,'rejected':True,'reason':str(error)})
        else:
            raise AssertionError('Invalid evidence accepted: '+name)
    report = {'passed':True,'valid_empty_evidence_checked':True,
              'actual_callback_invocation_return_verified':False,
              'rejected_cases':len(results),'cases':results}
    (output/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'rejected_cases':len(results)}))


if __name__ == '__main__':
    main()
