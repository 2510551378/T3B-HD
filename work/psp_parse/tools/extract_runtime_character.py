"""Legacy inspection helpers and PPSSPPGE dump IO.

GE captures contain BONE commands and weighted local vertices. Verified recovery
replays commands through each PRIM; the older size/draw-range filters below are
inspection heuristics and do not establish actor identity or original skinning.
"""
import argparse, ctypes, os, struct
import numpy as np

ZSTD_DLL = r"C:\Users\25105\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin\libzstd.dll"
SCALE = 3.125 / 32768.0
TCA=(0,1,2,4); TCS=(0,2,4,8); COLA=(0,0,0,0,2,2,2,4); COLS=(0,0,0,0,2,2,2,4)
NRMA=(0,1,2,4); NRMS=(0,3,6,12); POSA=(0,1,2,4); POSS=(3,3,6,12); WTA=(0,1,2,4); WTS=(0,1,2,4)
lib=ctypes.WinDLL(ZSTD_DLL)
lib.ZSTD_decompress.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t]
lib.ZSTD_decompress.restype=ctypes.c_size_t
lib.ZSTD_isError.argtypes=[ctypes.c_size_t]; lib.ZSTD_isError.restype=ctypes.c_uint

def dec(data, cap):
    out=ctypes.create_string_buffer(cap); src=ctypes.create_string_buffer(data)
    n=lib.ZSTD_decompress(out,cap,src,len(data))
    if lib.ZSTD_isError(n): raise RuntimeError(f'zstd error {n}')
    return out.raw[:n]

def layout(fmt):
    tc=fmt&3; co=(fmt>>2)&7; nm=(fmt>>5)&3; po=(fmt>>7)&3; wt=(fmt>>9)&3; nw=((fmt>>14)&7)+1
    size=0; off={}; align=1
    if wt: size=(size+WTA[wt]-1)//WTA[wt]*WTA[wt]; off['wt']=(size,WTS[wt]*nw); size+=WTS[wt]*nw; align=max(align,WTA[wt])
    if tc: size=(size+TCA[tc]-1)//TCA[tc]*TCA[tc]; off['uv']=(size,TCS[tc]); size+=TCS[tc]; align=max(align,TCA[tc])
    if co:
        a=COLA[co] or 1; size=(size+a-1)//a*a; off['col']=(size,COLS[co]); size+=COLS[co]; align=max(align,a)
    if nm:
        a=NRMA[nm] or 1; size=(size+a-1)//a*a; off['nrm']=(size,NRMS[nm]); size+=NRMS[nm]; align=max(align,a)
    if po:
        a=POSA[po]; size=(size+a-1)//a*a; off['pos']=(size,POSS[po]); size+=POSS[po]; align=max(align,a)
    return (size+align-1)//align*align, off

def read_ppdmp(path):
    with open(path,'rb') as source:
        blob=source.read()
    ncmd, bufsz=struct.unpack_from('<II',blob,24); pos=32
    c1=struct.unpack_from('<I',blob,pos)[0]; pos+=4; raw_cmds=dec(blob[pos:pos+c1],ncmd*9); pos+=c1
    c2=struct.unpack_from('<I',blob,pos)[0]; pos+=4; push=dec(blob[pos:pos+c2],bufsz)
    cmds=[struct.unpack_from('<BII',raw_cmds,i*9) for i in range(ncmd)]
    return cmds,push

def decode_uv(raw, off, tc):
    """Decode PSP texture coordinates to normalized 0..1 values."""
    if tc == 1:
        return struct.unpack_from('<2B', raw, off)[0] / 128.0, struct.unpack_from('<2B', raw, off)[1] / 128.0
    if tc == 2:
        u, v = struct.unpack_from('<2H', raw, off)
        return u / 32768.0, v / 32768.0
    if tc == 3:
        return struct.unpack_from('<2f', raw, off)
    return 0.0, 0.0

def extract(path, out_path, cmin, cmax, ymax):
    cmds,push=read_ppdmp(path); cur=0; verts=[]; uvs=[]; faces=[]; blocks=[]
    for i,(typ,size,ptr) in enumerate(cmds):
        if ptr+size>len(push): continue
        if typ==1:
            for word in struct.unpack_from('<%dI'%(size//4),push,ptr):
                if (word>>24)==0x12: cur=word&0xffffff
        elif typ==2 and cmin<=i<=cmax and ((cur>>9)&3):
            stride, offs=layout(cur); posoff,_=offs['pos']; raw=push[ptr:ptr+size]; count=(len(raw)-posoff)//stride
            if count<3: continue
            arr=np.frombuffer(raw[posoff:posoff+count*stride],dtype='<i2').reshape(count,stride//2)[:,:3].astype(float)*SCALE
            lo,hi=arr.min(0),arr.max(0); dx,dy,dz=hi-lo
            if dx>.90 or dz>.90 or lo[1]<.40 or hi[1]>ymax: continue
            base=len(verts); verts.extend(arr.tolist())
            tc = cur & 3
            if 'uv' in offs:
                uoff, _ = offs['uv']
                uvs.extend(decode_uv(raw, k * stride + uoff, tc) for k in range(count))
            else:
                uvs.extend((0.0, 0.0) for _ in range(count))
            faces.extend((base+k,base+k+1,base+k+2) for k in range(0,count-2,3))
            blocks.append((i,cur,count,dx,dy,dz))
    os.makedirs(os.path.dirname(out_path),exist_ok=True)
    with open(out_path,'w',encoding='utf-8') as f:
        for v in verts: f.write('v %.6f %.6f %.6f\n'%tuple(v))
        for u,v in uvs: f.write('vt %.6f %.6f\n' % (u, v))
        for a,b,c in faces: f.write('f %d/%d %d/%d %d/%d\n'%(a+1,a+1,b+1,b+1,c+1,c+1))
    print(f'{path}: {len(blocks)} blocks, {len(verts)} verts, {len(faces)} tris -> {out_path}')
    print('bbox',np.min(verts,axis=0),np.max(verts,axis=0))

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('dump'); ap.add_argument('out'); ap.add_argument('--cmd-min',type=int,default=837); ap.add_argument('--cmd-max',type=int,default=1100); ap.add_argument('--ymax',type=float,default=3.3); a=ap.parse_args(); extract(a.dump,a.out,a.cmd_min,a.cmd_max,a.ymax)
