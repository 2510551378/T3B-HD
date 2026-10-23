"""Freeze proven matrix-consumer and type6 target relationships without guessing a join."""
import argparse,datetime,hashlib,json,struct
from pathlib import Path
from analyze_fx_node_time import check,identity,sidecar,read

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--vector-capture',type=Path,required=True);p.add_argument('--matrix-verification',type=Path,required=True);p.add_argument('--failed-matrix-capture',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();check(not a.out.exists(),'Never overwrite matrix consumer audit');a.out.mkdir(parents=True)
    vector=read(a.vector_capture);matrix=read(a.matrix_verification);failed=read(a.failed_matrix_capture)
    check(vector['failure']is None and vector['ownedCPU']is None and vector['ownedMemory']is None,'Vector source capture not terminal/owned');check(matrix['status']=='actual_retained_stages_compared' and matrix['actual_sample_outputs_bit_exact'],'Matrix verifier not passed')
    row6=next(r for r in vector['rows']if r['type']==6);row14=next(r for r in vector['rows']if r['type']==14);row155=next(r for r in vector['rows']if r['type']==155);row23=next(r for r in vector['rows']if r['type']==23)
    node=sidecar(row6['entry']['before']['node']);state=sidecar(row6['entry']['before']['state']);ctx=sidecar(row6['entry']['before']['context']);
    check(struct.unpack_from('<I',node,0x40)[0]==vector['selection']['descriptor'] and struct.unpack_from('<I',ctx,0x90)[0]==vector['selection']['N'],'Vector source identity changed')
    target23=row23['random']['resolvedBase']
    target6=row6['parameterAddress'];matrixParam=row14['parameterAddress'];check(target23==target6==vector['selection']['N']+0x80,'type6/type23 shared N+0x80 target changed');check(row14['parameterAddress']==row155['parameterAddress'],'type14/type155 alias P+0x60 changed')
    # Existing matrix report explicitly records P+60 as matrix helper input.
    sample_rows=[]
    for capture in matrix['captures']:
        for sample in capture.get('rows',[]) if isinstance(capture,dict) else []:sample_rows.append(sample)
    result=dict(schema='t3b-FX-matrix-consumer-map/v1',passed=True,checked_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                source_capture=identity(a.vector_capture),matrix_verification=identity(a.matrix_verification),failed_realtime_capture=identity(a.failed_matrix_capture),
                node=dict(address=vector['selection']['N'],parameter_base=vector['selection']['N']+0x60,local_matrix_pointer=struct.unpack_from('<I',node,0x50)[0],parameter_pointer=struct.unpack_from('<I',node,0x44)[0]),
                type6=dict(type=6,declared_parameter_address=row6['parameterAddress'],internal_target=target6,target_offset=target6-vector['selection']['N'],
                           observed_state_before=struct.unpack_from('<4f',sidecar(row6['entry']['before']['parameterWindow']['raw']),0x20)),
                type23=dict(type=23,internal_target=target23,target_offset=target23-vector['selection']['N'],source_audit='same lookup mechanism as random modifier audit'),
                matrix_consumer=dict(type14_parameter_address=row14['parameterAddress'],type155_parameter_address=row155['parameterAddress'],
                                     shared_alias_confirmed=True,matrix_input_offset='P+0x60',local_matrix_pointer=struct.unpack_from('<I',node,0x50)[0],
                                     matrix_proof_scope='Existing actual matrix helper verifier; source P+60 window and GE matrix output are byte-checked.'),
                conclusions=['type6 and type23 share the observed N+0x80 target, which is not the proven matrix input P+0x60.',
                             'type14 and type155 share P+0x60 in this node; that alias is distinct from type6/type23 target.',
                             'No direct type6-to-local-matrix write or consumer was observed in the failed realtime probe.',
                             'Do not feed type6 output into the matrix pass until a same-stop writer/consumer join is captured.'],
                realtime_probe=dict(schema=failed.get('schema'),failure=failed.get('failure'),rows=len(failed.get('rows',[])),localMatrixCalls=len(failed.get('localMatrixCalls',[]))),
                formal_UE_executed=False,default_M1_changed=False)
    (a.out/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(dict(passed=True,type6_target=hex(target6),type23_target=hex(target23),matrix_input=hex(matrixParam),direct_join_proven=False)))
if __name__=='__main__':main()
