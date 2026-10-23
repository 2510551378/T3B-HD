"""Independent serialized-source, UE corner and PNG lighting A/B verification.

Matching uses exact float32 POSITION and float32/float16 UV words with oriented
cyclic corners. Color bytes are checked only after identity; no nearest matching.
"""
import argparse,collections,hashlib,json
from pathlib import Path
import numpy as np
from PIL import Image


def check(ok,msg):
    if not ok:raise ValueError(msg)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def corner_audit(gltf,probe):
    g=json.loads(gltf.read_text(encoding='utf-8'));raw=(gltf.parent/g['buffers'][0]['uri']).read_bytes()
    def accessor(i):
        d=g['accessors'][i];v=g['bufferViews'][d['bufferView']];n={'VEC3':3,'VEC2':2,'VEC4':4,'SCALAR':1}[d['type']]
        return np.frombuffer(raw,dtype={5126:'<f4',5121:'u1',5123:'<u2'}[d['componentType']],count=n*d['count'],
                             offset=v['byteOffset']+d.get('byteOffset',0)).reshape(-1,n)
    source=[]
    for p in g['meshes'][0]['primitives']:
        v=p['attributes'];pos=np.asarray(accessor(v['POSITION'])[:,[0,2,1]]*np.float32(100),dtype='<f4')
        uv=accessor(v['TEXCOORD_0']);color=accessor(v['COLOR_0'])
        source.extend(zip(pos.reshape(-1,3,3),uv.reshape(-1,3,2),color.reshape(-1,3,4)))
    results=[]
    for layer in probe['copies']:
        render=layer['lod']=='RenderData'
        def key(p,u):
            return tuple(np.asarray(p,dtype='<f4').view('<u4').tolist())+tuple(
                np.asarray(u,dtype='<f2'if render else'<f4').view('<u2'if render else'<u4').tolist())
        def triangle_key(p,u):
            rows=[key(x,y)for x,y in zip(p,u)]
            return min(tuple(rows[i:]+rows[:i])for i in range(3))
        lookup=collections.defaultdict(list);expected=collections.Counter();actual=collections.Counter()
        expected_attributes=collections.Counter();actual_attributes=collections.Counter()
        def attribute_key(p,u,c):
            rows=[key(x,y)+tuple(int(v)for v in z)for x,y,z in zip(p,u,c)]
            return min(tuple(rows[i:]+rows[:i])for i in range(3))
        for i,(p,u,c)in enumerate(source):
            lookup[triangle_key(p,u)].append(i);expected[triangle_key(p,u)]+=1
            expected_attributes[attribute_key(p,u,c)]+=1
        ambiguous=0
        for tri in layer['triangles']:
            tk=triangle_key(tri['positions_cm'],tri['uvs']);candidates=lookup.get(tk,[])
            check(candidates,'Actual triangle POSITION/UV has no exact oriented source class')
            actual[tk]+=1;ambiguous+=len(candidates)>1
            cbytes=np.rint(np.array(tri['colors'])*255).astype(int);good=False
            actual_attributes[attribute_key(tri['positions_cm'],tri['uvs'],cbytes)]+=1
            for i in candidates:
                p,u,c=source[i]
                for shift in range(3):
                    same=all(key(x,y)==key(z,w)for x,y,z,w in zip(np.roll(p,shift,axis=0),np.roll(u,shift,axis=0),tri['positions_cm'],tri['uvs']))
                    if same and np.array_equal(np.roll(c,shift,axis=0),cbytes):good=True
            check(good,'Actual source-matched corner color byte differs')
        check(not(actual-expected),'Actual triangle multiplicity exceeds recorded source')
        check(not(actual_attributes-expected_attributes),'Actual position/UV/color class multiplicity exceeds source')
        missing=expected-actual
        results.append(dict(lod=layer['lod'],actual_triangles=len(layer['triangles']),source_triangles=len(source),
            exact_oriented_position_and_uv_classes_matched=len(layer['triangles']),color_byte_mismatches=0,
            missing_source_multiplicity=sum(missing.values()),ambiguous_duplicate_class_triangles=ambiguous,
            missing_only_original_duplicate_classes=all(expected[k]>1 for k in missing),
            all_position_uv_color_class_multiplicities_bounded_by_source=True,
            raw_index_buffer_count_verified=False))
    return results


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True)
    p.add_argument('--corner-report',type=Path,required=True);p.add_argument('--gltf',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args();check(not a.out.exists(),'Never replace verification')
    r=json.loads(a.report.read_text(encoding='utf-8'));probe=json.loads(a.corner_report.read_text(encoding='utf-8'))
    verified=json.loads((a.report.parent/'verified.json').read_text(encoding='utf-8'))
    done=json.loads((a.report.parent/'process_completed.json').read_text(encoding='utf-8'))
    check(r['passed']and probe['passed']and verified['report_sha256']==sha(a.report)and done['exit_code']==0,
          'Actual completed producer/probe evidence missing')
    check(probe['input_sha256']==sha(a.report)and probe['actual_build_settings']['nanite_enabled']is False,
          'Corner probe is not the actual non-Nanite calibration')
    for item in r['protected_packages_before']+r['new_packages']:
        check(sha(Path(item['file']))==item['sha256'],'Saved package changed after actual run')
    pixels={};summaries=[]
    def image(item):
        path=Path(item['file']);check(sha(path)==item['sha256'],'Actual PNG changed')
        with Image.open(path)as im:check(im.size==(768,1024),'Unexpected dimensions');return np.asarray(im.convert('RGB'),dtype=np.int16)
    check(len(r['images'])==4,'Expected actual same-process four-image calibration')
    for i in r['images']:
        actual,empty=image(i['png']),image(i['empty_control']);mask=np.max(np.abs(actual-empty),axis=2)>8
        check(mask.sum()>1000,'No real rendered character foreground')
        key=(i['mode'],i['view']);check(key not in pixels,'Duplicate calibration key')
        pixels[key]=(actual,mask)
        identity=dict(translation=[0.,0.,0.],scale=[1.,1.,1.],quaternion=[0.,0.,0.,1.])
        check(i['actor_transform']==identity,'Compared calibration actor moved')
        check(i['camera_component_transform']['translation']==[0.,340. if i['view']=='front'else -340.,88.],
              'Actual camera component position differs')
        summaries.append(dict(mode=i['mode'],view=i['view'],foreground_pixels=int(mask.sum()),
            foreground_mean_RGB=actual[mask].mean(axis=0).tolist(),decoded_rgb_sha256=hashlib.sha256(actual.astype('u1').tobytes()).hexdigest()))
    deltas=[]
    for view in ('front','back'):
        white,wm=pixels['white',view];lit,lm=pixels['ge_lit',view];common=wm&lm
        check(common.sum()>1000,'No shared foreground for the color comparison')
        pair=[i for i in r['images']if i['view']==view]
        check(pair[0]['camera_component_transform']==pair[1]['camera_component_transform'],'A/B camera transform differs')
        deltas.append(dict(view=view,common_foreground_pixels=int(common.sum()),
            white_mean_RGB=white[common].mean(axis=0).tolist(),GE_mean_RGB=lit[common].mean(axis=0).tolist(),
            mean_absolute_pixel_difference=float(np.abs(white-lit)[common].mean())))
    corners=corner_audit(a.gltf,probe)
    check(next(x for x in corners if x['lod']=='SourceModel')['actual_triangles']==1152,'Complete SourceModel missing')
    check(next(x for x in corners if x['lod']=='RenderData')['missing_only_original_duplicate_classes'],
          'Conversion removed a unique source triangle')
    result=dict(schema='independent-aya-ge-light-calibration/v1',passed=True,
        capture_report_sha256=sha(a.report),corner_report_sha256=sha(a.corner_report),gltf_sha256=sha(a.gltf),
        actual_same_process_images=4,protected_packages=len(r['protected_packages_before']),new_packages=len(r['new_packages']),
        images=summaries,paired_pixels=deltas,exact_corner_checks=corners,shader_or_exposure_changed=False,
        original_pixels_verified=False,full_animated_light_timeline_verified=False,
        limits=['Static original capture pose; camera labels front/back denote the +/-Y axis, not Aya-facing orientation.',
                'This is a reconstructed software GE light model; no original hardware same-camera pixel comparison.',
                'One duplicate source face remains absent from converted RenderData; raw index deletion stage unknown.',
                'Original blended main-depth writes, output color, fog and production gameplay remain unverified.'])
    a.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(dict(passed=True,exact_corner_checks=corners)))


if __name__=='__main__':main()
