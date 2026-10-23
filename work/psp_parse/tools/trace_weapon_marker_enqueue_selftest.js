// VM/Mock only: never creates a real WebSocket, PPSSPP process or visible window.
const fs=require('fs'),path=require('path'),os=require('os'),vm=require('vm'),assert=require('assert'),crypto=require('crypto');
const ENTRY=0x08bbdce8,RET=0x08b935f0,BASE=0x08804000,HEADS=0x08cb1460,TAILS=0x08cb1960;
const cases=['empty','append','descriptor2','descriptor3','descriptor4','parents','gpr35','gpr36','no-input',
 'wrong-resource','wrong-geometry','primary-null','bad-context','bad-state','bad-resource-pointer','wrong-bone-count','wrong-vtype','wrong-vertex-count',
 'bad-entry-ra','bad-stack74','bad-stacka0','bad-stackb8','bad-stackc8','bad-entry-sp','bad-node','bad-E','wrong-node-E','unsupported-D',
 'bad-fep-base','bad-fep-magic','bad-fep-size','bad-fep-count','bad-fep-offset8','bad-fep194','bad-record','bad-slot','bad-D-count','bad-D-list','unrelocated-D-list','unrelocated-def-table','unrelocated-def-pointer','unrelocated-def-data','unrelocated-header-table','unrelocated-nested-list','bad-def-table','bad-index','bad-def-pointer','bad-def-type',
 'bad-matrix','bad-parent','nonfinite-matrix','bad-mode','bad-return-sp','bad-return-ra','bad-callee-saved','bad-return-v0','bad-E8','bad-E-C','bad-E-P','bad-E-N','bad-E-next','bad-E-prev','bad-head','bad-tail','bad-oldtail-next','bad-state-change',
 'short-gpr','negative-gpr','fractional-gpr','overflow-gpr','existing-bp','disabled-return-bp','bad-code','bad-disasm','short-read','entry-read-error','return-read-error','missing-return','external-return','queued-external-setup','add-timeout','add-timeout-own','add-timeout-external','return-add-timeout','return-add-timeout-own','return-add-timeout-external'];

async function test(name){
 const root=path.resolve(__dirname,'..'),filename=path.join(__dirname,'trace_weapon_marker_enqueue.js'),script=fs.readFileSync(filename,'utf8');
 const original=fs.readFileSync(path.join(root,'out/WEAPON_MARKER_STATE_20261020/original_source_match_section.bin'));
 const module=fs.readFileSync(path.join(root,'raw/ULJM05798_module_08804000.bin'));
 const snap=JSON.parse(fs.readFileSync(path.join(root,'out/AYA_BONE_GE_ACTIONS/slot0_fire_reverse120_world60/weapon_metadata_snapshot.json'),'utf8'));
 const pack=x=>{const b=Buffer.alloc(4*x.length);x.forEach((v,i)=>b.writeUInt32LE(v>>>0,i*4));return b;};
 const F=0x08d4d280,C=0x09a00000,P=0x097d2540,N=0x097d2340,E=0x097c0000,Q=0x09ff0000,H=0x09bd23c0,M=0x09ac0000,PAR=0x09ab0000,T=0x097c1000;
 const fep=Buffer.from(original),context=Buffer.alloc(0xa8),state=Buffer.alloc(0x1ac),node=Buffer.alloc(0x64),entry=Buffer.alloc(0x18),stack=Buffer.alloc(0xd0),matrix=Buffer.alloc(64),parent=Buffer.alloc(0x64),tailEntry=Buffer.alloc(8),actor=Buffer.alloc(0x1000),headArray=Buffer.alloc(0x500),tailArray=Buffer.alloc(0x500);
 for(let i=0;i<4;i++)matrix.writeFloatLE(1,i*20);
 const ds=[0x10ba0,0x10be8,0x10c30,0x10c78],di={'descriptor2':1,'descriptor3':2,'descriptor4':3}[name]||0,D=ds[di];
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
 const output=fs.mkdtempSync(path.join(os.tmpdir(),'weapon-enqueue-selftest-'));
 const active=new Set(),commands=[];let phase='setup',maxActive=0,externalAt=null,firstReadFailure=false;
 function gprs(){
  const g=Array(32).fill(0);g[4]=E;g[5]=C;g[6]=3;g[7]=0;g[29]=Q;g[31]=RET;
  for(let i=16;i<=23;i++)g[i]=i*0x100;g[30]=0x3000;
  if(name==='bad-entry-ra'&&phase==='entry')g[31]+=4;
  if(name==='bad-context'&&phase==='entry')g[5]=0x0c000000;
  if(name==='bad-entry-sp'&&phase==='entry')g[29]=0x0c000000;
  if(name==='bad-E'&&phase==='entry')g[4]=0x0c000000;
  if(name==='bad-mode')g[6]=256;
  if(phase==='return'){
   g[2]=1;
   if(name==='bad-return-sp')g[29]+=4;
   if(name==='bad-return-ra')g[31]+=4;
   if(name==='bad-callee-saved')g[20]+=4;
   if(name==='bad-return-v0')g[2]=2;
  }
  if(name==='gpr35')g.push(ENTRY,0,0);if(name==='gpr36')g.push(ENTRY,0,0,0);
  if(name==='short-gpr')g.length=31;if(name==='negative-gpr')g[4]=-1;if(name==='fractional-gpr')g[29]=1.5;if(name==='overflow-gpr')g[4]=0x100000000;
  return g;
 }
 function enqueue(){
  entry[8]=name==='bad-E8'?2:1;entry.writeUInt16LE(1,0xa);entry.writeUInt32LE(name==='bad-E-C'?C+4:C,0xc);entry.writeUInt32LE(name==='bad-E-P'?P+4:P,0x10);entry.writeUInt32LE(name==='bad-E-N'?N+4:N,0x14);
  entry.writeUInt32LE(name==='bad-E-next'?4:0,4);entry.writeUInt32LE(name==='bad-E-prev'?T:appended?T:0,0);
  headArray.writeUInt32LE(name==='bad-head'?E+4:appended?T:E,4);tailArray.writeUInt32LE(name==='bad-tail'?E+4:E,4);
  if(appended)tailEntry.writeUInt32LE(name==='bad-oldtail-next'?E+4:E,4);
  if(name==='bad-state-change')state[0x20]^=1;
 }
 class MockWebSocket{
  static OPEN=1;
  constructor(){this.readyState=0;this.handlers=new Map();queueMicrotask(()=>{this.readyState=1;this.emit('open',{});});}
  addEventListener(event,fn,options={}){const x=this.handlers.get(event)||[];x.push({fn,once:options.once});this.handlers.set(event,x);}
  emit(event,v){for(const x of [...(this.handlers.get(event)||[])]){x.fn(v);if(x.once)this.handlers.set(event,this.handlers.get(event).filter(q=>q!==x));}}
  stop(pc,ticks){this.emit('message',{data:JSON.stringify({event:'cpu.stepping',pc,ticks})});}
  send(text){
   const q=JSON.parse(text);commands.push(q);
   if(q.event==='cpu.resume'){
    if(active.has(RET)&&name!=='missing-return')queueMicrotask(()=>{if(name==='external-return'){externalAt=commands.length;this.stop(0x08804100,200);return;}phase='return';enqueue();this.stop(RET,200);});return;
   }
   const r={event:q.event,ticket:q.ticket};
   if(q.event==='version')r.version='offline-enqueue-fixture';
   else if(q.event==='cpu.breakpoint.list')r.breakpoints=name==='existing-bp'?[{address:ENTRY,enabled:true}]:name==='disabled-return-bp'?[{address:RET,enabled:false}]:[];
   else if(q.event==='cpu.breakpoint.add'){
    assert.equal(active.size,0,'single active owned BP');active.add(q.address);maxActive=Math.max(maxActive,active.size);
    if((name.startsWith('add-timeout')&&q.address===ENTRY)||(name.startsWith('return-add-timeout')&&q.address===RET)){
     if(name.endsWith('-own'))queueMicrotask(()=>{phase=q.address===ENTRY?'entry':'return';if(phase==='return')enqueue();this.stop(q.address,q.address===ENTRY?100:200);});
     if(name.endsWith('-external'))queueMicrotask(()=>{externalAt=commands.length;this.stop(0x08804100,100);});return;
    }
    if(q.address===ENTRY){phase='entry';queueMicrotask(()=>this.stop(ENTRY,100));}
   }else if(q.event==='cpu.breakpoint.remove'){assert(active.has(q.address));active.delete(q.address);}
   else if(q.event==='memory.read'){
    const failure=name==='entry-read-error'&&phase==='entry'&&q.address===N||name==='return-read-error'&&phase==='return'&&q.address===E;
    if(failure){r.event='error';r.error='injected guest read error';}
    else{
     const segment=[...segments].reverse().find(([a,b])=>q.address>=a&&q.address+q.size<=a+b.length);assert(segment,`missing fixture read ${q.address.toString(16)}/${q.size}`);
     const b=Buffer.from(segment[1].subarray(q.address-segment[0],q.address-segment[0]+q.size));
     if(segment[1]===module){if(q.replacements!==false)b.writeUInt32LE(0x68012345,0);if(name==='bad-code'&&q.replacements===false)b.writeUInt32LE(1,0);}
     if(name==='wrong-geometry'&&q.size===243*16)b[0]^=1;
     if(name==='short-read'&&phase==='entry'&&!firstReadFailure){firstReadFailure=true;r.base64=b.subarray(0,b.length-4).toString('base64');}else r.base64=b.toString('base64');
    }
   }else if(q.event==='memory.disasm'){
    r.lines=[];
    for(let a=q.address;a<q.end;a+=a===q.address?8:4){const w=module.readUInt32LE(a-BASE);r.lines.push({type:a===q.address?'macro':'opcode',address:a,addressSize:a===q.address?8:4,encoding:w,macroEncoding:a===q.address?[w,module.readUInt32LE(a+4-BASE)]:null});}
    if(name==='bad-disasm')r.lines[0].macroEncoding[1]^=1;
    if(name==='queued-external-setup'&&q.address===ENTRY){externalAt=commands.length;queueMicrotask(()=>this.stop(0x08804100,50));}
   }else if(q.event==='cpu.getAllRegs')r.categories=[{name:'MIPS GPR',uintValues:gprs()}];
   else assert(['input.buttons.send','input.analog.send'].includes(q.event),`unknown RPC ${q.event}`);
   queueMicrotask(()=>this.emit('message',{data:JSON.stringify(r)}));
  }
  close(){this.readyState=3;this.emit('close',{});}
 }
 const proc={env:{MARKER_ENQUEUE_OUT_DIR:output,MARKER_MAX_STOPS:'1',MARKER_MAX_ROWS:'1',MARKER_DURATION_MS:'1000',MARKER_STAGE_TIMEOUT_MS:'60'},on(){},exitCode:0};
 if(name!=='no-input'){proc.env.MARKER_BUTTONS_JSON='{"square":true,"select":true}';proc.env.MARKER_ANALOG_JSON='{"stick":"left","x":0.2,"y":0.3}';}
 const timeout=(fn,ms,...args)=>setTimeout(fn,name.includes('add-timeout')&&ms===10000?60:ms,...args);
 try{
  await vm.runInNewContext(script,{require,Buffer,WebSocket:MockWebSocket,process:proc,__dirname,__filename:filename,console:{log(){},error:console.error},setTimeout:timeout,clearTimeout,Date,Promise});
  const r=JSON.parse(fs.readFileSync(path.join(output,'marker_enqueue.json'),'utf8'));
  const good=['empty','append','descriptor2','descriptor3','descriptor4','parents','gpr35','gpr36','no-input','unrelocated-header-table'].includes(name);
  const negative=['wrong-resource','wrong-geometry','primary-null','bad-context','bad-state','bad-resource-pointer','wrong-bone-count','wrong-vtype','wrong-vertex-count'].includes(name);
  assert.equal(proc.exitCode,good||negative?0:1,`${name}: ${r.failure}`);assert.equal(active.size,0);assert(maxActive<=1);assert.equal(r.ownedBP,null);assert.equal(r.cleanup.errors.length,0);
  assert(r.cleanup.buttonsReleased&&r.cleanup.ownedBreakpointRemoved);assert.equal(r.producer.sha256,crypto.createHash('sha256').update(script).digest('hex'));
  assert(Object.values(commands.filter(x=>x.event==='input.buttons.send').at(-1).buttons).every(v=>v===false));
  if(name!=='no-input'){assert(r.cleanup.analogReleased);const last=commands.filter(x=>x.event==='input.analog.send').at(-1);assert.equal(last.x,0);assert.equal(last.y,0);}
  else assert(!commands.filter(x=>x.event==='input.buttons.send').some(x=>Object.values(x.buttons).some(Boolean)));
  if(externalAt!==null)assert(!commands.slice(externalAt).some(x=>x.event==='cpu.resume'),'preserve queued external pause');
  if(good){
   assert.equal(r.failure,null);assert.equal(r.rows.length,1);const row=r.rows[0];assert.equal(row.classification,'observed_enqueue');assert.equal(row.geDrawObserved,false);assert.equal(row.semanticName,null);
   assert.equal(row.E,E);assert.equal(row.C,C);assert.equal(row.P,P);assert.equal(row.N,N);assert.equal(row.entryStack.size,0xd0);assert.equal(row.entryGPR.length,32);
   assert.equal(row.returned.bucket,1);assert.equal(row.returned.gpr.length,32);assert(row.returned.linkValidation.validated);assert.equal(row.returned.oldTailBefore,appended?T:0);
   assert.equal(row.descriptorPath.offset,D);assert.equal(row.descriptorPath.lists.length,3);assert.equal(row.bucketSources.beforeHeads.size,0x500);assert.equal(row.bucketSources.beforeTails.size,0x500);
   assert.equal(row.returned.head.size,4);assert.equal(row.returned.tail.size,4);if(appended)assert.equal(row.returned.oldTailAfter.size,8);
   assert.equal(row.entry.parents.length,name==='parents'?2:0);assert.equal(r.firstStopTicks,100);assert.equal(r.lastStopTicks,200);assert(r.codeIdentity.verified);
   const ops=commands.filter(x=>['cpu.breakpoint.add','cpu.breakpoint.remove'].includes(x.event)).map(x=>[x.event,x.address]);assert.deepEqual(ops,[['cpu.breakpoint.add',ENTRY],['cpu.breakpoint.remove',ENTRY],['cpu.breakpoint.add',RET],['cpu.breakpoint.remove',RET]]);
  }else if(negative){assert.equal(r.failure,null);assert.equal(r.rows.length,0);assert.equal(r.targetEntryCount,0);assert(r.negativeScope);}
  else{assert(r.failure);assert.equal(r.rows.length,0);if(['missing-return','return-add-timeout','return-add-timeout-own','return-add-timeout-external'].includes(name))assert(r.inFlight);}
  console.log(`PASS ${name}`);
 }finally{
  const absolute=path.resolve(output),relative=path.relative(path.resolve(os.tmpdir()),absolute);
  assert(relative&&!relative.startsWith('..')&&!path.isAbsolute(relative)&&path.basename(absolute).startsWith('weapon-enqueue-selftest-'));
  fs.rmSync(absolute,{recursive:true,force:true});
 }
}
(async()=>{for(const x of cases)await test(x);console.log(`PASS all ${cases.length} offline enqueue scenarios`);})().catch(e=>{console.error(e.stack||e);process.exitCode=1;});
