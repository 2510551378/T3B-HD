"""UE-only source-camera adapter and independent visible marker capture controls."""
import hashlib
import json
import math
from pathlib import Path
import unreal


def check(v,msg):
    if not v:raise RuntimeError(msg)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def multiply(a,b):return [[sum(a[i][k]*b[k][j] for k in range(4))for j in range(4)]for i in range(4)]
def inverse(a):
    r=[list(row)+[float(i==j) for j in range(4)]for i,row in enumerate(a)]
    for i in range(4):
        pivot=max(range(i,4),key=lambda k:abs(r[k][i]));r[i],r[pivot]=r[pivot],r[i]
        check(abs(r[i][i])>1e-15,'Singular source-camera matrix');d=r[i][i];r[i]=[x/d for x in r[i]]
        for j in range(4):
            if j!=i:
                d=r[j][i];r[j]=[x-d*y for x,y in zip(r[j],r[i])]
    return [row[4:]for row in r]
def rows(matrix):
    return [[getattr(matrix.get_editor_property(key),axis)for axis in ('x','y','z','w')]
            for key in ('x_plane','y_plane','z_plane','w_plane')]
def matrix(r):
    return unreal.Matrix(**{k:unreal.Plane(*v)for k,v in zip(('x_plane','y_plane','z_plane','w_plane'),r)})
def vec(v):return [v.x,v.y,v.z]


class SourceCamera:
    def __init__(self,path,subsystem,capture,world):
        self.path=Path(path);self.data=json.loads(self.path.read_text(encoding='utf-8'))
        check(self.data['passed']and self.data['frame_count']==12,'Invalid source-camera fixture')
        check(sha(Path(self.data['binary']['file']))==self.data['binary']['sha256'],'Camera fixture changed')
        self.capture=capture;self.sub=subsystem;self.world=world;self.marker=None;self.marker_mesh=None
        self.identity=dict(file=str(self.path),sha256=sha(self.path),helper_sha256=sha(Path(__file__)),
                           engine_capture_source_pin=None,original_clock_recovered=False)

    def apply(self,camera,sample):
        f=self.data['frames'][sample];v=f['view_row_major'];inv=inverse(v)
        units=self.data['metres_per_PSP_world_unit']*100;origin=self.data['fixed_shared_PSP_world_origin']
        eye=[(inv[3][i]-origin[i])*units for i in (0,2,1)]
        forward=[-inv[2][i] for i in (0,2,1)];up=[inv[1][i] for i in (0,2,1)]
        rotation=unreal.MathLibrary.make_rot_from_xz(unreal.Vector(*forward),unreal.Vector(*up))
        camera.set_actor_location(unreal.Vector(*eye),False,False);camera.set_actor_rotation(rotation,False)
        actual_world=rows(self.capture.get_world_transform().to_matrix())
        swap=[[0.,0.,1.,0.],[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,0.,1.]]
        view=multiply(inverse(actual_world),swap)
        source_inverse=[[1/units,0.,0.,0.],[0.,0.,1/units,0.],[0.,1/units,0.,0.],[*origin,1.]]
        target=multiply(multiply(multiply(source_inverse,v),f['projection_row_major']),f['clip_remap_row_major'])
        projection=multiply(inverse(view),target)
        scale=projection[2][3];check(abs(scale)>1e-12,'Invalid homogeneous camera normalization')
        projection=[[x/scale for x in row]for row in projection]
        self.capture.set_editor_property('use_custom_projection_matrix',True)
        self.capture.set_editor_property('custom_projection_matrix',matrix(projection))
        # FOV is only a culling/LOD hint; actual rendering uses the stored custom matrix.
        self.capture.set_editor_property('fov_angle',math.degrees(2*math.atan(480/272*math.tan(math.radians(f['derived_vertical_fov_degrees'])/2))))
        self.capture.set_editor_property('camera_cut_this_frame',True)
        actual=rows(self.capture.get_editor_property('custom_projection_matrix'))
        check(actual==projection,'Actual UE custom projection property lost values')
        return dict(source_sample=sample,camera_component_world_matrix=actual_world,
                    derived_UE_view_matrix=view,actual_custom_projection_matrix=actual,
                    source_world_to_clip_f64=target,homogeneous_normalization=scale,
                    actual_use_custom_projection=self.capture.get_editor_property('use_custom_projection_matrix'),
                    actual_fov_hint=self.capture.get_editor_property('fov_angle'),
                    note='CPU property readback; marker PNG independently checks raster projection. Actual FViewInfo not read back.')

    def markers(self,sample,positions,export):
        if self.marker is None:
            material=unreal.new_object(unreal.Material)
            material.set_editor_property('blend_mode',unreal.BlendMode.BLEND_OPAQUE)
            material.set_editor_property('shading_model',unreal.MaterialShadingModel.MSM_UNLIT)
            material.set_editor_property('two_sided',True)
            color=unreal.MaterialEditingLibrary.create_material_expression(material,unreal.MaterialExpressionVertexColor,0,0)
            check(unreal.MaterialEditingLibrary.connect_material_property(color,'',unreal.MaterialProperty.MP_EMISSIVE_COLOR),'Marker emissive graph failed')
            unreal.MaterialEditingLibrary.recompile_material(material)
            self.marker_material=material
            self.marker=self.sub.spawn_actor_from_class(unreal.DynamicMeshActor,unreal.Vector(),unreal.Rotator(),True)
            comp=self.marker.get_dynamic_mesh_component();comp.set_material(0,material)
            comp.set_vertex_color_space_transform_mode(unreal.DynamicMeshVertexColorTransformMode.NO_TRANSFORM)
            self.marker_mesh=comp.get_dynamic_mesh();self.capture.show_only_actor_components(self.marker,False)
        check(self.marker_material.get_path_name().startswith('/Engine/Transient.'),'Marker material must remain transient')
        # Select six widely separated existing body vertices by source-predicted screen position.
        record=self.apply_report;target=record['source_world_to_clip_f64'];candidates=[]
        for i,p in enumerate(positions):
            h=[p.x,p.y,p.z,1.];clip=[sum(h[k]*target[k][j]for k in range(4))for j in range(4)]
            if clip[3]<=0:continue
            x=(clip[0]/clip[3]+1)*240;y=(1-clip[1]/clip[3])*136
            if 16<x<464 and 16<y<256:candidates.append((i,p,[x,y]))
        check(len(candidates)>6,'Not enough in-frame source vertices for camera control')
        chosen=[min(candidates,key=lambda c:c[2][0])]
        while len(chosen)<6:
            candidate=max(candidates,key=lambda c:min(sum((a-b)**2 for a,b in zip(c[2],x[2]))for x in chosen))
            check(min(sum((a-b)**2 for a,b in zip(candidate[2],x[2]))for x in chosen)>100,'Control markers overlap')
            chosen.append(candidate)
        right=unreal.Vector(*record['camera_component_world_matrix'][1][:3])
        up=unreal.Vector(*record['camera_component_world_matrix'][2][:3])
        palette=[(1,0,0),(0,1,0),(0,0,1),(1,1,0),(1,0,1),(0,1,1)]
        vertices=[];colors=[];triangles=[];records=[]
        for j,((index,p,predicted),rgb)in enumerate(zip(chosen,palette)):
            # Screen footprint radius~2 px. At source depth this covers several actual pixels.
            h=[p.x,p.y,p.z,1.];clip_w=sum(h[k]*target[k][3]for k in range(4))
            radius=2*clip_w/abs(target[0][0]*240) if abs(target[0][0])>1e-4 else 1.
            radius=max(.6,min(radius,2.0))
            for x,y in ((-1,-1),(1,-1),(1,1),(-1,1)):
                vertices.append(p+right*(x*radius)+up*(y*radius));colors.append(unreal.LinearColor(*rgb,1))
            triangles.extend([unreal.IntVector(j*4,j*4+1,j*4+2),unreal.IntVector(j*4,j*4+2,j*4+3)])
            records.append(dict(body_vertex_index=index,world_position=vec(p),rgb=list(rgb),radius_cm=radius,
                                predicted_source_pixel=predicted))
        dm=self.marker_mesh;dm.reset()
        buffers=unreal.GeometryScriptSimpleMeshBuffers()
        for prop,value in dict(vertices=vertices,vertex_colors=colors,triangles=triangles).items():buffers.set_editor_property(prop,value)
        unreal.GeometryScript_MeshEdits.append_buffers_to_mesh(dm,buffers,0,False)
        comp=self.marker.get_dynamic_mesh_component();comp.set_visibility(True,True)
        image=export('%02d_original_marker_control.png'%sample);comp.set_visibility(False,True)
        return dict(points=records,image=image,material_asset=self.marker_material.get_path_name(),
                    material_opaque=True,material_unlit=True,synthetic_control=True)
