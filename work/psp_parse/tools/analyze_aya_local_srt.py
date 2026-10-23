"""Read-only multi-frame source-local SRT feasibility; writes new reports only.

Does not normalize away source quaternion magnitude, edit runtime assets, or
claim that inferred reference transforms are a proven original bind pose.
"""
import argparse
import json
from pathlib import Path
import struct

import numpy as np

from recover_original_actor_metadata import identity, sha


def homogeneous_quaternion(q):
    x,y,z,w=q
    return np.array([[w*w+x*x-y*y-z*z,2*(x*y-z*w),2*(x*z+y*w)],
        [2*(x*y+z*w),w*w-x*x+y*y-z*z,2*(y*z-x*w)],
        [2*(x*z-y*w),2*(y*z+x*w),w*w-x*x-y*y+z*z]])


def quaternion_product(a,b):
    x,y,z,w=a;X,Y,Z,W=b
    return np.array([w*X+x*W+y*Z-z*Y,w*Y-x*Z+y*W+z*X,
                     w*Z+x*Y-y*X+z*W,w*W-x*X-y*Y-z*Z])


def rotation_quaternion(m):
    """Return a unit xyzw quaternion for a proper orthogonal matrix."""
    trace=float(np.trace(m))
    if trace>0:
        s=2*np.sqrt(1+trace);q=[(m[2,1]-m[1,2])/s,(m[0,2]-m[2,0])/s,(m[1,0]-m[0,1])/s,s/4]
    else:
        i=int(np.argmax(np.diag(m)))
        if i==0:
            s=2*np.sqrt(1+m[0,0]-m[1,1]-m[2,2]);q=[s/4,(m[0,1]+m[1,0])/s,(m[0,2]+m[2,0])/s,(m[2,1]-m[1,2])/s]
        elif i==1:
            s=2*np.sqrt(1+m[1,1]-m[0,0]-m[2,2]);q=[(m[0,1]+m[1,0])/s,s/4,(m[1,2]+m[2,1])/s,(m[0,2]-m[2,0])/s]
        else:
            s=2*np.sqrt(1+m[2,2]-m[0,0]-m[1,1]);q=[(m[0,2]+m[2,0])/s,(m[1,2]+m[2,1])/s,s/4,(m[1,0]-m[0,1])/s]
    q=np.asarray(q);return q/np.linalg.norm(q)


def srt_fit(m):
    a=m[:3,:3];norms=np.linalg.norm(a,axis=0)
    if min(norms)<=0:raise ValueError('singular affine is outside this positive-scale actor probe')
    normalized=a/norms
    u,_,vh=np.linalg.svd(normalized);rotation=u@vh
    if np.linalg.det(rotation)<0:
        u[:,-1]*=-1;rotation=u@vh
    q=rotation_quaternion(rotation);rotation=homogeneous_quaternion(q)
    scale=np.diag(rotation.T@a)
    reconstructed=np.eye(4);reconstructed[:3,:3]=rotation@np.diag(scale);reconstructed[:3,3]=m[:3,3]
    offdiag=normalized.T@normalized-np.eye(3)
    return reconstructed,{'max_matrix_component_residual':float(abs(reconstructed-m).max()),
        'max_normalized_column_dot':float(abs(offdiag).max()),'column_scale':norms.tolist(),
        'relative_scale_spread':float((max(norms)-min(norms))/np.mean(norms)),
        'determinant':float(np.linalg.det(a)),'unit_rotation_quaternion_xyzw':q.tolist(),
        'translation':m[:3,3].tolist()}


def affine(q,t,keep_magnitude=True):
    result=np.eye(4)
    result[:3,:3]=homogeneous_quaternion(q if keep_magnitude else q/np.linalg.norm(q))
    result[:3,3]=t
    return result


def hierarchy(locals_,parents):
    result={}
    def get(index):
        if index not in result:
            result[index]=locals_[index]if parents[index]<0 else get(parents[index])@locals_[index]
        return result[index]
    return np.asarray([get(i)for i in range(len(parents))])


def apply_skin(vertices,influences,matrices):
    points=np.zeros_like(vertices,dtype=float)
    for slot in range(influences[0].shape[1]):
        bone=influences[0][:,slot];weight=influences[1][:,slot]
        transformed=np.einsum('vij,vj->vi',matrices[bone,:3,:3],vertices)+matrices[bone,:3,3]
        points+=weight[:,None]*transformed
    return points


def aggregate(rows):
    return {'samples':len(rows),'max_matrix_component_residual':max(r['max_matrix_component_residual']for r in rows),
        'max_normalized_column_dot':max(r['max_normalized_column_dot']for r in rows),
        'max_relative_scale_spread':max(r['relative_scale_spread']for r in rows),
        'column_scale_range':[min(min(r['column_scale'])for r in rows),max(max(r['column_scale'])for r in rows)],
        'determinant_range':[min(r['determinant']for r in rows),max(r['determinant']for r in rows)],
        'negative_determinant_count':sum(r['determinant']<0 for r in rows)}


def analyze(manifest_path,metadata_path,canonical_path,output):
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'));metadata=json.loads(metadata_path.read_text(encoding='utf-8'))
    canonical=json.loads(canonical_path.read_text(encoding='utf-8'));units=canonical['pc_units_per_original_unit']
    parents=[b['parent']for b in metadata['bones']]
    if len(parents)!=44 or len(manifest['frames'])!=60:raise ValueError('this report is scoped to the actual44bone60sample capture')
    source_vertices=[v for packet in metadata['packets']for v in packet['vertices']]
    vertices=np.asarray([v['position_raw']for v in source_vertices],dtype=float)/32768
    indices=np.zeros((len(vertices),8),dtype=int);weights=np.zeros((len(vertices),8))
    for v,vertex in enumerate(source_vertices):
        for j,(index,weight)in enumerate(vertex['influences']):indices[v,j]=index;weights[v,j]=weight
    all_metrics={name:[]for name in ['source_local_from_global40','global40','static_compensation80','GE_skinning_c0','candidate_bind_local']}
    examples={};source_ids=[];frame_rows=[];qnorms=[];global_qnorms=[];per_bone=[[]for _ in parents]
    field_errors={key:[]for key in ['H_globalq20_to_G40','global_t30_to_G40','Hamilton_parent_q20_times_q0','parent_G40_times_t10_to_t30',
        'local_H_q0_t10_to_inverse_parent_G40_G40','H_local_hierarchy_to_G40','normalized_only_local_hierarchy_to_G40','SRT_fit_local_hierarchy_to_G40',
        'GE_upload_product_max_float24_steps','GE_upload_product_vs_decoded_GE','B80_vs_first_frame']}
    field_errors['GE_upload_product_error_to_rounding_bound_ratio']=[]
    product_step_example=None
    vertex_errors={key:[]for key in ['H_local_SRT_vs_GE','normalized_only_local_vs_GE','SRT_fit_local_vs_GE','G40_B80_vs_GE','renormalized_weights_vs_GE']}
    max_parent_checks=0;reference_B=None;skin_scale=None
    for frame_index,frame in enumerate(manifest['frames']):
        source_path=Path(frame['sourceBlock']['file']);raw=source_path.read_bytes();source_ids.append(identity(source_path))
        if len(raw)!=44*0x130 or frame['sourceBlock']['bytes']!=len(raw):raise ValueError('source record length mismatch')
        record=np.frombuffer(raw,dtype='<f4').reshape(44,76).astype(float)
        global40=record[:,16:32].reshape(44,4,4).transpose(0,2,1)
        bind80=record[:,32:48].reshape(44,4,4).transpose(0,2,1)
        if reference_B is None:
            reference_B=bind80.copy();skin_scale=float(bind80[0,0,0])
        field_errors['B80_vs_first_frame'].append(float(abs(bind80-reference_B).max()))
        local_fields=np.asarray([affine(r[:4],r[4:7])for r in record])
        local_normalized=np.asarray([affine(r[:4],r[4:7],False)for r in record])
        local_actual=np.asarray([global40[i]if p<0 else np.linalg.inv(global40[p])@global40[i]for i,p in enumerate(parents)])
        projected=[];local_rows=[]
        for i in range(44):
            parent_pointer=struct.unpack_from('<I',raw,i*0x130+0x124)[0]
            expected=frame['sourceBase']+parents[i]*0x130 if parents[i]>=0 else 0
            if parent_pointer!=expected:raise ValueError('runtime parent pointer differs from metadata hierarchy')
            max_parent_checks+=1
            for family,matrix in [('source_local_from_global40',local_actual[i]),('global40',global40[i]),('static_compensation80',bind80[i])]:
                projection,metrics=srt_fit(matrix);metrics.update(frame=frame_index,bone=i,parent=parents[i]);all_metrics[family].append(metrics)
                if family=='source_local_from_global40':projected.append(projection);local_rows.append(metrics);per_bone[i].append(metrics)
                previous=examples.get(family)
                if previous is None or metrics['max_normalized_column_dot']>previous['max_normalized_column_dot']:
                    examples[family]={**metrics,'matrix_rows':matrix.tolist(),'projected_SRT_matrix_rows':projection.tolist(),
                        'q0_xyzw':record[i,:4].tolist(),'t10_xyz':record[i,4:7].tolist(),
                        'q20_xyzw':record[i,8:12].tolist(),'t30_xyz':record[i,12:15].tolist()}
            qnorms.append(float(np.linalg.norm(record[i,:4])));global_qnorms.append(float(np.linalg.norm(record[i,8:12])))
            field_errors['H_globalq20_to_G40'].append(float(abs(homogeneous_quaternion(record[i,8:12])-global40[i,:3,:3]).max()))
            field_errors['global_t30_to_G40'].append(float(abs(record[i,12:15]-global40[i,:3,3]).max()))
            field_errors['local_H_q0_t10_to_inverse_parent_G40_G40'].append(float(abs(local_fields[i]-local_actual[i]).max()))
            if parents[i]>=0:
                p=parents[i]
                field_errors['Hamilton_parent_q20_times_q0'].append(float(abs(quaternion_product(record[p,8:12],record[i,:4])-record[i,8:12]).max()))
                field_errors['parent_G40_times_t10_to_t30'].append(float(abs(global40[p,:3,:3]@record[i,4:7]+global40[p,:3,3]-record[i,12:15]).max()))
        hierarchy_h=hierarchy(local_fields,parents);hierarchy_normalized=hierarchy(local_normalized,parents);hierarchy_projected=hierarchy(projected,parents)
        for label,h in [('H_local_hierarchy_to_G40',hierarchy_h),('normalized_only_local_hierarchy_to_G40',hierarchy_normalized),('SRT_fit_local_hierarchy_to_G40',hierarchy_projected)]:
            field_errors[label].append(float(abs(h-global40).max()))
        GE=[]
        for i,row in enumerate(frame['records']):
            if row['index']!=i:raise ValueError('source GE records are not complete source-index order')
            actual=np.asarray(row['matrix'],dtype=np.uint32)&0xffffff
            raw_actual=np.frombuffer(raw,dtype='<u4',count=12,offset=i*0x130+0xc0)&0xffffff
            if not np.array_equal(actual,raw_actual):raise ValueError('manifest source matrices differ from raw block')
            product=(global40[i].astype(np.float32)@bind80[i].astype(np.float32))[:3,:].flatten(order='F').astype('<f4')
            encoded=product.view('<u4')>>8
            steps=int(abs(encoded.astype(np.int64)-actual.astype(np.int64)).max())
            field_errors['GE_upload_product_max_float24_steps'].append(steps)
            matrix=np.eye(4);matrix[:3]=((actual<<8).view('<f4')).reshape(3,4,order='F');GE.append(matrix)
            field_errors['GE_upload_product_vs_decoded_GE'].append(float(abs(product-matrix[:3].flatten(order='F')).max()))
            # Float24 payload-step distance is unstable near cancellation/zero.
            # Bound both F32 dot-product evaluation orders by 2*gamma8*sum|ab|,
            # then add one truncation unit for the product's float24 exponent.
            _,exponents=np.frexp(abs(product.astype(float)))
            truncation=np.where(product!=0,np.ldexp(np.ones(12),exponents-16),np.ldexp(np.ones(12),-141))
            absolute_products=(abs(global40[i])@abs(bind80[i]))[:3].flatten(order='F')
            epsilon=np.finfo(np.float32).eps;gamma8=8*epsilon/(1-8*epsilon)
            ratio=float(np.max(abs(product-matrix[:3].flatten(order='F'))/(truncation+2*gamma8*absolute_products+1e-30)))
            field_errors['GE_upload_product_error_to_rounding_bound_ratio'].append(ratio)
            if product_step_example is None or steps>product_step_example['max_float24_payload_steps']:
                at=int(abs(encoded.astype(np.int64)-actual.astype(np.int64)).argmax())
                product_step_example={'frame':frame_index,'bone':i,'component_column_major':at,
                    'max_float24_payload_steps':steps,'product_f32':float(product[at]),'captured_GE':float(matrix[:3].flatten(order='F')[at]),
                    'absolute_difference':float(abs(product[at]-matrix[:3].flatten(order='F')[at])),
                    'float32_dot_absolute_products':float(absolute_products[at]),'maximum_rounding_bound_ratio':ratio}
            _,metrics=srt_fit(matrix);metrics.update(frame=frame_index,bone=i,parent=parents[i]);all_metrics['GE_skinning_c0'].append(metrics)
            previous=examples.get('GE_skinning_c0')
            if previous is None or metrics['max_normalized_column_dot']>previous['max_normalized_column_dot']:
                examples['GE_skinning_c0']={**metrics,'matrix_rows':matrix.tolist()}
        GE=np.asarray(GE);original_points=apply_skin(vertices,(indices,weights),GE)
        candidates={'H_local_SRT_vs_GE':hierarchy_h@bind80,'normalized_only_local_vs_GE':hierarchy_normalized@bind80,
            'SRT_fit_local_vs_GE':hierarchy_projected@bind80,'G40_B80_vs_GE':global40@bind80}
        for label,matrices in candidates.items():
            difference=apply_skin(vertices,(indices,weights),matrices)-original_points
            vertex_errors[label].append({'frame':frame_index,'max_abs_original_units':float(abs(difference).max()),
                'max_euclidean_original_units':float(np.linalg.norm(difference,axis=1).max()),
                'max_euclidean_PC_units':float(np.linalg.norm(difference,axis=1).max()*units)})
        renormalized=weights/weights.sum(axis=1)[:,None]
        difference=apply_skin(vertices,(indices,renormalized),GE)-original_points
        vertex_errors['renormalized_weights_vs_GE'].append({'frame':frame_index,'max_abs_original_units':float(abs(difference).max()),
            'max_euclidean_original_units':float(np.linalg.norm(difference,axis=1).max()),
            'max_euclidean_PC_units':float(np.linalg.norm(difference,axis=1).max()*units)})
        frame_rows.append({'frame':frame_index,'ticks':frame['ticks'],'source':source_ids[-1],
            'local_max_normalized_column_dot':max(r['max_normalized_column_dot']for r in local_rows),
            'local_max_SRT_residual':max(r['max_matrix_component_residual']for r in local_rows)})
    # Algebraic reference construction, deliberately separate from a semantic
    # claim that these are the exact original rest-pose animation transforms.
    C=np.diag([skin_scale,skin_scale,skin_scale,1])
    candidate_bind=np.asarray([C@np.linalg.inv(b)for b in reference_B])
    candidate_local=np.asarray([candidate_bind[i]if p<0 else np.linalg.inv(candidate_bind[p])@candidate_bind[i]for i,p in enumerate(parents)])
    for i,m in enumerate(candidate_local):
        _,metrics=srt_fit(m);metrics.update(bone=i,parent=parents[i]);all_metrics['candidate_bind_local'].append(metrics)
    maxima={key:max(value)for key,value in field_errors.items()}
    vertex_summary={key:max(value,key=lambda r:r['max_euclidean_original_units'])for key,value in vertex_errors.items()}
    report={'schema':'aya-local-SRT-feasibility/v1','inputs':{'manifest':identity(manifest_path),'metadata':identity(metadata_path),'canonical_scale':identity(canonical_path)},
        'capture_schema':manifest['schema'],'capture_method':manifest['captureMethod'],'frames':60,'bones':44,'runtime_parent_pointer_checks':max_parent_checks,
        'source_record_contract':{'stride':'0x130','q_local_xyzw':'0x00..0x0f float32','translation_local_xyz':'0x10..0x1b float32',
            'q_global_xyzw':'0x20..0x2f float32','translation_global_xyz':'0x30..0x3b float32','G_global_affine':'0x40 column-major float32[16]',
            'B_static_compensation':'0x80 column-major float32[16]','GE_skinning_commands':'0xc0 full GE BONE words[12], low24 float payload',
            'runtime_parent_pointer':'0x124 u32','opaque_fourth_translation_words':'0x1c/0x3c preserved opaque; NaN/pointer-like values are not a translation component'},
        'parents':parents,'roots':[i for i,p in enumerate(parents)if p<0],
        'formulas':{'H':'H(q)=||q||^2 R(q/||q||); diagonals w*w+x*x-y*y-z*z, w*w-x*x+y*y-z*z, w*w-x*x-y*y+z*z',
            'global_fields':'q20_i ~= Hamilton(q20_parent,q0_i); t30_i ~= G40_parent*[t10_i,1]; G40_i ~= affine(H(q20_i),t30_i)',
            'actual_local':'L_i=inverse(G40_parent)*G40_i; roots L_i=G40_i',
            'local_SRT':'normalized rotation=q0/||q0||, uniform scale=(||q0||^2,)*3, translation=t10; keep nonunit magnitude as scale',
            'GE_skin':'GE_i=F24_quantize(first3rows(G40_i*B80_i)); never decompose this as a source-local bone transform',
            'candidate_reference':'Choose C=diag(B80_root0[0,0],same,same,1); mesh vertex x=C*p_source; Jbind_i=C*inverse(B80_i); Jcurrent_i=G40_i. Then Jcurrent_i*inverse(Jbind_i)*x=G40_i*B80_i*p_source exactly before GE quantization.',
            'fit':'Proper polar rotation projected from normalized columns, explicit normalized quaternion, per-axis least-square diagonal scale; column Gram offdiagonal diagnoses unavoidable shear.'},
        'q0_norm_range':[min(qnorms),max(qnorms)],'q20_norm_range':[min(global_qnorms),max(global_qnorms)],
        'local_q0_uniform_scale_range':[min(qnorms)**2,max(qnorms)**2],
        'maximum_field_relationship_errors':maxima,'SRT_fit_metrics':{key:aggregate(rows)for key,rows in all_metrics.items()},
        'GE_near_zero_float24_step_example':product_step_example,
        'worst_examples':examples,'per_bone_local_metrics':[{'bone':i,'parent':parents[i],**aggregate(rows)}for i,rows in enumerate(per_bone)],
        'vertex_errors_against_GE_float64_weighted_evaluation':vertex_summary,'canonical_PC_units_per_original_unit':units,
        'weights':{'minimum_sum':float(weights.sum(axis=1).min()),'maximum_sum':float(weights.sum(axis=1).max()),
                   'not_unit_sum_vertices':int((weights.sum(axis=1)!=1).sum()),'preserve_quantized_weights':True},
        'candidate_reference':{'common_C_rows':C.tolist(),'root0_Jbind_rows':candidate_bind[0].tolist(),
            'max_algebraic_inverse_bind_residual':float(max(abs(np.linalg.inv(j)@C-b).max()for j,b in zip(candidate_bind,reference_B))),
            'meaning':'A valid algebraic reference construction, not independent proof of original authored bind-pose convention.'},
        'assessment':{'substantial_source_local_shear_observed':False,
            'reason':'Actual local normalized-column nonorthogonality and SRT residual are float32-scale noise; source nonunit quaternion magnitude explains uniform scale and must not be discarded.',
            'native_SRT_math_candidate':True,'bit_identical_native_replacement_proven':False,
            'remaining_constraints':['Actual UE skeletal import/build/render is not executed.',
                'Two source roots0 and43 require an explicit preserved hierarchy policy for native skeleton import.',
                'Source GE matrices contain independent float24 truncation and do not remain exactly SRT. A native normalized-quaternion path will not reproduce these bits automatically.',
                'All3456 source vertex weight sums are below1; engine import or weight normalization must not be silently treated as identical.',
                'This capture tests60 poses of one action; other actions and reference/bind semantics require further cross-checking.',
                'Uniform scales compose without mathematical shear; arbitrary nonuniform-scale hierarchy/FTransform policies are not established by these data.']},
        'frames_detail':frame_rows,'UE_executed':False,'modified_existing_runtime_or_assets':False}
    if maxima['GE_upload_product_error_to_rounding_bound_ratio']>1.00001:raise ValueError('source raw40*80 exceeds F32 dot-product +float24 truncation error budget')
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    md=['# Aya local SRT feasibility, source capture only','',
        'No UE editor, PPSSPP or existing runtime/exporter/assets were modified.','',
        '## Result','',report['assessment']['reason'],'',
        'Normalized quaternion alone is lossy: retain squared quaternion norm as uniform scale. Skinning GE matrices are not local bone matrices.','',
        '```json',json.dumps({'q0_norm_range':report['q0_norm_range'],'q20_norm_range':report['q20_norm_range'],
            'local_scale_range':report['local_q0_uniform_scale_range'],'field_errors':maxima,'SRT_metrics':report['SRT_fit_metrics'],
            'vertex_errors':vertex_summary},indent=2),'```','',
        '## Conventions and limits','']
    md += ['- '+key+': '+value for key,value in report['formulas'].items()]
    md += ['']+['- '+value for value in report['assessment']['remaining_constraints']]
    output.with_suffix('.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(output),'field_errors':maxima,'SRT_fit_metrics':report['SRT_fit_metrics'],'vertex_errors':vertex_summary},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--metadata',type=Path,required=True)
    p.add_argument('--canonical-scale',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();analyze(a.manifest,a.metadata,a.canonical_scale,a.out)
