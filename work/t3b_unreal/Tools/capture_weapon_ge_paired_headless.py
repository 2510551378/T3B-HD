"""Retain hidden UE process ownership for the actual paired weapon experiment."""
import argparse,hashlib,json,os,py_compile,subprocess,uuid
from pathlib import Path


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check(ok,reason):
    if not ok:raise ValueError(reason)


def main():
    p=argparse.ArgumentParser();p.add_argument('--engine-root',type=Path,required=True)
    p.add_argument('--inputs',type=Path,required=True);p.add_argument('--body-runtime',type=Path,required=True)
    p.add_argument('--weapon-runtime',type=Path,required=True);p.add_argument('--reuse-material-report',type=Path)
    p.add_argument('--cameras',type=Path);p.add_argument('--street-snapshot',type=Path);p.add_argument('--street-series',type=Path);p.add_argument('--other-actor-runtime',type=Path);a=p.parse_args()
    check(not a.cameras or a.reuse_material_report,'Original camera mode must reuse the existing material')
    check(not a.street_snapshot or a.cameras,'Street snapshot requires original camera mode')
    check(not a.street_series or a.cameras,'Street series requires original camera mode')
    check(not(a.street_snapshot and a.street_series),'Choose snapshot or series, not both')
    check(not a.other_actor_runtime or(a.street_series and a.cameras and a.reuse_material_report),'Same-capture actor requires camera/street series and existing weapon material')
    for path in (a.inputs,a.body_runtime,a.weapon_runtime,a.reuse_material_report,a.cameras,a.street_snapshot,a.street_series,a.other_actor_runtime):
        if path is not None:check(path.is_file(),'Missing explicit input: '+str(path))
    project=Path(__file__).resolve().parents[1];producer=project/'Tools/capture_weapon_ge_paired.py'
    py_compile.compile(str(producer),doraise=True)
    exe=a.engine_root/'Engine/Binaries/Win64/UnrealEditor-Cmd.exe';check(exe.is_file(),'Explicit engine missing')
    run=uuid.uuid4().hex;folder=project/('Validation/other_actor_paired_ue_runs' if a.other_actor_runtime else 'Validation/paired_street_series_ue_runs' if a.street_series else 'Validation/paired_street_ue_runs' if a.street_snapshot else 'Validation/original_camera_ue_runs' if a.cameras else 'Validation/weapon_ge_paired_runs')/run;folder.mkdir(parents=True)
    script=folder/'capture_weapon_ge_paired_executed.py';script.write_bytes(producer.read_bytes());report=folder/'ue_weapon_ge_paired.json'
    cmd=[str(exe),str(project/'T3BNativeProbe.uproject'),'-run=pythonscript','-script='+str(script),'-unattended',
         '-AllowCommandletRendering','-RenderOffScreen','-d3d11','-nosplash','-nosound','-nop4','-NoCrashDialog','-UTF8Output','-stdout',
         '-FullStdOutLogOutput','-abslog='+str(folder/'UnrealEditor-Cmd.log'),
         '-ini:Engine:[/Script/EngineSettings.GameMapsSettings]:GlobalDefaultGameMode=/Script/Engine.GameModeBase']
    request=dict(run_id=run,command=cmd,script_sha256=sha(script),inputs=str(a.inputs.resolve()),inputs_sha256=sha(a.inputs),
                 body_runtime=str(a.body_runtime.resolve()),body_runtime_sha256=sha(a.body_runtime),
                 weapon_runtime=str(a.weapon_runtime.resolve()),weapon_runtime_sha256=sha(a.weapon_runtime))
    if a.cameras:
        helper=project/'Tools/ge_source_camera_capture.py';py_compile.compile(str(helper),doraise=True)
        frozen_helper=folder/helper.name;frozen_helper.write_bytes(helper.read_bytes())
        request.update(cameras=dict(file=str(a.cameras.resolve()),sha256=sha(a.cameras)),
                       camera_helper=dict(file=str(frozen_helper),sha256=sha(frozen_helper)))
    street_source=a.street_series or a.street_snapshot
    if street_source:
        street_helper=project/('Tools/ge_paired_street_series_capture.py'if a.street_series else'Tools/ge_paired_street_capture.py');py_compile.compile(str(street_helper),doraise=True)
        frozen_street=folder/street_helper.name;frozen_street.write_bytes(street_helper.read_bytes())
        request['street_series'if a.street_series else'street_snapshot']=dict(file=str(street_source.resolve()),sha256=sha(street_source))
        request['street_helper']=dict(file=str(frozen_street),sha256=sha(frozen_street))
    if a.other_actor_runtime:
        actor_helper=project/'Tools/ge_other_actor_capture.py';py_compile.compile(str(actor_helper),doraise=True)
        frozen_actor=folder/actor_helper.name;frozen_actor.write_bytes(actor_helper.read_bytes())
        request.update(other_actor_runtime=dict(file=str(a.other_actor_runtime.resolve()),sha256=sha(a.other_actor_runtime)),
                       other_actor_helper=dict(file=str(frozen_actor),sha256=sha(frozen_actor)))
    (folder/'request.json').write_text(json.dumps(request,indent=2)+'\n',encoding='utf-8')
    env=dict(os.environ,T3B_PAIR_REPORT=str(report),T3B_PAIR_INPUT=str(a.inputs.resolve()),T3B_PAIR_BODY_RUNTIME=str(a.body_runtime.resolve()),
             T3B_PAIR_WEAPON_RUNTIME=str(a.weapon_runtime.resolve()),T3B_PAIR_RUN=run)
    if a.reuse_material_report:env['T3B_PAIR_REUSE_MATERIAL']=str(a.reuse_material_report.resolve())
    if a.other_actor_runtime:env.update(T3B_PAIR_OTHER_ACTOR_RUNTIME=str(a.other_actor_runtime.resolve()),T3B_PAIR_OTHER_ACTOR_HELPER=str(frozen_actor))
    if a.cameras:env.update(T3B_PAIR_CAMERAS=str(a.cameras.resolve()),T3B_PAIR_CAMERA_HELPER=str(frozen_helper))
    if street_source:env.update(T3B_PAIR_STREET=str(street_source.resolve()),T3B_PAIR_STREET_HELPER=str(frozen_street))
    with(folder/'stdout.log').open('wb')as stdout,(folder/'stderr.log').open('wb')as stderr:
        process=subprocess.Popen(cmd,cwd=project,env=env,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt'else 0)
        (folder/'process_started.json').write_text(json.dumps(dict(pid=process.pid,run_id=run))+'\n',encoding='utf-8')
        print(json.dumps(dict(pid=process.pid,run_id=run,folder=str(folder))),flush=True);code=process.wait()
    (folder/'process_completed.json').write_text(json.dumps(dict(pid=process.pid,exit_code=code))+'\n',encoding='utf-8')
    check(code==0,'UE failed; preserved '+str(folder));r=json.loads(report.read_text(encoding='utf-8'))
    check(r['passed']and r['process_id']==process.pid and r['run_id']==run and r['script_sha256']==sha(script),'Actual paired result incomplete')
    check(r['all_original_packages_unchanged']and len(r['new_packages'])==((0 if a.reuse_material_report else 1)+(1 if a.other_actor_runtime else 0)),'Unexpected source package changes')
    for item in r['protected_packages_before']:check(sha(Path(item['file']))==item['sha256'],'Protected package changed after exit')
    (folder/'verified.json').write_text(json.dumps(dict(passed=True,report_sha256=sha(report),pid=process.pid,run_id=run,
        same_dump_samples=len(r['samples']),original_main_depth_write_verified=False,muzzle_semantics_confirmed=False),indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=True,report=str(report))),flush=True)


if __name__=='__main__':main()
