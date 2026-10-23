"""Export the original descriptor10c78 type155 keys, with runtime callback cross-checks."""
import argparse
import json
import struct
from pathlib import Path
from analyze_fx_node_time import check,identity,read,sidecar,u16,u32


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--proof',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();check(not args.out.exists(),'Never replace authored source bank evidence');args.out.mkdir(parents=True)
    proof=read(args.proof);check(proof['passed'],'No actual callback proof')
    captures=[read(Path(c['capture']['file']))for c in proof['captures']]
    first=captures[0];source=Path(first['FEP']['file']);asset=source.read_bytes();check(identity(source)['sha256']==first['FEP']['sha256'],'Original FEP changed')
    descriptor=0x10c78;d=asset[descriptor:descriptor+0x48];table=u32(d,0x1c);definitions=[];aliases={}
    for index in range(d[8]):
        at=u32(asset,table+index*4);type_,offset=struct.unpack_from('<HH',asset,at)
        definitions.append(dict(index=index,source_type=type_,parameter_offset=offset,definition_offset=at))
        aliases.setdefault(offset,[]).append(index)
    check(definitions[9]['source_type']==155,'Different authored class')
    blocks=[('initial',u32(d,0x20))]+[('time_key',u32(asset,u32(d,0x24)+4*k))for k in range(d[0x13])]
    keys=[]
    for label,at in blocks:
        count,entries=u32(asset,at+4),u32(asset,at+8);check(count<=32,'Source block count bound')
        for k in range(count):
            entry=entries+8*k;index,relative,start,end=struct.unpack_from('<HHhh',asset,entry)
            if index!=9:continue
            payload=at+relative;raw=asset[payload:payload+0x28];check(len(raw)==0x28,'Source record outside asset')
            path=args.out/(label+'_type155_record.bin');path.write_bytes(raw)
            keys.append(dict(kind=label,block_offset=at,block_time_s16=struct.unpack_from('<h',asset,at)[0],entry_offset=entry,
                start_s16=start,end_s16=end,payload_offset=payload,curve_bits=list(struct.unpack_from('<6I',raw,0x10)),
                curve_values=list(struct.unpack_from('<6f',raw,0x10)),original_prefix=identity(path)))
    check(len(keys)==2,'Unexpected current source timeline coverage')
    initial=next(k for k in keys if k['kind']=='initial');current=next(k for k in keys if k['kind']=='time_key');checks=[]
    for capture in captures:
        base=capture['selection']['FEPbase'];mode=capture['mode']
        for row in capture['rows']:
            if row['type']!=155:continue
            for name,key in [('record',current),('oldRecord',current if mode=='reset'else initial)]:
                item=row[name];check(item['address']==base+key['payload_offset']and sidecar(item['raw'])[:0x28]==Path(key['original_prefix']['file']).read_bytes(),'Actual key operand differs from authored source')
            checks.append(dict(mode=mode,row=row['index'],actual_old_record_offset=row['oldRecord']['address']-base,actual_new_record_offset=row['record']['address']-base))
    init_list=u32(d,0x34);init_indices=[u16(asset,init_list+2*k)for k in range(d[0x17])]
    result=dict(schema='original-FX-type155-authored-curve-bank/v1',passed=True,source=identity(source),proof=identity(args.proof),producer=identity(Path(__file__)),
        descriptor_offset=descriptor,definition_index=9,parameter_offset=definitions[9]['parameter_offset'],loop_start_u16=u16(d,0xc),loop_end_u16=u16(d,0xe),
        definitions=definitions,shared_parameter_offsets=[dict(offset=k,definitions=v)for k,v in aliases.items()if len(v)>1],
        reset_initializer_definition_indices=init_indices,keys=keys,actual_operand_cross_checks=checks,
        time_units='original source units; seconds conversion unknown',semantic='type155 two-dimensional UV pixel-offset curve; actual CPU emitted UV commands verified separately',
        default_M1_binding_replaced=False,full_FX_lifecycle_verified=False,
        limits=['Only this descriptor and the type155 six scalar curve fields are exported; shared offsets are not separate allocations.',
                'Initializer/key payload selection and boundary events must follow original dispatch order; do not overwrite aliasing classes as independent structures.'])
    (args.out/'source_curve_bank.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=True,authored_keys=len(keys),actual_operand_cross_checks=len(checks),shared_offsets=len(result['shared_parameter_offsets']))))


if __name__=='__main__':main()
