"""Recover PRIM-time original camera/viewport for the paired Aya+gun samples."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import numpy as np
from exact_aya_materials import initial_registers
from extract_runtime_character import read_ppdmp


def check(ok, why):
    if not ok:
        raise ValueError(why)


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load(p):
    return json.loads(p.read_text(encoding='utf-8'))


def f24(x):
    return struct.unpack('<f', struct.pack('<I', x << 8))[0]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--geometry-request', type=Path, required=True)
    a = p.parse_args()
    check(not a.out.exists(), 'Refuse to replace camera evidence')
    a.out.mkdir(parents=True)
    geometry = load(a.geometry_request)
    body_file = Path(geometry['body_input']['file']); weapon_file = Path(geometry['weapon_input']['file'])
    for key, path in [('body_input', body_file), ('weapon_input', weapon_file)]:
        check(sha(path) == geometry[key]['sha256'], 'Geometry provenance changed')
    body, weapon = load(body_file), load(weapon_file)
    binaries = [Path(m['binary']['file']).read_bytes() for m in (body, weapon)]
    for data, m in zip(binaries, (body, weapon)):
        check(hashlib.sha256(data).hexdigest() == m['binary']['sha256'], 'Original lighting inputs changed')
    captures = {r['key']: r for r in weapon['captures']}
    origin = np.array(geometry['fixed_shared_PSP_world_origin'])
    unit = geometry['metres_per_PSP_world_unit'] * 100
    # Row-vector inverse of the existing source -> centimetres, XZY, recenter transform.
    inverse = np.array([[1/unit,0,0,0],[0,0,1/unit,0],[0,1/unit,0,0],[*origin,1]])
    rows = []
    camera_registers = [0x15,0x16,0x1c,0x42,0x43,0x44,0x45,0x46,0x47,0x4c,0x4d,0xd4,0xd5,0xd6,0xd7]
    for frame in weapon['frames']:
        sample = frame['sample']; bf = body['frames'][frame['body_frame_index']]
        targets = [(0,d) for d in body['draws'][bf['first_draw']:bf['first_draw']+106]]
        targets += [(1,weapon['draws'][frame['first_draw']])]
        expected = {(d['register_record'],d['register_word']):(actor,d) for actor,d in targets}
        capture = captures[frame['capture']]; path = Path(capture['path'])
        check(sha(path) == capture['sha256'], 'Original PPDMP changed')
        commands, push = read_ppdmp(str(path))
        regs = {}; view = [None]*12; projection = [None]*16; vc = pc = 0; observations = []
        for record,(kind,size,ptr) in enumerate(commands):
            check(ptr+size <= len(push), 'Truncated record')
            raw = push[ptr:ptr+size]
            if kind == 0:
                regs = initial_registers(raw)
            elif kind == 1:
                check(size % 4 == 0, 'Unaligned command')
                for wi in range(size//4):
                    word = struct.unpack_from('<I',raw,wi*4)[0]; cmd,val = word>>24,word&0xffffff
                    regs[cmd] = val
                    if cmd == 0x3c: vc = val&15
                    elif cmd == 0x3e: pc = val&15
                    elif cmd == 0x3d:
                        if vc < 12: view[vc] = val
                        vc = (vc+1)&15
                    elif cmd == 0x3f:
                        projection[pc] = val; pc = (pc+1)&15
                    if cmd != 4 or (record,wi) not in expected:
                        continue
                    actor,d = expected[(record,wi)]
                    check(view == d['VIEW_payload'] and projection == d['PROJECTION_payload'], 'PRIM camera payload mismatch')
                    saved = struct.unpack_from('<256I',binaries[actor],d['binary_byte_offset'])
                    check(all(regs.get(k) == saved[k] for k in camera_registers), 'PRIM viewport differs from paired input')
                    observations.append(dict(actor=actor, record=record, word=wi,
                        registers={hex(k):regs[k] for k in camera_registers},view=view[:],projection=projection[:]))
        check(len(observations) == 107, 'Missing paired PRIMs')
        first = observations[0]
        check(all(o['view']==first['view'] and o['projection']==first['projection'] and
                  o['registers']==first['registers'] for o in observations), 'Per-draw camera changes require separate matrices')
        registers = {int(k,16):v for k,v in first['registers'].items()}
        # This initial rendering scope is a full PSP drawing region and scissor.
        check(registers[0x15] == registers[0xd4] == 0 and
              registers[0x16] == registers[0xd5] == 0x43ddf and
              registers[0xd6] == 0 and registers[0xd7] == 65535 and registers[0x1c] == 1,
              'Non-full region/scissor/depth-clamp contract')
        v = np.eye(4); v[:,:3] = np.array([f24(x) for x in first['view']]).reshape(4,3)
        proj = np.array([f24(x) for x in first['projection']]).reshape(4,4)
        scale = np.array([f24(registers[k]) for k in (0x42,0x43,0x44)])
        center = np.array([f24(registers[k]) for k in (0x45,0x46,0x47)])
        offset = np.array([registers[k]&65535 for k in (0x4c,0x4d)])/16
        remap = np.diag([2*scale[0]/480,-2*scale[1]/272,scale[2]/65535,1])
        remap[3,:3] = [2*(center[0]-offset[0])/480-1,1-2*(center[1]-offset[1])/272,center[2]/65535]
        matrix = (inverse @ v @ proj @ remap).astype('<f4')
        check(np.isfinite(matrix).all(), 'Non-finite camera')
        # Lens angle is derived from diagonal projection entries, not an authored camera parameter.
        rows.append(dict(sample=sample,capture=capture,draws=observations,
            depth_clamp_enabled=True,
            view_payload=first['view'],projection_payload=first['projection'],
            viewport_scale=scale.tolist(),viewport_center=center.tolist(),offset_pixels=offset.tolist(),
            view_row_major=v.tolist(),projection_row_major=proj.tolist(),clip_remap_row_major=remap.tolist(),
            world_to_clip_row_major_f32=matrix.tolist(),
            derived_vertical_fov_degrees=float(np.degrees(2*np.arctan(1/proj[1,1]))),
            original_time_seconds=None))
    check(len(rows)==12 and [r['sample'] for r in rows]==list(range(12)), 'Unexpected sample coverage')
    binary = a.out/'original_camera_matrices.bin'
    with binary.open('wb') as f:
        f.write(b'T3BCAM1\0'+struct.pack('<3I',480,272,len(rows)))
        for r in rows:
            f.write(struct.pack('<I',r['sample']))
            f.write(np.asarray(r['world_to_clip_row_major_f32'],dtype='<f4').tobytes())
    result = dict(schema='t3b-original-ge-paired-camera/v1',passed=True,frames=rows,
        frame_count=12,PRIMs_verified=1284,source_camera_payloads_verified=True,
        geometry_request=dict(file=str(a.geometry_request.resolve()),sha256=sha(a.geometry_request)),
        geometry_bundle=geometry['bundle'],body_input=geometry['body_input'],weapon_input=geometry['weapon_input'],
        fixed_shared_PSP_world_origin=origin.tolist(),metres_per_PSP_world_unit=unit/100,
        binary=dict(file=str(binary.resolve()),sha256=sha(binary)),producer_sha256=sha(Path(__file__)),
        original_pixel_equivalence=False,original_timing_verified=False,UE_camera_executed=False,
        limits=['Derived float32 world-to-clip, not authored camera code or exact PSP subpixel/depth rasterization.',
                'GE depth clamp is enabled; a renderer without it requires proving the selected geometry stays within the clip Z interval.',
                'Frame sample order has no recovered original timing.',
                'Lens angle is a derivation from projection diagonal; view matrix is not forced orthonormal.',
                'Fog, scene geometry, postprocessing and full output colour remain separate.'])
    (a.out/'cameras.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=True,frames=12,PRIMs=1284,out=str(a.out),
        derived_vertical_fov_degrees=[r['derived_vertical_fov_degrees'] for r in rows])))


if __name__ == '__main__':
    main()
