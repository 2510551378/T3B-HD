"""Read-only original calibration SourceModel/RenderData corner color probe."""
import hashlib,json,os,traceback
from pathlib import Path
import unreal

P=Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
INPUT=Path(os.environ['T3B_LIGHT_PROBE_INPUT']);O=Path(os.environ['T3B_LIGHT_PROBE_REPORT'])
R={'schema':'aya-lighting-color-corner-probe/v1','passed':False,'copies':[]}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check(ok,msg):
    if not ok:raise RuntimeError(msg)
def vec(v):return [v.x,v.y,v.z]
def color(v):return [v.r,v.g,v.b,v.a]
def inventory():return [{'file':str(p),'sha256':sha(p)}for p in sorted((P/'Content').rglob('*.uasset'))]


def main():
    r=json.loads(INPUT.read_text(encoding='utf-8'));check(r['passed'],'Only actual completed calibration input')
    R['protected_before']=inventory();R['input_sha256']=sha(INPUT)
    mesh=unreal.load_asset(next(m['asset']for m in r['meshes']if m['mode']=='ge_lit'))
    check(isinstance(mesh,unreal.StaticMesh),'Saved calibration mesh missing')
    R['asset']=mesh.get_path_name();Q=unreal.GeometryScript_MeshQueries
    nanite=mesh.get_editor_property('nanite_settings')
    R['actual_build_settings']=dict(nanite=str(nanite),nanite_enabled=nanite.get_editor_property('enabled'))
    try:
        models=mesh.get_editor_property('source_models')
        R['actual_build_settings'].update(lod0_build=str(models[0].get_editor_property('build_settings')),
            lod0_reduction=str(models[0].get_editor_property('reduction_settings')))
    except Exception as error:R['actual_build_settings']['source_model_settings_unavailable']=str(error)
    R['API_docs']=dict(copy=unreal.GeometryScript_AssetUtils.copy_mesh_from_static_mesh.__doc__,
                        colors=Q.get_triangle_vertex_colors.__doc__)
    O.write_text(json.dumps(R,indent=2)+'\n',encoding='utf-8')
    for name,kind in [('SourceModel',unreal.GeometryScriptLODType.SOURCE_MODEL),('RenderData',unreal.GeometryScriptLODType.RENDER_DATA)]:
        options=unreal.GeometryScriptCopyMeshFromAssetOptions();options.set_editor_property('apply_build_settings',False)
        lod=unreal.GeometryScriptMeshReadLOD();lod.set_editor_property('lod_type',kind);lod.set_editor_property('lod_index',0)
        dm=unreal.DynamicMesh();_,outcome=unreal.GeometryScript_AssetUtils.copy_mesh_from_static_mesh(mesh,dm,options,lod)
        check(outcome==unreal.GeometryScriptOutcomePins.SUCCESS,'Actual mesh copy failed')
        entry=dict(lod=name,triangles=[],vertex_count=Q.get_vertex_count(dm));R['copies'].append(entry)
        for i in range(Q.get_num_triangle_i_ds(dm)):
            tri,valid=Q.get_triangle_indices(dm,i)
            if not valid:continue
            indices=[tri.x,tri.y,tri.z];positions=[]
            for j in indices:
                value,valid=Q.get_vertex_position(dm,j);check(valid,'Invalid actual vertex ID');positions.append(vec(value))
            uv=Q.get_triangle_u_vs(dm,0,i);check(uv[-1],'Actual UV missing')
            _,a,b,c,valid=Q.get_triangle_vertex_colors(dm,i);check(valid,'Actual corner color missing')
            entry['triangles'].append(dict(id=i,positions_cm=positions,uvs=[[v.x,v.y]for v in uv[:3]],colors=[color(v)for v in (a,b,c)]))
        O.write_text(json.dumps(R,indent=2)+'\n',encoding='utf-8')
    check(R['protected_before']==inventory(),'Read-only probe changed saved packages')
    R.update(passed=True,all_packages_unchanged=True)


if __name__=='__main__':
    try:main()
    except Exception as e:R.update(error=str(e),traceback=traceback.format_exc());raise
    finally:
        R.update(process_id=os.getpid(),engine_version=unreal.SystemLibrary.get_engine_version(),script_sha256=sha(Path(__file__)))
        O.write_text(json.dumps(R,indent=2)+'\n',encoding='utf-8')
