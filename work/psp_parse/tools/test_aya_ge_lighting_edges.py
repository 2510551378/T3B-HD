"""Independent upstream/native comparisons on explicitly synthetic edge inputs."""
import argparse,copy,hashlib,json,struct,subprocess
from pathlib import Path


def check(ok,msg):
    if not ok:raise ValueError(msg)


def f24(v):return struct.unpack('<I',struct.pack('<f',v))[0]>>8


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--reference-dir',type=Path);a=p.parse_args()
    check(not a.out.exists(),'Never replace edge-test evidence');a.out.mkdir(parents=True)
    root=Path(__file__).resolve().parents[1];base=root/'out/AYA_GE_VERTEX_LIGHTING_20261020'
    raw=(base/'inputs/lighting_inputs.bin').read_bytes();registers=list(struct.unpack_from('<256I',raw,12))
    # Isolate one directional light; vary semantically meaningful corner cases.
    registers[0x18:0x1C]=[1,0,0,0];registers[0x5F]=1
    registers[0x63:0x66]=[f24(0),f24(0),f24(1)]
    cases=[]
    def case(name,normal=(0,0,1),position=(0,0,0),edit=None):
        r=copy.copy(registers)
        if edit:edit(r)
        cases.append((name,r,normal,position))
    case('directional_front_diffuse_specular')
    case('directional_negative_diffuse',normal=(0,0,-1))
    case('zero_input_normal_fallback',normal=(0,0,0))
    case('zero_direction_fallback',edit=lambda r:r.__setitem__(slice(0x63,0x66),[0,0,0]))
    case('zero_half_vector',edit=lambda r:r.__setitem__(slice(0x63,0x66),[0,0,f24(-1)]))
    case('zero_specular_exponent',edit=lambda r:r.__setitem__(0x5B,0))
    case('negative_specular_exponent',edit=lambda r:r.__setitem__(0x5B,f24(-2)))
    case('secondary_specular_channel',edit=lambda r:r.__setitem__(0x5E,1))
    case('all_lights_disabled',edit=lambda r:r.__setitem__(slice(0x18,0x1C),[0,0,0,0]))
    def point(r):
        r[0x5F]=0x101;r[0x63:0x66]=[f24(0),f24(0),f24(1)];r[0x7B:0x7E]=[f24(1),f24(0),f24(0)]
    case('point_zero_distance',position=(0,0,1),edit=point)
    def negative(r):point(r);r[0x7B]=f24(-1)
    case('negative_attenuation_clamps_zero',edit=negative)
    def powered(r):r[0x5F]=2
    case('powered_diffuse',normal=(0,1,1),edit=powered)
    def material_zero(r):r[0x55]=r[0x56]=r[0x57]=0
    case('black_material_light_terms_disable',edit=material_zero)
    identity=[1.,0,0,0,1.,0,0,0,1.,0,0,0]
    dataset=bytearray(b'T3BLIT1\0'+struct.pack('<I',len(cases)))
    for name,r,n,v in cases:
        dataset+=struct.pack('<256I',*r)+struct.pack('<12f',*identity)+struct.pack('<96f',*(identity+[0.]*84))+struct.pack('<2I',1,1)
        dataset+=struct.pack('<16f',*(list(v)+list(n)+[1.]+[0.]*7+[0.,0.]))
    source=a.out/'synthetic_edges.bin';source.write_bytes(dataset)
    exe=(a.reference_dir or base/'comparison_v1')/'compare_lighting.exe'
    run=subprocess.run([str(exe),str(source),str(a.out/'upstream.bin'),str(a.out/'native.bin')],capture_output=True,text=True,encoding='utf-8')
    (a.out/'stdout.log').write_text(run.stdout,encoding='utf-8');(a.out/'stderr.log').write_text(run.stderr,encoding='utf-8')
    result=dict(schema='aya-ge-lighting-edge-tests/v1',passed=run.returncode==0,runtime_evidence=False,
                synthetic_cases=[x[0]for x in cases],comparison=json.loads(run.stdout),
                executable_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(),input_sha256=hashlib.sha256(dataset).hexdigest())
    (a.out/'verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result['comparison']));check(result['passed'],'Edge comparisons differ')


if __name__=='__main__':main()
