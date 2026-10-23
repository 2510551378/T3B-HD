import argparse,hashlib,json,shutil,struct,subprocess
from pathlib import Path
from analyze_fx_node_time import check,identity
def ref(seed,kind,rcx):
    A=((rcx[0]&0xffff)|(rcx[4]<<16))&0xffffffff;B=((rcx[1]&0xffff)|(rcx[5]<<16))&0xffffffff;C=((rcx[2]&0xffff)|(rcx[6]<<16))&0xffffffff;D=((rcx[3]&0xffff)|(rcx[7]<<16))&0xffffffff;E=sum(((rcx[i]>>16)&0xf)<<(4*i) for i in range(8));A=(69069*A+1)&0xffffffff;B^=(B<<13)&0xffffffff;B^=B>>17;B^=(B<<5)&0xffffffff;B&=0xffffffff;t=(2*D+C+E)&0xffffffff;E=((C+(D>>1)+E)>>32)&0xffffffff;C,D=D,t;rcx[:]=[0x3f800000|(((E>>(4*i))&0xf)<<16)|(x&0xffff) for i,x in enumerate((A,B,C,D))]+[0x3f800000|(((E>>(16+4*i))&0xf)<<16)|(x>>16) for i,x in enumerate((A,B,C,D))];return A+B+D if kind==0 else (0x3f800000 if kind==1 else 0x40000000)|(refval&0x7fffff)
def main():
 p=argparse.ArgumentParser();p.add_argument('--compiler',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();check(not a.out.exists(),'Never overwrite VRND proof');a.out.mkdir(parents=True)
 cases=[(0x1,0),(0x12345678,0),(0x12345678,1),(0xdeadbeef,2),(0,0),(0xffffffff,1)];raw=bytearray(b'T3BVRN1\0'+struct.pack('<I',len(cases)));expected=bytearray()
 for seed,kind in cases:
  steps=8;raw.extend(struct.pack('<2I',seed,steps));rcx=[0]*8;T3BGE=None
  for _ in range(steps):raw.extend(struct.pack('<I',kind));A=(seed>>0); # placeholder replaced below
  # independent Python reference
  rcx=[0x3f800000|((seed>>((i//4)*16))&0xffff)|(((seed>>(4*i))&0xf)<<16)for i in range(8)]
  for _ in range(steps):
   A=((rcx[0]&0xffff)|(rcx[4]<<16))&0xffffffff;B=((rcx[1]&0xffff)|(rcx[5]<<16))&0xffffffff;C=((rcx[2]&0xffff)|(rcx[6]<<16))&0xffffffff;D=((rcx[3]&0xffff)|(rcx[7]<<16))&0xffffffff;E=sum(((rcx[i]>>16)&0xf)<<(4*i)for i in range(8));A=(69069*A+1)&0xffffffff;B^=(B<<13)&0xffffffff;B^=B>>17;B^=(B<<5)&0xffffffff;B&=0xffffffff;t=(2*D+C+E)&0xffffffff;E=((C+(D>>1)+E)>>32)&0xffffffff;C,D=D,t;rcx[:]=[0x3f800000|(((E>>(4*i))&0xf)<<16)|(x&0xffff)for i,x in enumerate((A,B,C,D))]+[0x3f800000|(((E>>(16+4*i))&0xf)<<16)|(x>>16)for i,x in enumerate((A,B,C,D))];v=(A+B+D)&0xffffffff;expected+=struct.pack('<I',v if kind==0 else ((0x3f800000 if kind==1 else 0x40000000)|(v&0x7fffff)))
  expected+=struct.pack('<8I',*rcx)
 inp=a.out/'inputs.bin';refp=a.out/'expected.bin';inp.write_bytes(raw);refp.write_bytes(expected);proj=Path(__file__).resolve().parents[2]/'t3b_unreal';src=[proj/'Tools/ge_vfpu_random_probe.cpp',proj/'Source/T3BRemake/Public/T3BGEVfpuRandom.h',proj/'Source/T3BRemake/Private/T3BGEVfpuRandom.cpp',Path(__file__)];copies=[]
 for f in src:d=a.out/f.name;shutil.copyfile(f,d);copies.append(dict(source=str(f),**identity(d)))
 exe=a.out/'ge_vfpu_random_probe.exe';cmd=[str(a.compiler),'-std=c++17','-O2','-Wall','-Wextra','-Werror','-I'+str(a.out),str(a.out/'ge_vfpu_random_probe.cpp'),str(a.out/'T3BGEVfpuRandom.cpp'),'-o',str(exe)];b=subprocess.run(cmd,capture_output=True);(a.out/'build_stderr.log').write_bytes(b.stderr);check(b.returncode==0,'VRND build failed');out=a.out/'runtime.bin';run=subprocess.run([str(exe),str(inp),str(out)],capture_output=True);(a.out/'stderr.log').write_bytes(run.stderr);check(run.returncode==0 and out.read_bytes()==expected,'VRND production differs');r=dict(passed=True,cases=len(cases),steps=48,source_snapshots=copies,input=identity(inp),expected=identity(refp),runtime=identity(out),seed_algorithm_recovered=True,game_node_seed_captured=False,UE_module_built=False);(a.out/'verification.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(dict(passed=True,cases=len(cases),game_node_seed_captured=False)))
if __name__=='__main__':main()
