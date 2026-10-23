"""Recorded PSP rectangle semantics in bounded F32/16-subpixel arithmetic.

Produces capture-camera-dependent sprite quads from original endpoints, not PNGs.
The pinned upstream reference independently checks endpoints/parts/candidate pixels.
"""
import numpy as np

ENDPOINT=np.dtype([('clip','<f4',4),('xy','<i4',2),('z','<u4'),('fog','<f4'),('outside','<u4')])
PART=np.dtype([('sample','<u4'),('pair','<u4'),('id','<u4'),('xy','<i4',4),('z','<u4'),('uv','<f4',4),('fog','<f4'),('color','<u4'),('first','<u8'),('pixels','<u4')])
PIXEL=np.dtype([('part','<u4'),('x','<u4'),('y','<u4'),('uv','<f4',2),('z','<u4'),('fog','<u4'),('color','<u4')])
SOURCE=np.dtype([('pos','<f4',3),('uv','<f4',2),('color','<u4')])


def f24(v):return (np.asarray(v,dtype='<u4')<<8).view('<f4')
def affine(v):
    a=np.eye(4,dtype='<f4');a[:,:3]=np.asarray(v,dtype='<f4').reshape(4,3);return a
def multiply(a,b):
    r=a[:,0,None]*b[0]
    for i in range(1,4):r=r+a[:,i,None]*b[i]
    return r
def transform(regs,world,view,proj,vertices):
    wv=multiply(affine(world),affine(view));matrix=multiply(wv,np.asarray(proj,dtype='<f4').reshape(4,4));p=vertices['pos']
    clip=(p[:,0,None]*matrix[0]+p[:,1,None]*matrix[1])+(p[:,2,None]*matrix[2]+matrix[3])
    scale=f24([regs[k]for k in(0x42,0x43,0x44)]);center=f24([regs[k]for k in(0x45,0x46,0x47)])
    scaled=(clip[:,:3]*scale)/clip[:,3,None]+center
    if not np.isfinite(scaled).all():raise ValueError('Nonfinite source rectangle projection')
    if regs[0x1c]!=0:raise ValueError('Only observed non-clamped sprite path implemented')
    outside=(scaled[:,0]>np.float32(4095+15.5/16))|(scaled[:,1]>=np.float32(4095+15.5/16))|np.any(scaled[:,:2]<0,axis=1)|(scaled[:,2]<0)|(scaled[:,2]>=65536)
    xy=np.trunc((scaled[:,:2]*np.float32(16)+np.float32(.375))-np.array([regs[0x4c]&65535,regs[0x4d]&65535],dtype='<f4')).astype('<i4')
    xy[outside,0]=0x7fffffff;z=np.trunc(scaled[:,2]).astype(np.int64).astype('<u2').astype('<u4')
    fog_plane=wv[:,2].copy();fog_plane[3]=fog_plane[3]+f24([regs[0xcd]])[0];fog_plane=fog_plane*f24([regs[0xce]])[0]
    fog=(p[:,0]*fog_plane[0]+p[:,1]*fog_plane[1])+(p[:,2]*fog_plane[2]+fog_plane[3])
    output=np.empty(len(vertices),dtype=ENDPOINT);output['clip']=clip;output['xy']=xy;output['z']=z;output['fog']=fog;output['outside']=outside
    uv=vertices['uv']*f24([regs[0x48],regs[0x49]])+f24([regs[0x4a],regs[0x4b]])
    return output,uv


def quantize_fog(v):
    bits=int(np.asarray(v,dtype='<f4').view('<u4'));exponent=bits>>23
    if bits&0x80000000 or exponent<=118:return 0
    if exponent>126:return 255
    return ((bits&0x7fffff)|0x800000)>>(16+126-exponent)


def split(endpoints,uv,colors,sample):
    for pair in range(len(endpoints)//2):
        a,b=endpoints[pair*2:pair*2+2]
        if a['outside']or b['outside']:continue
        ratio=np.array([a['clip'][2]/a['clip'][3],b['clip'][2]/b['clip'][3]],dtype='<f4')
        if np.any(np.abs(ratio)>=np.float32(1.000030517578125)):continue
        x0,y0=map(int,a['xy']);x1,y1=map(int,b['xy']);u0,v0=uv[pair*2];u1,v1=uv[pair*2+1]
        f0,f1=a['fog'],b['fog'];half=np.float32(.5/255)
        split_fog=f0!=f1 and not(f1-half<=f0<=f1+half)
        common=dict(sample=sample,pair=pair,z=int(b['z']),color=int(colors[pair*2+1]))
        if split_fog:
            middle=x0+int((x1-x0)/2);um=u0+(u1-u0)/np.float32(2)
            yield dict(common,xy=[x0,y0,middle,y1],uv=np.array([u0,v0,um,v1],dtype='<f4'),fog=f1)
            yield dict(common,xy=[middle,y0,x1,y1],uv=np.array([um,v0,u1,v1],dtype='<f4'),fog=f0)
        else:yield dict(common,xy=[x0,y0,x1,y1],uv=np.array([u0,v0,u1,v1],dtype='<f4'),fog=f1)


def raster(part):
    x0,y0,x1,y1=part['xy'];left,right=min(x0,x1),max(x0,x1)-1;top,bottom=min(y0,y1),max(y0,y1)-1
    start_x=max(left&~15,0)|7;start_y=max(top&~15,0)|7;end_x=min(right,480*16-1);end_y=min(bottom,272*16-1)
    if start_x<left-1:start_x+=16
    if start_y<top-1:start_y+=16
    if start_x>=end_x or start_y>=end_y:return [],None
    u0,v0,u1,v1=part['uv'];ds=u1-u0;dt=v1-v0;dx=np.float32((right-left+1)/16);dy=np.float32((bottom-top+1)/16);zero=np.float32(0)
    if x0<x1 and y0<y1:row=np.array([u0,v0],dtype='<f4');sx=np.array([2*ds/dx,zero],dtype='<f4');sy=np.array([zero,2*dt/dy],dtype='<f4')
    elif x0<x1:row=np.array([u1,v0],dtype='<f4');sx=np.array([zero,2*dt/dx],dtype='<f4');sy=np.array([-2*ds/dy,zero],dtype='<f4')
    elif y0<y1:row=np.array([u0,v1],dtype='<f4');sx=np.array([zero,-2*dt/dx],dtype='<f4');sy=np.array([2*ds/dy,zero],dtype='<f4')
    else:row=np.array([u1,v1],dtype='<f4');sx=np.array([-2*ds/dx,zero],dtype='<f4');sy=np.array([zero,-2*dt/dy],dtype='<f4')
    row=row+(sx/np.float32(32))*np.float32(start_x-left+1);row=row+(sy/np.float32(32))*np.float32(start_y-top+1)
    first_uv=row.copy();step_offsets=np.array([[0,0],sx*np.float32(.5),sy*np.float32(.5),sx*np.float32(.5)+sy*np.float32(.5)],dtype='<f4')
    pixels=[]
    for cy in range(start_y,end_y,32):
        st=row.copy()
        for cx in range(start_x,end_x,32):
            all_uv=st+step_offsets
            for i in range(4):
                if cx+(i&1)*16>end_x or cy+(i//2)*16>end_y:continue
                pixels.append((part['id'],(cx>>4)+(i&1),(cy>>4)+(i//2),all_uv[i].copy(),part['z'],quantize_fog(part['fog']),part['color']))
            st=st+sx
        row=row+sy
    xs=[int(p[1])for p in pixels];ys=[int(p[2])for p in pixels];bounds=[min(xs),min(ys),max(xs)+1,max(ys)+1]
    return pixels,dict(bounds=bounds,first_uv=first_uv,sx=sx,sy=sy)


def quad(part,plane):
    left,top,right,bottom=plane['bounds'];sx=plane['sx'];sy=plane['sy'];uv=plane['first_uv']-np.float32(.25)*(sx+sy)
    offsets=[np.array([0,0],dtype='<f4'),np.float32((right-left)/2)*sx,np.float32((bottom-top)/2)*sy,np.float32((right-left)/2)*sx+np.float32((bottom-top)/2)*sy]
    xy=[(left,top),(right,top),(left,bottom),(right,bottom)]
    color=np.array([(part['color']>>(8*i))&255 for i in range(4)],dtype=float)/255;vertices=[]
    for i in (0,1,2,1,3,2):
        x,y=xy[i];tex=uv+offsets[i];vertices.append([x/240-1,1-y/136,part['z']/65535,*tex,part['fog'],*color])
    return np.asarray(vertices,dtype='<f4')
