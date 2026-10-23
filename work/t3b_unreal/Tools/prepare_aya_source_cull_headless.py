"""Build then independently reload a default source-cull Aya mesh, hidden.

Uses an existing explicit UE installation; never installs software. Each process
keeps its handle until actual exit and writes its own immutable run directory.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid


def check(value,message):
    if not value:
        raise ValueError(message)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write(p,r):
    check(not p.exists(),'Refusing existing report '+str(p))
    p.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine-root',type=Path,required=True)
    parser.add_argument('--fulluv-report',type=Path,required=True)
    parser.add_argument('--cull-report',type=Path,required=True)
    parser.add_argument('--cull-independent-verification',type=Path,required=True)
    parser.add_argument('--existing-candidate',help='Explicit owned saved candidate to verify without creating another asset')
    a = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    exe = a.engine_root/'Engine/Binaries/Win64/UnrealEditor-Cmd.exe'
    check(exe.is_file(),'Explicit installed commandlet not found')
    fulluv = json.loads(a.fulluv_report.read_text(encoding='utf-8'))
    cull = json.loads(a.cull_report.read_text(encoding='utf-8'))
    verified = json.loads(a.cull_independent_verification.read_text(encoding='utf-8'))
    check(fulluv['passed'] and cull['passed'] and verified['passed'] and
          verified['report_sha256'] == sha(a.cull_report),'Actual source input verification missing')
    for item in fulluv['saved_native_packages'] + [cull['new_material_package']]:
        check(sha(Path(item['file'])) == item['sha256'],'Measured source package changed')
    run_id = uuid.uuid4().hex
    output = project/'Validation/native_source_cull_binding_runs'/run_id
    output.mkdir(parents=True)
    script = project/'Tools/prepare_aya_source_cull.py'
    frozen = output/'prepare_aya_source_cull_executed.py'
    frozen.write_bytes(script.read_bytes())
    inputs = [{'file':str(p.resolve()),'sha256':sha(p)} for p in
              (a.fulluv_report,a.cull_report,a.cull_independent_verification)]
    request = dict(run_id=run_id,source_mesh=fulluv['skeletal_meshes'][0]['asset'],
                   source_cull_material=cull['derived_material']['asset'],inputs=inputs,
                   destination=a.existing_candidate or '/Game/T3B/NativeCandidates/AyaSourceCull/Run_'+run_id+'/aya_source_cull')
    if a.existing_candidate:
        check(a.existing_candidate.startswith('/Game/T3B/NativeCandidates/AyaSourceCull/Run_') and
              a.existing_candidate.endswith('/aya_source_cull'),'Explicit candidate outside this tool namespace')
    reports = []
    modes = ('reload',) if a.existing_candidate else ('build','reload')
    for mode in modes:
        report = output/(mode+'_report.json')
        req = output/(mode+'_request.json')
        write(req,{**request,'mode':mode})
        command = [str(exe),str(project/'T3BNativeProbe.uproject'),'-run=pythonscript',
                   '-script='+str(frozen),'-unattended','-NullRHI','-nosplash','-nosound',
                   '-nop4','-NoCrashDialog','-UTF8Output','-stdout','-FullStdOutLogOutput',
                   '-abslog='+str(output/(mode+'_UnrealEditor.log')),
                   '-ini:Engine:[/Script/EngineSettings.GameMapsSettings]:GlobalDefaultGameMode=/Script/Engine.GameModeBase']
        env = dict(os.environ,T3B_CULL_BIND_OUTPUT=str(report),T3B_CULL_BIND_REQUEST=str(req))
        with (output/(mode+'_stdout.log')).open('wb') as stdout, (output/(mode+'_stderr.log')).open('wb') as stderr:
            process = subprocess.Popen(command,cwd=project,env=env,stdout=stdout,stderr=stderr,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            write(output/(mode+'_process_started.json'),dict(pid=process.pid,command=command))
            print(json.dumps(dict(stage=mode,run_id=run_id,pid=process.pid,output=str(output))),flush=True)
            code = process.wait()
        write(output/(mode+'_process_completed.json'),dict(pid=process.pid,exit_code=code))
        check(code == 0,'UE '+mode+' failed; preserved diagnostics '+str(output))
        r = json.loads(report.read_text(encoding='utf-8'))
        check(r['passed'] and r['run_id'] == run_id and r['process_id'] == process.pid and
              r['script_sha256'] == sha(frozen),'Fresh UE result identity differs')
        reports.append(r)
    check(reports[0]['saved_package'] == reports[-1]['saved_package'] and
          reports[0]['actual'] == reports[-1]['actual'],'Saved asset reload differs')
    for item in reports[-1]['protected_packages_before']:
        check(sha(Path(item['file'])) == item['sha256'],'Package changed after process exit')
    write(output/'verified.json',dict(passed=True,run_id=run_id,
          source_mesh=request['source_mesh'],candidate=reports[-1]['actual'],saved_package=reports[-1]['saved_package'],
          reports=[dict(file=str(output/(m+'_report.json')),sha256=sha(output/(m+'_report.json')))
                   for m in modes],
          preexisting_packages_checked=len(reports[0]['protected_packages_before']),
          saved_asset_fresh_process_readonly_reload_verified=True,
          existing_candidate_recovery=bool(a.existing_candidate),original_pixels_verified=False,gameplay_verified=False))
    print(json.dumps(dict(passed=True,report=str(output/'verified.json'))),flush=True)


if __name__ == '__main__':
    main()
