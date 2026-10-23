"""Read-only actual animation settings and data-model clock; no asset edits."""
import hashlib,json,os,traceback
from pathlib import Path
import unreal
P=Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve();O=Path(os.environ['T3B_NATIVE_REPORT_PATH']);R={'passed':False,'asset_writes_performed':False}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def prop(o,k):
    try:
        v=o.get_editor_property(k)
        if isinstance(v,(float,int,bool,str)):return v
        if isinstance(v,unreal.Object):return {'asset':v.get_path_name(),'class':v.get_class().get_path_name()}
        return str(v)
    except Exception as e:return {'unavailable':str(e)}
try:
    source=json.loads(Path(os.environ['T3B_NATIVE_SAVED_REPORT']).read_text(encoding='utf-8'));old=json.loads((P/'Validation/asset_import_runs/0fac54502ca140d4accffa2e5a7bc618/ue_editor_asset_creation.json').read_text(encoding='utf-8'))
    for i in source['saved_native_packages']+old['saved_assets']:assert sha(Path(i['file']))==i['sha256']
    anim=unreal.load_asset(source['animations'][0]['asset']);R['animation']=anim.get_path_name()
    R['sequence_properties']={k:prop(anim,k)for k in ['bone_compression_settings','curve_compression_settings','variable_frame_stripping_settings','allow_frame_stripping','compression_error_threshold_scale','interpolation','use_raw_data_only','platform_target_frame_rate']}
    model=anim.get_editor_property('data_model_interface');rate=model.get_frame_rate();num=rate.numerator;den=rate.denominator
    times=json.loads((P.parent/'psp_parse/out/AYA_NATIVE_GLTF_20261020/provenance.json').read_text(encoding='utf-8'))['actual_times_seconds'];keys=model.get_number_of_keys()
    clock=[{'index':i,'original_time_seconds':t,'native_uniform_key_time_seconds':i*den/num,'delta_seconds':i*den/num-t}for i,t in enumerate(times)]
    R['clock']={'numerator':num,'denominator':den,'keys':keys,'frames':model.get_number_of_frames(),'length_seconds':model.get_play_length(),'max_key_time_absolute_delta_seconds':max(abs(x['delta_seconds'])for x in clock),'key_times':clock}
    bone=anim.get_editor_property('bone_compression_settings');R['bone_compression_settings']={k:prop(bone,k)for k in ['error_threshold','force_below_threshold']};R['bone_compression_codecs']=[]
    for codec in bone.get_editor_property('codecs'):
        R['bone_compression_codecs'].append({'asset':codec.get_path_name(),'class':codec.get_class().get_path_name(),'settings':{k:prop(codec,k)for k in ['compression_level','error_threshold','default_virtual_vertex_distance','safe_virtual_vertex_distance','rotation_format','translation_format','scale_format']}})
    R['ForceEvalRawData_console_value']=unreal.SystemLibrary.get_console_variable_int_value('a.ForceEvalRawData')
    R['branch_limit']='GetBonePose uses private ShouldUseRawDataForPoseExtraction; actual runtime branch cannot be established from settings alone. Default cvar0 does not prove compressed data was used. Compression settings are evidence of configuration, not attribution of measured error.'
    R['next_controlled_experiment']='In an isolated new run, force a.ForceEvalRawData=1 and repeat same SourceModel points/times/geometry; compare paired outputs. This changes only process-local sampling policy, not any source asset or reference.'
    for i in source['saved_native_packages']+old['saved_assets']:assert sha(Path(i['file']))==i['sha256']
    R['previous161_and_native3_packages_unchanged']=True;R['passed']=True
except Exception as e:R['error']=str(e);R['traceback']=traceback.format_exc();raise
finally:
    R.update(run_id=os.environ['T3B_NATIVE_RUN_ID'],process_id=os.getpid(),script_sha256=sha(Path(__file__)),engine_version=unreal.SystemLibrary.get_engine_version())
    O.write_text(json.dumps(R,indent=2)+'\n',encoding='utf-8')