"""Launch hidden real-D3D11 UE sample replay, retaining the exact process handle."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import py_compile
import subprocess
import uuid


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def check(ok, reason):
    if not ok:
        raise ValueError(reason)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--engine-root', type=Path, required=True)
    p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--runtime-report', type=Path, required=True)
    a = p.parse_args(); project = Path(__file__).resolve().parents[1]
    exe = a.engine_root / 'Engine/Binaries/Win64/UnrealEditor-Cmd.exe'
    check(exe.is_file(), 'Explicit installed engine missing')
    producer = project / 'Tools/capture_aya_ge_series.py'; py_compile.compile(str(producer), doraise=True)
    run = uuid.uuid4().hex; folder = project / 'Validation/ge_sample_series_runs' / run; folder.mkdir(parents=True)
    script = folder / 'capture_aya_ge_series_executed.py'; script.write_bytes(producer.read_bytes())
    report = folder / 'ue_ge_series.json'
    cmd = [str(exe), str(project / 'T3BNativeProbe.uproject'), '-run=pythonscript', '-script=' + str(script),
           '-unattended', '-AllowCommandletRendering', '-RenderOffScreen', '-d3d11', '-nosplash', '-nosound', '-nop4',
           '-NoCrashDialog', '-UTF8Output', '-stdout', '-FullStdOutLogOutput', '-abslog=' + str(folder / 'UnrealEditor-Cmd.log'),
           '-ini:Engine:[/Script/EngineSettings.GameMapsSettings]:GlobalDefaultGameMode=/Script/Engine.GameModeBase']
    request = dict(run_id=run, command=cmd, inputs=str(a.inputs.resolve()), inputs_sha256=sha(a.inputs),
                   runtime_report=str(a.runtime_report.resolve()), runtime_report_sha256=sha(a.runtime_report), script_sha256=sha(script))
    (folder / 'request.json').write_text(json.dumps(request, indent=2) + '\n', encoding='utf-8')
    env = dict(os.environ, T3B_SERIES_REPORT=str(report), T3B_SERIES_INPUT=str(a.inputs.resolve()),
               T3B_SERIES_RUNTIME=str(a.runtime_report.resolve()), T3B_SERIES_RUN=run)
    with (folder / 'stdout.log').open('wb') as stdout, (folder / 'stderr.log').open('wb') as stderr:
        process = subprocess.Popen(cmd, cwd=project, env=env, stdout=stdout, stderr=stderr,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        (folder / 'process_started.json').write_text(json.dumps(dict(pid=process.pid, run_id=run)) + '\n', encoding='utf-8')
        print(json.dumps(dict(pid=process.pid, run_id=run, folder=str(folder))), flush=True)
        code = process.wait()
    (folder / 'process_completed.json').write_text(json.dumps(dict(pid=process.pid, exit_code=code)) + '\n', encoding='utf-8')
    check(code == 0, 'UE replay failed; preserved ' + str(folder))
    result = json.loads(report.read_text(encoding='utf-8'))
    check(result['passed'] and result['process_id'] == process.pid and result['run_id'] == run and
          result['script_sha256'] == sha(script) and result['all_original_packages_unchanged'], 'Actual result incomplete')
    for item in result['protected_packages_before']:
        check(sha(Path(item['file'])) == item['sha256'], 'Original package changed after exit')
    (folder / 'verified.json').write_text(json.dumps(dict(passed=True, report_sha256=sha(report), samples=len(result['samples']),
         process_id=process.pid, run_id=run, original_timing_verified=False, original_hardware_pixels_verified=False), indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(passed=True, report=str(report))), flush=True)


if __name__ == '__main__':
    main()
