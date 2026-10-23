"""Finite/default-prefix replay of original type6 wrappers and common XYZ helpers."""
import math,struct
from analyze_fx_node_time import bits,number,u32,check
from replay_fx_color_scale import Machine as ColorMachine
from verify_weapon_ge_matrix_math import vindices

RANGES=((0x08b943d4,0x08b94508),(0x08b65f48,0x08b6616c),(0x08b662e0,0x08b664e0),(0x08bfcff4,0x08bfd05c))
class Machine(ColorMachine):
    def __init__(self,module,g,f,parameter,raw):
        super().__init__(module,g,f,parameter,raw);self.stack=(g[29]-0x180,g[29]+4)
    def execute(self,pc,delay=False):
        check(any(lo<=pc<hi for lo,hi in RANGES),'Unknown vector callback control flow '+hex(pc))
        w=u32(self.module,pc-0x08804000);op=w>>26;rs=(w>>21)&31;rt=(w>>16)&31;rd=(w>>11)&31;fn=w&63;fd=(w>>6)&31
        imm=struct.unpack('<h',struct.pack('<H',w&65535))[0];target=None;name=''
        if w==0:name='nop'
        elif op==9:self.g[rt]=(self.g[rs]+imm)&0xffffffff;name='addiu'
        elif op==13:self.g[rt]=self.g[rs]|(w&65535);name='ori'
        elif op==15:self.g[rt]=(w&65535)<<16;name='lui'
        elif op==0 and fn in(0x21,0x25):self.g[rd]=((self.g[rs]+self.g[rt])if fn==0x21 else(self.g[rs]|self.g[rt]))&0xffffffff;name='addu/or'
        elif op==0 and fn in(8,9):
            check(not delay,'Nested branch delay control');target=self.g[rs]
            if fn==9:self.g[rd]=pc+8
            name='jr/jalr'
        elif op==3:self.g[31]=pc+8;target=((pc+4)&0xf0000000)|((w&0x3ffffff)<<2);name='jal'
        elif op==0x23:self.g[rt]=self.load((self.g[rs]+imm)&0xffffffff);name='lw'
        elif op==0x21:
            a=(self.g[rs]+imm)&0xffffffff;check(a%2==0,'Misaligned original halfword');v=(self.load(a&~3)>>(8*(a&3)))&65535;self.g[rt]=(v-65536 if v&32768 else v)&0xffffffff;name='lh'
        elif op==0x2b:self.store((self.g[rs]+imm)&0xffffffff,self.g[rt],pc);name='sw'
        elif op==0x31:self.f[rt]=self.load((self.g[rs]+imm)&0xffffffff);name='lwc1'
        elif op==0x39:self.store((self.g[rs]+imm)&0xffffffff,self.f[rt],pc);name='swc1'
        elif op==0x11 and rs==0:self.g[rt]=self.f[rd];name='mfc1'
        elif op==0x11 and rs==4:self.f[rd]=self.g[rt];name='mtc1'
        elif op==0x11 and rs==16 and fn==6:self.f[fd]=self.f[rd];name='mov.s'
        elif op==0x11 and rs==16 and fn in(0,1,2):
            x,y=number(self.f[rd]),number(self.f[rt]);self.f[fd]=bits(x+y if fn==0 else x-y if fn==1 else x*y);name='COP1 arithmetic'
        elif op==0x12 and rs==7:
            check(w&0xff80==0,'Unknown mtv control encoding');self.v[vindices(w&127,1)[0]]=self.g[rt];name='mtv'
        elif op in(0x32,0x36,0x3a,0x3e):
            quad=op in(0x36,0x3e);reg=rt|((w&1)<<5)if quad else rt|((w&3)<<5);offset=w&0xfffc;offset-=65536 if offset&32768 else 0;a=(self.g[rs]+offset)&0xffffffff
            for k,index in enumerate(vindices(reg,4 if quad else 1)):
                if op in(0x32,0x36):self.v[index]=self.load(a+4*k)
                else:check(self.v[index]is not None,'Uninitialized vector store');self.store(a+4*k,self.v[index],pc)
            name='lv/sv'
        elif w>>24 in(0xdc,0xdd,0xde):self.prefix[(w>>24)-0xdc]=w&0xfffff;name='vpfx'
        else:
            vd,vs,vt=w&127,(w>>8)&127,(w>>16)&127;n=1+((w>>7)&1)+2*((w>>15)&1);code=w&0xff800000
            check(self.prefix[2]==0,'Unsupported VFPU destination prefix')
            if w&0xffff0000==0xd0060000:values=[bits(-0.0 if(self.prefix[0]>>(16+k))&1 else 0.)for k in range(n)];name='vzero'
            elif code in(0x60000000,0x60800000,0x64000000,0x65000000):
                left=self.swizzle(self.vector(vs,n),self.prefix[0])
                if code==0x65000000:
                    check(self.prefix[1]==0xe4,'Unsupported active VSCL T prefix');scalar=self.vector(vt,1)[0];check(scalar is not None,'Uninitialized VSCL scalar');right=[scalar]*n
                else:right=self.swizzle(self.vector(vt,n),self.prefix[1])
                values=[bits(number(x)+number(y)if code==0x60000000 else number(x)-number(y)if code==0x60800000 else number(x)*number(y))for x,y in zip(left,right)]
                name='VFPU arithmetic'
            else:raise ValueError('Unsupported original vector opcode '+hex(w)+' at '+hex(pc))
            for index,value in zip(vindices(vd,n),values):check(math.isfinite(number(value)),'Nonfinite VFPU result');self.v[index]=value
            self.prefix=[0xe4,0xe4,0]
        self.g[0]=0;self.trace.append(dict(pc=pc,word=w,instruction=name));return target
    def run_checked(self,start,stop,checkpoints=None):
        pc=start;stages=checkpoints or {};visited=[]
        while pc!=stop:
            check(len(self.trace)<2048,'Original vector instruction bound')
            if pc in stages:stages[pc](self);visited.append(pc)
            target=self.execute(pc)
            if target is None:pc+=4
            else:self.execute(pc+4,True);pc=target
        check(set(visited)==set(stages),'Missing original vector execution checkpoint')
        return b''.join(struct.pack('<I',self.load(self.parameter+k))for k in range(0,self.size,4))
