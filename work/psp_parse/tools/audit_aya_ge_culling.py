"""Independent PRIM-time original Aya culling audit; no target execution/assets edits."""
import argparse,collections,hashlib,json,struct,sys
from pathlib import Path
import numpy as np
from exact_aya_materials import CONTEXT_RANGES
from extract_runtime_character import read_ppdmp,layout

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check(v,msg):
    if not v:raise ValueError(msg)
def f24(x):return struct.unpack('<f',struct.pack('<I',x<<8))[0]
def affine(payload):
    m=np.eye(4);m[:3]=np.asarray([f24(v)for v in payload]).reshape(3,4,order='F');return m

def main():
    a=argparse.ArgumentParser();a.add_argument('--output',type=Path,required=True);a=a.parse_args();check(not a.output.exists(),'Refuse overwrite')
    root=Path(__file__).resolve().parents[1];source=root/'out/AYA_NATIVE_GLTF_20261020/raw/input_materials.json';materials=json.loads(source.read_text(encoding='utf-8'));observations=[];captures=[]
    for capture in materials['captures']:
        file=Path(capture['path']);check(sha(file)==capture['sha256'],'PPDMP identity changed');commands,push=read_ppdmp(str(file))
        expected={(o['register_record'],o['register_word']):o for o in materials['observations']if o['capture']==capture['key']};check(len(expected)==106,'Expected106 unique packet observations')
        registers={};vertices=None;matrices={'world':[None]*12,'view':[None]*12,'proj':[None]*16,'bones':[None]*96};cursor={k:0 for k in matrices};found=set();states=collections.Counter()
        cursor_cmd={0x3a:'world',0x3c:'view',0x3e:'proj',0x2a:'bones'};data_cmd={0x3b:'world',0x3d:'view',0x3f:'proj',0x2b:'bones'}
        for record,(kind,size,pointer)in enumerate(commands):
            data=push[pointer:pointer+size];check(len(data)==size,'Truncated push record')
            if kind==0:
                at=17*4
                for low,high in CONTEXT_RANGES:
                    for cmd in range(low,high+1):
                        word=struct.unpack_from('<I',data,at)[0];check(word>>24==cmd or(cmd<=2 and word==0),'Context opcode mismatch');registers[cmd]=word&0xffffff;at+=4
            elif kind==2:vertices=data
            elif kind==1:
                for offset in range(0,len(data),4):
                    word=struct.unpack_from('<I',data,offset)[0];cmd,val=word>>24,word&0xffffff;registers[cmd]=val
                    if cmd in cursor_cmd:
                        key=cursor_cmd[cmd];cursor[key]=val&(127 if key=='bones'else 15)
                    elif cmd in data_cmd:
                        key=data_cmd[cmd];at=cursor[key]
                        if at<len(matrices[key]):matrices[key][at]=val
                        cursor[key]=(at+1)&(127 if key=='bones'else 15)
                    if cmd!=4 or(record,offset//4)not in expected:continue
                    e=expected[(record,offset//4)];vt=registers[0x12];check(hashlib.sha256(struct.pack('<I',vt)+vertices).hexdigest()==e['vertex_sha256'],'PRIM geometry identity differs')
                    for k in [0x1d,0x9b,0xd3,0x43,0x42]:check(registers[k]==e['register_payloads'][hex(k)],'Independent PRIM state differs from frozen row')
                    count=val&65535;check((val>>16)&7==3 and count==e['vertex_count']and not(vt&(1<<23)),'Unexpected primitive/throughmode')
                    check(all(v is not None for key in ['world','view','proj']for v in matrices[key]),'Matrices not explicitly recovered before PRIM')
                    stride,offs=layout(vt);check(count*stride==len(vertices),'Raw vertex size contract differs');weights=((vt>>14)&7)+1
                    check(((vt>>9)&3)==2 and((vt>>7)&3)==2 and((vt>>11)&3)==0,'Expected direct U16weights/POS16 indexednone')
                    check(all(v is not None for v in matrices['bones'][:weights*12]),'Bone palette unknown')
                    bones=np.stack([affine(matrices['bones'][12*i:12*i+12])for i in range(weights)]);posed=[]
                    for i in range(count):
                        pos=np.asarray(struct.unpack_from('<3h',vertices,i*stride+offs['pos'][0]),dtype=float)/32768;w=np.asarray(struct.unpack_from('<'+'H'*weights,vertices,i*stride+offs['wt'][0]),dtype=float)/32768
                        posed.append(sum(weight*(m@np.r_[pos,1])[:3]for weight,m in zip(w,bones)))
                    posed=np.asarray(posed);world,view=affine(matrices['world']),affine(matrices['view']);proj=np.asarray([f24(v)for v in matrices['proj']]).reshape(4,4,order='F')
                    clip=(proj@view@world@np.column_stack([posed,np.ones(count)]).T).T;ndc=clip[:,:2]/clip[:,3,None]
                    vp=np.asarray([f24(registers[k])for k in [0x42,0x43]]);screen=ndc*vp;tri=screen.reshape(-1,3,2);edge1=tri[:,1]-tri[:,0];edge2=tri[:,2]-tri[:,0];area=edge1[:,0]*edge2[:,1]-edge1[:,1]*edge2[:,0]
                    mode=registers[0x9b]&1;enabled=bool(registers[0x1d]&1);clear=bool(registers[0xd3]&1);states[(enabled,mode,clear)]+=1
                    observations.append({'capture':capture['key'],'packet':e['packet'],'register_record':record,'register_word':offset//4,'vertex_sha256':e['vertex_sha256'],'vertex_count':count,'primitive':3,'vtype':vt,
                        'raw_cullenable_payload':registers[0x1d],'raw_cullmode_payload':registers[0x9b],'cull_enabled':enabled,'GE_cull_enum':'GE_CULL_CW'if mode==0 else'GE_CULL_CCW','clear_mode':clear,
                        'viewport_xy_scale':vp.tolist(),'world_determinant':float(np.linalg.det(world[:3,:3])),'view_determinant':float(np.linalg.det(view[:3,:3])),
                        'raw_projected_area_signs_before_clipping':{'negative':int(np.sum(area<0)),'positive':int(np.sum(area>0)),'zero':int(np.sum(area==0))},
                        'clip_W_minmax':[float(clip[:,3].min()),float(clip[:,3].max())],
                        'float_screen_front_candidates_for_recorded_mode':int(np.sum(area<0 if mode==0 else area>0)),
                        'WORLD_payload':matrices['world'][:],'VIEW_payload':matrices['view'][:],'PROJ_payload':matrices['proj'][:]})
                    found.add((record,offset//4))
        check(found==set(expected),'Missing exact106 packets');captures.append({'key':capture['key'],'file':str(file),'sha256':sha(file),'packets':106,'states':[{'cull_enabled':k[0],'mode':k[1],'clear_mode':k[2],'draws':v}for k,v in states.items()]})
    gpath=root/'out/AYA_NATIVE_GLTF_20261020/aya_native.gltf';g=json.loads(gpath.read_text(encoding='utf-8'));b=(gpath.parent/g['buffers'][0]['uri']).read_bytes()
    def accessor(i):
        t=g['accessors'][i];v=g['bufferViews'][t['bufferView']];n={'VEC3':3,'SCALAR':1}[t['type']];dtype={5126:'<f4',5123:'<u2'}[t['componentType']];return np.frombuffer(b,dtype=dtype,count=t['count']*n,offset=v.get('byteOffset',0)+t.get('byteOffset',0)).reshape(t['count'],n).astype(float)
    p=accessor(0).reshape(-1,3,3);n=accessor(1).reshape(-1,3,3);cross=np.cross(p[:,1]-p[:,0],p[:,2]-p[:,0]);dot=(cross*n.mean(axis=1)).sum(axis=1)
    A=np.array([[1,0,0],[0,0,1],[0,1,0]]);uep=p@A.T;uen=n@A.T;ue_left_cross=np.cross(uep[:,2]-uep[:,0],uep[:,1]-uep[:,0]);uedot=(ue_left_cross*uen.mean(axis=1)).sum(axis=1)
    project=root.parent/'t3b_unreal';manifest=json.loads((project/'Content/SourceData/manifest.json').read_text(encoding='utf-8'));aya=next(x for x in manifest['actors']if x['name']=='Aya')
    build_version=json.loads(Path('C:/Program Files/Epic Games/UE_5.8/Engine/Build/Build.version').read_text(encoding='utf-8-sig'))
    result={'schema':'t3b-original-Aya-culling-orientation-audit/v1','passed':True,'target_execution_performed':False,'observations':len(observations),'captures':captures,
        'all_recorded_Aya_draws_cull_enabled':all(o['cull_enabled']and not o['clear_mode']for o in observations),'all_recorded_Aya_cull_mode':sorted(set(o['raw_cullmode_payload']for o in observations)),
        'frozen_source_gltf_sha256':sha(gpath),'source_bind_triangles':len(dot),'source_RH_cross_dot_original_normals_positive':int(np.sum(dot>0)),
        'native_axis_matrix':A.tolist(),'native_axis_determinant':float(np.linalg.det(A)),'native_UE_LH_cross_dot_transformed_original_normals_positive':int(np.sum(uedot>0)),
        'source_indices_preserved_without_reversal':all(np.array_equal(accessor(q['indices']).reshape(-1),np.arange(q['extras']['first_source_vertex'],q['extras']['first_source_vertex']+q['extras']['source_vertex_count']))for q in g['meshes'][0]['primitives']),
        'source_gltf_doubleSided':g['materials'][0]['doubleSided'],'source_gltf_original_GE_parameters':g['materials'][0]['extras']['original_GE_parameters'],'UE_manifest_Aya_material':aya['materials'][0],
        'current_installed_build_version':build_version,'observations_detail':observations,
        'limits':['318PRIM observations cover106packet Aya in3 retained captures only; not every action/costume/game draw.',
            'Projected signs use decoded float24 matrices and floating-point viewport math before clipping; not PSP fixed-point rasterization or original pixels.',
            'All1152 bind triangles agree with expected UE left-handed original-normal orientation after source->UE(x,z,y) conversion, but actual GPU front-face state remains an experimental readback boundary.',
            'Single-sided culling is proven for retained original observations; normal/depth-write/blending and positive/negative component-transform parity require distinct renderer handling.']}
    a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:v for k,v in result.items()if k not in ['observations_detail','limits','UE_manifest_Aya_material','source_gltf_original_GE_parameters']},indent=2))
if __name__=='__main__':main()