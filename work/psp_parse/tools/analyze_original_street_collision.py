"""Read-only original-street ground, plane/Gram LOS and material-alpha evidence.

Writes only an independent report. Visual triangles are collision candidates,
not recovered original PSP collision or navigation data.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import struct

import numpy as np
from PIL import Image

from recover_original_actor_metadata import identity, sha


def plane_gram(start,end,vertices):
    """Segment/plane intersection followed by Gram-matrix barycentric test."""
    a,b,c=vertices;e0=b-a;e1=c-a;n=np.cross(e0,e1);direction=end-start
    denominator=float(np.dot(n,direction));normal_squared=float(np.dot(n,n))
    if normal_squared<=1e-24 or abs(denominator)<=1e-12*np.sqrt(normal_squared)*max(np.linalg.norm(direction),1):return None
    t=float(np.dot(n,a-start)/denominator)
    if t < -1e-9 or t > 1+1e-9:return None
    q=start+t*direction-a
    d00=float(e0@e0);d01=float(e0@e1);d11=float(e1@e1)
    determinant=d00*d11-d01*d01
    if determinant<=1e-20:return None
    u=float(((q@e0)*d11-(q@e1)*d01)/determinant)
    v=float(((q@e1)*d00-(q@e0)*d01)/determinant)
    if u < -1e-7 or v < -1e-7 or u+v > 1+1e-7:return None
    return {'segment_t':t,'distance':float(t*np.linalg.norm(direction)),
            'point':(start+t*direction).tolist(),'barycentric':[1-u-v,u,v],
            'unit_normal':(n/np.sqrt(normal_squared)).tolist()}


def analyze(metadata_path,output):
    metadata=json.loads(metadata_path.read_text(encoding='utf-8'));binary=Path(metadata['binary']['path'])
    if identity(binary)!=metadata['binary']:raise ValueError('scene binary identity changed')
    data=binary.read_bytes();head=struct.unpack_from('<8s4I8f',data)
    if head[:5]!=(b'T3BSCN1\0',1,140,31656,81):raise ValueError('unexpected original scene schema')
    packets=[struct.unpack_from('<3I',data,56+i*12)for i in range(head[2])]
    vertex_base=56+12*head[2]
    vertices=np.asarray([struct.unpack_from('<5f4B',data,vertex_base+i*24)for i in range(head[3])])
    material_info=[];alpha_images={}
    for m in metadata['materials']:
        path=Path(m['texture']['png']['path'])
        if identity(path)!=m['texture']['png']:raise ValueError('texture identity changed')
        rgba=np.asarray(Image.open(path).convert('RGBA'));alpha=rgba[:,:,3]
        counts={name:int(condition.sum())for name,condition in [('zero',alpha==0),('partial',(alpha>0)&(alpha<255)),('opaque',alpha==255)]}
        category='all_opaque'if counts['opaque']==alpha.size else 'contains_zero_and_partial'if counts['zero']and counts['partial']else'contains_zero'if counts['zero']else'contains_partial'
        flags=[m['blend_enable'],m['depth_write'],m['cull_enable']]
        material_info.append({'material':m['material_index'],'material_id':m['material_id'],
            'texture_RGBA_sha256':sha(rgba.tobytes()),'texture_png':str(path),'alpha_pixels':counts,
            'alpha_category':category,'blend_enable':flags[0],'depth_write':flags[1],'cull_enable':flags[2],
            'coarse_solid_candidate':bool(flags[1]and not flags[0])})
        alpha_images[m['material_index']]=alpha
    triangles=[];ground_draws=[]
    for draw,(first,count,material)in enumerate(packets):
        if draw in [4,5,6,7,8,9]:
            points=vertices[first:first+count,:3]
            ground_draws.append({'draw':draw,'source_vertex_record':metadata['draws'][draw]['vertex_record'],
                'triangles':count//3,'material':material,'xz_bbox':[points[:,[0,2]].min(0).tolist(),points[:,[0,2]].max(0).tolist()],
                'y_range':[float(points[:,1].min()),float(points[:,1].max())]})
        for local in range(0,count,3):
            attributes=vertices[first+local:first+local+3]
            triangles.append({'draw':draw,'local_triangle':local//3,'material':material,'attributes':attributes,
                              'points':attributes[:,:3],'solid':material_info[material]['coarse_solid_candidate']})
    def texture_alpha_at(triangle,barycentric):
        bary=np.asarray(barycentric);uv=bary@triangle['attributes'][:,3:5]
        alpha=alpha_images[triangle['material']];height,width=alpha.shape
        # Describes original logical RGBA row order. Both vertical conventions
        # are reported, avoiding any assumption about the C BMP loader.
        sampled=[]
        for v in [uv[1],1-uv[1]]:
            x,y=uv[0]*width-.5,v*height-.5;ix,iy=int(np.floor(x)),int(np.floor(y));fx,fy=x-ix,y-iy
            sampled.append(float((1-fy)*((1-fx)*alpha[iy%height,ix%width]+fx*alpha[iy%height,(ix+1)%width])+fy*((1-fx)*alpha[(iy+1)%height,ix%width]+fx*alpha[(iy+1)%height,(ix+1)%width])))
        vertex_alpha=float(bary@triangle['attributes'][:,8])
        return {'raw_uv':uv.tolist(),'linear_repeat_alpha_0_to255_logicalV_and_flippedV':sampled,'interpolated_vertex_alpha':vertex_alpha,
                'passes_alpha_greater0_both_V_conventions':all(a*vertex_alpha>0 for a in sampled)}
    def intersections(start,end,ground_only=False):
        hits=[]
        for tri in triangles:
            if ground_only and tri['draw']not in [4,5,6,7,8,9]:continue
            hit=plane_gram(np.asarray(start,dtype=float),np.asarray(end,dtype=float),tri['points'])
            if hit:
                hit.update(draw=tri['draw'],local_triangle=tri['local_triangle'],material=tri['material'],coarse_solid_candidate=tri['solid'],
                           texture_alpha=texture_alpha_at(tri,hit['barycentric']))
                hits.append(hit)
        return sorted(hits,key=lambda h:h['segment_t'])
    spawn_ground={}
    for name,index in [('player',5),('enemy',8)]:
        x,z=head[index:index+2]
        ground_hits=intersections([x,5,z],[x,-5,z],True)
        spawn_ground[name]={'xz':[x,z],'base_road_covered':bool(ground_hits),'downward_plane_Gram_hits':ground_hits}
    player=[head[5],1.4,head[6]];enemy=[head[8],1.4,head[9]]
    los_hits=intersections(player,enemy)
    solid_hits=[hit for hit in los_hits if hit['coarse_solid_candidate']]
    alpha_hits=[hit for hit in solid_hits if hit['texture_alpha']['passes_alpha_greater0_both_V_conventions']]
    summary=Counter();vertex_alpha=Counter()
    for tri in triangles:
        info=material_info[tri['material']]
        if tri['solid']:
            summary[info['alpha_category']]+=1
            a=tri['attributes'][:,8]
            vertex_alpha['all_zero'if(a==0).all()else'all_opaque'if(a==255).all()else'nonopaque_or_mixed']+=1
    report={'schema':'original-street-collision-evidence/v1','passed':True,'inputs':{'scene_metadata':identity(metadata_path),'scene_binary':identity(binary)},
        'method':'float64 segment-plane intersection + independent Gram-matrix barycentric inclusion; no Moller-Trumbore or C collision function reused',
        'base_road_draws':ground_draws,'spawn_ground':spawn_ground,
        'spawn_line_of_sight_y1_4':{'start':player,'end':enemy,'segment_length':float(np.linalg.norm(np.asarray(enemy)-player)),
            'all_static_triangle_intersections':len(los_hits),'coarse_solid_intersections':len(solid_hits),
            'nonzero_alpha_solid_intersections_both_V_conventions':len(alpha_hits),
            'nearest_static':los_hits[0]if los_hits else None,'nearest_coarse_solid':solid_hits[0]if solid_hits else None,
            'nearest_nonzero_alpha_solid':alpha_hits[0]if alpha_hits else None,'all_hits':los_hits},
        'materials':material_info,'material_alpha_category_counts':dict(Counter(m['alpha_category']for m in material_info)),
        'unique_RGBA_texture_count':len({m['texture_RGBA_sha256']for m in material_info}),
        'coarse_solid_candidate_materials':sum(m['coarse_solid_candidate']for m in material_info),
        'coarse_solid_candidate_triangles':sum(summary.values()),'coarse_solid_triangle_texture_alpha_categories':dict(summary),
        'coarse_solid_triangle_vertex_alpha_categories':dict(vertex_alpha),
        'limits':['These are visible geometry candidates, not original collision/navigation semantics.',
            'Draw XZ bboxes are inventory bounds, not safe rectangular movement boundaries; query actual containing ground triangles.',
            'Texture cutout/vertex alpha and cull side can affect visibility; depth-write and disabled blending alone do not prove physical solidity.',
            'Original off-camera/culled collision geometry is unavailable. This report does not modify original assets or choose gameplay bounds.'],
        'runtime_C_executed':False}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({key:report[key]for key in ['passed','material_alpha_category_counts','coarse_solid_candidate_materials','coarse_solid_candidate_triangles','coarse_solid_triangle_texture_alpha_categories','spawn_ground','spawn_line_of_sight_y1_4']},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--metadata',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();analyze(a.metadata,a.out)
