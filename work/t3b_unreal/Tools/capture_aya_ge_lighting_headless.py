"""Hidden real-RHI static GE-lighting calibration; retain process until exit."""
import argparse,hashlib,json,os,subprocess,uuid,py_compile
from pathlib import Path


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check(ok,msg):
    if not ok:raise ValueError(msg)


def main():
    a=argparse.ArgumentParser();a.add_argument('--engine-root',type=Path,required=True);a.add_argument('--input',type=Path,required=True)
    a.add_argument('--reuse-report',type=Path);a.add_argument('--disable-nanite',action='store_true');a=a.parse_args()
    project=Path(__file__).resolve().parents[1];exe=a.engine_root/'Engine/Binaries/Win64/UnrealEditor-Cmd.exe'
    check(exe.is_file(),'Explicit installed UE missing')
    py_compile.compile(str(project/'Tools/capture_aya_ge_lighting.py'),doraise=True)
    run=uuid.uuid4().hex;folder=project/'Validation/ge_lighting_calibration_runs'/run;folder.mkdir(parents=True)
    script=folder/'capture_aya_ge_lighting_executed.py';script.write_bytes((project/'Tools/capture_aya_ge_lighting.py').read_bytes())
    report=folder/'ue_ge_lighting_calibration.json'
    cmd=[str(exe),str(project/'T3BNativeProbe.uproject'),'-run=pythonscript','-script='+str(script),'-unattended',
         '-AllowCommandletRendering','-RenderOffScreen','-d3d11','-nosplash','-nosound','-nop4','-NoCrashDialog','-UTF8Output','-stdout','-FullStdOutLogOutput',
         '-abslog='+str(folder/'UnrealEditor-Cmd.log'),'-ini:Engine:[/Script/EngineSettings.GameMapsSettings]:GlobalDefaultGameMode=/Script/Engine.GameModeBase']
    (folder/'request.json').write_text(json.dumps(dict(run_id=run,command=cmd,input=str(a.input),input_sha256=sha(a.input),script_sha256=sha(script)),indent=2)+'\n',encoding='utf-8')
    env=dict(os.environ,T3B_LIGHT_REPORT=str(report),T3B_LIGHT_INPUT=str(a.input.resolve()),T3B_LIGHT_RUN=run)
    if a.reuse_report:env['T3B_LIGHT_REUSE_REPORT']=str(a.reuse_report.resolve())
    if a.disable_nanite:
        check(a.reuse_report is not None,'Explicit measured Nanite control required')
        env['T3B_LIGHT_DISABLE_NANITE']='1'
    with (folder/'stdout.log').open('wb')as o,(folder/'stderr.log').open('wb')as e:
        p=subprocess.Popen(cmd,cwd=project,env=env,stdout=o,stderr=e,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt'else 0)
        (folder/'process_started.json').write_text(json.dumps(dict(pid=p.pid,run_id=run))+'\n',encoding='utf-8')
        print(json.dumps(dict(pid=p.pid,run_id=run,folder=str(folder))),flush=True)
        code=p.wait()
    (folder/'process_completed.json').write_text(json.dumps(dict(pid=p.pid,exit_code=code))+'\n',encoding='utf-8')
    check(code==0,'UE failed; preserved '+str(folder))
    r=json.loads(report.read_text(encoding='utf-8'));check(r['passed']and r['process_id']==p.pid and r['run_id']==run and r['script_sha256']==sha(script),'Fresh actual result mismatch')
    for i in r['protected_packages_before']:check(sha(Path(i['file']))==i['sha256'],'Protected package changed after exit')
    check(len(r['new_packages'])==(2 if a.disable_nanite or not a.reuse_report else 0),'Unexpected calibration asset additions')
    (folder/'verified.json').write_text(json.dumps(dict(passed=True,report_sha256=sha(report),run_id=run,pid=p.pid,
         protected_packages=len(r['protected_packages_before']),static_snapshot_only=True,original_pixels_verified=False),indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=True,report=str(report))),flush=True)


if __name__=='__main__':main()
