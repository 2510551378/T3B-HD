"""Export a paired static light-calibration pose, never an animated replacement.

Same recorded pose/UV/triangles/texture; only reconstructed vertex COLOR_0 differs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

import numpy as np

ROOT=Path(__file__).resolve().parents[1]


def check(ok,message):
    if not ok:raise ValueError(message)


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    check(not a.out.exists(),'Never overwrite calibration pose');a.out.mkdir(parents=True)
    base=ROOT/'out/AYA_GE_VERTEX_LIGHTING_20261020'
    comparison=base/'comparison_v1/comparison.json';proof=json.loads(comparison.read_text(encoding='utf-8'))
    check(proof['passed'] and proof['comparison']['color_vertex_mismatches']==0,'Native/reference light mismatch')
    manifest=json.loads((base/'inputs/inputs.json').read_text(encoding='utf-8'))
    inputfile=Path(manifest['binary']['file']);raw=inputfile.read_bytes()
    outputs=base/'comparison_v1/native_outputs.bin'
    check(sha(inputfile)==proof['inputs_sha256'] and sha(outputs)==proof['native_output_sha256'],'Compared input/output changed')
    values=np.frombuffer(outputs.read_bytes(),dtype=np.dtype([('p','<f4',3),('n','<f4',3),('rgba','u1',4),('secondary','u1',3),('pad','u1')]))
    draws=[d for d in manifest['draws']if d['capture']==manifest['captures'][0]['key']]
    check(len(draws)==106 and sum(d['vertex_count']for d in draws)==3456,'Expected complete original calibration pose')
    point=values[:3456]['p'].astype(np.float64)
    origin=np.array([(point[:,0].min()+point[:,0].max())/2,point[:,1].min(),(point[:,2].min()+point[:,2].max())/2])
    original=ROOT/'out/AYA_NATIVE_GLTF_20261020/aya_native.gltf';g=json.loads(original.read_text(encoding='utf-8'))
    units=g['nodes'][0]['scale'][0];report={'schema':'aya-ge-lighting-static-calibration-pair/v1','passed':False,
        'comparison':str(comparison),'comparison_sha256':sha(comparison),'capture':manifest['captures'][0],
        'input_sha256':sha(inputfile),'native_output_sha256':sha(outputs),
        'PSP_world_origin_subtracted':origin.tolist(),'metres_per_PSP_world_unit':units,
        'source_pose_vertices':3456,'source_pose_draws':106,'snapshots':[],
        'frozen_native_srt_animation_replaced':False,'original_hardware_pixels_verified':False,
        'limits':['Static captured pose for lighting isolation; not a playable character or dynamic light timeline.',
                  'Colors reconstruct the pinned PPSSPP software-lighting model, not sampled GPU outputs.',
                  'Camera centering is common to both modes, not the original game camera.',
                  'Original main-depth write, texture combine/output color/fog remain separate.']}
    for mode in ('white','ge_lit'):
        folder=a.out/mode;folder.mkdir();binary=bytearray();views=[];accessors=[];prims=[]
        def add(data,kind,component,count,bounds=False):
            while len(binary)%4:binary.append(0)
            at=len(binary);b=np.ascontiguousarray(data).tobytes();binary.extend(b)
            views.append({'buffer':0,'byteOffset':at,'byteLength':len(b)})
            item={'bufferView':len(views)-1,'componentType':component,'count':count,'type':kind}
            if bounds:item.update(min=data.min(axis=0).tolist(),max=data.max(axis=0).tolist())
            accessors.append(item);return len(accessors)-1
        for d in draws:
            count=d['vertex_count'];first=d['first_output_vertex'];v=values[first:first+count]
            check(not np.any(v['secondary']),'Secondary specular COLOR_1 needs a separate shader; never discard it')
            # Each primitive owns compact attributes; original triangle order/multiplicity retained.
            pos=((v['p'].astype(np.float64)-origin)*units).astype('<f4')
            normal=v['n'].copy().astype('<f4')
            source=np.frombuffer(raw,dtype='<f4',count=count*16,offset=d['binary_byte_offset']+1464).reshape(count,16)
            uv=source[:,14:16].copy()
            rgba=np.full((count,4),255,dtype='u1')if mode=='white'else v['rgba'].copy()
            attrs={'POSITION':add(pos,'VEC3',5126,count,True),'NORMAL':add(normal,'VEC3',5126,count),
                   'TEXCOORD_0':add(uv,'VEC2',5126,count),'COLOR_0':add(rgba,'VEC4',5121,count)}
            accessors[attrs['COLOR_0']]['normalized']=True
            prims.append({'attributes':attrs,'indices':add(np.arange(count,dtype='<u2'),'SCALAR',5123,count),'material':0,'mode':4,
                          'extras':{'source_packet':d['packet'],'source_vertex_sha256':d['vertex_sha256']}})
        mat={'name':'Aya_calibration_original_material','doubleSided':False,'alphaMode':'BLEND',
             'extensions':{'KHR_materials_unlit':{}},'pbrMetallicRoughness':{'baseColorFactor':[1,1,1,1],'metallicFactor':0,'roughnessFactor':1}}
        gltf={'asset':{'version':'2.0','generator':'T3B original GE static lighting calibration',
                       'extras':{'mode':mode,'static_snapshot_only':True,'source_capture_sha256':manifest['captures'][0]['sha256']}},
              'extensionsUsed':['KHR_materials_unlit'],'scene':0,'scenes':[{'nodes':[0]}],
              'nodes':[{'name':'Aya_'+mode+'_calibration','mesh':0}],
              'meshes':[{'name':'Aya_'+mode+'_calibration','primitives':prims}],'materials':[mat],
              'buffers':[{'uri':'pose.bin','byteLength':len(binary)}],'bufferViews':views,'accessors':accessors}
        (folder/'pose.bin').write_bytes(binary)
        target=folder/('aya_'+mode+'_calibration.gltf');target.write_text(json.dumps(gltf,indent=2)+'\n',encoding='utf-8')
        report['snapshots'].append(dict(mode=mode,gltf=str(target.resolve()),gltf_sha256=sha(target),
                                        binary_sha256=sha(folder/'pose.bin')))
    # Independently inspect serialized accessors: same buffers except COLOR_0 byte ranges.
    paths=[a.out/mode for mode in ('white','ge_lit')]
    ga,gb=[json.loads(next(p.glob('*.gltf')).read_text(encoding='utf-8'))for p in paths]
    ba,bb=[(p/'pose.bin').read_bytes()for p in paths]
    whitelist=set()
    for primitive in gb['meshes'][0]['primitives']:
        accessor=gb['accessors'][primitive['attributes']['COLOR_0']];view=gb['bufferViews'][accessor['bufferView']]
        whitelist.update(range(view['byteOffset'],view['byteOffset']+view['byteLength']))
    check(len(ba)==len(bb) and all(x==y or i in whitelist for i,(x,y)in enumerate(zip(ba,bb))),
          'Paired calibration buffers changed beyond vertex colors')
    check(ga['accessors']==gb['accessors'] and ga['bufferViews']==gb['bufferViews'] and ga['materials']==gb['materials'],
          'Paired calibration layouts/materials differ')
    report.update(passed=True,only_vertex_colors_differ_in_paired_buffers=True,
                  reconstructed_color_rgb_min=values[:3456]['rgba'][:,:3].min(axis=0).tolist(),
                  reconstructed_color_rgb_max=values[:3456]['rgba'][:,:3].max(axis=0).tolist())
    (a.out/'calibration_pair.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'vertices':3456,'draws':106,'only_vertex_colors_differ':True}))


if __name__=='__main__':main()
