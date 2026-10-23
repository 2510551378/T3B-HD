// VM + MockWebSocket only: no network, PPSSPP process, UI or savestate access.
const fs=require('fs'),path=require('path'),os=require('os'),vm=require('vm'),assert=require('assert'),crypto=require('crypto');
const ENTRY=0x08b6513c,POST=0x08b65214,BASE=0x08804000;
const scenarios=['direct','recursive-one','recursive-two','gpr35','gpr36','noop','signed-noop','group-entry','wrong-resource','wrong-geometry','primary-null',
 'bad-root-ra','bad-bind-ra','bad-global-ra','bad-game-ra','depth-exceeded','bad-post-sp','bad-post-ra','bad-post-saved-ra','bad-post-register','bad-callee-saved',
 'short-gpr','negative-gpr','fractional-gpr','overflow-gpr','existing-bp','disabled-post-bp','bad-initial-code','bad-game-code','bad-post-code','bad-disasm',
 'missing-post','entry-read-error','post-read-error','wrong-selector-output','other-state-change','external-post','add-timeout','add-timeout-own-stop','add-timeout-external-stop'];
async function test(scenario){
 const root=path.resolve(__dirname,'..'),filename=path.join(__dirname,'trace_weapon_marker_selector_writer.js');
 const snapshot=JSON.parse(fs.readFileSync(path.join(root,'out/AYA_BONE_GE_ACTIONS/slot0_fire_reverse120_world60/weapon_metadata_snapshot.json'),'utf8'));
 const moduleBytes=fs.readFileSync(path.join(root,'raw/ULJM05798_module_08804000.bin'));
 const pack=v=>{const b=Buffer.alloc(v.length*4);v.forEach((x,i)=>b.writeUInt32LE(x>>>0,i*4));return b;};
 const S=0x09ff0000,P=0x097d2540,handle=0x09bd23c0,context=0x09b00000,resourceAddress=0x08d51b70;
 const depth=scenario==='recursive-two'?2:['recursive-one','depth-exceeded'].includes(scenario)?1:0,rootS=S+depth*0x20;
 const entryRA=scenario==='bad-root-ra'?0x08b5b9f8:depth?0x08b651ac:0x08b5b9f4;
 const state=Buffer.alloc(0x1a4),actor=Buffer.alloc(0x1000),stack=Buffer.alloc(0x400),postStack=Buffer.alloc(0x20);
 state[0]=scenario==='group-entry'?0x6c:0x65;state.writeUInt32LE(scenario==='primary-null'?0:handle,0x144);
 const newSelector=scenario==='signed-noop'?0xffffffff:1,oldSelector=scenario==='signed-noop'?0xffff:scenario==='noop'?1:0;
 state.writeUInt16LE(oldSelector,0x14c);state.writeUInt16LE(0xabcd,0x14e);state.writeUInt32LE(0x08d4d280,0x190);state.writeUInt32LE(0x08d4e234,0x194);state.writeUInt32LE(resourceAddress,0x198);
 const resource=Buffer.from('0068280001000000000002010000000000000000000000800000008000000000000000000000008000000080000000000000803f0000803f0000803f00000000','hex');
 if(scenario==='wrong-resource')resource[0]^=1;
 actor.writeUInt32LE(snapshot.sourceBase,0x3c4);actor.writeUInt32LE(snapshot.metadata,0x3e8);
 for(let d=0;d<depth;d++)stack.writeUInt32LE(d===depth-1?0x08b5b9f4:0x08b651ac,d*0x20+0x18);
 stack.writeUInt32LE(scenario==='bad-bind-ra'?0x08b59adc:0x08b59ad8,rootS-S+0x10);
 stack.writeUInt32LE(scenario==='bad-global-ra'?0x08b26d08:0x08b26d04,rootS-S+0x20);
 stack.writeUInt32LE(scenario==='bad-game-ra'?0x08a9a8cc:0x08a9a8c8,rootS-S+0x48);
 postStack.writeUInt32LE(scenario==='bad-post-saved-ra'?entryRA+4:entryRA,0x18);
 const segments=[[BASE,moduleBytes],[snapshot.object,actor],[snapshot.metadata,pack(snapshot.header)],[snapshot.drawTable,pack(snapshot.drawWords)],
  [snapshot.sourceBase,Buffer.concat(snapshot.records.map(r=>pack(r.words)))],[P,state],[handle,pack([snapshot.object])],[resourceAddress,resource],[S,stack],[S-0x20,postStack]];
 const out=fs.mkdtempSync(path.join(os.tmpdir(),'weapon-selector-selftest-'));
 const active=new Set(),commands=[];let phase='setup',maxActive=0,externalAt=null;
 const gprs=()=>{
  const g=Array(32).fill(0);g[4]=context;g[5]=P;g[6]=newSelector;
  g[16]=0x100;g[17]=0x200;g[18]=0x300;g[19]=0x400;g[20]=0x500;g[21]=0x600;g[22]=0x700;g[23]=0x800;g[30]=0x900;g[29]=S;g[31]=entryRA;
  if(phase==='post'){g[16]=newSelector;g[17]=context;g[18]=P;g[29]=S-0x20;g[31]=0x08b65208;}
  if(scenario==='bad-post-sp'&&phase==='post')g[29]+=4;
  if(scenario==='bad-post-ra'&&phase==='post')g[31]=entryRA;
  if(scenario==='bad-post-register'&&phase==='post')g[17]+=4;
  if(scenario==='bad-callee-saved'&&phase==='post')g[19]+=4;
  if(scenario==='gpr35')g.push(ENTRY,0,0);
  if(scenario==='gpr36')g.push(ENTRY,0,0,0);
  if(scenario==='short-gpr')g.length=31;
  if(scenario==='negative-gpr')g[4]=-1;
  if(scenario==='fractional-gpr')g[6]=1.25;
  if(scenario==='overflow-gpr')g[29]=0x100000000;
  return g;
 };
 class MockWebSocket{
  static OPEN=1;
  constructor(){this.readyState=0;this.handlers=new Map();queueMicrotask(()=>{this.readyState=1;this.emit('open',{});});}
  addEventListener(event,fn,options={}){const a=this.handlers.get(event)||[];a.push({fn,once:options.once});this.handlers.set(event,a);}
  emit(event,value){for(const l of [...(this.handlers.get(event)||[])]){l.fn(value);if(l.once)this.handlers.set(event,this.handlers.get(event).filter(v=>v!==l));}}
  stop(pc,ticks){this.emit('message',{data:JSON.stringify({event:'cpu.stepping',pc,ticks})});}
  send(text){
   const q=JSON.parse(text);commands.push(q);
   if(q.event==='cpu.resume'){
    if(active.has(POST)&&scenario!=='missing-post')queueMicrotask(()=>{
     if(scenario==='external-post'){externalAt=commands.length;this.stop(0x08804100,200);return;}
     phase='post';state.writeUInt16LE(scenario==='wrong-selector-output'?2:newSelector&0xffff,0x14c);
     if(scenario==='other-state-change')state[0x154]^=1;
     this.stop(POST,200);
    });return;
   }
   const result={event:q.event,ticket:q.ticket};
   if(q.event==='version')result.version='offline-selector-fixture';
   else if(q.event==='cpu.breakpoint.list')result.breakpoints=scenario==='existing-bp'?[{address:ENTRY,enabled:true}]:scenario==='disabled-post-bp'?[{address:POST,enabled:false}]:[];
   else if(q.event==='cpu.breakpoint.add'){
    assert.equal(active.size,0,'never install two BPs');active.add(q.address);maxActive=Math.max(maxActive,active.size);
    if(scenario.startsWith('add-timeout')){
     if(scenario==='add-timeout-own-stop')queueMicrotask(()=>this.stop(ENTRY,100));
     if(scenario==='add-timeout-external-stop')queueMicrotask(()=>{externalAt=commands.length;this.stop(0x08804100,100);});
     return;
    }
    if(q.address===ENTRY){phase='entry';queueMicrotask(()=>this.stop(ENTRY,100));}
   }else if(q.event==='cpu.breakpoint.remove'){assert(active.has(q.address));active.delete(q.address);}
   else if(q.event==='memory.read'){
    if(scenario==='entry-read-error'&&phase==='entry'&&q.address===P||scenario==='post-read-error'&&phase==='post'&&q.address===P){result.event='error';result.error='injected read error';}
    else{
     const s=segments.find(([a,b])=>q.address>=a&&q.address+q.size<=a+b.length);assert(s,`missing ${q.address.toString(16)} size ${q.size}`);
     const b=Buffer.from(s[1].subarray(q.address-s[0],q.address-s[0]+q.size));
     if(q.address>=BASE&&q.address+q.size<=BASE+moduleBytes.length){
      if(q.replacements!==false)b.writeUInt32LE(0x68012345,0);
      const bad=scenario==='bad-initial-code'&&q.address===ENTRY||scenario==='bad-post-code'&&q.address===POST||scenario==='bad-game-code'&&q.address===0x08a9a1f0;
      if(bad&&q.replacements===false)b.writeUInt32LE(0x12345678,0);
     }
     if(scenario==='wrong-geometry'&&q.size===243*16)b[0]^=1;
     result.base64=b.toString('base64');
    }
   }else if(q.event==='memory.disasm'){
    result.lines=[];
    for(let a=q.address;a<q.end;a+=a===q.address?8:4){const first=moduleBytes.readUInt32LE(a-BASE);result.lines.push({type:a===q.address?'macro':'opcode',address:a,addressSize:a===q.address?8:4,encoding:first,macroEncoding:a===q.address?[first,moduleBytes.readUInt32LE(a+4-BASE)]:null});}
    if(scenario==='bad-disasm')result.lines[0].macroEncoding[1]^=1;
   }else if(q.event==='cpu.getAllRegs')result.categories=[{name:'MIPS GPR',uintValues:gprs()}];
   else assert(['input.buttons.send','input.analog.send'].includes(q.event),`unknown RPC ${q.event}`);
   queueMicrotask(()=>this.emit('message',{data:JSON.stringify(result)}));
  }
  close(){this.readyState=3;this.emit('close',{});}
 }
 const fakeProcess={env:{MARKER_SELECTOR_OUT_DIR:out,MARKER_MAX_STOPS:'1',MARKER_MAX_ROWS:'1',MARKER_DURATION_MS:'1000',MARKER_STAGE_TIMEOUT_MS:'60',
  MARKER_MAX_GROUP_DEPTH:scenario==='depth-exceeded'?'0':'8'},on(){},exitCode:0};
 if(scenario!=='direct'){fakeProcess.env.MARKER_BUTTONS_JSON=JSON.stringify({square:true,select:true});fakeProcess.env.MARKER_ANALOG_JSON=JSON.stringify({stick:'left',x:0.2,y:0.3});}
 const mockTimeout=(fn,ms,...args)=>setTimeout(fn,scenario.startsWith('add-timeout')&&ms===10000?60:ms,...args);
 try{
  await vm.runInNewContext(fs.readFileSync(filename,'utf8'),{require,Buffer,WebSocket:MockWebSocket,process:fakeProcess,__dirname,__filename:filename,console:{log(){},error:console.error},setTimeout:mockTimeout,clearTimeout,Date,Promise});
  const r=JSON.parse(fs.readFileSync(path.join(out,'marker_selector_writer.json'),'utf8'));
  const success=['direct','recursive-one','recursive-two','gpr35','gpr36'].includes(scenario),noop=['noop','signed-noop'].includes(scenario),negative=['group-entry','wrong-resource','wrong-geometry','primary-null'].includes(scenario),fail=!success&&!noop&&!negative;
  assert.equal(fakeProcess.exitCode,fail?1:0,scenario);assert.equal(active.size,0);assert(maxActive<=1);assert.equal(r.ownedBP,null);assert.equal(r.cleanup.errors.length,0);assert(r.cleanup.buttonsReleased&&r.cleanup.ownedBreakpointRemoved);
  assert.equal(r.producer.sha256,crypto.createHash('sha256').update(fs.readFileSync(filename)).digest('hex'));
  assert(Object.values(commands.filter(q=>q.event==='input.buttons.send').at(-1).buttons).every(v=>v===false));
  if(scenario==='direct')assert(!commands.filter(q=>q.event==='input.buttons.send').some(q=>Object.values(q.buttons).some(Boolean)),'default no held input');
  else{assert(r.cleanup.analogReleased);const last=commands.filter(q=>q.event==='input.analog.send').at(-1);assert.equal(last.x,0);assert.equal(last.y,0);}
  if(fail){
   assert(r.failure);assert.equal(r.rows.length,0);
   if(['external-post','add-timeout-external-stop'].includes(scenario))assert(!commands.slice(externalAt).some(q=>q.event==='cpu.resume'),'external pause must remain');
   if(scenario==='add-timeout-own-stop')assert(r.cleanup.resumedOwnStop&&r.cleanup.unconsumedStops.length===1);
   if(['existing-bp','disabled-post-bp','bad-initial-code','bad-disasm'].includes(scenario))assert(!commands.some(q=>q.event==='cpu.breakpoint.add'));
   if(scenario==='missing-post')assert(r.inFlight&&r.failure.includes('timeout')&&r.failure.includes('unknown'));
   console.log(`PASS ${scenario}: fail closed, original code/ABI guard and owned cleanup`);return;
  }
  assert.equal(r.firstStopTicks,100);assert.equal(r.firstEntryTicks,100);assert.equal(r.lastEntryTicks,100);
  if(negative){assert.equal(r.rows.length,0);assert.equal(r.targetEntryCount,0);assert(r.negativeScope);assert.equal(r.postWriteStopCount,0);console.log(`PASS ${scenario}: bounded negative, no false target`);return;}
  assert.equal(r.targetEntryCount,1);assert.equal(r.negativeScope,null);
  if(noop){assert.equal(r.noOpEntries.length,1);assert.equal(r.rows.length,0);assert.equal(r.postWriteStopCount,0);assert.equal(r.noOpEntries[0].classification,'no_op_entry');assert.equal(r.noOpEntries[0].actualWriteObserved,false);assert(!commands.some(q=>q.event==='cpu.breakpoint.add'&&q.address===POST));console.log(`PASS ${scenario}: no-op classified without claiming a store`);return;}
  assert.equal(r.rows.length,1);const row=r.rows[0];assert.equal(row.actualWriteObserved,true);assert.equal(row.classification,'observed_selector_write');assert.equal(row.newSelector,1);assert.equal(row.oldSelectorSigned,0);assert.equal(row.postWrite.fields.selectorU16,1);
  assert.equal(row.entryStack.bytes,0x400);assert.equal(row.postWrite.postStack.bytes,0x20);assert.equal(row.callerChain.recursionDepth,depth);assert.equal(row.callerChain.recursion.length,depth);assert.equal(row.callerChain.rootSelectorEntrySP,rootS);
  assert.equal(row.callerChain.gameCallsite,0x08a9a8c0);assert.equal(row.callerChain.savedRA.bind.value,0x08b59ad8);assert.equal(row.callerChain.savedRA.global.value,0x08b26d04);assert.equal(row.callerChain.savedRA.game.value,0x08a9a8c8);
  assert.equal(row.postWrite.gpr[29],S-0x20);assert.equal(row.postWrite.gpr[31],0x08b65208);assert.deepEqual(row.changedByteOffsets,[0x14c]);assert.equal(row.postWrite.fields.flags154,0);
  assert.equal(row.beforeFields.sourceState190,0x08d4d280);assert.equal(row.weapon.geometrySHA256,'168578abca4c4f5d22d5994ebced6b93a25d5167428bfd47f1a1150a8d42e65a');assert.equal(row.semanticName,null);
  const expectedLength=scenario==='gpr35'?35:scenario==='gpr36'?36:32;assert(r.gprCategoryDiagnostics.every(x=>x.length===expectedLength));assert.equal(row.entryGPR.length,32);assert.equal(row.postWrite.gpr.length,32);
  assert.equal(r.codeIdentity.checks.length,11);assert(r.codeIdentity.verified);assert.equal(r.lastStopTicks,200);
  const ops=commands.filter(q=>['cpu.breakpoint.add','cpu.breakpoint.remove'].includes(q.event)).map(q=>[q.event,q.address]);assert.deepEqual(ops,[['cpu.breakpoint.add',ENTRY],['cpu.breakpoint.remove',ENTRY],['cpu.breakpoint.add',POST],['cpu.breakpoint.remove',POST]]);
  console.log(`PASS ${scenario}: exact target, recursive RA provenance, actual SH output and one-BP lifecycle`);
 }finally{
  const resolved=path.resolve(out),relative=path.relative(path.resolve(os.tmpdir()),resolved);assert(relative&&!relative.startsWith('..')&&!path.isAbsolute(relative)&&path.basename(resolved).startsWith('weapon-selector-selftest-'));fs.rmSync(resolved,{recursive:true,force:true});
 }
}
(async()=>{for(const scenario of scenarios)await test(scenario);console.log(`PASS all ${scenarios.length} offline selector-writer scenarios`);})().catch(e=>{console.error(e.stack||e);process.exitCode=1;});
