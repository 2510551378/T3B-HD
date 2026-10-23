"""Bounded original color/percent-scale MIPS + VFPU replay, finite/default-entry-prefix domain."""
import math
import struct
from analyze_fx_node_time import bits,check,number,u32
from verify_weapon_ge_matrix_math import vindices


class Machine:
    def __init__(self,module,g,f,parameter,parameter_bytes):
        self.module=module;self.g=list(g);self.f=list(f);self.v=[None]*128
        self.prefix=[0xe4,0xe4,0];self.memory={};self.parameter=parameter;self.size=len(parameter_bytes)
        self.stack=(g[29]-0x80,g[29]+4);self.trace=[];self.stores=[]
        self.retain(parameter,parameter_bytes)

    def retain(self,address,raw):
        check(address%4==0 and len(raw)%4==0,'Unaligned oracle region')
        for at in range(0,len(raw),4):
            value=u32(raw,at);p=address+at
            check(p not in self.memory or self.memory[p]==value,'Contradictory original regions');self.memory[p]=value

    def load(self,address):
        check(address%4==0 and address in self.memory,'Unretained oracle load '+hex(address));return self.memory[address]

    def store(self,address,value,pc):
        check(address%4==0 and (self.parameter<=address<self.parameter+self.size or self.stack[0]<=address<self.stack[1]),'Unbounded original store')
        self.memory[address]=value
        if self.parameter<=address<self.parameter+self.size:self.stores.append(dict(pc=pc,address=address,bits=value))

    def vector(self,reg,n):return [self.v[i]for i in vindices(reg,n)]

    def swizzle(self,values,prefix):
        out=[];constants=[0,1,2,0.5,3,1/3,0.25,1/6]
        for k in range(len(values)):
            index=(prefix>>(2*k))&3
            if(prefix>>(12+k))&1:value=bits(constants[index+4*((prefix>>(8+k))&1)])
            else:
                check(index<len(values)and values[index]is not None,'Uninitialized VFPU source lane')
                value=values[index]
                if(prefix>>(8+k))&1:value &=0x7fffffff
            if(prefix>>(16+k))&1:value ^=0x80000000
            check(math.isfinite(number(value)),'Nonfinite VFPU source outside supported domain');out.append(value)
        return out

    def execute(self,pc,delay=False):
        check(0x08b8f898<=pc<0x08b8fa60 or 0x08b94968<=pc<0x08b949fc,'Unsupported original callback control flow '+hex(pc))
        w=u32(self.module,pc-0x08804000);op=w>>26;rs=(w>>21)&31;rt=(w>>16)&31;rd=(w>>11)&31;fn=w&63
        imm=struct.unpack('<h',struct.pack('<H',w&65535))[0];target=None;name=''
        if w==0:name='nop'
        elif op==9:self.g[rt]=(self.g[rs]+imm)&0xffffffff;name='addiu'
        elif op==13:self.g[rt]=self.g[rs]|(w&65535);name='ori'
        elif op==15:self.g[rt]=(w&65535)<<16;name='lui'
        elif op==0 and fn in (0x21,0x25):self.g[rd]=((self.g[rs]+self.g[rt])if fn==0x21 else(self.g[rs]|self.g[rt]))&0xffffffff;name='addu/or'
        elif op==0 and fn in (8,9):
            check(not delay,'Nested branch delay control');target=self.g[rs]
            if fn==9:self.g[rd]=pc+8
            name='jr/jalr'
        elif op==0x23:self.g[rt]=self.load((self.g[rs]+imm)&0xffffffff);name='lw'
        elif op==0x21:
            address=(self.g[rs]+imm)&0xffffffff;check(address%2==0,'Unaligned signed halfword')
            value=(self.load(address&~3)>>(8*(address&3)))&65535
            self.g[rt]=(value-65536 if value&32768 else value)&0xffffffff;name='lh'
        elif op==0x2b:self.store((self.g[rs]+imm)&0xffffffff,self.g[rt],pc);name='sw'
        elif op==0x31:self.f[rt]=self.load((self.g[rs]+imm)&0xffffffff);name='lwc1'
        elif op==0x39:self.store((self.g[rs]+imm)&0xffffffff,self.f[rt],pc);name='swc1'
        elif op==0x11 and rs==0:self.g[rt]=self.f[rd];name='mfc1'
        elif op==0x11 and rs==4:self.f[rd]=self.g[rt];name='mtc1'
        elif op==0x12 and rs==7:
            check(w&0xff80==0,'Unsupported mtv control encoding');self.v[vindices(w&127,1)[0]]=self.g[rt];name='mtv'
        elif op in (0x32,0x36,0x3a,0x3e):
            quad=op in (0x36,0x3e);reg=rt|((w&1)<<5)if quad else rt|((w&3)<<5)
            offset=w&0xfffc;offset-=0x10000 if offset&32768 else 0;address=(self.g[rs]+offset)&0xffffffff
            for k,index in enumerate(vindices(reg,4 if quad else 1)):
                if op in (0x32,0x36):self.v[index]=self.load(address+4*k)
                else:
                    check(self.v[index]is not None,'Uninitialized VFPU store');self.store(address+4*k,self.v[index],pc)
            name='lv/sv'
        elif w>>24 in (0xdc,0xdd,0xde):
            which=(w>>24)-0xdc;self.prefix[which]=w&0xfffff;name='vpfx'
        else:
            vd,vs,vt=w&127,(w>>8)&127,(w>>16)&127;n=1+((w>>7)&1)+2*((w>>15)&1)
            check(self.prefix[2]==0,'Unsupported VFPU destination prefix')
            code=w&0xff800000
            if w&0xffff0000==0xd0060000:
                result=[bits(-0.0 if(self.prefix[0]>>(16+k))&1 else 0.0)for k in range(n)];name='vzero'
            elif code in (0x60000000,0x60800000,0x65000000,0x6d000000,0x6d800000):
                a=self.swizzle(self.vector(vs,n),self.prefix[0])
                if code==0x65000000:
                    check(self.prefix[1]==0xe4,'Unsupported active VSCL T prefix');value=self.vector(vt,1)[0]
                    check(value is not None and math.isfinite(number(value)),'Uninitialized/nonfinite VSCL scalar');b=[value]*n
                else:b=self.swizzle(self.vector(vt,n),self.prefix[1])
                result=[]
                for x,y in zip(a,b):
                    xf,yf=number(x),number(y)
                    if code==0x60000000:v=bits(xf+yf)
                    elif code==0x60800000:v=bits(xf-yf)
                    elif code==0x65000000:v=bits(xf*yf)
                    elif code==0x6d000000:v=x if xf<yf else y
                    else:v=x if xf>yf else y
                    check(math.isfinite(number(v)),'Nonfinite VFPU result outside supported domain');result.append(v)
                name={0x60000000:'vadd',0x60800000:'vsub',0x65000000:'vscl',0x6d000000:'vmin',0x6d800000:'vmax'}[code]
            else:raise ValueError('Unsupported original opcode '+hex(w)+' at '+hex(pc))
            for index,value in zip(vindices(vd,n),result):self.v[index]=value
            self.prefix=[0xe4,0xe4,0]
        self.g[0]=0;self.trace.append(dict(pc=pc,word=w,instruction=name));return target

    def run(self,start,stop):
        pc=start
        while pc!=stop:
            check(len(self.trace)<512,'Callback instruction bound')
            target=self.execute(pc)
            if target is None:pc+=4
            else:self.execute(pc+4,True);pc=target
        return b''.join(struct.pack('<I',self.load(self.parameter+k))for k in range(0,self.size,4))
