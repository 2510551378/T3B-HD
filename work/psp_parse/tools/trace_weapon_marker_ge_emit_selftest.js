// VM/Mock only: never creates a real WebSocket, PPSSPP process or visible window.
const fs=require('fs'),path=require('path'),os=require('os'),vm=require('vm'),assert=require('assert'),crypto=require('crypto');
const ENTRY=0x08b69b58,DISPATCH=0x08b69d64,RET=0x08b69d6c,BASE=0x08804000,HEADS=0x08cb1460,TAILS=0x08cb1960;
const cases=['type152','type155','descriptor2','descriptor4','stale-entry-context','gpr35','gpr36','no-input',
'wrong-resource','wrong-geometry','primary-null','bad-state','bad-resource-pointer','wrong-bone-count','wrong-vtype','wrong-vertex-count','wrong-pass',
'bad-entry-ra','bad-entry-sp','unsupported-D','bad-fep194','bad-record','bad-D-list','bad-D-count','unrelocated-D-list','unrelocated-def-pointer',
'bad-dispatch-sp','bad-dispatch-C','bad-dispatch-N','bad-dispatch-D','bad-dispatch-stackRA','bad-dispatch-saved-reg','bad-dispatch-B','bad-dispatch-type','bad-dispatch-index','bad-dispatch-target','bad-handler-object','bad-method-arg','bad-parameter-slot','bad-data-pointer','bad-filter','bad-registry-object','bad-vtable','bad-method-target','bad-handler-code',
'bad-return-sp','bad-return-ra','bad-callee-saved','bad-return-stack','bad-return-state-pointer','bad-return-geometry','bad-return-resource','bad-parameter-read','bad-data-read',
'short-gpr','negative-gpr','fractional-gpr','overflow-gpr','existing-bp','disabled-dispatch-bp','disabled-return-bp','bad-code','bad-disasm','short-read','entry-read-error','dispatch-read-error','return-read-error',
'missing-dispatch','missing-return','external-dispatch','external-return','queued-external-setup','add-timeout','add-timeout-own','add-timeout-external','dispatch-add-timeout','dispatch-add-timeout-own','dispatch-add-timeout-external','return-add-timeout','return-add-timeout-own','return-add-timeout-external',
'unresolved-resource-id','bad-source-table','bad-source-slot','bad-geometry-container','unsupported-152-branch','unsupported-155-branch',
'bad-matrix-sp','bad-matrix-ra','bad-matrix-output','bad-matrix-frame','bad-matrix-parent','bad-matrix-input','bad-matrix-mode','bad-matrix-return-sp','bad-matrix-return-ra','bad-matrix-callee','bad-matrix-finite',
'bad-view-sp','bad-view-ra','bad-view-kind','bad-view-input','bad-view-stack','bad-view-handler-matrix','bad-matrix-context','bad-dl-global','bad-dl-cursor','bad-view-packet',
'bad-geometry-sp','bad-geometry-ra','bad-geometry-id','bad-geometry-arg','bad-geometry-cursor','bad-geometry-dl',
'bad-emit-sp','bad-emit-ra','bad-emit-chain','bad-emit-handler-ra','bad-emit-primitive','bad-emit-index','bad-emit-count','bad-emit-morph','bad-emit-vtype','bad-emit-pointer','bad-emit-return-sp','bad-emit-return-ra','bad-emit-callee','bad-emit-cursor','bad-emit-packet','bad-emit-dl','bad-new-code','disabled-matrix-bp',
'missing-matrix-entry','missing-matrix-return','missing-view-entry','missing-geometry-entry','missing-emit-entry','missing-emit-return','external-matrix-entry','external-view-entry','external-emit-entry','external-emit-return','bad-155-draw-record','bad-155-draw-vtype','bad-155-matrix-frame','bad-155-emit-chain','bad-155-geometry-container','matrix-add-timeout','matrix-add-timeout-own','matrix-add-timeout-external','component-unaligned1','component-unaligned2','component-cross-word','component-last-ram-byte','component-low-pointer','component-field-outside','component-byte-mismatch','component-read-error','matrix-full-registers','bad-mode-global-pointer','bad-mode-global-matrix','bad-mode-helper-code','dl-uncached','dl-uncached155','dl-alias-lower-boundary','bad-dl-alias-low','bad-dl-alias-high','bad-dl-other-alias','bad-dl-kernel-alias','bad-dl-unaligned-alias','bad-dl-window-cross-alias','bad-dl-window-cross-normal','uncached-ordinary-matrix','uncached-ordinary-vertices'];

async function test(name){
 const root=path.resolve(__dirname,'..'),filename=path.join(__dirname,'trace_weapon_marker_ge_emit.js'),script=fs.readFileSync(filename,'utf8');
 const original=fs.readFileSync(path.join(root,'out/WEAPON_MARKER_STATE_20261020/original_source_match_section.bin'));
 const module=fs.readFileSync(path.join(root,'raw/ULJM05798_module_08804000.bin'));
 // Independent exact original anchors for the alternate function/callsite.
 for(const [pc,word]of[[ENTRY,0x27bdffd0],[0x08bbd850,0x0e2da6d6],[0x08bbd854,0x34070001],[DISPATCH,0x0140f809],[DISPATCH+4,0x01003025],[RET,0x92640015]])assert.equal(module.readUInt32LE(pc-BASE),word);
 for(const [pc,word]of[[0x08b66bb4,0x27bdff10],[0x08b982b4,0x0e2eee35],[0x08b9a76c,0x12400032],[0x08c01088,0x24030001],[0x08b6270c,0x27bdfff0],[0x08b6050c,0x27bdffe0],[0x08bfff98,0x308c0007],[0x08bba214,0x8fbf0000],[0x08b5e3b0,0x26100001]])assert.equal(module.readUInt32LE(pc-BASE),word);
 const snap=JSON.parse(fs.readFileSync(path.join(root,'out/AYA_BONE_GE_ACTIONS/slot0_fire_reverse120_world60/weapon_metadata_snapshot.json'),'utf8'));
 const pack=x=>{const b=Buffer.alloc(4*x.length);x.forEach((v,i)=>b.writeUInt32LE(v>>>0,i*4));return b;};
 const F=0x08d4d280,C=0x09a00000,P=0x097d2540,N=0x097d2340,E=0x097c0000,Q=0x09ff0000,H=0x09bd23c0,M=0x09ac0000,PAR=0x09ab0000,T=0x097c1000;
 const fep=Buffer.from(original),context=Buffer.alloc(0xa8),state=Buffer.alloc(0x1ac),node=Buffer.alloc(0x64),entry=Buffer.alloc(0x18),stack=Buffer.alloc(0xd0),matrix=Buffer.alloc(64),parent=Buffer.alloc(0x64),tailEntry=Buffer.alloc(8),actor=Buffer.alloc(0x1000),headArray=Buffer.alloc(0x500),tailArray=Buffer.alloc(0x500);
 for(let i=0;i<4;i++)matrix.writeFloatLE(1,i*20);
 const ds=[0x10ba0,0x10be8,0x10c30,0x10c78],di={'descriptor2':1,'type155':2,'descriptor4':3,'unsupported-155-branch':2,'bad-155-draw-record':2,'bad-155-draw-vtype':2,'bad-155-matrix-frame':2,'bad-155-emit-chain':2,'bad-155-geometry-container':2,'dl-uncached155':2}[name]||0,D=ds[di];
 for(const o of [8,0x28,0x2c])fep.writeUInt32LE(F+original.readUInt32LE(o),o);
 fep.writeUInt32LE(F+0xfb4,0x1d4);fep.writeUInt32LE(F+original.readUInt32LE(0xfb4+0x20),0xfb4+0x20);
 for(let i=0;i<4;i++){const p=original.readUInt32LE(0xfb4+0x20)+i*4;fep.writeUInt32LE(F+original.readUInt32LE(p),p);}
 for(const d of ds){
  for(const o of [0x1c,0x28,0x2c,0x3c])fep.writeUInt32LE(F+original.readUInt32LE(d+o),d+o);
  const defs=original.readUInt32LE(d+0x1c),seen=new Set();
  for(const [co,po] of [[0x19,0x3c],[0x14,0x28],[0x15,0x2c]]){
   const list=original.readUInt32LE(d+po);
   for(let j=0;j<original[d+co];j++){
    const index=original.readUInt16LE(list+j*2),bo=original.readUInt32LE(defs+index*4);
    fep.writeUInt32LE(F+bo,defs+index*4);
    if(!seen.has(bo)){seen.add(bo);const v=original.readUInt32LE(bo+8);if(v)fep.writeUInt32LE(F+v,bo+8);}
   }
  }
 }
 context.writeUInt32LE(P,0x8c);context.writeUInt32LE(N,0x90);state[0]=0x65;state.writeUInt32LE(H,0x144);state.writeUInt16LE(1,0x14c);
 state.writeUInt32LE(F,0x190);state.writeUInt32LE(F+0xfb4,0x194);state.writeUInt32LE(F+0x48f0,0x198);
 node.writeUInt32LE(E,0x3c);node.writeUInt32LE(F+D,0x40);node.writeUInt32LE(M,0x50);node.writeUInt32LE(M,0x54);
 for(const [o,v]of[[0x74,0x08b68ff0],[0xa0,0x08b69080],[0xb8,0x08b69a40],[0xc8,0x08b6a9e8]])stack.writeUInt32LE(v,o);
 actor.writeUInt32LE(snap.sourceBase,0x3c4);actor.writeUInt32LE(snap.metadata,0x3e8);
 const appended=['append','bad-oldtail-next'].includes(name);if(appended){headArray.writeUInt32LE(T,4);tailArray.writeUInt32LE(T,4);}
 if(name==='parents'){node.writeUInt32LE(PAR,0x18);node.writeUInt32LE(PAR,0x1c);parent.writeUInt32LE(M,0x50);parent.writeUInt32LE(M,0x54);}
 if(name==='wrong-resource')fep[0x48f0]^=1;
 if(name==='primary-null')state.writeUInt32LE(0,0x144);
 if(name==='bad-state')context.writeUInt32LE(0x0c000000,0x8c);
 if(name==='bad-resource-pointer')state.writeUInt32LE(0x0c000000,0x198);
 if(name==='bad-entry-sp'){} // register points outside guest RAM below
 if(name==='bad-node')context.writeUInt32LE(0x0c000000,0x90);
 if(name==='wrong-node-E')node.writeUInt32LE(E+4,0x3c);
 if(name==='unsupported-D')node.writeUInt32LE(F+0x10cc0,0x40);
 if(name==='bad-fep-base')state.writeUInt32LE(0x0bfff000,0x190);
 if(name==='bad-fep-magic')fep[0]^=1;
 if(name==='bad-fep-size')fep.writeUInt32LE(1,0x14);
 if(name==='bad-fep-count')fep.writeUInt16LE(94,0x1c);
 if(name==='bad-fep-offset8')fep.writeUInt32LE(F+0x4c,8);
 if(name==='bad-fep194')state.writeUInt32LE(F+0xfb8,0x194);
 if(name==='bad-record')fep[0x48f0+0x80]^=1;
 if(name==='bad-slot')fep.writeUInt32LE(F+0xfb8,0x1d4);
 if(name==='bad-D-count')fep[D+0x19]=255;
 if(name==='bad-D-list')fep.writeUInt32LE(0x0c000000,D+0x3c);
 if(name==='unrelocated-D-list')fep.writeUInt32LE(original.readUInt32LE(D+0x3c),D+0x3c);
 if(name==='unrelocated-def-table')fep.writeUInt32LE(original.readUInt32LE(D+0x1c),D+0x1c);
 if(name==='unrelocated-header-table')fep.writeUInt32LE(original.readUInt32LE(0x2c),0x2c);
 if(name==='unrelocated-nested-list')fep.writeUInt32LE(original.readUInt32LE(0xfb4+0x20),0xfb4+0x20);
 if(name==='bad-def-table')fep.writeUInt32LE(0x0c000000,D+0x1c);
 const list=original.readUInt32LE(D+0x3c),defs=original.readUInt32LE(D+0x1c),index=original.readUInt16LE(list),bo=original.readUInt32LE(defs+index*4);
 if(name==='bad-index')fep.writeUInt16LE(96,list);
 if(name==='bad-def-pointer')fep.writeUInt32LE(0x0c000000,defs+index*4);
 if(name==='unrelocated-def-pointer')fep.writeUInt32LE(bo,defs+index*4);
 if(name==='unrelocated-def-data')fep.writeUInt32LE(original.readUInt32LE(bo+8),bo+8);
 if(name==='bad-def-type')fep[bo]^=1;
 if(name==='bad-matrix')node.writeUInt32LE(0x0c000000,0x50);
 if(name==='bad-parent')node.writeUInt32LE(N,0x18);
 if(name==='nonfinite-matrix')matrix.writeFloatLE(Infinity,0);
 for(const [scenario,o]of[['bad-stack74',0x74],['bad-stacka0',0xa0],['bad-stackb8',0xb8],['bad-stackc8',0xc8]])if(name===scenario)stack.writeUInt32LE(0,o);
 const actorHeader=pack(snap.header),draw=pack(snap.drawWords);
 if(name==='wrong-bone-count')actorHeader.writeUInt16LE(2,6);
 if(name==='wrong-vtype')draw.writeUInt32LE(0x521,12);
 if(name==='wrong-vertex-count')draw.writeUInt16LE(242,4);
 const segments=[[BASE,module],[F,fep],[C,context],[P,state],[N,node],[E,entry],[Q,stack],[M,matrix],[PAR,parent],[T,tailEntry],
  [snap.object,actor],[snap.metadata,actorHeader],[snap.drawTable,draw],[snap.sourceBase,Buffer.concat(snap.records.map(r=>pack(r.words)))],[H,pack([snap.object])],[HEADS,headArray],[TAILS,tailArray]];
 const output=fs.mkdtempSync(path.join(os.tmpdir(),'weapon-ge-emit-selftest-'));
 const active=new Set(),commands=[];let phase='setup',maxActive=0,externalAt=null,firstReadFailure=false;

 const DATA=0x09aa0000,PARAM=0x09a90000,PTABLE=0x09a80000;
 const renderList=original.readUInt32LE(D+0x2c),rIndex=original.readUInt16LE(renderList),rDef=original.readUInt32LE(original.readUInt32LE(D+0x1c)+rIndex*4),typ=original.readUInt16LE(rDef),dataOffset=original.readUInt16LE(rDef+2);
 const target=typ===152?0x08b9809c:0x08b9a514,paramSize=typ===152?0x20:0x4c,dataSize=typ===152?7:0x20;
 const param=Buffer.alloc(paramSize),data=Buffer.alloc(original.readUInt16LE(D+2)),pt=Buffer.alloc(96*4),frame=Buffer.alloc(0x30);
 param.writeInt32LE(di===2?4:5,0xc);if(typ===152){param[0x1d]=1;param[0x1f]=1;}else param[0x4b]=1;
 const HF=typ===152?0xd0:0x110,HS=Q-0x30-HF,MR=typ===152?0x08b982b4:0x08b9a76c,GEOM=typ===152?0x08b6270c:0x08b6050c,GR=typ===152?0x08b98410:0x08b9acc0,ED=typ===152?0x70:0x80,ER=typ===152?0x08bba214:0x08b5e3b0;
 const DL=0x09a60000,CMD=name==='dl-alias-lower-boundary'?0x08000000:0x09a50000,VERT=0x09a40000,CONT=0x09a30000,OT=0x09a20000,OBJ=0x09a10000,COMP=0x09a70000,GM=0x09a78000,DR=0x09a05000;
 const CPU_CMD=['dl-uncached','dl-uncached155','dl-alias-lower-boundary'].includes(name)?CMD+0x40000000:CMD;
 const stackAll=Buffer.alloc(0x400),stackBase=Q-0x300,at=(a)=>a-stackBase;
 const dl=Buffer.alloc(0x20),cmd=Buffer.alloc(0x2000),verts=Buffer.alloc(16*4),cont=Buffer.alloc(0x24),objects=Buffer.alloc(8),obj=Buffer.alloc(0x20),component=Buffer.alloc(8),modeGlobalMatrix=Buffer.from(matrix),drawRecord=pack([4,0,4,VERT]);
 dl.writeUInt32LE(CPU_CMD,8);cont.writeUInt32LE(OT,0);objects.writeUInt32LE(OBJ,4);
 context.writeUInt32LE(CONT,0xa0);context.writeUInt32LE(CONT,0xa4);node.writeUInt32LE(0,0x54);
 const sourceField=typ===152?0x38:0x34,sourceTable=original.readUInt32LE(sourceField),sourceIndex=param.readInt32LE(0xc),sourceRecord=original.readUInt32LE(sourceTable+4*sourceIndex);
 fep.writeUInt32LE(F+sourceTable,sourceField);fep.writeUInt32LE(F+sourceRecord,sourceTable+sourceIndex*4);fep.writeInt32LE(1,sourceRecord+0x10);
 const matrixList=original.readUInt32LE(rDef+8),matrixIndex=original.readUInt16LE(matrixList+2);let componentPointer=COMP;
 if(name==='component-unaligned1')componentPointer=COMP+1;
 if(name==='component-unaligned2'||name==='component-byte-mismatch')componentPointer=COMP+2;
 if(name==='component-cross-word')componentPointer=COMP+3;
 if(name==='component-last-ram-byte')componentPointer=0x0bfffffe;
 if(name==='component-low-pointer')componentPointer=0x07ffffff;
 if(name==='component-field-outside')componentPointer=0x0bffffff;
 if(name==='component-unaligned2')component[3]=1;
 pt.writeUInt32LE(componentPointer,matrixIndex*4);
 segments.push([stackBase,stackAll],[DL,dl],[CMD,cmd],[VERT,verts],[CONT,cont],[OT,objects],[OBJ,obj],[COMP,component],[GM,modeGlobalMatrix],[DR,drawRecord],[0x08ca31d8,pack([DL])],[0x08c3b588,pack([M])],[0x08c3b58c,pack([name==='bad-mode-global-pointer'?0x0c000000:GM])],[0x0bfffffc,Buffer.alloc(4)]);
 if(name==='uncached-ordinary-matrix')node.writeUInt32LE(M+0x40000000,0x50);
 if(name==='bad-mode-global-matrix')modeGlobalMatrix.writeFloatLE(NaN,0);
 if(name==='unresolved-resource-id')fep.writeInt32LE(-1,sourceRecord+0x10);
 if(name==='bad-source-table')fep.writeUInt32LE(sourceTable,sourceField);
 if(name==='bad-source-slot')fep.writeUInt32LE(F+sourceRecord+4,sourceTable+sourceIndex*4);
 if(name==='bad-geometry-container'||name==='bad-155-geometry-container')context.writeUInt32LE(0x0c000000,typ===152?0xa0:0xa4);
 if(name==='unsupported-152-branch')param[0x1d]=0;
 if(name==='unsupported-155-branch'){param[0x1f]=0;param[0x4b]=0;}

 pt.writeUInt32LE(PARAM,rIndex*4);node.writeUInt32LE(DATA,0x44);node.writeUInt32LE(PTABLE,0x48);
 const regSlot=0x08c3a820+typ*4,regObj=module.readUInt32LE(regSlot-BASE),vt=module.readUInt32LE(regObj-BASE),vtBytes=Buffer.from(module.subarray(vt-BASE,vt-BASE+0x28));
 const slotRaw=pack([regObj]),objRaw=pack([vt]),filterAddress=0x08c3acc0+typ,filterWord=Buffer.from(module.subarray((filterAddress&~3)-BASE,(filterAddress&~3)-BASE+4));
 segments.push([DATA,data],[PARAM,param],[PTABLE,pt],[Q-0x30,frame],[regSlot,slotRaw],[regObj,objRaw],[vt,vtBytes],[filterAddress&~3,filterWord]);
 if(name==='stale-entry-context'){context.writeUInt32LE(0,0x8c);context.writeUInt32LE(0,0x90);}
 function entryRegs(){
  const g=Array(32).fill(0);g[4]=C;g[5]=P;g[6]=N;g[7]=1;g[29]=Q;g[31]=0x08bbd858;
  for(let i=16;i<=23;i++)g[i]=i*0x100;g[30]=0x3000;return g;
 }
 const oldEntry=entryRegs();for(const [r,o]of[[16,4],[17,8],[18,0xc],[19,0x10],[20,0x14],[21,0x18],[22,0x1c],[23,0x20]])frame.writeUInt32LE(oldEntry[r],o);frame.writeUInt32LE(oldEntry[31],0x24);
 function dispatchRegs(){const oldPhase=phase;phase='dispatch';const g=gprs();phase=oldPhase;return g;}
 function newRegs(){
  const g=dispatchRegs();g[29]=HS;g[31]=MR;
  const matrixPhase=phase==='matrix-entry'||phase==='matrix-return';
  if(matrixPhase){g[4]=C;g[5]=N;g[6]=M;g[7]=name==='component-unaligned2'?1:0;g[8]=HS+0x10;
  if(name==='component-byte-mismatch')g[7]=1;
   if(phase==='matrix-entry'){
    if(name==='bad-matrix-sp')g[29]+=4;if(name==='bad-matrix-ra')g[31]+=4;if(name==='bad-matrix-output')g[8]+=4;if(name==='bad-matrix-input')g[6]+=4;if(name==='bad-matrix-mode')g[7]=1;
   }else{if(name==='bad-matrix-return-sp')g[29]+=4;if(name==='bad-matrix-return-ra')g[31]+=4;if(name==='bad-matrix-callee')g[16]+=4;}
  }else if(phase==='view-entry'){
   g[29]=HS-0x60;g[31]=0x08bfff8c;g[4]=DL;g[5]=1;g[6]=HS-0x50;
   if(name==='bad-view-sp')g[29]+=4;if(name==='bad-view-ra')g[31]+=4;if(name==='bad-view-kind')g[5]=2;if(name==='bad-view-input')g[6]+=4;
  }else if(phase==='geometry-entry'){
   g[29]=HS;g[31]=GR;g[4]=typ===152?C:CONT;g[5]=1;g[6]=typ===152?0:HS;g[7]=HS;
   if(name==='bad-geometry-sp')g[29]+=4;if(name==='bad-geometry-ra')g[31]+=4;if(name==='bad-geometry-id')g[5]=2;if(name==='bad-geometry-arg')g[4]+=4;
  }else{
   g[29]=HS-ED;g[31]=ER;g[4]=4;g[5]=0x102;g[6]=4;g[7]=0;g[8]=VERT;if(typ===155){g[17]=0x102;g[19]=DR;}
   if(phase==='emit-entry'){
    if(name==='bad-emit-sp')g[29]+=4;if(name==='bad-emit-ra')g[31]+=4;if(name==='bad-emit-primitive')g[4]=8;if(name==='bad-emit-index')g[7]=VERT;if(name==='bad-emit-count')g[6]=0;if(name==='bad-emit-morph')g[5]|=1<<18;if(name==='bad-emit-vtype')g[5]=0;if(name==='bad-emit-pointer')g[8]=0x0c000000;if(name==='uncached-ordinary-vertices')g[8]=VERT+0x40000000;
   }else{if(name==='bad-emit-return-sp')g[29]+=4;if(name==='bad-emit-return-ra')g[31]+=4;if(name==='bad-emit-callee')g[16]+=4;}
  }
  if(name==='gpr35')g.push(ENTRY,0,0);if(name==='gpr36')g.push(ENTRY,0,0,0);return g;
 }
 function gprs(){
  if(['matrix-entry','matrix-return','view-entry','geometry-entry','emit-entry','emit-return'].includes(phase))return newRegs();
  const g=entryRegs();
  if(phase==='entry'){
   if(name==='bad-entry-ra')g[31]+=4;if(name==='bad-entry-sp')g[29]=0x0c000000;if(name==='wrong-pass')g[7]=0;if(name==='bad-state')g[5]=0x0c000000;
  }else{
   g[4]=regObj+vtBytes.readInt16LE(0x20);g[5]=C;g[6]=vt+0x20;g[7]=DATA+dataOffset;g[8]=PARAM;g[10]=target;
   g[16]=C;g[17]=N;g[18]=1;g[19]=F+D;g[20]=0;g[21]=F+renderList;g[22]=0x08c3acc0;g[23]=0x08c3a820;g[29]=Q-0x30;g[31]=0x08b6941c;
   if(phase==='dispatch'){
    if(name==='bad-dispatch-sp')g[29]+=4;if(name==='bad-dispatch-C')g[16]+=4;if(name==='bad-dispatch-N')g[17]+=4;if(name==='bad-dispatch-D')g[19]+=4;
    if(name==='bad-dispatch-index')g[20]=1;if(name==='bad-dispatch-target')g[10]+=4;if(name==='bad-handler-object')g[4]+=4;
    if(name==='bad-method-arg')g[6]+=4;if(name==='bad-data-pointer')g[7]+=4;
   }else{
    g[31]=RET;if(name==='bad-return-sp')g[29]+=4;if(name==='bad-return-ra')g[31]+=4;if(name==='bad-callee-saved')g[20]+=4;
   }
  }
  if(name==='gpr35')g.push(ENTRY,0,0);if(name==='gpr36')g.push(ENTRY,0,0,0);
  if(name==='short-gpr')g.length=31;if(name==='negative-gpr')g[4]=-1;if(name==='fractional-gpr')g[29]=1.5;if(name==='overflow-gpr')g[4]=0x100000000;
  return g;
 }
 function dispatch(){
  context.writeUInt32LE(P,0x8c);context.writeUInt32LE(N,0x90);context.writeUInt32LE(F+rDef,0x94);
  if(name==='bad-dispatch-stackRA')frame.writeUInt32LE(0,0x24);if(name==='bad-dispatch-saved-reg')frame.writeUInt32LE(0,4);
  if(name==='bad-dispatch-B')context.writeUInt32LE(F+rDef+4,0x94);if(name==='bad-dispatch-type')fep.writeUInt16LE(153,rDef);
  if(name==='bad-parameter-slot')pt.writeUInt32LE(PARAM+4,rIndex*4);if(name==='bad-filter')filterWord[filterAddress&3]|=1;
  if(name==='bad-registry-object')slotRaw.writeUInt32LE(regObj+4,0);if(name==='bad-vtable')objRaw.writeUInt32LE(vt+4,0);
  if(name==='bad-method-target')vtBytes.writeUInt32LE(target+4,0x24);
 }
 function initHandler(){
  const offsets=typ===152?[[16,0xb4],[17,0xb8],[18,0xbc],[19,0xc0],[20,0xc4],[21,0xc8]]:[[16,0xe0],[17,0xe4],[18,0xe8],[19,0xec],[20,0xf0],[21,0xf4],[22,0xf8],[23,0xfc],[30,0x100]];
  const g=dispatchRegs();for(const [r,o]of offsets)stackAll.writeUInt32LE(g[r],at(HS)+o);stackAll.writeUInt32LE(RET,at(HS)+(typ===152?0xcc:0x104));
  if(name==='bad-matrix-frame'||name==='bad-155-matrix-frame')stackAll.writeUInt32LE(0,at(HS)+(typ===152?0xcc:0x104));
  if(name==='bad-matrix-parent')node.writeUInt32LE(PAR,0x1c);
 }
 function advanceData(next){
  if(next==='matrix-entry'){initHandler();if(name==='bad-matrix-context')context.writeUInt32LE(P+4,0x8c);}
  if(next==='matrix-return'){matrix.copy(stackAll,at(HS+0x10));if(name==='bad-matrix-finite')stackAll.writeFloatLE(Infinity,at(HS+0x10));}
  if(next==='view-entry'){matrix.copy(stackAll,at(HS-0x50));stackAll.writeUInt32LE(0x08bbb924,at(HS-0x60));stackAll.writeUInt32LE(typ===152?0x08b982bc:0x08b9a840,at(HS-0x10));if(name==='bad-view-stack')stackAll.writeUInt32LE(0,at(HS-0x10));if(name==='bad-view-handler-matrix')stackAll.writeFloatLE(NaN,at(HS+0x10));if(name==='bad-dl-global')segments.push([0x08ca31d8,pack([0x0c000000])]);if(name==='bad-dl-cursor')dl.writeUInt32LE(0x0c000000,8);
    const badAlias={'bad-dl-alias-low':0x47fffffc,'bad-dl-alias-high':0x4c000000,'bad-dl-other-alias':0x88000000,'bad-dl-kernel-alias':0xc8a50000,'bad-dl-unaligned-alias':0x49a50002,'bad-dl-window-cross-alias':0x4bfffff0,'bad-dl-window-cross-normal':0x0bfffff0}[name];if(badAlias!==undefined)dl.writeUInt32LE(badAlias,8);}
  if(next==='geometry-entry'){
   const w=[0x3c000000,...[0,1,2,4,5,6,8,9,10,12,13,14].map(i=>(0x3d000000|(matrix.readUInt32LE(i*4)>>>8))>>>0)];pack(w).copy(cmd,0);dl.writeUInt32LE(CPU_CMD+52,8);
   if(name==='bad-view-packet')cmd[8]^=1;if(name==='bad-geometry-cursor')dl.writeUInt32LE(CPU_CMD+48,8);if(name==='bad-geometry-dl')segments.push([0x08ca31d8,pack([DL+4])]);
  }
  if(next==='emit-entry'){
   const chains=typ===152?[[0,0x08b5d53c],[0x44,0x08b5ddd4],[0x50,0x08b6274c],[0x60,GR]]:[[0x10,0x08b5ee08],[0x50,0x08b60558],[0x70,GR]];
   for(const [o,v]of chains)stackAll.writeUInt32LE(v,at(HS-ED)+o);
   frame.copy(stackAll,at(Q-0x30));if(name==='bad-155-draw-record')drawRecord.writeUInt32LE(VERT+4,12);if(name==='bad-155-draw-vtype')drawRecord.writeUInt32LE(8,8);if(name==='bad-emit-chain'||name==='bad-155-emit-chain')stackAll.writeUInt32LE(0,at(HS-ED)+chains[0][0]);if(name==='bad-emit-handler-ra')stackAll.writeUInt32LE(0,at(HS)+(typ===152?0xcc:0x104));
  }
  if(next==='emit-return'){
   const w=[0x12000102,0x10090000,0x01000000|(VERT&0xffffff),0x04040004];pack(w).copy(cmd,52);dl.writeUInt32LE(CPU_CMD+68,8);
   if(name==='bad-emit-cursor')dl.writeUInt32LE(CPU_CMD+72,8);if(name==='bad-emit-packet')cmd[52]^=1;if(name==='bad-emit-dl')segments.push([0x08ca31d8,pack([DL+4])]);
  }
 }
 function returned(){
  data[dataOffset]^=1;
  if(name==='bad-return-stack')frame.writeUInt32LE(0,0x24);if(name==='bad-return-state-pointer')context.writeUInt32LE(P+4,0x8c);
  if(name==='bad-return-resource')fep[0x48f0+0x80]^=1;
 }
 class MockWebSocket{
  static OPEN=1;
  constructor(){this.readyState=0;this.handlers=new Map();queueMicrotask(()=>{this.readyState=1;this.emit('open',{});});}
  addEventListener(event,fn,options={}){const a=this.handlers.get(event)||[];a.push({fn,once:options.once});this.handlers.set(event,a);}
  emit(event,v){for(const x of [...(this.handlers.get(event)||[])]){x.fn(v);if(x.once)this.handlers.set(event,this.handlers.get(event).filter(v=>v!==x));}}
  stop(pc,ticks){this.emit('message',{data:JSON.stringify({event:'cpu.stepping',pc,ticks})});}
  continueStage(address){
   const next=address===DISPATCH?'dispatch':address===MR?'matrix-return':address===0x08b66bb4?'matrix-entry':address===0x08c01088?'view-entry':address===GEOM?'geometry-entry':address===0x08bfff98?'emit-entry':address===ER?'emit-return':'return';
   if(name===`missing-${next}`)return;
   queueMicrotask(()=>{if(name===`external-${next}`){externalAt=commands.length;this.stop(0x08804100,next==='dispatch'?200:300);return;}phase=next;if(next==='dispatch')dispatch();else if(next==='return')returned();else advanceData(next);this.stop(address,100+100*(['dispatch','matrix-entry','matrix-return','view-entry','geometry-entry','emit-entry','emit-return','return'].indexOf(next)+1));});
  }
  send(text){
   const q=JSON.parse(text);commands.push(q);
   if(q.event==='cpu.resume'){for(const a of active)if(a!==ENTRY)this.continueStage(a);return;}
   const r={event:q.event,ticket:q.ticket};
   if(q.event==='version')r.version='offline-render-fixture';
   else if(q.event==='cpu.breakpoint.list')r.breakpoints=name==='existing-bp'?[{address:ENTRY,enabled:true}]:name==='disabled-dispatch-bp'?[{address:DISPATCH,enabled:false}]:name==='disabled-return-bp'?[{address:RET,enabled:false}]:name==='disabled-matrix-bp'?[{address:0x08b66bb4,enabled:false}]:[];
   else if(q.event==='cpu.breakpoint.add'){
    assert.equal(active.size,0);active.add(q.address);maxActive=Math.max(maxActive,active.size);
    const timeoutHere=name.startsWith('add-timeout')&&q.address===ENTRY||name.startsWith('dispatch-add-timeout')&&q.address===DISPATCH||name.startsWith('return-add-timeout')&&q.address===RET||name.startsWith('matrix-add-timeout')&&q.address===0x08b66bb4;
    if(timeoutHere){
     if(name.endsWith('-own'))queueMicrotask(()=>{phase=q.address===ENTRY?'entry':q.address===DISPATCH?'dispatch':q.address===0x08b66bb4?'matrix-entry':'return';if(phase==='dispatch')dispatch();if(phase==='return')returned();if(phase==='matrix-entry')advanceData(phase);this.stop(q.address,q.address===ENTRY?100:q.address===DISPATCH?200:300);});
     if(name.endsWith('-external'))queueMicrotask(()=>{externalAt=commands.length;this.stop(0x08804100,200);});return;
    }
    if(q.address===ENTRY){phase='entry';queueMicrotask(()=>this.stop(ENTRY,100));}
   }else if(q.event==='cpu.breakpoint.remove'){assert(active.has(q.address));active.delete(q.address);}
   else if(q.event==='memory.read'){
    const fail=name==='entry-read-error'&&phase==='entry'&&q.address===N||name==='dispatch-read-error'&&phase==='dispatch'&&q.address===Q-0x30||name==='return-read-error'&&phase==='return'&&q.address===P||name==='bad-parameter-read'&&phase==='dispatch'&&q.address===PARAM||name==='bad-data-read'&&phase==='dispatch'&&q.address===DATA+dataOffset||name==='component-read-error'&&phase==='matrix-entry'&&q.address===COMP;
    if(fail){r.event='error';r.error='injected guest read failure';}
    else{
     const s=(q.address>=stackBase&&q.address+q.size<=Q+0x100&&q.address<Q-0x30? [stackBase,stackAll]:null)||[...segments].reverse().find(([a,b])=>q.address>=a&&q.address+q.size<=a+b.length);assert(s,`missing read ${q.address.toString(16)}/${q.size}`);
     const b=Buffer.from(s[1].subarray(q.address-s[0],q.address-s[0]+q.size));
     if(s[1]===module){
      if(q.replacements!==false)b.writeUInt32LE(0x68012345,0);
      if(name==='bad-code'&&q.replacements===false&&q.address===ENTRY||name==='bad-handler-code'&&q.replacements===false&&q.address===target)b.writeUInt32LE(1,0);
      if(name==='bad-mode-helper-code'&&q.replacements===false&&q.address===0x08b6589c)b.writeUInt32LE(1,0);
      if(name==='bad-new-code'&&q.replacements===false&&q.address===0x08b66bb4)b.writeUInt32LE(1,0);
     }
     if(name==='wrong-geometry'&&q.size===243*16||name==='bad-return-geometry'&&phase==='return'&&q.size===243*16)b[0]^=1;
     if(name==='short-read'&&phase==='entry'&&!firstReadFailure){firstReadFailure=true;r.base64=b.subarray(0,b.length-4).toString('base64');}else r.base64=b.toString('base64');
    }
   }else if(q.event==='memory.disasm'){
    r.lines=[];for(let a=q.address;a<q.end;a+=a===q.address?8:4){const w=module.readUInt32LE(a-BASE);r.lines.push({type:a===q.address?'macro':'opcode',address:a,addressSize:a===q.address?8:4,encoding:w,macroEncoding:a===q.address?[w,module.readUInt32LE(a+4-BASE)]:null});}
    if(name==='bad-disasm')r.lines[0].macroEncoding[1]^=1;
    if(name==='queued-external-setup'&&q.address===ENTRY){externalAt=commands.length;queueMicrotask(()=>this.stop(0x08804100,50));}
   }else if(q.event==='cpu.getAllRegs'){
    r.categories=[{name:'MIPS GPR',uintValues:gprs()}];
    if(name==='matrix-full-registers'){r.categories.push({name:'FPU mock raw only',uintValues:Array.from({length:32},(_,i)=>0x3f800000+i)},{name:'VFPU mock raw only',uintValues:Array.from({length:128},(_,i)=>i)},{name:'VFPU control mock raw only',uintValues:[0,1,2,3,4,5,6,7,8,9,10]});r.extraFixtureEvidence={uninterpreted:true};}
   }
   else assert(['input.buttons.send','input.analog.send'].includes(q.event),q.event);
   queueMicrotask(()=>this.emit('message',{data:JSON.stringify(r)}));
  }
  close(){this.readyState=3;this.emit('close',{});}
 }
 const proc={env:{MARKER_GE_EMIT_OUT_DIR:output,MARKER_MAX_STOPS:'1',MARKER_MAX_ROWS:'1',MARKER_DURATION_MS:'1000',MARKER_STAGE_TIMEOUT_MS:'60'},on(){},exitCode:0};
 if(name!=='no-input'){proc.env.MARKER_BUTTONS_JSON='{"square":true,"select":true}';proc.env.MARKER_ANALOG_JSON='{"stick":"left","x":0.2,"y":0.3}';}
 const timeout=(fn,ms,...args)=>setTimeout(fn,name.includes('add-timeout')&&ms===10000?60:ms,...args);
 try{
  await vm.runInNewContext(script,{require,Buffer,WebSocket:MockWebSocket,process:proc,__dirname,__filename:filename,console:{log(){},error:console.error},setTimeout:timeout,clearTimeout,Date,Promise});
  const r=JSON.parse(fs.readFileSync(path.join(output,'marker_ge_emit.json'),'utf8'));
  const good=['type152','type155','descriptor2','descriptor4','stale-entry-context','gpr35','gpr36','no-input','component-unaligned1','component-unaligned2','component-cross-word','component-last-ram-byte','matrix-full-registers','dl-uncached','dl-uncached155','dl-alias-lower-boundary'].includes(name),negative=['wrong-resource','wrong-geometry','primary-null','bad-state','bad-resource-pointer','wrong-bone-count','wrong-vtype','wrong-vertex-count','wrong-pass'].includes(name);
  assert.equal(proc.exitCode,good||negative?0:1,`${name}: ${r.failure}`);assert.equal(active.size,0);assert(maxActive<=1);assert.equal(r.ownedBP,null);assert.equal(r.cleanup.errors.length,0);assert(r.cleanup.buttonsReleased&&r.cleanup.ownedBreakpointRemoved);
  assert.equal(r.producer.sha256,crypto.createHash('sha256').update(script).digest('hex'));assert(Object.values(commands.filter(x=>x.event==='input.buttons.send').at(-1).buttons).every(v=>v===false));
  if(name!=='no-input')assert(r.cleanup.analogReleased);else assert(!commands.filter(x=>x.event==='input.buttons.send').some(x=>Object.values(x.buttons).some(Boolean)));
  if(externalAt!==null)assert(!commands.slice(externalAt).some(x=>x.event==='cpu.resume'),'preserve external pause');
  if(good){
   assert.equal(r.failure,null);assert.equal(r.route,'alternate69b58');assert.equal(r.entryPC,ENTRY);assert.equal(r.dispatchPC,DISPATCH);assert.equal(r.returnPC,RET);assert(r.codeIdentity.checks.some(x=>x.address===ENTRY&&x.size===0x258));assert(r.codeIdentity.checks.some(x=>x.address===0x08bbd828&&x.size===0x3c));assert.equal(r.rows.length,1);const row=r.rows[0];assert.equal(row.classification,'observed_handler_invocation_return');assert.equal(row.geDrawObserved,false);assert.equal(row.semanticName,null);
   assert.equal(row.C,C);assert.equal(row.P,P);assert.equal(row.N,N);assert.equal(row.D,F+D);assert.equal(row.dispatch.sp,Q-0x30);assert.equal(row.returned.sp,Q-0x30);
   assert.equal(row.dispatch.actualType,typ);assert.equal(row.dispatch.target,target);assert.equal(row.dispatch.parameterPointer,PARAM);assert.equal(row.dispatch.mutableDataPointer,DATA+dataOffset);assert.equal(row.dispatch.expectedDelaySlotA2,PARAM);
   assert.equal(row.dispatch.gpr[6],vt+0x20);assert.equal(row.dispatch.parameterBefore.size,paramSize);assert.equal(row.dispatch.mutableDataBefore.size,dataSize);assert.equal(row.returned.mutableDataAfter.size,dataSize);
   assert.notEqual(row.dispatch.mutableDataBefore.raw.sha256,row.returned.mutableDataAfter.raw.sha256);assert.equal(row.entryGPR.length,32);assert.equal(row.returned.gpr.length,32);assert(r.codeIdentity.verified);
   assert.equal(r.firstStopTicks,100);assert.equal(r.lastStopTicks,900);assert.equal(r.entryStopCount,1);assert.equal(r.dispatchStopCount,1);assert.equal(r.returnStopCount,1);
   const schedule=[ENTRY,DISPATCH,0x08b66bb4,MR,0x08c01088,GEOM,0x08bfff98,ER,RET];
   const ops=commands.filter(x=>['cpu.breakpoint.add','cpu.breakpoint.remove'].includes(x.event)).map(x=>[x.event,x.address]);assert.deepEqual(ops,schedule.flatMap(a=>[['cpu.breakpoint.add',a],['cpu.breakpoint.remove',a]]));
   const ms=row.matrix.entry.modeSource;assert.equal(ms.componentPointer,componentPointer);assert.equal(ms.fieldAddress,componentPointer+1);assert.equal(ms.component.address,(componentPointer+1)&~3);assert.equal(ms.byteOffset,(componentPointer+1)&3);
   const completeRegs=JSON.parse(fs.readFileSync(row.matrix.entry.allRegisters.raw.file,'utf8'));assert.deepEqual(completeRegs.categories[0].uintValues.slice(0,32),row.matrix.entry.gpr);assert.equal(row.matrix.entry.allRegisters.f12Decoded,false);assert.equal(row.matrix.entry.allRegisters.f12Value,null);
   if(name==='matrix-full-registers'){assert.equal(completeRegs.categories.length,4);assert.equal(completeRegs.categories[1].uintValues[12],0x3f80000c);assert.equal(completeRegs.categories[3].uintValues[10],10);assert(completeRegs.extraFixtureEvidence.uninterpreted);assert.equal(row.matrix.entry.allRegisters.f12Availability,'raw_categories_uninterpreted');}else assert.equal(row.matrix.entry.allRegisters.f12Availability,'unavailable_gpr_only');
   assert.equal(row.matrix.entry.globalSlot.address,0x08c3b58c);assert.equal(row.matrix.entry.globalMatrix.address,GM);assert(r.codeIdentity.checks.some(x=>x.address===0x08b6589c&&x.size===0x104&&x.verified));assert(commands.filter(x=>x.event==='memory.read').every(x=>x.address%4===0));
   for(const [d,offset]of[[row.view.entry.dl,0],[row.geometryHelper.entry.dl,52],[row.emit.entry.dl,52],[row.emit.returned.dl,68]]){assert.equal(d.cursor,CPU_CMD+offset);assert.equal(d.readCursor,CMD+offset);}
   for(const [w,offset]of[[row.view.entry.packetBefore,0],[row.view.packetAtGeometry,0],[row.view.commandsThroughGeometry,0],[row.emit.entry.packetBefore,52],[row.emit.returned.packet,52]]){assert.equal(w.address,CPU_CMD+offset);assert.equal(w.readAddress,CMD+offset);}
   assert(commands.filter(x=>x.event==='memory.read').every(x=>x.address>=0x08000000&&x.address+x.size<=0x0c000000));
   assert.equal(r.probe,'cpu-ge-emit-v1');assert.equal(row.cpuCommandWriteObserved,true);assert.equal(row.cpuEmissionClassification,'observed_geometry_cpu_commands');assert.equal(row.emit.entry.vertexStride,10);assert.equal(row.emit.returned.packet.size,16);assert.equal(row.view.packetAtGeometry.size,52);assert.equal(row.geometrySource.runtimeId,1);assert.equal(Object.keys(r.stageStopCounts).length,9);
   const actual=fs.readFileSync(row.emit.returned.packet.raw.file);assert.equal(actual.toString('hex'),pack([0x12000102,0x10090000,0x01000000|(VERT&0xffffff),0x04040004]).toString('hex'));
  }else if(negative){assert.equal(r.failure,null);assert.equal(r.rows.length,0);assert.equal(r.targetEntryCount,0);assert(r.negativeScope);}
  else{assert(r.failure);assert.equal(r.rows.length,0);if(name.startsWith('missing-')||name.includes('-add-timeout'))assert(r.inFlight);}
  console.log(`PASS ${name}`);
 }finally{
  const absolute=path.resolve(output),relative=path.relative(path.resolve(os.tmpdir()),absolute);assert(relative&&!relative.startsWith('..')&&!path.isAbsolute(relative)&&path.basename(absolute).startsWith('weapon-ge-emit-selftest-'));fs.rmSync(absolute,{recursive:true,force:true});
 }
}
(async()=>{for(const x of cases)await test(x);console.log(`PASS all ${cases.length} offline GE-emit scenarios`);})().catch(e=>{console.error(e.stack||e);process.exitCode=1;});
