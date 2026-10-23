"""Independent Pillow readback of an actual UE TwoSided A/B capture.

Does not import the capture producer or UE, alter packages, or set image-fidelity
thresholds. Material/camera/bone inputs, file identities and measured pixels are
checked separately; rear garment correctness still requires visual review.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


def check(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    a = parser.parse_args()
    check(not a.out.exists(),'Refusing existing verification')
    r = json.loads(a.report.read_text(encoding='utf-8'))
    v = json.loads((a.report.parent/'verified.json').read_text(encoding='utf-8-sig'))
    completed = json.loads((a.report.parent/'process_completed.json').read_text(encoding='utf-8-sig'))
    check(r['schema'] == 't3b-native-aya-cull-comparison/v1' and r['passed'] and
          v['passed'] and v['report_sha256'] == sha(a.report) and
          v['run_id'] == r['run_id'] and v['process_id'] == r['process_id'],
          'Fresh actual capture identity differs')
    check(completed['exit_code'] == 0,'Capture process did not finish successfully')
    frozen = a.report.parent/'capture_aya_cull_comparison_executed.py'
    check(sha(frozen) == r['script_sha256'],'Executed source identity differs')
    protected = r['protected_packages_before']
    for item in protected + [r['new_material_package']]:
        p = Path(item['file'])
        check(sha(p) == item['sha256'] and p.stat().st_size == item['bytes'],
              'Content package no longer matches actual run: '+str(p))
    original,derived = r['actual_material'],r['derived_material']
    check(original['two_sided'] is True and derived['two_sided'] is False,
          'Controlled cull state differs')
    def canonical(item, two_sided):
        item = dict(item)
        path = item['asset']
        item['two_sided'] = two_sided
        item.pop('recipe_signature',None)
        return json.dumps(item,sort_keys=True).replace(path,'<MATERIAL>')
    check(canonical(original,False) == canonical(derived,False),
          'Recorded graph/settings differ beyond culling')
    check(all(item.get('equal',True) for item in r['additional_material_properties'].values()),
          'Additional material property changed')
    pixels,controls = {},{}
    decoded = []
    def image(item):
        path = Path(item['file'])
        check(sha(path) == item['sha256'] and path.stat().st_size == item['bytes'],
              'Actual PNG bytes changed')
        with Image.open(path) as im:
            check(im.size == (768,1024),'Actual image dimensions differ')
            return np.asarray(im.convert('RGB'),dtype=np.int16)
    records = r['images']
    check(len(records) == 8,'Expected same-process eight-image A/B')
    by_key = {(i['mode'],i['source_frame'],i['view']):i for i in records}
    check(len(by_key) == 8,'Repeated capture key')
    for key,item in by_key.items():
        p,bg = image(item['png']),image(item['empty_control'])
        pixels[key],controls[key] = p,bg
        fg = np.max(np.abs(p-bg),axis=2)>8
        check(int(fg.sum()) == item['image_validation']['foreground_pixels'] and fg.sum() >= 1000,
              'Foreground readback differs/absent')
        check(abs(item['actual_time']-item['requested_time']) < 2e-6,'Animation time differs')
        identity = {'translation':[0.,0.,0.],'scale':[1.,1.,1.],'quaternion':[0.,0.,0.,1.]}
        check(item['skeletal_actor_world_transform'] == identity and
              item['skeletal_component_world_transform'] == identity,'Skeletal placement differs')
        camera = item['capture_component_world_transform']
        check(camera == item['capture_actor_world_transform'] and
              camera['translation'] == item['camera_location_cm'] and camera['scale'] == [1.,1.,1.],
              'Component camera readback differs')
        q = camera['quaternion']
        forward = np.array([1-2*(q[1]**2+q[2]**2),2*(q[0]*q[1]+q[2]*q[3]),
                            2*(q[0]*q[2]-q[1]*q[3])])
        target = np.array(item['camera_look_at_cm'])-camera['translation']
        check(np.max(np.abs(forward-target/np.linalg.norm(target))) < 1e-6,
              'Actual camera forward differs from recorded target')
        decoded.append(dict(mode=key[0],frame=key[1],view=key[2],foreground_pixels=int(fg.sum()),
                            decoded_rgb_sha256=hashlib.sha256(p.astype('u1').tobytes()).hexdigest()))
    comparisons = []
    for frame in (0,30):
        group = [i for i in records if i['source_frame'] == frame]
        check(all(i['bone_world'] == group[0]['bone_world'] and
                  i['actual_time'] == group[0]['actual_time'] for i in group),
              'Compared modes/views use different actual poses/times')
        for mode in ('baseline_two_sided','source_single_sided'):
            front,back = (mode,frame,'front_plus_Y'),(mode,frame,'back_minus_Y')
            f,b = pixels[front][:,::-1],pixels[back]
            mask = (np.max(np.abs(f-controls[front][:,::-1]),axis=2)>8) | (
                    np.max(np.abs(b-controls[back]),axis=2)>8)
            mae = float(np.abs(f-b)[mask].mean())
            saved = r['paired_mirror_diagnostics'][mode][str(frame)]
            check(abs(mae-saved['foreground_union_rgb_mae_mirrored_front_vs_back']) < 1e-12,
                  'Independent mirror diagnostic differs')
            comparisons.append(dict(mode=mode,frame=frame,foreground_union_pixels=int(mask.sum()),
                                    foreground_union_mirrored_rgb_mae=mae))
    result = dict(schema='root-independent-aya-cull-comparison/v1',passed=True,
                  report_sha256=sha(a.report),run_id=r['run_id'],engine_version=r['engine_version'],
                  original_packages_hash_checked=len(protected),new_material_package=r['new_material_package'],
                  actual_same_process_images=8,matched_pose_and_time_verified=True,
                  component_camera_transform_verified=True,images=decoded,mirror_diagnostics=comparisons,
                  pixel_fidelity_verified=False,HD_verified=False,gameplay_verified=False,
                  limitations=['Image differences are diagnostic, not original-pixel acceptance.',
                               'Single-sided culling does not implement original blended main-depth writes.',
                               'Original lighting/output color and residual through-body visibility remain.'])
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'actual_images':8,'protected_packages':len(protected)}))


if __name__ == '__main__':
    main()
