"""Actual UE components for the exact same-capture 28-draw original creature."""
import hashlib,json,struct
from pathlib import Path
import unreal


def check(v,msg):
    if not v:raise RuntimeError(msg)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def identity(p):return dict(file=str(p),sha256=sha(p))
def transform(t):return dict(translation=[t.translation.x,t.translation.y,t.translation.z],scale=[t.scale3d.x,t.scale3d.y,t.scale3d.z],quaternion=[t.rotation.x,t.rotation.y,t.rotation.z,t.rotation.w])


class OtherActor:
    def __init__(self,proof_path,project,folder,run_id,sub,capture,origin,units,weapon,body,read_proof):
        proof_path=Path(proof_path);proof=read(proof_path);source=Path(proof['input_manifest']['file'])
        check(sha(source)==proof['input_manifest']['sha256'],'Other actor manifest changed');self.source=read(source)
        check(self.source['captures']==weapon['captures']and self.source['same_GE_dump_pairing'],'Other actor is not from same original GE dumps')
        self.data,self.uv=read_proof(proof_path,self.source)
        self.origin=origin;self.units=units;self.entries=[];self.folder=folder;self.current=-1
        self.paths={k:folder/('other_actor_actual_'+k+'.bin')for k in ('components','indices','uv')}
        for p in self.paths.values():check(not p.exists(),'Never replace component readback');p.write_bytes(b'')
        bundle=project/'Content/SourceData/manifest.json';recipe=next(x for x in read(bundle)['actors']if x['name']=='Twisted')['materials'][0]
        check(len(self.source['materials'])==1,'Expected one original creature atlas')
        material_id=next(iter(self.source['materials']));params=self.source['draws'][0]['material_parameters']
        check(all(d['material_id']==material_id and d['material_parameters']==params for d in self.source['draws']),'Actor material state varies; needs per-draw materials')
        check(params['cull_enabled']and params['color_double']and params['alpha_blend_enabled']and params['alpha_test_ref']==0 and
              params['texture_function']==0 and params['texture_alpha_used']and params['uv_scale']==[recipe['su'],recipe['sv']]==[1.,1.]and
              params['uv_offset']==[recipe['ou'],recipe['ov']]==[0.,0.]and recipe['rgb_scale']==2.,'Unsupported actor material recipe')
        parent=unreal.load_asset(recipe['asset']);tex=unreal.load_asset(recipe['texture_asset'])
        check(isinstance(parent,unreal.Material)and isinstance(tex,unreal.Texture2D),'Original creature material/texture missing')
        destination='/Game/T3B/NativeCandidates/OtherActorGEPaired/Run_'+run_id+'/M_Creature_SourceCull'
        check(not unreal.EditorAssetLibrary.does_asset_exist(destination),'Never overwrite actor material candidate')
        material=unreal.EditorAssetLibrary.duplicate_asset(parent.get_path_name(),destination)
        check(isinstance(material,unreal.Material),'Actor material duplicate failed');material.set_editor_property('two_sided',False)
        unreal.EditorAssetLibrary.set_metadata_tag(material,'T3BMaterialSignature','same_GE_creature_source_cull_'+sha(proof_path))
        unreal.MaterialEditingLibrary.recompile_material(material)
        check(unreal.EditorAssetLibrary.save_loaded_asset(material,False),'Actor material save failed')
        package=project/'Content'/destination.removeprefix('/Game/');package=package.with_suffix('.uasset')
        check(package.is_file(),'Saved actor material package absent')
        check(material.get_editor_property('blend_mode')==unreal.BlendMode.BLEND_TRANSLUCENT and material.get_editor_property('shading_model')==unreal.MaterialShadingModel.MSM_UNLIT,'Original blend/unlit material changed')
        nodes=list(unreal.MaterialEditingLibrary.get_material_expressions(material))
        samples=[n for n in nodes if isinstance(n,unreal.MaterialExpressionTextureSample)]
        check(len(samples)==1 and samples[0].get_editor_property('texture')==tex,'Actual material uses another texture')
        check(samples[0].get_editor_property('sampler_type')==unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR,'Expected linear original texture sampling')
        check(tex.get_editor_property('srgb')is False,'Original actor texture is not linear')
        png=folder/'actual_other_actor_texture.png';task=unreal.AssetExportTask()
        for prop,value in dict(object=tex,exporter=unreal.TextureExporterPNG(),filename=str(png),automated=True,prompt=False,replace_identical=False).items():task.set_editor_property(prop,value)
        check(unreal.Exporter.run_asset_export_task(task)and png.is_file(),'Actor Texture2D Source export failed')
        self.identity=dict(runtime_proof=identity(proof_path),input=identity(source),helper_sha256=sha(Path(__file__)),frames=[],
            source_material_recipe=recipe,material=dict(asset=material.get_path_name(),parent_asset=parent.get_path_name(),two_sided=material.get_editor_property('two_sided'),
            blend_mode=str(material.get_editor_property('blend_mode')),shading_model=str(material.get_editor_property('shading_model')),texture_asset=tex.get_path_name()),
            created_material_package=dict(file=str(package),bytes=package.stat().st_size,sha256=sha(package)),texture=dict(**identity(png),srgb=False,source_rgba_sha256=material_id),
            original_timing_verified=False,source_translucent_main_depth_equivalence=False)
        for i in range(28):
            actor=sub.spawn_actor_from_class(unreal.DynamicMeshActor,unreal.Vector(),unreal.Rotator(),True);comp=actor.get_dynamic_mesh_component()
            comp.set_material(0,material);comp.set_vertex_color_space_transform_mode(unreal.DynamicMeshVertexColorTransformMode.NO_TRANSFORM)
            comp.set_translucent_sort_priority(-100+i);comp.set_visibility(False,True);capture.show_only_actor_components(actor,False)
            self.entries.append(dict(actor=actor,component=comp,mesh=comp.get_dynamic_mesh(),built=False))
        # The entire creature precedes both Aya and gun in all these exact captures.
        for f,wf in zip(self.source['frames'],weapon['frames']):
            bf=body['frames'][wf['body_frame_index']];draws=self.source['draws'][f['first_draw']:f['first_draw']+28]
            last=max((d['register_record'],d['register_word'])for d in draws)
            following=body['draws'][bf['first_draw']:bf['first_draw']+106]+[weapon['draws'][wf['first_draw']]]
            check(all(last<(d['register_record'],d['register_word'])for d in following),'Interleaved actor order needs another replay layout')

    def select_sample(self,sample):
        check(sample==self.current+1,'Actor samples must follow original captured order')
        f=self.source['frames'][sample];draws=self.source['draws'][f['first_draw']:f['first_draw']+28]
        frame=dict(sample=sample,capture=f['capture'],draws=[])
        Q=unreal.GeometryScript_MeshQueries;L=unreal.GeometryScript_List;E=unreal.GeometryScript_MeshEdits;N=unreal.GeometryScript_Normals;C=unreal.GeometryScript_VertexColors
        with self.paths['components'].open('ab')as output,self.paths['indices'].open('ab')as indices,self.paths['uv'].open('ab')as uv:
            for entry,d in zip(self.entries,draws):
                count=d['vertex_count'];first=d['first_output_vertex'];rows=list(struct.iter_unpack('<6f4B3Bx',self.data[first*32:(first+count)*32]));tex=list(struct.iter_unpack('<2f',self.uv[first*8:(first+count)*8]))
                points=[unreal.Vector((v[0]-self.origin[0])*self.units*100,(v[2]-self.origin[2])*self.units*100,(v[1]-self.origin[1])*self.units*100)for v in rows]
                normals=[unreal.Vector(v[3],v[5],v[4])for v in rows];colors=[unreal.LinearColor(*[c/255 for c in v[6:10]])for v in rows];mesh=entry['mesh']
                if not entry['built']:
                    buffers=unreal.GeometryScriptSimpleMeshBuffers()
                    for prop,value in dict(vertices=points,normals=normals,uv0=[unreal.Vector2D(*v)for v in tex],vertex_colors=colors,triangles=[unreal.IntVector(k,k+1,k+2)for k in range(0,count,3)]).items():buffers.set_editor_property(prop,value)
                    E.append_buffers_to_mesh(mesh,buffers,0,False);entry['built']=True
                else:
                    E.set_all_mesh_vertex_positions(mesh,L.convert_array_to_vector_list(points));N.set_mesh_per_vertex_normals(mesh,L.convert_array_to_vector_list(normals));C.set_mesh_per_vertex_colors(mesh,L.convert_array_to_color_list(colors))
                check(Q.get_vertex_count(mesh)==count and Q.get_num_triangle_i_ds(mesh)==count//3,'Actor component topology differs')
                _,pl,pg=Q.get_all_vertex_positions(mesh,False);_,cl,cv,cg=C.get_mesh_per_vertex_colors(mesh,False);_,nl,nv,ng=N.get_mesh_per_vertex_normals(mesh,False)
                check(cv and nv and not(pg or cg or ng),'Actor component attribute readback failed')
                begin=output.tell();ix_at=indices.tell();uv_at=uv.tell()
                for p,c,n in zip(L.convert_vector_list_to_array(pl),L.convert_color_list_to_array(cl),L.convert_vector_list_to_array(nl)):output.write(struct.pack('<3d4f3f',p.x,p.y,p.z,c.r,c.g,c.b,c.a,n.x,n.y,n.z))
                for ti in range(count//3):
                    t,valid=Q.get_triangle_indices(mesh,ti);check(valid,'Missing actor triangle');indices.write(struct.pack('<3I',t.x,t.y,t.z))
                    a,b,c,valid=Q.get_triangle_u_vs(mesh,0,ti);check(valid,'Missing actor UV')
                    for v in(a,b,c):uv.write(struct.pack('<2f',v.x,v.y))
                comp=entry['component'];frame['draws'].append(dict(packet=d['packet'],vertices=count,readback_byte_offset=begin,index_byte_offset=ix_at,uv_byte_offset=uv_at,
                    material_asset=comp.get_material(0).get_path_name(),actual_sort_priority=comp.get_editor_property('translucency_sort_priority'),component_transform=transform(comp.get_world_transform())))
        self.identity['frames'].append(frame);self.current=sample
        for k,p in self.paths.items():self.identity[k]=identity(p)

    def show(self,visible):
        for e in self.entries:e['component'].set_visibility(visible,True)
