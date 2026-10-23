"""Valid-hash counterexamples for the independent CPU GE-emission auditor.

These deliberately corrupted derivatives are tests, never runtime observations.
"""
import argparse
import copy
import json
import struct
from pathlib import Path

from analyze_weapon_ge_emit import audit
from analyze_weapon_marker_output import check, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,required=True)
    parser.add_argument('--section',type=Path,required=True)
    parser.add_argument('--producer',type=Path,required=True)
    parser.add_argument('--out-dir',type=Path,required=True)
    a = parser.parse_args()
    check(not a.out_dir.exists(), 'refusing to overwrite counterexamples')
    original = json.loads(a.capture.read_bytes())
    positive = audit(a.capture,a.section,a.producer)
    a.out_dir.mkdir(parents=True)
    tests = []

    def replace_raw(item, raw, name):
        p = (a.out_dir / (name+'.bin')).resolve()
        p.write_bytes(raw)
        item['raw'] = dict(file=str(p),bytes=len(raw),sha256=sha(raw))

    def mutate_word(item,offset,value,name):
        data = bytearray(Path(item['raw']['file']).read_bytes())
        struct.pack_into('<I',data,offset,value)
        replace_raw(item,bytes(data),name)

    def rejected(name,edit):
        c = copy.deepcopy(original)
        edit(c,c['rows'][0])
        p = a.out_dir / (name+'.json')
        p.write_text(json.dumps(c,indent=2)+'\n',encoding='utf-8')
        try:
            audit(p,a.section,a.producer)
        except (ValueError,KeyError,AssertionError) as exc:
            tests.append(dict(name=name,rejected=True,reason=str(exc)))
        else:
            raise AssertionError('auditor accepted corrupted evidence: '+name)

    rejected('not_actual_cpu_write',lambda c,r:c.update(cpuCommandWriteObserved=False))
    rejected('stage_stop_missing',lambda c,r:c['stageStopCounts'].update(matrix_return=0))
    rejected('ge_execution_overclaim',lambda c,r:c.update(geDrawObserved=True))
    rejected('semantic_overclaim',lambda c,r:r.update(semanticName='muzzle'))
    rejected('wrong_matrix_caller',lambda c,r:r['matrix']['entry'].update(ra=0x08B982BC))
    rejected('wrong_mode_component_pointer',lambda c,r:r['matrix']['entry']['modeSource'].update(componentPointer=0x08D5E278))

    def mode_byte(c,r):
        mode = r['matrix']['entry']['modeSource']
        raw = bytearray(Path(mode['component']['raw']['file']).read_bytes())
        offset = mode['fieldAddress'] & 3
        raw[offset] ^= 1
        replace_raw(mode['component'],bytes(raw),'wrong_mode_byte_valid_hash')
    rejected('wrong_mode_byte_valid_hash',mode_byte)

    def source_id(c,r):
        item = r['geometrySource']
        mutate_word(item['record'],0x10,item['runtimeId']+1,'wrong_runtime_id_valid_hash')
    rejected('wrong_runtime_id_valid_hash',source_id)

    def source_offset(c,r):
        item = r['geometrySource']
        raw = Path(item['record']['raw']['file']).read_bytes()
        mutate_word(item['record'],0xC,struct.unpack_from('<I',raw,0xC)[0]+4,'wrong_source_relocation_valid_hash')
    rejected('wrong_source_relocation_valid_hash',source_offset)

    def view_packet(c,r):
        view = r['view']
        old = view['expectedWords'][1]
        view['expectedWords'][1] = old ^ 1
        mutate_word(view['packetAtGeometry'],4,old^1,'wrong_VIEW_payload_valid_hash')
        mutate_word(view['commandsThroughGeometry'],4,old^1,'wrong_VIEW_span_valid_hash')
    rejected('wrong_VIEW_payload_self_consistent_hashes',view_packet)

    def prim_packet(c,r):
        emit = r['emit']
        n = len(emit['expectedWords'])-1
        old = emit['expectedWords'][n]
        emit['expectedWords'][n] = old ^ 1
        mutate_word(emit['returned']['packet'],4*n,old^1,'wrong_PRIM_payload_valid_hash')
    rejected('wrong_PRIM_payload_self_consistent_hashes',prim_packet)

    def chain(c,r):
        mutate_word(r['emit']['entry']['stack'],r['path']['emitDelta']+r['path']['callbackRAOffset'],
                    0x08B694FC,'wrong_handler_chain_valid_hash')
    rejected('wrong_handler_chain_valid_hash',chain)
    def emitted_object(c,r):
        if r['dispatch']['actualType'] == 152:
            mutate_word(r['emit']['entry']['stack'],0x14,r['geometrySource']['object']+4,
                        'wrong_actual_geometry_object_valid_hash')
        else:
            r['emit']['entry']['gpr'][20] += 4
            r['emit']['returned']['gpr'][20] += 4
    rejected('wrong_actual_geometry_object_valid_hash',emitted_object)
    rejected('wrong_vertex_stride',lambda c,r:r['emit']['entry'].update(vertexStride=1))
    rejected('unordered_stage_ticks',lambda c,r:r['emit']['returned'].update(ticks=r['emit']['entry']['ticks']))
    rejected('missing_single_BP_transition',lambda c,r:c['transitions'].pop(8))
    result = dict(schema='weapon-ge-emit-auditor-counterexamples/v1',passed=True,
                  source_capture_sha256=sha(a.capture.read_bytes()),synthetic_derivatives=True,
                  positive_actual_rows=positive['rows_checked'],counterexamples_rejected=len(tests),tests=tests,
                  scope='Tests of the auditor; no counterexample is an actual capture.')
    (a.out_dir/'verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'counterexamples_rejected':len(tests)}))


if __name__ == '__main__':
    main()
