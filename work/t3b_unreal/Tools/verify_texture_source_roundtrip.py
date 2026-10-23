"""Export saved UE texture source art headlessly, then compare decoded RGBA.

This uses an installed UE5.8 editor; no C++ compilation or software installation.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid

from PIL import Image

PROJECT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def must(value, message):
    if not value:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine-root',type=Path,required=True)
    args = parser.parse_args()
    engine = args.engine_root.resolve()
    version = json.loads((engine/'Engine/Build/Build.version').read_text(encoding='utf-8-sig'))
    must((version['MajorVersion'],version['MinorVersion']) == (5,8), 'Explicit UE5.8 required')
    executable = engine/'Engine/Binaries/Win64/UnrealEditor-Cmd.exe'
    host = PROJECT/'T3BAssetImport.uproject'
    script = PROJECT/'Tools/export_saved_texture_sources.py'
    for path in (executable,host,script):
        must(path.is_file() and not any(c in str(path) for c in '"\r\n'), 'Missing or unsafe command path')
    run_id = uuid.uuid4().hex
    folder = PROJECT/'Validation/texture_roundtrip_runs'/run_id
    folder.mkdir(parents=True,exist_ok=False)
    report_path = folder/'ue_texture_source_export.json'
    log = folder/'UnrealEditor-Cmd.log'
    # The installed commandlet manually parses -script="...". Use an exact
    # Windows command line without a shell; all embedded paths were validated.
    command = subprocess.list2cmdline([str(executable),str(host)])
    command += f' -run=pythonscript -script="{script}" -unattended -NullRHI -nosplash -nosound -nop4 -NoCrashDialog -UTF8Output -stdout -FullStdOutLogOutput -abslog="{log}"'
    command += ' -ini:Engine:[/Script/EngineSettings.GameMapsSettings]:GlobalDefaultGameMode=/Script/Engine.GameModeBase'
    request = {'schema':'t3b-texture-roundtrip-request/v1','run_id':run_id,'requested_utc':datetime.now(timezone.utc).isoformat(),
               'command':command,'script_sha256':digest(script),'report':str(report_path)}
    (folder/'request.json').write_text(json.dumps(request,indent=2)+'\n',encoding='utf-8')
    env = os.environ.copy()
    env.update({'T3B_TEXTURE_RUN_ID':run_id,'T3B_TEXTURE_REPORT':str(report_path)})
    print(f'Starting hidden texture source-art export run_id={run_id}; {folder}',flush=True)
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    with (folder/'stdout.log').open('wb') as stdout, (folder/'stderr.log').open('wb') as stderr:
        process = subprocess.Popen(command,executable=str(executable),cwd=PROJECT,env=env,shell=False,
                                   stdout=stdout,stderr=stderr,startupinfo=startup,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            code = process.wait(timeout=1200)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise RuntimeError(f'Owned export commandlet timed out; logs retained: {folder}')
    must(code == 0, f'Export commandlet failed exit={code}; inspect {folder}')
    report = json.loads(report_path.read_text(encoding='utf-8-sig'))
    must(report['schema'] == 't3b-ue-texture-source-export/v1' and report['export_completed'], 'Fresh export failed')
    must(report['run_id'] == run_id and report['process_id'] == process.pid, 'Fresh run/PID mismatch')
    must(Path(report['project_file']).resolve() == host.resolve() and report['engine_version'].startswith('5.8.'), 'Wrong host/engine')
    must(report['exporter_script_sha256'] == request['script_sha256'] == digest(script), 'Exporter script changed')
    must(report['textures_exported'] == 76 and report['package_files_unchanged'] == 161, 'Export inventory incomplete')
    manifest = PROJECT/'Content/SourceData/manifest.json'
    must(report['manifest_sha256'] == digest(manifest), 'Source manifest changed')
    expected = json.loads(manifest.read_text(encoding='utf-8'))['textures']
    must([r['asset'] for r in report['rows']] == [t['asset'] for t in expected], 'Export asset inventory differs')
    comparisons = []
    for row,item in zip(report['rows'],expected):
        exported,source = Path(row['export_file']).resolve(),Path(row['source_file']).resolve()
        must(exported.is_relative_to(folder/'texture_sources') and digest(exported) == row['export_png_sha256'], 'Export path/hash differs')
        must(source == (PROJECT/'Content/SourceData'/item['file']).resolve(), 'Source path differs')
        with Image.open(exported) as image:
            actual_size,actual = image.size,image.convert('RGBA').tobytes()
        with Image.open(source) as image:
            source_size,original = image.size,image.convert('RGBA').tobytes()
        must(actual_size == source_size == (item['width'],item['height']), 'Texture dimensions differ')
        must(hashlib.sha256(original).hexdigest() == item['rgba_sha256'], 'Staged source RGBA identity differs')
        must(actual == original, f'Saved texture source RGBA differs: {row["asset"]}')
        comparisons.append({'asset':row['asset'],'width':actual_size[0],'height':actual_size[1],
                            'rgba_sha256':hashlib.sha256(actual).hexdigest(),'rgba_bytes_compared':len(actual),
                            'byte_identical':True,'export_file':str(exported)})
    result = {'schema':'t3b-saved-texture-source-roundtrip/v1','passed':True,'run_id':run_id,'process_id':process.pid,
              'exit_code':code,'engine_version':report['engine_version'],'source_report':str(report_path),
              'source_report_sha256':digest(report_path),'textures_checked':len(comparisons),
              'rgba_bytes_compared':sum(r['rgba_bytes_compared'] for r in comparisons),'rows':comparisons,
              'package_files_unchanged':161,'ue_render_verified':False,
              'limits':['Checks saved source-art RGBA, including hidden RGB and alpha, not GPU platform data or texture sampling.',
                        'Does not certify CLUT selection beyond the staged manifest, shader output, source view parity or gameplay.']}
    target = folder/'verified.json'
    target.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(f'All76 saved texture source-art RGBA exports match byte-for-byte; report: {target}')


if __name__ == '__main__':
    main()
