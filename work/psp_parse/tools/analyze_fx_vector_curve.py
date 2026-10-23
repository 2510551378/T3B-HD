"""Audit type6 key/wrap and nested evaluation against retained original opcodes."""
import argparse,json,struct
from pathlib import Path
from analyze_fx_node_time import check,read,sidecar,identity,registers,u32
from analyze_fx_property_callbacks import audit,original_window
from analyze_fx_random_modifiers import references
from replay_fx_random_modifiers import vfpu_registers
from replay_fx_vector_curve import Machine

def make_machine(module,row,entry,snapshot):
    g,f=registers(entry['allRegisters']);w=snapshot['parameterWindow'];vm=Machine(module,g,f,w['address'],sidecar(w['raw']))
    for k in('record','oldRecord','typeObject','vtable'):
        item=row[k]
        if item:vm.retain(item['address'],sidecar(item['raw']))
    if entry.get('stack'):
        stack=entry['stack'];vm.retain(stack['address'],sidecar(stack['raw']))
    elif row.get('vector'):
        stack=row['vector']['stages'][0]['stack'];vm.retain(stack['address'],sidecar(stack['raw']))
    return vm

def operation(kind,path,row,entry,snapshot,expected,trace):
    g,f=registers(entry['allRegisters']);offset=row['parameterAddress']-snapshot['parameterWindow']['address'];before=sidecar(snapshot['parameterWindow']['raw'])
    def key(item):
        raw=sidecar(item['raw']);return[u32(raw,group*16+axis*4)for group in range(3)for axis in range(3)]
    return dict(kind=kind,capture=identity(path),capture_row=row['index'],state_bits=list(struct.unpack_from('<16I',before,offset)),
                previous_key_bits=key(row['oldRecord']),current_key_bits=key(row['record']),relative_time_bits=f[12],previous_relative_time_bits=f[13],
                expected_bits=list(struct.unpack_from('<16I',expected,offset)),trace=trace,
                default_entry_prefix_directly_observed=False,default_entry_prefix_established=kind=='vector_evaluate')

def audit_vectors(paths):
    results=[];ops=[];base_audits=[]
    for path in paths:
        r=read(path);references(r['rows']);base_audits.append(audit(path));module=Path(r['module']['file']).read_bytes()
        for row in r['rows']:
            if row['type']!=6:continue
            vm=make_machine(module,row,row['entry'],row['entry']['before']);stages={}
            if row.get('vector'):
                check(row['vector']['complete'],'Incomplete internal vector stages')
                for s in row['vector']['stages']:
                    def verify(machine,s=s):
                        window=s['snapshot']['parameterWindow'];actual=sidecar(window['raw'])
                        predicted=b''.join(struct.pack('<I',machine.load(window['address']+i))for i in range(0,window['size'],4))
                        check(predicted==actual,'Actual intermediate vector window differs at '+s['stage'])
                        g,f=registers(s['allRegisters']);check(machine.g[29]==g[29]and machine.g[31]==g[31],'Internal vector ABI differs')
                        v=vfpu_registers(s['allRegisters']);check(all(x is None or x==v[i]for i,x in enumerate(machine.v)),'Actual initialized VFPU lane differs at '+s['stage'])
                    stages[s['stop']['pc']]=verify
            predicted=vm.run_checked(row['target'],row['return']['stop']['pc'],stages)
            check(predicted==sidecar(row['return']['after']['parameterWindow']['raw']),'Actual full vector callback return differs')
            kind='vector_wrap'if r['mode']=='reset'else'vector_key';ops.append(operation(kind,path,row,row['entry'],row['entry']['before'],predicted,vm.trace))
            results.append(dict(capture=identity(path),row=row['index'],kind=kind,instructions=len(vm.trace),stages=list(stages),all_retained_parameter_bytes_equal=True))
            if r['mode']=='reset'and row.get('vector'):
                en=next(s for s in row['vector']['stages']if s['stage']=='evaluate_entry');ret=next(s for s in row['vector']['stages']if s['stage']=='evaluate_return')
                ev=make_machine(module,row,en,en['snapshot']);actual=sidecar(ret['snapshot']['parameterWindow']['raw']);p=ev.run_checked(0x08b94438,0x08b944e4)
                check(p==actual,'Actual nested vector evaluator differs');ops.append(operation('vector_evaluate',path,row,en,en['snapshot'],p,ev.trace))
        previous_tick=None
        references(r.get('vectorEvaluations',[]));references(r.get('vectorStateSeries',[]));series_previous=None
        for call in r.get('vectorEvaluations',[])+r.get('vectorStateSeries',[]):
            row=dict(r['rows'][call['sourceRow']]);en=call['entry'];ret=call['return'];g,f=registers(en['allRegisters']);s=r['selection'];kind=call.get('kind','vector_evaluate');start=0x08b9447c if kind=='vector_wrap'else 0x08b94438
            check(call['complete']and row['type']==6 and en['stop']['pc']==start and g[5]==s['C']and g[7]==row['parameterAddress']==call['parameterAddress'],'Wrong continuous evaluator identity/ABI')
            if kind=='vector_wrap':
                row['record']=call['currentRecord'];row['oldRecord']=call['previousRecord']
                check(row['record']['address']==g[6]and row['oldRecord']['address']==g[8],'Continuous wrap key ABI differs')
                for item in(row['record'],row['oldRecord']):original_window(item,Path(r['FEP']['file']).read_bytes(),s['FEPbase'])
            check(g[31]==ret['stop']['pc']==call['returnPC']and en['stop']['ticks']<ret['stop']['ticks'],'Nonexecuted continuous evaluator')
            if previous_tick is not None:check(previous_tick<en['stop']['ticks'],'Continuous observations not chronological')
            previous_tick=ret['stop']['ticks'];snapshot=en['snapshot'];node=sidecar(snapshot['node']);context=sidecar(snapshot['context'])
            check(u32(node,0x40)==s['descriptor']and u32(context,0x90)==s['N']and u32(node,0x44)+0x20==g[7],'Continuous evaluator changed node/parameter binding')
            original_window(dict(address=s['descriptor'],raw=snapshot['descriptor']),Path(r['FEP']['file']).read_bytes(),s['FEPbase'])
            ev=make_machine(module,row,en,snapshot);p=ev.run_checked(start,ret['stop']['pc']);check(p==sidecar(ret['snapshot']['parameterWindow']['raw']),'Continuous vector evaluator bytes differ')
            op=operation(kind,path,row,en,snapshot,p,ev.trace);op.update(default_entry_prefix_established=False,
                       node_time_bits=snapshot['timeBits'],return_pc=ret['stop']['pc'],entry_ticks=en['stop']['ticks'],return_ticks=ret['stop']['ticks'])
            if r.get('vectorTransitions'):
                op['state_series_index']=call['index']
                if series_previous is not None:check(series_previous==op['state_bits'],'Live vector state changed between recorded transitions')
                else:
                    modifier=next(rr for rr in r['rows']if rr['type']==23);w=modifier['return']['after']['parameterWindow'];b=sidecar(w['raw']);check(list(struct.unpack_from('<16I',b,0x20))==op['state_bits'],'Modifier output does not feed first live vector evaluation')
                series_previous=op['expected_bits']
            else:op['evaluation_series_index']=call['index']
            ops.append(op)
    check(ops,'No vector operations')
    return dict(passed=True,operations=ops,callbacks=results,base_audits=base_audits,actual_operations=len(ops),F32_components=16*len(ops),
                full_FX_clock_recovered=False,vector_units_or_anatomy_confirmed=False,UE_module_built=False,
                limits=['Finite/default-entry-prefix instruction replay; prefix controls are not directly exported.',
                        'Nested evaluate follows a helper vsub that consumes prefix; other entries remain default-prefix-compatible observations.',
                        'Three-component key helpers preserve state W fields, while the evaluator computes all four lanes.'])

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--capture',type=Path,action='append',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    check(not a.out.exists(),'Never overwrite vector audit');a.out.mkdir(parents=True);r=audit_vectors(a.capture)
    (a.out/'verification.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(dict(passed=True,operations=r['actual_operations'],F32_components=r['F32_components'])))
