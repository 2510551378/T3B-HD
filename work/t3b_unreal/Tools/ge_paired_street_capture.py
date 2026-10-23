"""UE-only diagnostic scene from exact same GE sample; never saves assets."""
import hashlib,json,struct
from pathlib import Path
import unreal


def check(v,msg):
    if not v:raise RuntimeError(msg)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


class StreetSnapshot:
    def __init__(self,path,sub,capture,folder):
        path=Path(path);self.data=json.loads(path.read_text(encoding='utf-8'));self.components=[];self.report=[]
        check(self.data['passed']and self.data['source_sample']==0,'Only exact source sample0 is supported')
        binary=Path(self.data['binary']['file']);check(sha(binary)==self.data['binary']['sha256'],'Street input changed')
        raw=binary.read_bytes();check(raw[:8]==b'T3BSTG1\0'and struct.unpack_from('<3I',raw,8)==(140,31656,81),'Street header differs')
        check(len(raw)==20+140*20+31656*36,'Street input extent differs')
        materials={};Q=unreal.GeometryScript_MeshQueries;L=unreal.GeometryScript_List;C=unreal.GeometryScript_VertexColors
        readback=folder/'actual_street_components.bin';indices=folder/'actual_street_indices.bin';uvfile=folder/'actual_street_uv.bin'
        with readback.open('wb')as output,indices.open('wb')as ix,uvfile.open('wb')as uv:
            for i,d in enumerate(self.data['draws']):
                record,word,first,count,material_index=struct.unpack_from('<5I',raw,20+i*20)
                check((record,word,first,count,material_index)==(d['register_record'],d['register_word'],d['first_vertex'],d['vertices'],d['material']),'Draw header mismatch')
                if material_index not in materials:
                    m=unreal.load_asset(d['material_asset']);check(isinstance(m,unreal.Material),'Missing original street material')
                    check(m.get_editor_property('two_sided')==(not bool(d['source_cull'])),'Street cull property mismatch')
                    check(m.get_editor_property('shading_model')==unreal.MaterialShadingModel.MSM_UNLIT,'Street must use vertex colours')
                    materials[material_index]=m
                actor=sub.spawn_actor_from_class(unreal.DynamicMeshActor,unreal.Vector(),unreal.Rotator(),True)
                comp=actor.get_dynamic_mesh_component();comp.set_material(0,materials[material_index])
                comp.set_vertex_color_space_transform_mode(unreal.DynamicMeshVertexColorTransformMode.NO_TRANSFORM)
                comp.set_translucent_sort_priority(-1000+i);comp.set_visibility(False,True)
                values=list(struct.iter_unpack('<3d2f4B',raw[20+140*20+first*36:20+140*20+(first+count)*36]))
                buffers=unreal.GeometryScriptSimpleMeshBuffers()
                for prop,value in dict(vertices=[unreal.Vector(*v[:3])for v in values],uv0=[unreal.Vector2D(*v[3:5])for v in values],
                    vertex_colors=[unreal.LinearColor(*[c/255 for c in v[5:9]])for v in values],
                    triangles=[unreal.IntVector(k,k+1,k+2)for k in range(0,count,3)]).items():buffers.set_editor_property(prop,value)
                mesh=comp.get_dynamic_mesh();unreal.GeometryScript_MeshEdits.append_buffers_to_mesh(mesh,buffers,0,False)
                check(Q.get_vertex_count(mesh)==count and Q.get_num_triangle_i_ds(mesh)==count//3,'Scene topology differs')
                _,pl,pg=Q.get_all_vertex_positions(mesh,False);_,cl,cv,cg=C.get_mesh_per_vertex_colors(mesh,False)
                check(cv and not(pg or cg),'Scene component readback invalid')
                begin=output.tell()
                for v,c in zip(L.convert_vector_list_to_array(pl),L.convert_color_list_to_array(cl)):
                    output.write(struct.pack('<3d4f',v.x,v.y,v.z,c.r,c.g,c.b,c.a))
                for ti in range(count//3):
                    t,valid=Q.get_triangle_indices(mesh,ti);check(valid,'Missing scene triangle');ix.write(struct.pack('<3I',t.x,t.y,t.z))
                    a,b,c,valid=Q.get_triangle_u_vs(mesh,0,ti);check(valid,'Missing scene UV')
                    for t in(a,b,c):uv.write(struct.pack('<2f',t.x,t.y))
                self.report.append(dict(source_draw=i,vertices=count,readback_byte_offset=begin,
                    material_asset=comp.get_material(0).get_path_name(),two_sided=materials[material_index].get_editor_property('two_sided'),
                    actual_sort_priority=comp.get_editor_property('translucency_sort_priority'),
                    component_transform=str(comp.get_world_transform()),source_blend=d['source_blend'],
                    source_depth_write=d['source_depth_write'],source_fog_stencil_not_emulated=True))
                self.components.append(comp);capture.show_only_actor_components(actor,False)
        textures=[]
        for i,row in enumerate(self.data['textures']):
            texture=unreal.load_asset(row['asset']);check(isinstance(texture,unreal.Texture2D),'Street texture missing')
            file=folder/('actual_street_texture_%02d.png'%i);task=unreal.AssetExportTask()
            for prop,value in dict(object=texture,exporter=unreal.TextureExporterPNG(),filename=str(file),automated=True,prompt=False,replace_identical=False).items():task.set_editor_property(prop,value)
            check(unreal.Exporter.run_asset_export_task(task)and file.is_file(),'Street texture source export failed')
            textures.append(dict(asset=texture.get_path_name(),file=str(file),sha256=sha(file),source_rgba_sha256=row['rgba_sha256'],
                                 srgb=texture.get_editor_property('srgb')))
        self.identity=dict(snapshot=dict(file=str(path),sha256=sha(path)),helper_sha256=sha(Path(__file__)),draws=self.report,
            readback=dict(file=str(readback),sha256=sha(readback)),indices=dict(file=str(indices),sha256=sha(indices)),
            uv=dict(file=str(uvfile),sha256=sha(uvfile)),textures=textures,source_sample=0,
            source_fog_stencil_equivalence=False,source_translucent_main_depth_equivalence=False)

    def show(self,visible):
        for comp in self.components:comp.set_visibility(visible,True)
