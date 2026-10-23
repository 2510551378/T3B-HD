"""Replay exact observed street draw sets; render-buffer slots are not object IDs."""
import hashlib,json,struct
from pathlib import Path
import unreal


def check(v,msg):
    if not v:raise RuntimeError(msg)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def transform(t):
    return dict(translation=[t.translation.x,t.translation.y,t.translation.z],scale=[t.scale3d.x,t.scale3d.y,t.scale3d.z],
                quaternion=[t.rotation.x,t.rotation.y,t.rotation.z,t.rotation.w])


class StreetSnapshot:
    is_series=True
    def __init__(self,path,sub,capture,folder):
        path=Path(path);series=read(path)
        check(series['passed']and series['schema']=='t3b-paired-original-street-series/v1','Wrong scene series')
        check([f['sample']for f in series['frames']]==list(range(12)),'Incomplete scene series')
        self.snapshots=[];self.snapshot_refs=[f['snapshot']for f in series['frames']]
        for f in series['frames']:
            p=Path(f['snapshot']['file']);check(sha(p)==f['snapshot']['sha256'],'Snapshot changed')
            d=read(p);check(d['passed']and d['source_sample']==f['sample'],'Source sample mismatch');self.snapshots.append(d)
        self.sub=sub;self.capture=capture;self.folder=folder;self.entries=[];self.materials={};self.current=-1;self.active=0
        self.paths={key:folder/('street_series_actual_'+key+'.bin')for key in ('components','indices','uv')}
        for p in self.paths.values():check(not p.exists(),'Never overwrite actual scene readback');p.write_bytes(b'')
        textures={t['rgba_sha256']:t for d in self.snapshots for t in d['textures']};actual_textures=[]
        for i,t in enumerate(textures.values()):
            tex=unreal.load_asset(t['asset']);check(isinstance(tex,unreal.Texture2D),'Missing source street texture')
            png=folder/('actual_street_texture_%02d.png'%i);task=unreal.AssetExportTask()
            for prop,value in dict(object=tex,exporter=unreal.TextureExporterPNG(),filename=str(png),automated=True,prompt=False,replace_identical=False).items():task.set_editor_property(prop,value)
            check(unreal.Exporter.run_asset_export_task(task)and png.is_file(),'Street texture export failed')
            actual_textures.append(dict(asset=tex.get_path_name(),file=str(png),sha256=sha(png),source_rgba_sha256=t['rgba_sha256'],srgb=tex.get_editor_property('srgb')))
        self.identity=dict(series=dict(file=str(path),sha256=sha(path)),helper_sha256=sha(Path(__file__)),frames=[],textures=actual_textures,
            temporal_object_identity_verified=False,interpolation_used=False,source_fog_stencil_equivalence=False,
            source_translucent_main_depth_equivalence=False)

    def select_sample(self,sample):
        if self.current==sample:return
        check(sample==self.current+1,'Only ordered original sample replay is supported')
        self.data=self.snapshots[sample];source=Path(self.data['binary']['file'])
        check(sha(source)==self.data['binary']['sha256'],'Scene binary changed');raw=source.read_bytes()
        n,total,mats=struct.unpack_from('<3I',raw,8)
        check(raw[:8]==b'T3BSTG1\0'and n==self.data['draw_count']and total==self.data['vertices']and mats==81,'Scene header mismatch')
        check(len(raw)==20+n*20+total*36,'Scene binary extent mismatch')
        for e in self.entries:e['component'].set_visibility(False,True)
        Q=unreal.GeometryScript_MeshQueries;L=unreal.GeometryScript_List;C=unreal.GeometryScript_VertexColors;E=unreal.GeometryScript_MeshEdits
        frame=dict(sample=sample,draw_count=n,vertices=total,snapshot=self.snapshot_refs[sample],draws=[])
        with self.paths['components'].open('ab')as output,self.paths['indices'].open('ab')as ix,self.paths['uv'].open('ab')as uv:
            for i,d in enumerate(self.data['draws']):
                record,word,first,count,mid=struct.unpack_from('<5I',raw,20+i*20)
                check((record,word,first,count,mid)==(d['register_record'],d['register_word'],d['first_vertex'],d['vertices'],d['material']),'Draw header mismatch')
                if mid not in self.materials:
                    material=unreal.load_asset(d['material_asset']);check(isinstance(material,unreal.Material),'Street material missing')
                    check(material.get_editor_property('two_sided')==(not bool(d['source_cull'])),'Street cull changed')
                    self.materials[mid]=material
                if i==len(self.entries):
                    actor=self.sub.spawn_actor_from_class(unreal.DynamicMeshActor,unreal.Vector(),unreal.Rotator(),True)
                    comp=actor.get_dynamic_mesh_component();comp.set_vertex_color_space_transform_mode(unreal.DynamicMeshVertexColorTransformMode.NO_TRANSFORM)
                    comp.set_visibility(False,True);self.capture.show_only_actor_components(actor,False)
                    self.entries.append(dict(component=comp,mesh=comp.get_dynamic_mesh(),geometry=None))
                entry=self.entries[i];comp=entry['component'];mesh=entry['mesh'];comp.set_material(0,self.materials[mid]);comp.set_translucent_sort_priority(-1000+i)
                values=list(struct.iter_unpack('<3d2f4B',raw[20+n*20+first*36:20+n*20+(first+count)*36]))
                points=[unreal.Vector(*v[:3])for v in values];rebuild=entry['geometry']!=d['raw_vertex_sha256']
                if rebuild:
                    mesh.reset();buffers=unreal.GeometryScriptSimpleMeshBuffers()
                    for prop,value in dict(vertices=points,uv0=[unreal.Vector2D(*v[3:5])for v in values],
                        vertex_colors=[unreal.LinearColor(*[c/255 for c in v[5:9]])for v in values],
                        triangles=[unreal.IntVector(k,k+1,k+2)for k in range(0,count,3)]).items():buffers.set_editor_property(prop,value)
                    E.append_buffers_to_mesh(mesh,buffers,0,False);entry['geometry']=d['raw_vertex_sha256']
                else:E.set_all_mesh_vertex_positions(mesh,L.convert_array_to_vector_list(points))
                check(Q.get_vertex_count(mesh)==count and Q.get_num_triangle_i_ds(mesh)==count//3,'Actual scene topology changed')
                _,pl,pg=Q.get_all_vertex_positions(mesh,False);_,cl,cv,cg=C.get_mesh_per_vertex_colors(mesh,False)
                check(cv and not(pg or cg),'Scene readback invalid')
                begin=output.tell();index_start=ix.tell();uv_start=uv.tell()
                for p,c in zip(L.convert_vector_list_to_array(pl),L.convert_color_list_to_array(cl)):
                    output.write(struct.pack('<3d4f',p.x,p.y,p.z,c.r,c.g,c.b,c.a))
                for ti in range(count//3):
                    t,valid=Q.get_triangle_indices(mesh,ti);check(valid,'Missing scene triangle');ix.write(struct.pack('<3I',t.x,t.y,t.z))
                    a,b,c,valid=Q.get_triangle_u_vs(mesh,0,ti);check(valid,'Missing scene UV')
                    for v in(a,b,c):uv.write(struct.pack('<2f',v.x,v.y))
                frame['draws'].append(dict(buffer_slot=i,vertices=count,readback_byte_offset=begin,index_byte_offset=index_start,uv_byte_offset=uv_start,
                    material_asset=comp.get_material(0).get_path_name(),two_sided=self.materials[mid].get_editor_property('two_sided'),
                    actual_sort_priority=comp.get_editor_property('translucency_sort_priority'),component_transform=transform(comp.get_world_transform()),
                    geometry_rebuilt=rebuild,source_world_matches_old_reference=d['WORLD_matches_old_reference']))
        self.active=n;self.current=sample;frame['inactive_buffer_slots']=len(self.entries)-n
        self.identity['frames'].append(frame)
        for key,p in self.paths.items():self.identity[key]=dict(file=str(p),sha256=sha(p))

    def show(self,visible):
        for i,e in enumerate(self.entries):e['component'].set_visibility(visible and i<self.active,True)
