"""Real UE module/RHI validation launcher; never launches against a missing DLL."""
import argparse,hashlib,json,os,py_compile,subprocess,uuid
from pathlib import Path


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check(ok,reason):
    if not ok:raise ValueError(reason)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--engine-root',type=Path,required=True)
    p.add_argument('--bundle',type=Path,required=True);a=p.parse_args();project=Path(__file__).resolve().parents[1]
    dll=project/'Binaries/Win64/UnrealEditor-T3BRemake.dll'
    check(dll.is_file(),'No compiled UE game module. Install approved dependencies and run actual UBT first.')
    exe=a.engine_root/'Engine/Binaries/Win64/UnrealEditor-Cmd.exe';check(exe.is_file(),'Explicit installed editor missing')
    producer=project/'Tools/capture_ge_ordered_pass.py';py_compile.compile(str(producer),doraise=True)
    run=uuid.uuid4().hex;out=project/'Validation/ue_ordered_ge_pass_runs'/run;out.mkdir(parents=True)
    script=out/'capture_ge_ordered_pass_executed.py';script.write_bytes(producer.read_bytes());report=out/'actual_ue_ge_pass.json'
    cmd=[str(exe),str(project/'T3BRemake.uproject'),'-run=pythonscript','-script='+str(script),'-unattended',
         '-AllowCommandletRendering','-RenderOffScreen','-d3d11','-nosplash','-nosound','-nop4','-NoCrashDialog','-UTF8Output','-stdout',
         '-FullStdOutLogOutput','-abslog='+str(out/'UnrealEditor-Cmd.log'),
         '-ini:Engine:[/Script/EngineSettings.GameMapsSettings]:GlobalDefaultGameMode=/Script/Engine.GameModeBase']
    files=sorted((project/'Source').rglob('*'))+sorted((project/'Shaders').rglob('*'))+[project/'T3BRemake.uproject']
    request=dict(run_id=run,command=cmd,bundle=dict(file=str(a.bundle.resolve()),sha256=sha(a.bundle)),script_sha256=sha(script),
                 actual_module=dict(file=str(dll),sha256=sha(dll)),current_source_inventory=[dict(file=str(f),sha256=sha(f))for f in files if f.is_file()],
                 source_inventory_scope='Current source at launch; actual UBT build evidence remains separately required.')
    (out/'request.json').write_text(json.dumps(request,indent=2)+'\n',encoding='utf-8')
    env=dict(os.environ,T3B_GE_PASS_REPORT=str(report),T3B_GE_PASS_BUNDLE=str(a.bundle.resolve()),T3B_GE_PASS_RUN=run)
    with(out/'stdout.log').open('wb')as stdout,(out/'stderr.log').open('wb')as stderr:
        process=subprocess.Popen(cmd,cwd=project,env=env,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt'else 0)
        (out/'process_started.json').write_text(json.dumps(dict(pid=process.pid,run_id=run))+'\n',encoding='utf-8')
        print(json.dumps(dict(pid=process.pid,run_id=run,folder=str(out))),flush=True);code=process.wait()
    (out/'process_completed.json').write_text(json.dumps(dict(pid=process.pid,exit_code=code))+'\n',encoding='utf-8')
    check(code==0,'Actual UE pass failed; preserved '+str(out));r=json.loads(report.read_text(encoding='utf-8'))
    check(r['passed']and r['process_id']==process.pid and r['script_sha256']==sha(script)and r['run_id']==run,'Incomplete actual run identity')
    check(r['all_original_packages_unchanged'],'Existing UE assets changed')
    for row in r['protected_packages_before']:check(sha(Path(row['file']))==row['sha256'],'Package changed after exit')
    # Acquisition is not original-pixel/occlusion acceptance. Independently compare
    # the submitted geometry, hidden controls and depth-mode PNGs after this run.
    print(json.dumps(dict(acquisition_passed=True,independent_render_acceptance_pending=True,report=str(report))),flush=True)


if __name__=='__main__':main()
