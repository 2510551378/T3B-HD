// Offline VM/MockWebSocket tests. No real WebSocket, PPSSPP, UI, or savestate IO.
'use strict';
const fs=require('fs'),path=require('path'),os=require('os'),vm=require('vm'),assert=require('assert'),crypto=require('crypto');
const ENTRY=0x08b6513c,POST=0x08b65214,BASE=0x08804000;
const root=path.resolve(__dirname,'..'),sampler=path.join(__dirname,'trace_weapon_marker_selector_writer.js');
const samplerSource=fs.readFileSync(sampler,'utf8'),samplerSHA=hash(Buffer.from(samplerSource));
const moduleBytes=fs.readFileSync(path.join(root,'raw/ULJM05798_module_08804000.bin'));
const snapshot=JSON.parse(fs.readFileSync(path.join(root,'out/AYA_BONE_GE_ACTIONS/slot0_fire_reverse120_world60/weapon_metadata_snapshot.json'),'utf8'));
function hash(b){return crypto.createHash('sha256').update(b).digest('hex');}
function pack(v){const b=Buffer.alloc(v.length*4);v.forEach((x,i)=>b.writeUInt32LE(x>>>0,i*4));return b;}
function put(b,o,v){b.writeUInt32LE(v>>>0,o);}
const cases=[];
function scenario(name,mutate=()=>{},failure=null,options={}){cases.push({name,mutate,failure,...options});}
scenario('supported-mode1');
scenario('supported-mode0',f=>f.mode=0);
scenario('supported-mode-nonzero-255',f=>f.mode=255);
scenario('supported-recursive-one',()=>{},null,{depth:1});
scenario('supported-recursive-two',()=>{},null,{depth:2});
scenario('supported-count-boundary4096',f=>{f.slotCount=4096;f.arrayCount=4096;});
scenario('supported-slot-end-of-RAM',f=>f.slotsBase=0x0bfffff8);
scenario('supported-primary-end-of-RAM',f=>f.arrayBase=0x0bffffd0);
scenario('requested-IDs-retained-without-unproven-equality',f=>{put(f.config,8,0x00445566);put(f.locals,4,0x00112233);});
scenario('opt-out-keeps-old-caller-path',f=>{f.gameRA=0x08a9a8c8;f.configAddress=0;f.bindingActor=0;f.containerAddress=0;},null,{enabled:false});
scenario('wrong-stack-selector',f=>f.stackSelector=2,/binding selector\/slot offset/);
scenario('wrong-config90-selector',f=>put(f.config,4,2),/binding source selector is not preserved/);
scenario('wrong-upperlocal378-selector',f=>put(f.locals,8,2),/binding source selector is not preserved/);
scenario('wrong-upperlocal37c-primary',f=>put(f.locals,12,f.primary+4),/binding primary source is not preserved/);
scenario('wrong-primary-record0',f=>put(f.primaryRecords,24,f.primary+4),/binding primary source is not preserved/);
scenario('wrong-primary-record0-mode0',f=>{f.mode=0;put(f.primaryRecords,0,f.primary+4);},/binding primary source is not preserved/);
scenario('wrong-stack-primary',f=>f.stackPrimary=f.primary+4,/binding primary source is not preserved/);
scenario('wrong-upper-saved-RA',f=>f.upperRA+=4,/binding upper saved RA/);
scenario('unsupported-known-game-caller',f=>f.gameRA=0x08a9a8c8,/binding probe encountered an unsupported game caller/);
scenario('unknown-game-caller',f=>f.gameRA=0x08804108,/unknown game caller/);
scenario('unknown-root-selector-caller',f=>f.entryRA=0x08b5b9f8,/unknown root selector caller/);
scenario('unaligned-slot-byte-offset',f=>f.slotByteOffset=3,/binding selector\/slot offset/);
scenario('slot-count-zero',f=>f.slotCount=0,/binding slot index\/count/);
scenario('slot-count4097',f=>f.slotCount=4097,/binding slot index\/count/);
scenario('slot-index-equals-count',f=>{f.slotByteOffset=12;f.slotCount=3;},/binding slot index\/count/);
scenario('slot-index-u32-large',f=>f.slotByteOffset=0xfffffffc,/binding slot index\/count/);
scenario('primary-count-zero',f=>f.arrayCount=0,/binding primary array index\/count/);
scenario('primary-count4097',f=>f.arrayCount=4097,/binding primary array index\/count/);
scenario('primary-index-equals-count',f=>f.arrayCount=1,/binding primary array index\/count/);
scenario('config-null-RAM',f=>f.configAddress=0,/binding window config_8c outside bounded guest RAM/);
scenario('config-unaligned-RAM',f=>f.configAddress+=1,/binding window config_8c outside bounded guest RAM/);
scenario('config-crosses-RAM-end',f=>f.configAddress=0x0bffff70,/binding window config_8c outside bounded guest RAM/);
scenario('actor-null-RAM',f=>f.bindingActor=0,/binding window actor_80 outside bounded guest RAM/);
scenario('actor-field-crosses-RAM-end',f=>f.bindingActor=0x0bffea00,/binding window actor_161c outside bounded guest RAM/);
scenario('container-null-RAM',f=>f.containerAddress=0,/binding window slot_container outside bounded guest RAM/);
scenario('container-crosses-RAM-end',f=>f.containerAddress=0x0bfffffc,/binding window slot_container outside bounded guest RAM/);
scenario('slots-base-null-RAM',f=>f.slotsBase=0,/binding window selected_slot outside bounded guest RAM/);
scenario('slots-base-crosses-RAM-end',f=>f.slotsBase=0x0bfffffc,/binding window selected_slot outside bounded guest RAM/);
scenario('primary-array-null-RAM',f=>f.arrayBase=0,/binding window primary_record outside bounded guest RAM/);
scenario('primary-record-crosses-RAM-end',f=>f.arrayBase=0x0bffffd4,/binding window primary_record outside bounded guest RAM/);
scenario('upperlocals-read-error',()=>{},/injected binding read failure/,{readError:'upper_locals'});
scenario('primary-record-short-read',()=>{},/short guest read/,{shortRead:'primary_record'});
scenario('binding-upper-original-code-mismatch',()=>{},/original opcode identity failed: binding_upper_full/,{badCode:0x08976f1c});
scenario('binding-getter-original-code-mismatch',()=>{},/original opcode identity failed: binding_primary_getter_full/,{badCode:0x08b38dd0});
scenario('binding-external-post-stop-preserved',()=>{},/unexpected external CPU stop/,{externalPost:true});

async function test(c){
 const S=0x09ff0000,P=0x097d2540,primary=0x09bd23c0,context=0x09b00000,resourceAddress=0x08d51b70;
 const depth=c.depth||0,R=S+depth*0x20,G=R+0x30,Q=R+0x50,U=R+0x70;
 const f={primary,context,mode:1,slotByteOffset:4,slotCount:3,arrayCount:2,
  slotsBase:0x09a00100,arrayBase:0x09c20000,bindingActor:0x09c00000,
  configAddress:0x09c10000,containerAddress:0x09a00000,
  stackSelector:1,stackPrimary:primary,gameRA:0x08971fe8,upperRA:0x08977cc8,
  entryRA:depth?0x08b651ac:0x08b5b9f4,
  config:pack([0x100,1,0x222333,0x400]),locals:pack([0x500,0x222333,1,primary]),
  primaryRecords:pack([primary,0x111,0x222,0x333,0x444,0x555,primary,0x666,0x777,0x888,0x999,0xaaa])};
 c.mutate(f);
 const state=Buffer.alloc(0x1a4),weaponActor=Buffer.alloc(0x1000),stack=Buffer.alloc(0x500),postStack=Buffer.alloc(0x20);
 state[0]=0x65;put(state,0x144,primary);state.writeUInt16LE(0,0x14c);state.writeUInt16LE(0xabcd,0x14e);
 put(state,0x190,0x08d4d280);put(state,0x194,0x08d4e234);put(state,0x198,resourceAddress);
 const resource=Buffer.from('0068280001000000000002010000000000000000000000800000008000000000000000000000008000000080000000000000803f0000803f0000803f00000000','hex');
 put(weaponActor,0x3c4,snapshot.sourceBase);put(weaponActor,0x3e8,snapshot.metadata);
 for(let d=0;d<depth;d++)put(stack,d*0x20+0x18,d===depth-1?0x08b5b9f4:0x08b651ac);
 put(stack,R-S+0x10,0x08b59ad8);put(stack,R-S+0x20,0x08b26d04);put(stack,R-S+0x48,f.gameRA);
 for(const [at,value] of [[G,f.context],[G+4,f.stackPrimary],[G+8,f.stackSelector],[G+0x14,f.containerAddress],
                         [Q+0xc,f.configAddress],[Q+0x10,f.bindingActor],[Q+0x1c,f.upperRA]])put(stack,at-S,value);
 f.locals.copy(stack,U+0x370-S);put(postStack,0x18,f.entryRA);
 const bindingActor=Buffer.alloc(0x1620);put(bindingActor,0x80,f.arrayBase);put(bindingActor,0x84,f.arrayCount);
 put(bindingActor,0x148c,0x10203040);put(bindingActor,0x1538,0x50607080);bindingActor[0x161e]=f.mode;
 const slots=pack([0x0000abcd,0x00112233,0x00445566]);
 const windows={upper_locals:[U+0x370,16],config_8c:[f.configAddress+0x8c,16],actor_80:[f.bindingActor+0x80,8],
  actor_148c:[f.bindingActor+0x148c,4],actor_1538:[f.bindingActor+0x1538,4],actor_161c:[f.bindingActor+0x161c,4],
  slot_container:[f.containerAddress,8],selected_slot:[f.slotsBase+f.slotByteOffset,4],
  primary_record:[f.arrayBase+24*(f.mode!==0?1:0),24]};
 const segments=[[BASE,moduleBytes],[snapshot.object,weaponActor],[snapshot.metadata,pack(snapshot.header)],
  [snapshot.drawTable,pack(snapshot.drawWords)],[snapshot.sourceBase,Buffer.concat(snapshot.records.map(x=>pack(x.words)))],
  [P,state],[primary,pack([snapshot.object])],[resourceAddress,resource],[S,stack],[S-0x20,postStack],
  [f.bindingActor,bindingActor],[f.configAddress+0x8c,f.config],[f.containerAddress,pack([f.slotsBase,f.slotCount])],
  [f.slotsBase,slots],[f.arrayBase,f.primaryRecords]];
 const out=fs.mkdtempSync(path.join(os.tmpdir(),'weapon-binding-selftest-'));
 const active=new Set(),commands=[],errors=[];let phase='setup',maxActive=0,externalAt=null,closed=false;
 const actualReads=[];
 function gprs(){const g=Array(32).fill(0);g[4]=context;g[5]=P;g[6]=1;
  for(let i=16;i<=23;i++)g[i]=0x100+i;g[22]=f.slotByteOffset;g[29]=S;g[30]=0x900;g[31]=f.entryRA;
  if(phase==='post'){g[16]=1;g[17]=context;g[18]=P;g[29]=S-0x20;g[31]=0x08b65208;}
  return g;
 }
 class MockWebSocket{
  static OPEN=1;
  constructor(url,protocol){assert.equal(url,'ws://127.0.0.1:9900/debugger');assert.equal(protocol,'debugger.ppsspp.org');
   this.readyState=0;this.handlers=new Map();queueMicrotask(()=>{this.readyState=1;this.emit('open',{});});}
  addEventListener(event,fn,options={}){const a=this.handlers.get(event)||[];a.push({fn,once:options.once});this.handlers.set(event,a);}
  emit(event,value){for(const l of [...(this.handlers.get(event)||[])]){l.fn(value);if(l.once)this.handlers.set(event,this.handlers.get(event).filter(x=>x!==l));}}
  stop(pc,ticks){this.emit('message',{data:JSON.stringify({event:'cpu.stepping',pc,ticks})});}
  send(text){const q=JSON.parse(text);commands.push(q);
   if(q.event==='cpu.resume'){
    if(active.has(POST))queueMicrotask(()=>{if(c.externalPost){externalAt=commands.length;this.stop(0x08804100,200);return;}
     phase='post';state.writeUInt16LE(1,0x14c);this.stop(POST,200);});return;
   }
   const result={event:q.event,ticket:q.ticket};
   if(q.event==='version')result.version='offline-binding-fixture';
   else if(q.event==='cpu.breakpoint.list')result.breakpoints=[];
   else if(q.event==='cpu.breakpoint.add'){
    assert.equal(active.size,0,'single owned BP invariant');active.add(q.address);maxActive=Math.max(maxActive,active.size);
    if(q.address===ENTRY){phase='entry';queueMicrotask(()=>this.stop(ENTRY,100));}
   }else if(q.event==='cpu.breakpoint.remove'){assert(active.has(q.address),'remove only owned BP');active.delete(q.address);}
   else if(q.event==='memory.read'){
    actualReads.push({address:q.address,size:q.size});const name=Object.keys(windows).find(k=>windows[k][0]===q.address&&windows[k][1]===q.size);
    if(name&&c.readError===name){result.event='error';result.error='injected binding read failure';}
    else{
     const segment=segments.find(([a,b])=>q.address>=a&&q.address+q.size<=a+b.length);
     assert(segment,`fixture missing ${q.address.toString(16)}/${q.size} in ${c.name}`);
     const bytes=Buffer.from(segment[1].subarray(q.address-segment[0],q.address-segment[0]+q.size));
     if(q.address>=BASE&&q.address+q.size<=BASE+moduleBytes.length){
      if(q.replacements!==false)put(bytes,0,0x68012345);
      if(c.badCode===q.address&&q.replacements===false)put(bytes,0,0x12345678);
     }
     result.base64=(name&&c.shortRead===name?bytes.subarray(0,bytes.length-1):bytes).toString('base64');
    }
   }else if(q.event==='memory.disasm'){
    result.lines=[];for(let at=q.address;at<q.end;at+=4)result.lines.push({type:'opcode',address:at,addressSize:4,encoding:moduleBytes.readUInt32LE(at-BASE)});
   }else if(q.event==='cpu.getAllRegs')result.categories=[{name:'MIPS GPR',uintValues:gprs()}];
   else assert(['input.buttons.send','input.analog.send'].includes(q.event),`unexpected RPC ${q.event}`);
   queueMicrotask(()=>this.emit('message',{data:JSON.stringify(result)}));
  }
  close(){closed=true;this.readyState=3;this.emit('close',{});}
 }
 const fakeProcess={env:{MARKER_SELECTOR_OUT_DIR:out,MARKER_MAX_STOPS:'1',MARKER_MAX_ROWS:'1',MARKER_DURATION_MS:'1000',
  MARKER_STAGE_TIMEOUT_MS:'60',MARKER_BINDING_PROBE:c.enabled===false?'0':'1',
  MARKER_BUTTONS_JSON:JSON.stringify({square:true,rtrigger:true}),MARKER_ANALOG_JSON:JSON.stringify({stick:'left',x:0.2,y:-0.4})},on(){},exitCode:0};
 function outputOnly(filename){const relative=path.relative(out,path.resolve(filename));assert(!relative.startsWith('..')&&!path.isAbsolute(relative),'VM may write only its temporary output');}
 const guardedFS={...fs,writeFileSync(filename,...args){outputOnly(filename);return fs.writeFileSync(filename,...args);},
  mkdirSync(filename,...args){outputOnly(filename);return fs.mkdirSync(filename,...args);}};
 const limitedRequire=name=>{assert(['fs','path','crypto'].includes(name),`sampler dependency not whitelisted: ${name}`);return name==='fs'?guardedFS:require(name);};
 try{
  await vm.runInNewContext(samplerSource,{require:limitedRequire,Buffer,WebSocket:MockWebSocket,process:fakeProcess,__dirname,__filename:sampler,
   console:{log(){},error(x){errors.push(String(x));}},setTimeout,clearTimeout,Date,Promise});
  const report=JSON.parse(fs.readFileSync(path.join(out,'marker_selector_writer.json'),'utf8'));
  assert.equal(fakeProcess.exitCode,c.failure?1:0,c.name);assert.equal(active.size,0);assert(maxActive<=1);assert(closed);assert.equal(errors.length,0);
  assert.equal(report.ownedBP,null);assert.equal(report.cleanup.errors.length,0);assert(report.cleanup.buttonsReleased&&report.cleanup.analogReleased&&report.cleanup.ownedBreakpointRemoved);
  assert.equal(report.producer.sha256,samplerSHA);assert.equal(report.bounds.bindingProbe,c.enabled!==false);
  const lastButtons=commands.filter(q=>q.event==='input.buttons.send').at(-1),lastAnalog=commands.filter(q=>q.event==='input.analog.send').at(-1);
  assert(Object.values(lastButtons.buttons).every(x=>x===false));assert.equal(lastAnalog.x,0);assert.equal(lastAnalog.y,0);
  assert(commands.some(q=>q.event==='input.buttons.send'&&q.buttons.square&&q.buttons.rtrigger),'exercise release after held input');
  if(c.failure){
   assert(report.failure&&c.failure.test(report.failure),`${c.name}: wrong rejection ${report.failure}`);assert.equal(report.rows.length,0);
   if(c.externalPost){assert(!commands.slice(externalAt).some(q=>q.event==='cpu.resume'),'external stop must remain paused');assert(!report.cleanup.resumedOwnStop);}
   else{assert.equal(report.postWriteStopCount,0);assert(!commands.some(q=>q.event==='cpu.breakpoint.add'&&q.address===POST),'binding rejection must not advance to post-write');assert(report.cleanup.resumedOwnStop);}
   console.log(`PASS ${c.name}: rejected; no false row; owned BP/input cleanup`);
   return {scenario:c.name,outcome:'rejected',reason:report.failure.split('\n')[0],cleanup:true};
  }
  assert.equal(report.failure,null);assert.equal(report.rows.length,1);const row=report.rows[0];assert(row.actualWriteObserved);assert.equal(row.classification,'observed_selector_write');
  assert.equal(row.callerChain.rootSelectorEntrySP,R);assert.equal(row.callerChain.recursionDepth,depth);assert.deepEqual(row.changedByteOffsets,[0x14c]);
  assert.equal(row.postWrite.fields.selectorU16,1);assert.equal(row.semanticName,null);
  if(c.enabled===false){assert.equal(row.bindingProvenance,undefined);assert(!actualReads.some(q=>Object.values(windows).some(([a,n])=>q.address===a&&q.size===n)));}
  else{
   const b=row.bindingProvenance;assert.equal(b.schema,'weapon-binding-source-provenance/v1');assert.equal(b.status,'read');assert.equal(b.semanticName,null);
   for(const [key,value] of Object.entries({rootSelectorEntrySP:R,gameWrapperLocalSP:G,gameFunctionLocalSP:Q,upperLocalSP:U,
    context,primary,selector:1,slotContainer:f.containerAddress,slotByteOffset:f.slotByteOffset,slotIndex:f.slotByteOffset/4,
    config:f.configAddress,actor:f.bindingActor,primaryIndex:f.mode!==0?1:0}))assert.equal(b[key],value,key);
   assert.deepEqual(Object.keys(b.windows).sort(),Object.keys(windows).sort());
   for(const [name,[address,size]] of Object.entries(windows)){
    const window=b.windows[name];assert.equal(window.address,address);assert.equal(window.size,size);assert.equal(window.raw.bytes,size);
    const raw=fs.readFileSync(window.raw.file);assert.equal(hash(raw),window.raw.sha256);
    const segment=segments.find(([a,z])=>address>=a&&address+size<=a+z.length);assert(segment);
    assert(raw.equals(segment[1].subarray(address-segment[0],address-segment[0]+size)),`exact ${name} bytes`);
    assert(actualReads.some(q=>q.address===address&&q.size===size),`actual ${name} read`);
   }
   assert.equal(b.requestedID.config94,f.config.readUInt32LE(8));assert.equal(b.requestedID.upper374,f.locals.readUInt32LE(4));
   for(const name of ['binding_upper_full','binding_primary_getter_full'])assert(report.codeIdentity.checks.some(q=>q.name===name&&q.verified));
  }
  assert.deepEqual(commands.filter(q=>['cpu.breakpoint.add','cpu.breakpoint.remove'].includes(q.event)).map(q=>[q.event,q.address]),
   [['cpu.breakpoint.add',ENTRY],['cpu.breakpoint.remove',ENTRY],['cpu.breakpoint.add',POST],['cpu.breakpoint.remove',POST]]);
  console.log(`PASS ${c.name}: exact raw provenance and post-write pair; cleanup`);
  return {scenario:c.name,outcome:'accepted',bindingProbe:c.enabled!==false,rawWindows:c.enabled===false?0:9,cleanup:true};
 }finally{
  const resolved=path.resolve(out),relative=path.relative(path.resolve(os.tmpdir()),resolved);
  assert(relative&&!relative.startsWith('..')&&!path.isAbsolute(relative)&&path.basename(resolved).startsWith('weapon-binding-selftest-'));
  fs.rmSync(resolved,{recursive:true,force:true});
 }
}
(async()=>{
 const results=[];for(const c of cases)results.push(await test(c));
 assert.equal(hash(fs.readFileSync(sampler)),samplerSHA,'sampler changed during selftest');
 console.log(JSON.stringify({schema:'weapon-binding-offline-selftest/v1',passed:true,scenarios:results.length,
  accepted:results.filter(x=>x.outcome==='accepted').length,rejected:results.filter(x=>x.outcome==='rejected').length,
  samplerSHA256:samplerSHA,testSHA256:hash(fs.readFileSync(__filename)),networkUsed:false,results}));
})().catch(e=>{console.error(e.stack||e);process.exitCode=1;});
