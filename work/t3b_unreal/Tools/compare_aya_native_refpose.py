"""Compare actual UE asset reference-pose getter output against frozen glTF local TRS.

This does not read native skinned vertices or simulate the UE skinning pipeline.
"""
import argparse,hashlib,json
from pathlib import Path

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--import-report',type=Path,required=True);parser.add_argument('--gltf',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise RuntimeError('Refuse to overwrite a prior comparison report')
    r=json.loads(args.import_report.read_text(encoding='utf-8'));g=json.loads(args.gltf.read_text(encoding='utf-8'))
    nodes={n['name']:n for n in g['nodes']};rows=[]
    for actual in r['skeletal_meshes'][0]['actual_asset_reference_pose']:
        name=actual['bone'];node=nodes['Scene_units_and_floor']if name=='Source_skeleton_root'else nodes[name]
        t=node.get('translation',[0,0,0]);s=node.get('scale',[1,1,1]);q=node.get('rotation',[0,0,0,1])
        et=[100*t[0],100*t[2],100*t[1]];es=[s[0],s[2],s[1]];eq=[-q[0],-q[2],-q[1],q[3]]
        dq=min(max(abs(x-sign*y)for x,y in zip(actual['quaternion_xyzw'],eq))for sign in [1,-1])
        rows.append({'bone':name,'translation_max_abs_cm':max(abs(a-b)for a,b in zip(actual['translation'],et)),
            'scale_max_abs':max(abs(a-b)for a,b in zip(actual['scale'],es)),'quaternion_sign_invariant_max_abs':dq})
    result={'schema':'t3b-native-refpose-comparison/v1','source_import_report_sha256':hashlib.sha256(args.import_report.read_bytes()).hexdigest(),
        'bone_count':len(rows),'max_translation_component_error_cm':max(x['translation_max_abs_cm']for x in rows),
        'max_scale_component_error':max(x['scale_max_abs']for x in rows),'max_quaternion_component_error_sign_invariant':max(x['quaternion_sign_invariant_max_abs']for x in rows),
        'bone_comparisons':rows,'formula':'native local T=100*(source.x,source.z,source.y); Q=(-qx,-qz,-qy,qw); S=(sx,sz,sy). Synthetic skeleton root absorbs Scene_units_and_floor canonical units/floor.',
        'axis_runtime_limit':'PMC uses (pc.z,pc.x,pc.y)*100; native uses (pc.x,pc.z,pc.y)*100; relative change swaps native X/Y (reflection, not a yaw-only rotation). No correction applied.',
        'installed_engine_sources':['GLTFCore/Private/GLTF/ConversionUtilities.h:16,32','Engine/Private/Components/SkinnedMeshComponent.cpp:2727'],
        'native_skinned_vertices_verified':False}
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items()if k!='bone_comparisons'},indent=2))
if __name__=='__main__':main()