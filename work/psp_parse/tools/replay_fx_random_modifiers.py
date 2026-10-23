"""Bounded original type23/24 instruction replay; VRND outputs remain observed inputs."""
import math,struct
from analyze_fx_node_time import bits,number,signed,u32,check,sidecar,registers
from verify_weapon_ge_matrix_math import vindices

BASE=0x08804000

def vfpu_registers(item):
    import json
    c=next(c for c in json.loads(sidecar(item))['categories']if c['name']=='VFPU')
    check(len(c['uintValues'])==128,'Missing original VFPU data')
    out=[None]*128
    for encoded,value in enumerate(c['uintValues']):out[vindices(encoded,1)[0]]=value
    return out

class Machine:
    def __init__(self,module,row):
        self.module=module;self.row=row;self.g,self.f=map(list,registers(row['entry']['allRegisters']));self.v=vfpu_registers(row['entry']['allRegisters'])
        self.memory={};self.trace=[];self.stores=[];self.lo=0;self.injected=[];self.checkpoints={};self.visits={}
        before=row['entry']['before'];self.window=before['parameterWindow'];self.writable=[(self.window['address'],self.window['address']+self.window['size']),(self.g[29]-0x100,self.g[29]+4),(0x08cb0fa0,0x08cb0fb4)]
        self.retain(self.window['address'],sidecar(self.window['raw']))
        for address,key in [(self.g[5],'context'),(u32(sidecar(before['context']),0x90),'node')]:self.retain(address,sidecar(before[key]))
        rnd=row['random']
        # First loop stop precedes all generated-vector arithmetic. Quad loads
        # include an old stack W lane that is subsequently overwritten by vone.
        stack=rnd['channels'][0]['loop']['stack'];self.retain(stack['address'],sidecar(stack['raw']))
        for key in ('tables','vectorCache','vectorConstants','activeDefinitionHeader','targetOffset'):
            item=rnd[key];self.retain(item['address'],sidecar(item['raw']))
        self.retain(row['record']['address'],sidecar(row['record']['raw']))
        self.vrnd={};self.vrndVisits={};self.rng=[]
        def add(stage):self.checkpoints.setdefault(stage['stop']['pc'],[]).append(stage)
        for c in rnd['channels']:
            add(c['loop']);add(c['advanced'])
            if c['enabled']:
                add(c['ready'])
                if row['type']==23:
                    vr=c['vectorRandom'];add(vr);self.vrnd.setdefault(vr['stop']['pc']-4,[]).append(vfpu_registers(vr['allRegisters']))
                for call in c['rng']:
                    self.rng.append(call);add(call['entry']);add(call['return'])
        if self.rng:
            item=self.rng[0]['entry']['seedRoot'];self.retain(item['address'],sidecar(item['raw']))
            item=self.rng[0]['entry']['seed'];self.retain(item['address'],sidecar(item['raw']));self.writable.append((item['address'],item['address']+4))
    def retain(self,address,raw):
        for i,b in enumerate(raw):check(address+i not in self.memory or self.memory[address+i]==b,'Conflicting retained region');self.memory[address+i]=b
    def load(self,address,n=4):
        check(all(address+i in self.memory for i in range(n)),'Unretained original read '+hex(address));return int.from_bytes(bytes(self.memory[address+i]for i in range(n)),'little')
    def store(self,address,value,pc):
        check(address%4==0 and any(lo<=address and address+4<=hi for lo,hi in self.writable),'Unbounded original write '+hex(address))
        for i,b in enumerate(struct.pack('<I',value)):self.memory[address+i]=b
        self.stores.append(dict(pc=pc,address=address,bits=value))
    def window_bytes(self):return bytes(self.memory[self.window['address']+i]for i in range(self.window['size']))
    def checkpoint(self,pc):
        if pc not in self.checkpoints:return
        index=self.visits.get(pc,0);check(index<len(self.checkpoints[pc]),'Unexpected original loop iteration');stage=self.checkpoints[pc][index];self.visits[pc]=index+1
        check(self.window_bytes()==sidecar(stage['snapshot']['parameterWindow']['raw']),'Original intermediate parameter bytes differ at '+hex(pc))
        g,_=registers(stage['allRegisters']);check(self.g[29]==g[29],'Original stack pointer differs')
        if 'seed'in stage:
            check(self.load(stage['seed']['address'])==u32(sidecar(stage['seed']['raw'])),'Actual LCG seed chain differs')
            if pc!=0x08afc000:check(self.g[2]==g[2],'Actual LCG return differs')
        if pc in (0x08bb8f90,0x08bb97f0):
            actual=sidecar(stage['stack']['raw']);check(bytes(self.memory[self.g[29]+i]for i in range(12))==actual[:12],'Actual generated vector differs')
        actual_v=vfpu_registers(stage['allRegisters'])
        # Compare data lanes written by arithmetic/loads since entry; register
        # layout is debugger scalar encoding -> pinned software physical layout.
        check(self.v==actual_v,'Actual VFPU data differs at '+hex(pc))
    def execute(self,pc,delay=False):
        check(0x08bb8cbc<=pc<0x08bb9048 or 0x08bb94fc<=pc<0x08bb98e4 or 0x08afc000<=pc<0x08afc034,'Unsupported original control flow '+hex(pc))
        w=u32(self.module,pc-BASE);op=w>>26;rs=(w>>21)&31;rt=(w>>16)&31;rd=(w>>11)&31;fn=w&63;fd=(w>>6)&31
        imm=struct.unpack('<h',struct.pack('<H',w&65535))[0];control=None
        if w==0:pass
        elif op==9:self.g[rt]=(self.g[rs]+imm)&0xffffffff
        elif op==13:self.g[rt]=self.g[rs]|(w&65535)
        elif op==12:self.g[rt]=self.g[rs]&(w&65535)
        elif op==15:self.g[rt]=(w&65535)<<16
        elif op==10:self.g[rt]=int(signed(self.g[rs])<imm)
        elif op==0 and fn in(0x21,0x25,0x24):self.g[rd]=((self.g[rs]+self.g[rt])if fn==0x21 else(self.g[rs]|self.g[rt])if fn==0x25 else(self.g[rs]&self.g[rt]))&0xffffffff
        elif op==0 and fn==0x18:self.lo=(self.g[rs]*self.g[rt])&0xffffffff
        elif op==0 and fn==0x12:self.g[rd]=self.lo
        elif op==0 and fn==8:control=(True,self.g[rs],False)
        elif op==3:self.g[31]=pc+8;control=(True,((pc+4)&0xf0000000)|((w&0x3ffffff)<<2),False)
        elif op in(4,5,6,7,0x14,0x15,0x16,0x17):
            base=op&15;take=self.g[rs]==self.g[rt]if base==4 else self.g[rs]!=self.g[rt]if base==5 else signed(self.g[rs])<=0 if base==6 else signed(self.g[rs])>0
            control=(take,pc+4+4*imm,op>=0x14)
        elif op==1:
            check(rt in(0,2),'Unsupported REGIMM');control=(signed(self.g[rs])<0,pc+4+4*imm,rt==2)
        elif op in(0x23,0x24,0x25):self.g[rt]=self.load((self.g[rs]+imm)&0xffffffff,{0x23:4,0x24:1,0x25:2}[op])
        elif op==0x2b:self.store((self.g[rs]+imm)&0xffffffff,self.g[rt],pc)
        elif op==0x31:self.f[rt]=self.load((self.g[rs]+imm)&0xffffffff)
        elif op==0x39:self.store((self.g[rs]+imm)&0xffffffff,self.f[rt],pc)
        elif op==0x11 and rs==0:self.g[rt]=self.f[rd]
        elif op==0x11 and rs==4:self.f[rd]=self.g[rt]
        elif op==0x11 and rs==20 and fn==32:self.f[fd]=bits(signed(self.f[rd]))
        elif op==0x11 and rs==16 and fn in(0,1,2):
            x,y=number(self.f[rd]),number(self.f[rt]);self.f[fd]=bits(x+y if fn==0 else x-y if fn==1 else x*y)
        elif op==0x12 and rs==7:
            check(w&0xff80==0,'Unknown VFPU control transfer');self.v[vindices(w&127,1)[0]]=self.g[rt]
        elif op in(0x32,0x36,0x3a,0x3e):
            quad=op in(0x36,0x3e);reg=rt|((w&1)<<5)if quad else rt|((w&3)<<5);offset=w&0xfffc;offset-=65536 if offset&32768 else 0;address=(self.g[rs]+offset)&0xffffffff
            for k,index in enumerate(vindices(reg,4 if quad else 1)):
                if op in(0x32,0x36):self.v[index]=self.load(address+k*4)
                else:self.store(address+k*4,self.v[index],pc)
        else:
            vd,vs,vt=w&127,(w>>8)&127,(w>>16)&127;n=1+((w>>7)&1)+2*((w>>15)&1);code=w&0xff800000
            if w&0xffff0000==0xd0230000:
                index=self.vrndVisits.get(pc,0);check(pc in self.vrnd and index<len(self.vrnd[pc]),'Missing observed VRND output');observed=self.vrnd[pc][index];self.vrndVisits[pc]=index+1
                values=[observed[index]for index in vindices(vd,n)];check(all(2<=number(v)<4 for v in values),'Observed VRNDF2 outside source range');self.injected.append(dict(pc=pc,bits=values))
            elif w&0xffff0000==0xd0070000:values=[bits(1.)]*n
            elif w&0xffff0000==0xd0060000:values=[bits(0.)]*n
            elif code in(0x60000000,0x60800000,0x64000000,0x65000000):
                left=[self.v[i]for i in vindices(vs,n)];right=[self.v[i]for i in vindices(vt,1 if code==0x65000000 else n)]
                if code==0x65000000:right*=n
                values=[bits(number(x)+number(y)if code==0x60000000 else number(x)-number(y)if code==0x60800000 else number(x)*number(y))for x,y in zip(left,right)]
            else:raise ValueError('Unsupported original modifier opcode '+hex(w)+' at '+hex(pc))
            for index,value in zip(vindices(vd,n),values):check(math.isfinite(number(value)),'Nonfinite modifier result');self.v[index]=value
        self.g[0]=0;self.trace.append(dict(pc=pc,word=w));check(not(delay and control),'Nested delay-slot control');return control
    def run(self,reference_only=False):
        pc=self.row['target'];stop=self.row['return']['stop']['pc']
        while pc!=stop:
            check(len(self.trace)<4096,'Modifier instruction bound')
            if not reference_only:self.checkpoint(pc)
            control=self.execute(pc)
            if control:
                take,target,likely=control
                if take or not likely:self.execute(pc+4,True)
                pc=target if take else pc+8
            else:pc+=4
        if not reference_only:
            check(all(self.visits.get(pc,0)==len(stages)for pc,stages in self.checkpoints.items()),'Unconsumed actual callback checkpoint')
            check(self.window_bytes()==sidecar(self.row['return']['after']['parameterWindow']['raw']),'Actual complete modifier return bytes differ')
        return dict(instructions=len(self.trace),trace=self.trace,stores=self.stores,observed_VRND_outputs=self.injected,all_parameter_bytes_equal=True)
