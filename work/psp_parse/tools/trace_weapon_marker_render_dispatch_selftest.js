// VM/Mock only: never creates a real WebSocket, PPSSPP process or visible window.
const fs=require('fs'),path=require('path'),os=require('os'),vm=require('vm'),assert=require('assert'),crypto=require('crypto');
const ENTRY=0x08b692f4,DISPATCH=0x08b694f4,RET=0x08b694fc,BASE=0x08804000,HEADS=0x08cb1460,TAILS=0x08cb1960;
const cases=['type152','type155','descriptor2','descriptor4','stale-entry-context','gpr35','gpr36','no-input',
'wrong-resource','wrong-geometry','primary-null','bad-state','bad-resource-pointer','wrong-bone-count','wrong-vtype','wrong-vertex-count','wrong-pass',
'bad-entry-ra','bad-entry-sp','unsupported-D','bad-fep194','bad-record','bad-D-list','bad-D-count','unrelocated-D-list','unrelocated-def-pointer',
'bad-dispatch-sp','bad-dispatch-C','bad-dispatch-N','bad-dispatch-D','bad-dispatch-stackRA','bad-dispatch-saved-reg','bad-dispatch-B','bad-dispatch-type','bad-dispatch-index','bad-dispatch-target','bad-handler-object','bad-method-arg','bad-parameter-slot','bad-data-pointer','bad-filter','bad-registry-object','bad-vtable','bad-method-target','bad-handler-code',
'bad-return-sp','bad-return-ra','bad-callee-saved','bad-return-stack','bad-return-state-pointer','bad-return-geometry','bad-return-resource','bad-parameter-read','bad-data-read',
'short-gpr','negative-gpr','fractional-gpr','overflow-gpr','existing-bp','disabled-dispatch-bp','disabled-return-bp','bad-code','bad-disasm','short-read','entry-read-error','dispatch-read-error','return-read-error',
'missing-dispatch','missing-return','external-dispatch','external-return','queued-external-setup','add-timeout','add-timeout-own','add-timeout-external','dispatch-add-timeout','dispatch-add-timeout-own','dispatch-add-timeout-external','return-add-timeout','return-add-timeout-own','return-add-timeout-external'];

async function test(name){
 const root=path.resolve(__dirname,'..'),filename=path.join(__dirname,'trace_weapon_marker_render_dispatch.js'),script=fs.readFileSync(filename,'utf8');
 const original=fs.readFileSync(path.join(root,'out/WEAPON_MARKER_STATE_20261020/original_source_match_section.bin'));
 const module=fs.readFileSync(path.join(root,'raw/ULJM05798_module_08804000.bin'));
 const snap=JSON.parse(fs.readFileSync(path.join(root,'out/AYA_BONE_GE_ACTIONS/slot0_fire_reverse120_world60/weapon_metadata_snapshot.json'),'utf8'));
 const pack=x=>{const b=Buffer.alloc(4*x.length);x.forEach((v,i)=>b.writeUInt32LE(v>>>0,i*4));return b;};
 const F=0x08d4d280,C=0x09a00000,P=0x097d2540,N=0x097d2340,E=0x097c0000,Q=0x09ff0000,H=0x09bd23c0,M=0x09ac0000,PAR=0x09ab0000,T=0x097c1000;
 const fep=Buffer.from(original),context=Buffer.alloc(0xa8),state=Buffer.alloc(0x1ac),node=Buffer.alloc(0x64),entry=Buffer.alloc(0x18),stack=Buffer.alloc(0xd0),matrix=Buffer.alloc(64),parent=Buffer.alloc(0x64),tailEntry=Buffer.alloc(8),actor=Buffer.alloc(0x1000),headArray=Buffer.alloc(0x500),tailArray=Buffer.alloc(0x500);
 for(let i=0;i<4;i++)matrix.writeFloatLE(1,i*20);
 const ds=[0x10ba0,0x10be8,0x10c30,0x10c78],di={'descriptor2':1,'type155':2,'descriptor4':3}[name]||0,D=ds[di];
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
 const output=fs.mkdtempSync(path.join(os.tmpdir(),'weapon-render-selftest-'));
 const active=new Set(),commands=[];let phase='setup',maxActive=0,externalAt=null,firstReadFailure=false;

 const DATA=0x09aa0000,PARAM=0x09a90000,PTABLE=0x09a80000;
 const renderList=original.readUInt32LE(D+0x2c),rIndex=original.readUInt16LE(renderList),rDef=original.readUInt32LE(original.readUInt32LE(D+0x1c)+rIndex*4),typ=original.readUInt16LE(rDef),dataOffset=original.readUInt16LE(rDef+2);
 const target=typ===152?0x08b9809c:0x08b9a514,paramSize=typ===152?0x20:0x4c,dataSize=typ===152?7:0x20;
 const param=Buffer.alloc(paramSize,0x31),data=Buffer.alloc(original.readUInt16LE(D+2),0x42),pt=Buffer.alloc((rIndex+1)*4),frame=Buffer.alloc(0x30);
 pt.writeUInt32LE(PARAM,rIndex*4);node.writeUInt32LE(DATA,0x44);node.writeUInt32LE(PTABLE,0x48);
 const regSlot=0x08c3a820+typ*4,regObj=module.readUInt32LE(regSlot-BASE),vt=module.readUInt32LE(regObj-BASE),vtBytes=Buffer.from(module.subarray(vt-BASE,vt-BASE+0x28));
 const slotRaw=pack([regObj]),objRaw=pack([vt]),filterAddress=0x08c3acc0+typ,filterWord=Buffer.from(module.subarray((filterAddress&~3)-BASE,(filterAddress&~3)-BASE+4));
 segments.push([DATA,data],[PARAM,param],[PTABLE,pt],[Q-0x30,frame],[regSlot,slotRaw],[regObj,objRaw],[vt,vtBytes],[filterAddress&~3,filterWord]);
 if(name==='stale-entry-context'){context.writeUInt32LE(0,0x8c);context.writeUInt32LE(0,0x90);}
 function entryRegs(){
  const g=Array(32).fill(0);g[4]=C;g[5]=P;g[6]=N;g[7]=1;g[29]=Q;g[31]=0x08b69558;
  for(let i=16;i<=23;i++)g[i]=i*0x100;g[30]=0x3000;return g;
 }
 const oldEntry=entryRegs();for(const [r,o]of[[16,4],[17,8],[18,0xc],[19,0x10],[20,0x14],[21,0x18],[22,0x1c],[23,0x20]])frame.writeUInt32LE(oldEntry[r],o);frame.writeUInt32LE(oldEntry[31],0x24);
 function gprs(){
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
   const next=address===DISPATCH?'dispatch':'return';
   if(name===`missing-${next}`)return;
   queueMicrotask(()=>{if(name===`external-${next}`){externalAt=commands.length;this.stop(0x08804100,next==='dispatch'?200:300);return;}phase=next;if(next==='dispatch')dispatch();else returned();this.stop(address,next==='dispatch'?200:300);});
  }
  send(text){
   const q=JSON.parse(text);commands.push(q);
   if(q.event==='cpu.resume'){if(active.has(DISPATCH))this.continueStage(DISPATCH);if(active.has(RET))this.continueStage(RET);return;}
   const r={event:q.event,ticket:q.ticket};
   if(q.event==='version')r.version='offline-render-fixture';
   else if(q.event==='cpu.breakpoint.list')r.breakpoints=name==='existing-bp'?[{address:ENTRY,enabled:true}]:name==='disabled-dispatch-bp'?[{address:DISPATCH,enabled:false}]:name==='disabled-return-bp'?[{address:RET,enabled:false}]:[];
   else if(q.event==='cpu.breakpoint.add'){
    assert.equal(active.size,0);active.add(q.address);maxActive=Math.max(maxActive,active.size);
    const timeoutHere=name.startsWith('add-timeout')&&q.address===ENTRY||name.startsWith('dispatch-add-timeout')&&q.address===DISPATCH||name.startsWith('return-add-timeout')&&q.address===RET;
    if(timeoutHere){
     if(name.endsWith('-own'))queueMicrotask(()=>{phase=q.address===ENTRY?'entry':q.address===DISPATCH?'dispatch':'return';if(phase==='dispatch')dispatch();if(phase==='return')returned();this.stop(q.address,q.address===ENTRY?100:q.address===DISPATCH?200:300);});
     if(name.endsWith('-external'))queueMicrotask(()=>{externalAt=commands.length;this.stop(0x08804100,200);});return;
    }
    if(q.address===ENTRY){phase='entry';queueMicrotask(()=>this.stop(ENTRY,100));}
   }else if(q.event==='cpu.breakpoint.remove'){assert(active.has(q.address));active.delete(q.address);}
   else if(q.event==='memory.read'){
    const fail=name==='entry-read-error'&&phase==='entry'&&q.address===N||name==='dispatch-read-error'&&phase==='dispatch'&&q.address===Q-0x30||name==='return-read-error'&&phase==='return'&&q.address===P||name==='bad-parameter-read'&&phase==='dispatch'&&q.address===PARAM||name==='bad-data-read'&&phase==='dispatch'&&q.address===DATA+dataOffset;
    if(fail){r.event='error';r.error='injected guest read failure';}
    else{
     const s=[...segments].reverse().find(([a,b])=>q.address>=a&&q.address+q.size<=a+b.length);assert(s,`missing read ${q.address.toString(16)}/${q.size}`);
     const b=Buffer.from(s[1].subarray(q.address-s[0],q.address-s[0]+q.size));
     if(s[1]===module&&[ENTRY,0x08b69540,DISPATCH,RET,target].includes(q.address)){
      if(q.replacements!==false)b.writeUInt32LE(0x68012345,0);
      if(name==='bad-code'&&q.replacements===false&&q.address===ENTRY||name==='bad-handler-code'&&q.replacements===false&&q.address===target)b.writeUInt32LE(1,0);
     }
     if(name==='wrong-geometry'&&q.size===243*16||name==='bad-return-geometry'&&phase==='return'&&q.size===243*16)b[0]^=1;
     if(name==='short-read'&&phase==='entry'&&!firstReadFailure){firstReadFailure=true;r.base64=b.subarray(0,b.length-4).toString('base64');}else r.base64=b.toString('base64');
    }
   }else if(q.event==='memory.disasm'){
    r.lines=[];for(let a=q.address;a<q.end;a+=a===q.address?8:4){const w=module.readUInt32LE(a-BASE);r.lines.push({type:a===q.address?'macro':'opcode',address:a,addressSize:a===q.address?8:4,encoding:w,macroEncoding:a===q.address?[w,module.readUInt32LE(a+4-BASE)]:null});}
    if(name==='bad-disasm')r.lines[0].macroEncoding[1]^=1;
    if(name==='queued-external-setup'&&q.address===ENTRY){externalAt=commands.length;queueMicrotask(()=>this.stop(0x08804100,50));}
   }else if(q.event==='cpu.getAllRegs')r.categories=[{name:'MIPS GPR',uintValues:gprs()}];
   else assert(['input.buttons.send','input.analog.send'].includes(q.event),q.event);
   queueMicrotask(()=>this.emit('message',{data:JSON.stringify(r)}));
  }
  close(){this.readyState=3;this.emit('close',{});}
 }
 const proc={env:{MARKER_RENDER_OUT_DIR:output,MARKER_MAX_STOPS:'1',MARKER_MAX_ROWS:'1',MARKER_DURATION_MS:'1000',MARKER_STAGE_TIMEOUT_MS:'60'},on(){},exitCode:0};
 if(name!=='no-input'){proc.env.MARKER_BUTTONS_JSON='{"square":true,"select":true}';proc.env.MARKER_ANALOG_JSON='{"stick":"left","x":0.2,"y":0.3}';}
 const timeout=(fn,ms,...args)=>setTimeout(fn,name.includes('add-timeout')&&ms===10000?60:ms,...args);
 try{
  await vm.runInNewContext(script,{require,Buffer,WebSocket:MockWebSocket,process:proc,__dirname,__filename:filename,console:{log(){},error:console.error},setTimeout:timeout,clearTimeout,Date,Promise});
  const r=JSON.parse(fs.readFileSync(path.join(output,'marker_render_dispatch.json'),'utf8'));
  const good=['type152','type155','descriptor2','descriptor4','stale-entry-context','gpr35','gpr36','no-input'].includes(name),negative=['wrong-resource','wrong-geometry','primary-null','bad-state','bad-resource-pointer','wrong-bone-count','wrong-vtype','wrong-vertex-count','wrong-pass'].includes(name);
  assert.equal(proc.exitCode,good||negative?0:1,`${name}: ${r.failure}`);assert.equal(active.size,0);assert(maxActive<=1);assert.equal(r.ownedBP,null);assert.equal(r.cleanup.errors.length,0);assert(r.cleanup.buttonsReleased&&r.cleanup.ownedBreakpointRemoved);
  assert.equal(r.producer.sha256,crypto.createHash('sha256').update(script).digest('hex'));assert(Object.values(commands.filter(x=>x.event==='input.buttons.send').at(-1).buttons).every(v=>v===false));
  if(name!=='no-input')assert(r.cleanup.analogReleased);else assert(!commands.filter(x=>x.event==='input.buttons.send').some(x=>Object.values(x.buttons).some(Boolean)));
  if(externalAt!==null)assert(!commands.slice(externalAt).some(x=>x.event==='cpu.resume'),'preserve external pause');
  if(good){
   assert.equal(r.failure,null);assert.equal(r.rows.length,1);const row=r.rows[0];assert.equal(row.classification,'observed_handler_invocation_return');assert.equal(row.geDrawObserved,false);assert.equal(row.semanticName,null);
   assert.equal(row.C,C);assert.equal(row.P,P);assert.equal(row.N,N);assert.equal(row.D,F+D);assert.equal(row.dispatch.sp,Q-0x30);assert.equal(row.returned.sp,Q-0x30);
   assert.equal(row.dispatch.actualType,typ);assert.equal(row.dispatch.target,target);assert.equal(row.dispatch.parameterPointer,PARAM);assert.equal(row.dispatch.mutableDataPointer,DATA+dataOffset);assert.equal(row.dispatch.expectedDelaySlotA2,PARAM);
   assert.equal(row.dispatch.gpr[6],vt+0x20);assert.equal(row.dispatch.parameterBefore.size,paramSize);assert.equal(row.dispatch.mutableDataBefore.size,dataSize);assert.equal(row.returned.mutableDataAfter.size,dataSize);
   assert.notEqual(row.dispatch.mutableDataBefore.raw.sha256,row.returned.mutableDataAfter.raw.sha256);assert.equal(row.entryGPR.length,32);assert.equal(row.returned.gpr.length,32);assert(r.codeIdentity.verified);
   assert.equal(r.firstStopTicks,100);assert.equal(r.lastStopTicks,300);assert.equal(r.entryStopCount,1);assert.equal(r.dispatchStopCount,1);assert.equal(r.returnStopCount,1);
   const ops=commands.filter(x=>['cpu.breakpoint.add','cpu.breakpoint.remove'].includes(x.event)).map(x=>[x.event,x.address]);assert.deepEqual(ops,[['cpu.breakpoint.add',ENTRY],['cpu.breakpoint.remove',ENTRY],['cpu.breakpoint.add',DISPATCH],['cpu.breakpoint.remove',DISPATCH],['cpu.breakpoint.add',RET],['cpu.breakpoint.remove',RET]]);
  }else if(negative){assert.equal(r.failure,null);assert.equal(r.rows.length,0);assert.equal(r.targetEntryCount,0);assert(r.negativeScope);}
  else{assert(r.failure);assert.equal(r.rows.length,0);if(name.startsWith('missing-')||name.includes('-add-timeout'))assert(r.inFlight);}
  console.log(`PASS ${name}`);
 }finally{
  const absolute=path.resolve(output),relative=path.relative(path.resolve(os.tmpdir()),absolute);assert(relative&&!relative.startsWith('..')&&!path.isAbsolute(relative)&&path.basename(absolute).startsWith('weapon-render-selftest-'));fs.rmSync(absolute,{recursive:true,force:true});
 }
}
(async()=>{for(const x of cases)await test(x);console.log(`PASS all ${cases.length} offline render-dispatch scenarios`);})().catch(e=>{console.error(e.stack||e);process.exitCode=1;});
