"""Read-only saved-asset reload checks inside a second UE Python commandlet.

No import, asset-property setter, save, material compile or C++ game module is used.
Expected signatures come from the frozen successful creation report.
"""
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re

import unreal

PROJECT=Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
MANIFEST=PROJECT/'Content/SourceData/manifest.json'
OUTPUT=Path(os.environ['T3B_VERIFY_REPORT_PATH']).resolve()
FROZEN=Path(os.environ['T3B_VERIFY_IMPORT_REPORT']).resolve()
if not OUTPUT.is_relative_to(PROJECT/'Validation'):
    raise RuntimeError('Reload report must remain in project Validation')
ASSETS=unreal.EditorAssetLibrary
LIB=unreal.MaterialEditingLibrary
TEXT_GRAPH={}


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def must(condition,message):
    if not condition:raise RuntimeError(message)


def path_name(obj):return obj.get_path_name()if obj is not None else None


def close(actual,expected,label):
    must(math.isclose(float(actual),float(expected),rel_tol=2e-6,abs_tol=1e-7),f'{label}: {actual} != {expected}')


def package_fingerprints(frozen):
    result=[]
    for item in frozen['saved_assets']:
        path=Path(item['file']).resolve()
        must(path.is_relative_to(PROJECT/'Content'),f'Frozen asset outside shared Content: {path}')
        must(path.is_file(),f'Frozen saved package missing: {path}')
        current={'file':str(path),'bytes':path.stat().st_size,'sha256':digest(path)}
        must(current['bytes']==item['bytes']and current['sha256']==item['sha256'],f'Frozen package changed: {path}')
        result.append(current)
    must(len(result)==161,'Expected frozen76+84+1 packages')
    return result


def verify_texture(item):
    asset=ASSETS.load_asset(item['asset'])
    must(isinstance(asset,unreal.Texture2D),f'Expected Texture2D: {item["asset"]}')
    width,height=asset.blueprint_get_size_x(),asset.blueprint_get_size_y()
    must(width==item['width']and height==item['height'],f'Texture dimensions differ: {item["asset"]}')
    must(ASSETS.get_metadata_tag(asset,'T3BSourceRGBA')==item['rgba_sha256'],f'Texture provenance differs: {item["asset"]}')
    expected={'srgb':False,'compression_no_alpha':False,
        'compression_settings':unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP,
        'mip_gen_settings':unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS,
        'filter':unreal.TextureFilter.TF_BILINEAR,'address_x':unreal.TextureAddress.TA_WRAP,'address_y':unreal.TextureAddress.TA_WRAP}
    settings={}
    for key,value in expected.items():
        actual=asset.get_editor_property(key);must(actual==value,f'Texture {item["asset"]} property {key} differs: {actual} != {value}')
        settings[key]=str(actual)
    source=PROJECT/'Content/SourceData'/item['file']
    must(digest(source)==item['container']['sha256'],f'Staged original PNG changed: {source}')
    return {'asset':item['asset'],'class':asset.get_class().get_path_name(),'dimensions':[width,height],
        'source_RGBA_tag':item['rgba_sha256'],'settings':settings,'passed':True}


def export_graph_text(material):
    # FExpressionInput is protected from direct Python access in this build.
    # The stock read-only UObjectExporterT3D exports serialized properties,
    # including these masks, into our new verification-run directory only.
    directory=OUTPUT.parent/'material_graph_text';directory.mkdir(exist_ok=True)
    filename=directory/(material.get_name()+'.T3D')
    task=unreal.AssetExportTask()
    task.set_editor_property('object',material)
    task.set_editor_property('exporter',unreal.ObjectExporterT3D())
    task.set_editor_property('filename',str(filename))
    task.set_editor_property('automated',True)
    task.set_editor_property('prompt',False)
    must(unreal.Exporter.run_asset_export_task(task),f'Read-only graph text export failed: {material.get_name()}')
    raw=filename.read_bytes()
    text=raw.decode('utf-16')if raw.startswith((b'\xff\xfe',b'\xfe\xff'))else raw.decode('utf-8-sig')
    stack=[];properties={}
    for line in text.splitlines():
        line=line.strip()
        if line.startswith('Begin Object'):
            name=re.search(r'\bName="([^"]+)"',line);stack.append(name.group(1)if name else None)
        elif line=='End Object':
            if stack:stack.pop()
        elif stack and stack[-1]and '='in line:
            key,value=line.split('=',1);properties.setdefault(stack[-1],{})[key]=value
    TEXT_GRAPH[material.get_path_name()]=properties
    return {'file':str(filename),'sha256':sha256_bytes(raw),'node_property_blocks':len(properties)}


def sha256_bytes(raw):return hashlib.sha256(raw).hexdigest()


def connection(node,field):
    """Official query API for edges; object text for protected channel masks."""
    material=node.get_outer()
    names=list(LIB.get_material_expression_input_names(node));inputs=list(LIB.get_inputs_for_material_expression(material,node))
    def clean(name):return re.sub(r'[^a-z0-9]','',str(name).lower())
    aliases={'coordinates':['uvs','coordinates'],'a_greater_than_b':['agreaterthanb'],
        'a_equals_b':['aequalsb'],'a_less_than_b':['alessthanb']}
    # Symbol comparisons must remain distinct even though punctuation removal
    # maps all three to 'ab'. Prefer exact display names before aliases.
    displays={'a_greater_than_b':['A > B'],'a_equals_b':['A == B'],'a_less_than_b':['A < B']}
    matching=[i for i,name in enumerate(names)if str(name).replace(' ','')in [n.replace(' ','')for n in displays.get(field,[])]]
    if not matching:
        matching=[i for i,name in enumerate(names)if clean(name)in aliases.get(field,[clean(field)])]
    must(len(matching)==1,f'Cannot identify official input pin {node.get_name()}.{field}: {names}')
    expression=inputs[matching[0]]
    property_name={'a_greater_than_b':'AGreaterThanB','a_equals_b':'AEqualsB','a_less_than_b':'ALessThanB','coordinates':'Coordinates'}.get(field,field.upper())
    properties=TEXT_GRAPH[material.get_path_name()].get(node.get_name(),{})
    serialized=properties.get(property_name,'')
    if expression is not None:
        must(expression.get_name()in serialized,f'Official edge and serialized object property differ: {node.get_name()}.{property_name}: {serialized}')
    def number(name):
        match=re.search(r'\b'+name+r'=(-?\d+)',serialized);return int(match.group(1))if match else 0
    return expression,{'source':path_name(expression),'output_index':number('OutputIndex'),
        'mask':[number(k)for k in ['Mask','MaskR','MaskG','MaskB','MaskA']],
        'serialized_input':serialized,'official_input_name':str(names[matching[0]])}


def edge(node,field,source,kind='default'):
    actual,evidence=connection(node,field)
    must(actual==source,f'Graph edge {node.get_name()}.{field} != {path_name(source)}')
    if kind=='RGB':must(evidence['mask']==[1,1,1,1,0],f'RGB output mask differs: {evidence}')
    elif kind=='A':must(evidence['mask']==[1,0,0,0,1],f'Alpha output mask differs: {evidence}')
    elif isinstance(source,unreal.MaterialExpressionConstant2Vector):must(evidence['mask']==[1,1,1,0,0],f'UV offset RG mask differs: {evidence}')
    else:must(evidence['mask'][0]==0,f'Unexpected channel mask on scalar/vector graph edge: {evidence}')
    return evidence


def verify_material(item,signatures):
    material=ASSETS.load_asset(item['asset'])
    must(isinstance(material,unreal.Material),f'Expected Material: {item["asset"]}')
    signature=ASSETS.get_metadata_tag(material,'T3BMaterialSignature')
    must(signature==signatures[item['asset']],f'Frozen material recipe metadata differs: {item["asset"]}')
    blend=bool(item['blend']);masked=bool(item.get('alpha_test',True))and not blend
    expected_blend=unreal.BlendMode.BLEND_TRANSLUCENT if blend else unreal.BlendMode.BLEND_MASKED if masked else unreal.BlendMode.BLEND_OPAQUE
    must(material.get_editor_property('blend_mode')==expected_blend,f'Blend mode differs: {item["asset"]}')
    must(material.get_editor_property('two_sided')==(not bool(item['cull'])),f'Cull/two-sided differs: {item["asset"]}')
    must(material.get_editor_property('shading_model')==unreal.MaterialShadingModel.MSM_UNLIT,f'Expected unlit baseline: {item["asset"]}')
    close(material.get_editor_property('opacity_mask_clip_value'),.5,'Opacity mask clip')
    nodes=list(LIB.get_material_expressions(material))
    text_evidence=export_graph_text(material)
    def one(cls):
        matches=[n for n in nodes if isinstance(n,cls)]
        must(len(matches)==1,f'Expected exactly one{cls} in{item["asset"]}, got{len(matches)}')
        return matches[0]
    texture=one(unreal.MaterialExpressionTextureSample)
    uv=one(unreal.MaterialExpressionTextureCoordinate)
    offset=one(unreal.MaterialExpressionConstant2Vector)
    add=one(unreal.MaterialExpressionAdd)
    vertex=one(unreal.MaterialExpressionVertexColor)
    must(path_name(texture.get_editor_property('texture'))==item['texture_asset'],f'Texture reference differs: {item["asset"]}')
    must(texture.get_editor_property('sampler_type')==unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR,'Expected linear-color texture sampler')
    must(texture.get_editor_property('sampler_source')==unreal.SamplerSourceMode.SSM_FROM_TEXTURE_ASSET,'Expected texture-asset sampler source')
    close(uv.get_editor_property('u_tiling'),item['su'],'UV U scale');close(uv.get_editor_property('v_tiling'),item['sv'],'UV V scale')
    close(offset.get_editor_property('r'),item['ou'],'UV U offset');close(offset.get_editor_property('g'),item['ov'],'UV V offset')
    must(uv.get_editor_property('coordinate_index')==0,'Expected original UV0, no inferred flip')
    evidence={'UV_add_A':edge(add,'a',uv),'UV_add_B':edge(add,'b',offset),'texture_coordinates':edge(texture,'coordinates',add)}
    emissive=LIB.get_material_property_input_node(material,unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    must(isinstance(emissive,unreal.MaterialExpressionMultiply),'Emissive must be color*rgb_scale')
    rgb,_=connection(emissive,'a');scale,_=connection(emissive,'b')
    must(isinstance(rgb,unreal.MaterialExpressionMultiply)and isinstance(scale,unreal.MaterialExpressionConstant),'RGB scale graph differs')
    close(scale.get_editor_property('r'),item['rgb_scale'],'RGB scale')
    evidence.update(emissive_A=edge(emissive,'a',rgb),emissive_B=edge(emissive,'b',scale),rgb_A=edge(rgb,'a',texture,'RGB'),rgb_B=edge(rgb,'b',vertex,'RGB'))
    alpha_nodes=[]
    for node in nodes:
        if isinstance(node,unreal.MaterialExpressionMultiply):
            a,_=connection(node,'a');b,_=connection(node,'b')
            if a==texture and b==vertex and node!=rgb:alpha_nodes.append(node)
    must(len(alpha_nodes)==1,'Expected one textureAlpha*vertexAlpha node')
    alpha=alpha_nodes[0];evidence.update(alpha_A=edge(alpha,'a',texture,'A'),alpha_B=edge(alpha,'b',vertex,'A'))
    test=None
    if item.get('alpha_test',True):
        test=one(unreal.MaterialExpressionIf)
        close(test.get_editor_property('equals_threshold'),0,'Strict alpha test equals threshold')
        reference,_=connection(test,'b');greater,_=connection(test,'a_greater_than_b')
        equal,_=connection(test,'a_equals_b');less,_=connection(test,'a_less_than_b')
        must(all(isinstance(n,unreal.MaterialExpressionConstant)for n in [reference,greater,equal,less]),'Alpha test constant type differs')
        close(reference.get_editor_property('r'),item['alpha_ref']/255.,'Alpha reference')
        close(greater.get_editor_property('r'),1,'Alpha greater result');close(equal.get_editor_property('r'),0,'Alpha equal result');close(less.get_editor_property('r'),0,'Alpha less result')
        evidence.update(test_A=edge(test,'a',alpha),test_B=edge(test,'b',reference),test_greater=edge(test,'a_greater_than_b',greater),
            test_equal=edge(test,'a_equals_b',equal),test_less=edge(test,'a_less_than_b',less))
    opacity=LIB.get_material_property_input_node(material,unreal.MaterialProperty.MP_OPACITY)
    mask=LIB.get_material_property_input_node(material,unreal.MaterialProperty.MP_OPACITY_MASK)
    if masked:
        must(mask==test and opacity is None,'Masked alpha output property differs')
    elif blend:
        must(mask is None,'Translucent baseline must not masquerade as masked')
        if test:
            must(isinstance(opacity,unreal.MaterialExpressionMultiply),'Translucent opacity must multiply alpha and strict test')
            evidence.update(opacity_A=edge(opacity,'a',alpha),opacity_B=edge(opacity,'b',test))
        else:must(opacity==alpha,'Translucent alpha output differs')
    else:must(mask is None and opacity is None,'Opaque material has unexpected alpha output')
    # Independently record official query-API connections too, to make the
    # reflected property checks auditable without depending on node layout.
    graph=[]
    for node in nodes:
        names=list(LIB.get_material_expression_input_names(node));inputs=list(LIB.get_inputs_for_material_expression(material,node))
        must(len(names)==len(inputs),'Official graph query pin/node arrays differ')
        graph.append({'node':node.get_path_name(),'class':node.get_class().get_name(),
            'inputs':{str(name):path_name(source)for name,source in zip(names,inputs)}})
    return {'asset':item['asset'],'class':material.get_class().get_path_name(),'recipe_signature':signature,'blend_mode':str(expected_blend),
        'two_sided':not bool(item['cull']),'UV_scale':[item['su'],item['sv']],'UV_offset':[item['ou'],item['ov']],
        'alpha_reference':item['alpha_ref'],'emissive_node':path_name(emissive),'opacity_node':path_name(opacity),'opacity_mask_node':path_name(mask),
        'checked_graph_edges':evidence,'graph_nodes':graph,'read_only_object_text':text_evidence,'passed':True}


def main():
    frozen=json.loads(FROZEN.read_text(encoding='utf-8'));manifest=json.loads(MANIFEST.read_text(encoding='utf-8'))
    must(frozen['asset_creation_completed']and frozen['run_id']=='0fac54502ca140d4accffa2e5a7bc618','Expected frozen successful import run')
    must(frozen['manifest_sha256']==digest(MANIFEST),'Current source manifest differs from frozen import')
    before=package_fingerprints(frozen)
    textures=[verify_texture(item)for item in manifest['textures']]
    items=manifest['scene']['materials']+[item for actor in manifest['actors']for item in actor['materials']]
    materials=[verify_material(item,frozen['material_recipe_signatures'])for item in items]
    registry=unreal.AssetRegistryHelpers.get_asset_registry()
    registry.scan_paths_synchronous(['/Game/T3B'],True)
    options=unreal.AssetRegistryDependencyOptions()
    for field in ['include_soft_package_references','include_hard_package_references','include_game_package_references','include_editor_only_package_references']:
        # Query options are transient helper values, never asset properties.
        options.set_editor_property(field,True)
    dependencies=[]
    packages=[item['package']for item in frozen['saved_assets']]
    for package in packages:
        refs=[str(x)for x in registry.get_dependencies(package,options)]
        non_script=[r for r in refs if not r.startswith('/Script/')]
        for reference in non_script:must(ASSETS.does_asset_exist(reference),f'Missing saved-package dependency {package} -> {reference}')
        dependencies.append({'package':package,'dependencies':refs,'non_script_package_references_resolve':True,
            'script_packages':[r for r in refs if r.startswith('/Script/')]})
    world=unreal.EditorLoadingAndSavingUtils.load_map(frozen['map'])
    must(isinstance(world,unreal.World),'Saved map did not reload as World')
    actors=list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors())
    actor_rows=[{'actor':a.get_path_name(),'class':a.get_class().get_path_name()}for a in actors]
    internal_types=(unreal.WorldSettings,unreal.Brush,unreal.LevelScriptActor)
    unexpected=[a for a in actors if not isinstance(a,internal_types)]
    must(not unexpected,'Expected empty replay map; found placed gameplay/content actors')
    after=package_fingerprints(frozen);must(before==after,'Read-only UE reload altered saved source packages')
    return {'schema':'t3b-ue-saved-assets-reload/v1','passed':True,'frozen_import_report':str(FROZEN),'frozen_import_report_sha256':digest(FROZEN),
        'frozen_import_run_id':frozen['run_id'],'manifest_sha256':digest(MANIFEST),'textures_reloaded':len(textures),'materials_reloaded':len(materials),
        'map_reloaded':frozen['map'],'map_class':world.get_class().get_path_name(),'map_actors':actor_rows,'empty_content_map':True,
        'package_files_unchanged':True,'package_files_checked':len(after),'textures':textures,'materials':materials,'package_dependencies':dependencies,
        'unsupported_render_states':frozen['unsupported_render_states'],'ue_render_verified':False,'ue_cpp_build_executed':False,'ue_gameplay_executed':False,
        'scope':'Second-process on-disk reload, reflected texture/material settings/graph and package-reference existence; NullRHI, no pixel/shader runtime validation',
        'limits':['NullRHI does not verify texture GPU pixels, shader rendering, color/tonemapping, winding or transparency sorting.',
            'Source blended main-pass depth-write remains unsupported by the baseline material path.',
            'Empty map reload does not instantiate T3B C++ source replay, skeletal importer or gameplay.',
            'Script-package dependencies are recorded; engine loads them normally. Non-script package references are checked against the asset registry.']}


if __name__=='__main__':
    started=datetime.now(timezone.utc).isoformat();result={'schema':'t3b-ue-saved-assets-reload/v1','passed':False}
    try:result=main()
    except Exception as error:
        result['error']=str(error)
        raise
    finally:
        result.update(run_id=os.environ.get('T3B_VERIFY_RUN_ID'),process_id=os.getpid(),started_utc=started,
            finished_utc=datetime.now(timezone.utc).isoformat(),project_file=unreal.Paths.get_project_file_path(),
            engine_version=unreal.SystemLibrary.get_engine_version(),command_line=unreal.SystemLibrary.get_command_line(),
            verifier_sha256=digest(Path(__file__)),read_only_asset_reload=True)
        OUTPUT.parent.mkdir(parents=True,exist_ok=True);OUTPUT.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
