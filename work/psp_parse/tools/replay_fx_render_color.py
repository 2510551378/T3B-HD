"""Finite scalar MIPS/COP1 reference for original RGB mode selection and palette modulation."""
import math
import struct
from analyze_fx_node_time import bits,check,number,signed,u32


class Machine:
    def __init__(self,module,g,f):
        self.module=module;self.g=list(g);self.f=list(f);self.mem={};self.writable=[];self.trace=[];self.cc=None

    def retain(self,address,raw,write=False):
        for i,b in enumerate(raw):
            check(address+i not in self.mem or self.mem[address+i]==b,'Contradictory reference regions');self.mem[address+i]=b
        if write:self.writable.append((address,address+len(raw)))

    def load(self,a,n):
        check(all(a+i in self.mem for i in range(n)),'Unretained scalar color load '+hex(a))
        return int.from_bytes(bytes(self.mem[a+i]for i in range(n)),'little')

    def store(self,a,value,n):
        check(any(lo<=a and a+n<=hi for lo,hi in self.writable),'Out-of-bounds color store')
        for i,b in enumerate((value&((1<<(8*n))-1)).to_bytes(n,'little')):self.mem[a+i]=b

    def execute(self,pc,delay=False):
        check(0x08b9a8e0<=pc<0x08b9aa84 or 0x08b5f684<=pc<0x08b5f780,'Unsupported color control flow '+hex(pc))
        w=u32(self.module,pc-0x08804000);op=w>>26;rs=(w>>21)&31;rt=(w>>16)&31;rd=(w>>11)&31;fd=(w>>6)&31;fn=w&63
        imm=struct.unpack('<h',struct.pack('<H',w&65535))[0];control=None
        if w==0:pass
        elif op==0:
            if fn==8:check(not delay,'Control in delay slot');control=(True,self.g[rs],False)
            elif fn==0:self.g[rd]=(self.g[rt]<<fd)&0xffffffff
            elif fn==0x21:self.g[rd]=(self.g[rs]+self.g[rt])&0xffffffff
            elif fn==0x25:self.g[rd]=self.g[rs]|self.g[rt]
            elif fn==0x2a:self.g[rd]=int(signed(self.g[rs])<signed(self.g[rt]))
            else:raise ValueError('Unknown original color integer opcode '+hex(w))
        elif op==9:self.g[rt]=(self.g[rs]+imm)&0xffffffff
        elif op==10:self.g[rt]=int(signed(self.g[rs])<imm)
        elif op==11:self.g[rt]=int(self.g[rs]<(imm&0xffffffff))
        elif op==13:self.g[rt]=self.g[rs]|(w&65535)
        elif op==15:self.g[rt]=(w&65535)<<16
        elif op in (4,5,20):
            check(not delay,'Integer branch in delay slot');take=self.g[rs]==self.g[rt]
            if op==5:take=not take
            control=(take,pc+4+imm*4,op==20)
        elif op in (0x23,0x24):self.g[rt]=self.load((self.g[rs]+imm)&0xffffffff,4 if op==0x23 else 1)
        elif op in (0x28,0x2b):self.store((self.g[rs]+imm)&0xffffffff,self.g[rt],1 if op==0x28 else 4)
        elif op==0x31:self.f[rt]=self.load((self.g[rs]+imm)&0xffffffff,4)
        elif op==0x39:self.store((self.g[rs]+imm)&0xffffffff,self.f[rt],4)
        elif op==0x11:
            if rs==0:self.g[rt]=self.f[rd]
            elif rs==4:self.f[rd]=self.g[rt]
            elif rs==8:
                check(not delay and self.cc is not None,'Unknown COP1 branch condition');control=(self.cc==bool(rt&1),pc+4+imm*4,bool(rt&2))
            elif rs==16 and fn in (0,1,2):
                a,b=number(self.f[rd]),number(self.f[rt]);check(math.isfinite(a)and math.isfinite(b),'Nonfinite original color operand')
                self.f[fd]=bits(a+b if fn==0 else a-b if fn==1 else a*b)
            elif rs==16 and fn in (60,62):
                a,b=number(self.f[rd]),number(self.f[rt]);check(math.isfinite(a)and math.isfinite(b),'Nonfinite color comparison')
                self.cc=a<b if fn==60 else a<=b
            elif rs==16 and fn==13:
                a=number(self.f[rd]);check(math.isfinite(a)and -2147483648<=a<2147483648,'Unsupported trunc.w.s domain');self.f[fd]=int(a)&0xffffffff
            elif rs==20 and fn==32:self.f[fd]=bits(signed(self.f[rd]))
            else:raise ValueError('Unsupported original color COP1 '+hex(w))
        else:raise ValueError('Unsupported scalar color opcode '+hex(w))
        self.g[0]=0;self.trace.append(dict(pc=pc,word=w));return control

    def run(self,start,stop):
        pc=start
        while pc!=stop:
            check(len(self.trace)<65536,'Original scalar color instruction bound')
            control=self.execute(pc)
            if control:
                take,target,likely=control
                if take or not likely:self.execute(pc+4,True)
                pc=target if take else pc+8
            else:pc+=4

    def bytes(self,address,size):return bytes(self.mem[address+i]for i in range(size))
