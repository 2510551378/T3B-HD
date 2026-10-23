"""Compile the expanded project shader with FXC and capture an owned GPU probe."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--compiler', required=True, type=Path)
    a = p.parse_args()
    project = Path(__file__).resolve().parents[1]
    out = project / 'Validation/ge_world_shader_probe_runs' / uuid.uuid4().hex
    out.mkdir(parents=True)
    inputs = [project / 'Tools/ge_world_shader_probe.cpp',
              project / 'Shaders/Private/T3BGEOrdered.usf',
              project / 'Shaders/Private/T3BGECommon.ush']
    frozen = []
    for source in inputs:
        copy = out / source.name
        copy.write_bytes(source.read_bytes())
        frozen.append(dict(source=str(source), file=str(copy), sha256=sha(copy)))
    shader = (out / 'T3BGEOrdered.usf').read_bytes()
    platform = b'#include "/Engine/Public/Platform.ush"'
    shared = b'#include "/T3B/Private/T3BGECommon.ush"'
    if shader.count(platform) != 1 or shader.count(shared) != 1:
        raise ValueError('Unexpected shader include structure')
    # No replacement UE headers or macros; the current body uses no Platform symbols.
    expanded = out / 'executed_shader.hlsl'
    expanded.write_bytes(shader.replace(platform, b'// Direct FXC probe: Engine Platform include omitted.')
                         .replace(shared, (out / 'T3BGECommon.ush').read_bytes()))
    exe = out / 'ge_world_shader_probe.exe'
    cmd = [str(a.compiler), '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
           str(out / 'ge_world_shader_probe.cpp'), '-o', str(exe),
           '-ld3d11', '-ld3dcompiler', '-ldxgi', '-ldxguid']
    request = dict(schema='t3b-world-shader-body-probe/v1', sources=frozen,
                   expanded_shader=dict(file=str(expanded), sha256=sha(expanded)),
                   build_command=cmd, UE_module_built=False, UE_shader_compiler_used=False,
                   UE_pass_executed=False)
    write_json(out / 'request.json', request)
    build = subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='replace')
    (out / 'build_stdout.log').write_text(build.stdout, encoding='utf-8')
    (out / 'build_stderr.log').write_text(build.stderr, encoding='utf-8')
    request['build_exit_code'] = build.returncode
    write_json(out / 'request.json', request)
    if build.returncode:
        raise RuntimeError(f'Native build failed; evidence: {out}')
    command = [str(exe), str(expanded), str(out)]
    request.update(executable_sha256=sha(exe), run_command=command)
    write_json(out / 'request.json', request)
    with (out / 'stdout.log').open('w', encoding='utf-8') as stdout, \
            (out / 'stderr.log').open('w', encoding='utf-8') as stderr:
        process = subprocess.Popen(command, cwd=out, stdout=stdout, stderr=stderr,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        write_json(out / 'started.json', dict(pid=process.pid, command=command))
        code = process.wait()
    write_json(out / 'completed.json', dict(pid=process.pid, exit_code=code))
    print(json.dumps(dict(run=str(out), pid=process.pid, exit_code=code), ensure_ascii=False))
    if code:
        raise RuntimeError(f'GPU probe failed; evidence: {out}')


if __name__ == '__main__':
    main()
