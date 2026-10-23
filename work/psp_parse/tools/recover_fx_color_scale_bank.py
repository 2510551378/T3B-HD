"""Export only consumed original color/percent-scale key fields with alias/order metadata."""
import argparse
import json
import struct
from pathlib import Path
from analyze_fx_node_time import check,identity,read,sidecar,u16,u32


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--proof',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();check(not args.out.exists(),'Never replace original color/scale bank');args.out.mkdir(parents=True)
    proof=read(args.proof);check(proof['passed'],'No audited callbacks')
    captures=[read(Path(c['capture']['file']))for c in proof['captures']];source=Path(captures[0]['FEP']['file']);asset=source.read_bytes()
    check(identity(source)['sha256']==captures[0]['FEP']['sha256'],'Source FEP changed')
    d=asset[0x10c78:0x10cc0];defs=[]
    for index in range(d[8]):
        ptr=u32(asset,u32(d,0x1c)+4*index);defs.append(dict(index=index,type=u16(asset,ptr),parameter_offset=u16(asset,ptr+2)))
    blocks=[('initial',u32(d,0x20))]+[('time_key',u32(asset,u32(d,0x24)+4*k))for k in range(d[0x13])]
    records=[]
    for kind,block in blocks:
        count,entries=u32(asset,block+4),u32(asset,block+8);check(count<=32,'Unsupported authored block bound')
        for k in range(count):
            entry=entries+k*8;index,offset,start,end=struct.unpack_from('<HHhh',asset,entry)
            if index not in (3,5):continue
            n=12 if index==3 else 32;at=block+offset;raw=asset[at:at+n]
            path=args.out/(kind+('_scale_percent.bin'if index==3 else'_color_linear.bin'));path.write_bytes(raw)
            records.append(dict(kind=kind,definition_index=index,source_type=defs[index]['type'],parameter_offset=defs[index]['parameter_offset'],
                block_offset=block,entry_offset=entry,start_s16=start,end_s16=end,payload_offset=at,consumed_prefix_bytes=n,
                values=list(struct.unpack('<%df'%(n//4),raw)),F32_bits=list(struct.unpack('<%dI'%(n//4),raw)),original_payload=identity(path)))
    check(len(records)==4,'Expected initial and time key for both classes')
    checks=[]
    for capture in captures:
        for row in capture['rows']:
            if row['type']not in (7,16):continue
            mode=capture['mode'];base=capture['selection']['FEPbase']
            for field,kind in [('record','time_key'),('oldRecord','time_key'if mode=='reset'else'initial')]:
                key=next(k for k in records if k['kind']==kind and k['definition_index']==row['definitionIndex']);n=key['consumed_prefix_bytes'];item=row[field]
                check(item['address']==base+key['payload_offset']and sidecar(item['raw'])[:n]==Path(key['original_payload']['file']).read_bytes(),'Actual color/scale operand differs from original authored key')
            checks.append(dict(mode=mode,row=row['index'],definition_index=row['definitionIndex']))
    reset_order=[u16(asset,u32(d,0x34)+2*k)for k in range(d[0x17])]
    check(d[0x13]==1,'Multiple authored time blocks not yet covered')
    key_block=u32(asset,u32(d,0x24));key_entries=u32(asset,key_block+8)
    time_order=[u16(asset,key_entries+8*k)for k in range(u32(asset,key_block+4))]
    for capture in captures:
        order=reset_order if capture['mode']=='reset'else time_order
        check([r['definitionIndex']for r in capture['rows'][:len(order)]]==order,'Actual callback order differs from authored block order')
    check(defs[2]['parameter_offset']==defs[3]['parameter_offset']==0x60 and defs[4]['parameter_offset']==defs[5]['parameter_offset']==0x80,'Original color/scale alias relation differs')
    result=dict(schema='original-FX-color-scale-authored-bank/v1',passed=True,source=identity(source),proof=identity(args.proof),producer=identity(Path(__file__)),
                descriptor_offset=0x10c78,definitions=defs,records=records,actual_operand_cross_checks=checks,
                aliases=[dict(parameter_offset=0x60,definitions=[2,3]),dict(parameter_offset=0x80,definitions=[4,5])],
                original_reset_order=reset_order,original_time_key_order=time_order,actual_dispatch_order_matches=True,
                time_units='Original source units; seconds conversion unknown',default_M1_binding_replaced=False,
                limits=['Only consumed type7 XYZ percent and type16 RGBA/base-velocity key fields are decoded.',
                        'Shared classes23/24 remain unported. Their original dispatch order and parameter aliases must be retained.',
                        'Do not reset the shared percent/color state to authored values each frame; actual values may include previous class contributions.'])
    (args.out/'source_color_scale_bank.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=True,authored_records=len(records),actual_operand_cross_checks=len(checks))))


if __name__=='__main__':main()
