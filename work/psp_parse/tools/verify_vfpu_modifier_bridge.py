import argparse,json,shutil,struct,subprocess
from pathlib import Path
from analyze_fx_node_time import check,identity

def generate(seed):
    rcx=[0x3f800000|((seed>>((i//4)*16))&0xffff)|(((seed>>(4*i))&0xf)<<16) for i in range(8)]
    out=[]
    for _ in range(6):
        A=((rcx[0]&0xffff)|(rcx[4]<<16))&0xffffffff;B=((rcx[1]&0xffff)|(rcx[5]<<16))&0xffffffff
        C=((rcx[2]&0xffff)|(rcx[6]<<16))&0xffffffff;D=((rcx[3]&0xffff)|(rcx[7]<<16))&0xffffffff
        E=sum(((rcx[i]>>16)&0xf)<<(4*i) for i in range(8));A=(69069*A+1)&0xffffffff;B^=(B<<13)&0xffffffff;B^=B>>17;B^=(B<<5)&0xffffffff;B&=0xffffffff
        t=(2*D+C+E)&0xffffffff;E=((C+(D>>1)+E)>>32)&0xffffffff;C,D=D,t
        rcx[:]=[0x3f800000|(((E>>(4*i))&0xf)<<16)|(x&0xffff) for i,x in enumerate((A,B,C,D))]+[0x3f800000|(((E>>(16+4*i))&0xf)<<16)|(x>>16) for i,x in enumerate((A,B,C,D))]
        out.append(0x40000000|((A+B+D)&0x7fffff))
    return out

def main():
    p=argparse.ArgumentParser();p.add_argument('--compiler',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();check(not a.out.exists(),'Never overwrite bridge proof');a.out.mkdir(parents=True)
    proj=Path(__file__).resolve().parents[2]/'t3b_unreal';files=[proj/'Tools/ge_effect_rcx_modifier_probe.cpp',proj/'Source/T3BRemake/Public/T3BGEEffectModifiers.h',proj/'Source/T3BRemake/Private/T3BGEEffectModifiers.cpp',proj/'Source/T3BRemake/Public/T3BGEVfpuRandom.h',proj/'Source/T3BRemake/Private/T3BGEVfpuRandom.cpp'];copies=[]
    for f in files:
        d=a.out/f.name;shutil.copyfile(f,d);copies.append(dict(source=str(f),**identity(d)))
    exe=a.out/'probe.exe';cmd=[str(a.compiler),'-std=c++17','-O2','-Wall','-Wextra','-Werror','-I'+str(a.out),str(a.out/'ge_effect_rcx_modifier_probe.cpp'),str(a.out/'T3BGEEffectModifiers.cpp'),str(a.out/'T3BGEVfpuRandom.cpp'),'-o',str(exe)];b=subprocess.run(cmd,capture_output=True);(a.out/'build_stderr.log').write_bytes(b.stderr);check(b.returncode==0,'Bridge build failed')
    r=subprocess.run([str(exe)],capture_output=True,text=True);check(r.returncode==0,'Bridge execution failed');words=r.stdout.strip().split();check(int(words[0])==6,'Wrong generated count');actual=[int(x,16) for x in words[1:]];random=generate(0x12345678)
    z0=struct.unpack('<f',struct.pack('<I',random[2]))[0];z1=struct.unpack('<f',struct.pack('<I',random[5]))[0];expected=[0,0,45,0,0,0,45,1,0,0,0,1,0,0,0,0];expected[6]=45+(z0-3)*32;expected[10]=(z1-3)*16
    expbits=[struct.unpack('<I',struct.pack('<f',x))[0] for x in expected];check(actual==expbits,'RCX modifier bridge differs')
    report=dict(passed=True,seed=0x12345678,generated_vectors=6,source_snapshots=copies,algorithm_reference='PPSSPP v1.20.4',game_node_seed_captured=False);(a.out/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(dict(passed=True,generated_vectors=6,game_node_seed_captured=False)))
if __name__=='__main__':main()
