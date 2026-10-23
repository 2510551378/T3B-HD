// Independent config-probe VM/MockWebSocket tests, adapted from binding harness.
// No real WebSocket, PPSSPP, UI, or savestate IO; production sampler is not patched in VM.
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
scenario('both-memberships-with-aliases');
scenario('contiguous-only',f=>f.pointerValues=[0,0xdeadbeef,0x08000001,f.configAddress+0xe4],null,{layout:'contiguous_only'});
scenario('pointer-only',f=>f.contiguousBase=f.configAddress+0x1000,null,{layout:'pointer_only'});
scenario('unmatched-valid-layout',f=>{f.contiguousBase=f.configAddress+0x1000;f.pointerValues=[0,0xdeadbeef,0x08000001,f.configAddress+0xe4];},null,{layout:'unmatched'});
scenario('mode-does-not-select-membership',f=>f.actorMode=999);
scenario('unaligned-relative-contiguous-delta',f=>f.contiguousBase=f.configAddress-4,null,{layout:'pointer_only'});
scenario('null-and-sentinel-unfollowed',f=>f.pointerValues=[0,0xffffffff,0xdeadbeef,f.configAddress]);
scenario('all-slots-alias-config',f=>f.pointerValues=Array(4).fill(f.configAddress));
scenario('count1',f=>{f.managerCount=1;f.contiguousBase=f.configAddress;});
scenario('count108',f=>f.managerCount=108);
scenario('pointer-table-ends-at-RAM',f=>{f.managerCount=108;f.pointerTableBase=0x0bfffe50;});
scenario('config-record-ends-at-RAM',f=>f.configAddress=0x0bffff1c,null,{layout:'pointer_only'});
scenario('raw-unknown-config-fields-retained',f=>f.unknownConfigField=0xdeadbeef);
scenario('recursive-two-config',()=>{},null,{depth:2});
scenario('config-opt-out-reads-no-manager',()=>{},null,{configEnabled:false});
scenario('full-config-fragment-mismatch',f=>f.badFullRecord=true,/config full record disagrees with retained binding fragment/);
scenario('config-record-crosses-RAM',f=>f.configAddress=0x0bffff20,/config window config_record outside bounded guest RAM/);
scenario('global-object-null',f=>f.globalObject=0,/config manager global object outside bounded guest RAM/);
scenario('global-object-unaligned',f=>f.globalObject+=1,/config manager global object outside bounded guest RAM/);
scenario('global-object-crosses-RAM',f=>f.globalObject=0x0bfffd00,/config manager global object outside bounded guest RAM/);
scenario('manager-fields-crosses-RAM',f=>f.globalObject=0x0bff8000,/config window manager_fields outside bounded guest RAM/);
scenario('manager-count0',f=>f.managerCount=0,/config manager count outside 1..108/);
scenario('manager-count109',f=>f.managerCount=109,/config manager count outside 1..108/);
scenario('manager-count-u32-max',f=>f.managerCount=0xffffffff,/config manager count outside 1..108/);
scenario('contiguous-base-null',f=>f.contiguousBase=0,/config contiguous table range outside bounded guest RAM/);
scenario('contiguous-base-unaligned',f=>f.contiguousBase+=1,/config contiguous table range outside bounded guest RAM/);
scenario('contiguous-span-crosses-RAM',f=>f.contiguousBase=0x0bfffff0,/config contiguous table range outside bounded guest RAM/);
scenario('pointer-base-null',f=>f.pointerTableBase=0,/config pointer table range outside bounded guest RAM/);
scenario('pointer-base-unaligned',f=>f.pointerTableBase+=1,/config pointer table range outside bounded guest RAM/);
scenario('pointer-span-crosses-RAM',f=>f.pointerTableBase=0x0bfffffc,/config pointer table range outside bounded guest RAM/);
scenario('full-config-short-read',()=>{},/short guest read/,{shortRead:'config_record'});
scenario('manager-global-short-read',()=>{},/short guest read/,{shortRead:'manager_global'});
scenario('manager-fields-short-read',()=>{},/short guest read/,{shortRead:'manager_fields'});
scenario('pointer-table-short-read',()=>{},/short guest read/,{shortRead:'pointer_table'});
scenario('manager-fields-RPC-error',()=>{},/injected binding read failure/,{readError:'manager_fields'});
scenario('manager-getter-code-mismatch',()=>{},/original opcode identity failed: config_manager_getter_full/,{badCode:0x0896c5fc});
scenario('contiguous-getter-code-mismatch',()=>{},/original opcode identity failed: config_contiguous_getter_full/,{badCode:0x08ac288c});
scenario('pointer-getter-code-mismatch',()=>{},/original opcode identity failed: config_pointer_getter_full/,{badCode:0x08ac28cc});
scenario('contiguous-wrapper-code-mismatch',()=>{},/original opcode identity failed: config_contiguous_wrapper_full/,{badCode:0x0896ce9c});
scenario('config-unknown-caller',f=>f.gameRA=0x08a9a8c8,/binding probe encountered an unsupported game caller/);
scenario('config-external-post-preserved',()=>{},/unexpected external CPU stop/,{externalPost:true});

async function test(c){
 const S=0x09ff0000,P=0x097d2540,primary=0x09bd23c0,context=0x09b00000,resourceAddress=0x08d51b70;
 const depth=c.depth||0,R=S+depth*0x20,G=R+0x30,Q=R+0x50,U=R+0x70;
 const f={primary,context,mode:1,slotByteOffset:4,slotCount:3,arrayCount:2,
  slotsBase:0x09a00100,arrayBase:0x09c20000,bindingActor:0x09c00000,
  configAddress:0x09c10000,containerAddress:0x09a00000,
  stackSelector:1,stackPrimary:primary,gameRA:0x08971fe8,upperRA:0x08977cc8,
  entryRA:depth?0x08b651ac:0x08b5b9f4,
  globalObject:0x09d00000,contiguousBase:0x09c10000-2*0xe4,pointerTableBase:0x09a01000,managerCount:4,actorMode:1,
  configRecord:Buffer.alloc(0xe4,0x5a),config:pack([0x100,1,0x222333,0x400]),locals:pack([0x500,0x222333,1,primary]),
  primaryRecords:pack([primary,0x111,0x222,0x333,0x444,0x555,primary,0x666,0x777,0x888,0x999,0xaaa])};
 c.mutate(f);
 f.config.copy(f.configRecord,0x8c);if(f.badFullRecord)f.configRecord[0x90]^=1;
 if(f.unknownConfigField!==undefined)put(f.configRecord,0x10,f.unknownConfigField);
 const configCount=f.managerCount>=1&&f.managerCount<=108?f.managerCount:4;
 const configSlots=f.pointerValues||Array.from({length:configCount},(_,i)=>i===1||i===configCount-1?f.configAddress:f.configAddress+0x1000+i*0xe4);
 const configTable=pack(configSlots),manager=f.globalObject+0x340;
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
 put(bindingActor,0x148c,0x10203040);put(bindingActor,0x1538,f.actorMode);bindingActor[0x161e]=f.mode;
 const slots=pack([0x0000abcd,0x00112233,0x00445566]);
 const windows={upper_locals:[U+0x370,16],config_8c:[f.configAddress+0x8c,16],actor_80:[f.bindingActor+0x80,8],
  actor_148c:[f.bindingActor+0x148c,4],actor_1538:[f.bindingActor+0x1538,4],actor_161c:[f.bindingActor+0x161c,4],
  slot_container:[f.containerAddress,8],selected_slot:[f.slotsBase+f.slotByteOffset,4],
  primary_record:[f.arrayBase+24*(f.mode!==0?1:0),24]};
 const configWindows={config_record:[f.configAddress,0xe4],manager_global:[0x08c3bc0c,4],manager_fields:[manager+0x8be0,12],pointer_table:[f.pointerTableBase,f.managerCount*4]};
 const segments=[[0x08c3bc0c,pack([f.globalObject])],[BASE,moduleBytes],[snapshot.object,weaponActor],[snapshot.metadata,pack(snapshot.header)],
  [snapshot.drawTable,pack(snapshot.drawWords)],[snapshot.sourceBase,Buffer.concat(snapshot.records.map(x=>pack(x.words)))],
  [P,state],[primary,pack([snapshot.object])],[resourceAddress,resource],[S,stack],[S-0x20,postStack],
  [f.bindingActor,bindingActor],[f.configAddress+0x8c,f.config],[f.containerAddress,pack([f.slotsBase,f.slotCount])],
  [f.slotsBase,slots],[f.arrayBase,f.primaryRecords],[f.configAddress,f.configRecord],
  [manager+0x8be0,pack([f.contiguousBase,f.pointerTableBase,f.managerCount])],[f.pointerTableBase,configTable]];
 const out=fs.mkdtempSync(path.join(os.tmpdir(),'weapon-config-probe-selftest-'));
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
    actualReads.push({address:q.address,size:q.size});const allWindows={...windows,...configWindows};const name=Object.keys(allWindows).find(k=>allWindows[k][0]===q.address&&allWindows[k][1]===q.size);
    if(name&&c.readError===name){result.event='error';result.error='injected binding read failure';}
    else{
     const segment=segments.find(([a,b])=>q.address>=a&&q.address+q.size<=a+b.length);
     assert(segment,`fixture missing ${q.address.toString(16)}/${q.size} in ${c.name}`);
     const bytes=Buffer.from(segment[1].subarray(q.address-segment[0],q.address-segment[0]+q.size));
     if(segment[0]===BASE&&q.address>=BASE&&q.address+q.size<=BASE+moduleBytes.length){
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
  MARKER_STAGE_TIMEOUT_MS:'60',MARKER_CONFIG_PROBE:c.configEnabled===false?'0':'1',MARKER_BINDING_PROBE:c.enabled===false?'0':'1',
  MARKER_BUTTONS_JSON:JSON.stringify({square:true,rtrigger:true}),MARKER_ANALOG_JSON:JSON.stringify({stick:'left',x:0.2,y:-0.4})},on(){},exitCode:0};
 function outputOnly(filename){const relative=path.relative(out,path.resolve(filename));assert(!relative.startsWith('..')&&!path.isAbsolute(relative),'VM may write only its temporary output');}
 const guardedFS={...fs,writeFileSync(filename,...args){outputOnly(filename);return fs.writeFileSync(filename,...args);},
  mkdirSync(filename,...args){outputOnly(filename);return fs.mkdirSync(filename,...args);}};
 const limitedRequire=name=>{assert(['fs','path','crypto'].includes(name),`sampler dependency not whitelisted: ${name}`);return name==='fs'?guardedFS:require(name);};
 try{
  await vm.runInNewContext(samplerSource,{require:limitedRequire,Buffer,WebSocket:MockWebSocket,process:fakeProcess,__dirname,__filename:sampler,
   console:{log(){},error(x){errors.push(String(x));}},setTimeout,clearTimeout,Date,Promise});
  const report=JSON.parse(fs.readFileSync(path.join(out,'marker_selector_writer.json'),'utf8'));
  assert.equal(fakeProcess.exitCode,c.failure?1:0,c.name+': '+report.failure);assert.equal(active.size,0);assert(maxActive<=1);assert(closed);assert.equal(errors.length,0);
  assert.equal(report.ownedBP,null);assert.equal(report.cleanup.errors.length,0);assert(report.cleanup.buttonsReleased&&report.cleanup.analogReleased&&report.cleanup.ownedBreakpointRemoved);
  assert.equal(report.producer.sha256,samplerSHA);assert.equal(report.bounds.bindingProbe,c.enabled!==false);assert.equal(report.bounds.configProbe,c.configEnabled!==false);
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
  if(c.configEnabled===false){
   assert.equal(row.configProvenance,undefined);
   assert(!actualReads.some(q=>Object.values(configWindows).some(([a,n])=>q.address===a&&q.size===n)));
   assert(!report.codeIdentity.checks.some(x=>x.name.startsWith('config_')));
  }else{
   const cp=row.configProvenance;assert.equal(cp.schema,'weapon-config-source-provenance/v1');assert.equal(cp.status,'read');
   assert.equal(cp.config,f.configAddress);assert.equal(cp.recordBytes,0xe4);assert.equal(cp.maxCount,108);assert.equal(cp.count,f.managerCount);
   assert.equal(cp.manager,manager);assert.equal(cp.globalObject,f.globalObject);assert.equal(cp.contiguousBase,f.contiguousBase);assert.equal(cp.pointerTableBase,f.pointerTableBase);
   assert.equal(cp.semanticName,null);assert.equal(cp.branchExecuted,null);assert.equal(cp.sourceHeaderCaptured,false);assert.equal(cp.actorMode1538,f.actorMode);
   assert.equal(cp.layoutMembership,c.layout||'both');
   const expectedAliases=configSlots.flatMap((value,index)=>value===f.configAddress?[index]:[]);
   assert.deepEqual(cp.pointerMembership.indices,expectedAliases);assert.deepEqual(cp.pointerMembership.rawSlotValues,configSlots);
   assert.equal(cp.pointerMembership.payloadsRead,false);
   assert.deepEqual(cp.pointerMembership.slotAddresses,expectedAliases.map(i=>f.pointerTableBase+4*i));
   assert.deepEqual(cp.pointerMembership.slotValueClasses,configSlots.map(value=>value===0?'null':value%4===0&&value>=0x08000000&&value+0xe4<=0x0c000000?'bounded_record_candidate':'unfollowed_non_RAM_or_unaligned_value'));
   assert.deepEqual(Object.keys(cp.windows).sort(),Object.keys(configWindows).sort());
   for(const [name,[address,size]] of Object.entries(configWindows)){
    const window=cp.windows[name],raw=fs.readFileSync(window.raw.file);assert.equal(window.address,address);assert.equal(window.size,size);
    assert.equal(window.raw.bytes,size);assert.equal(hash(raw),window.raw.sha256);
    const segment=segments.find(([a,z])=>address>=a&&address+size<=a+z.length);assert(segment);
    assert(raw.equals(segment[1].subarray(address-segment[0],address-segment[0]+size)),`exact config ${name}`);
    assert.equal(actualReads.filter(q=>q.address===address&&q.size===size).length,1,`one ${name} read`);
   }
   const tableRead=actualReads.filter(q=>q.address===f.pointerTableBase&&q.size===f.managerCount*4);assert.equal(tableRead.length,1);assert(tableRead[0].size<=432);
   for(const value of configSlots){
    if(value!==f.configAddress)assert(!actualReads.some(q=>q.address===value&&q.size===0xe4),'never follow unmatched slot payload');
   }
   assert(!actualReads.some(q=>q.address===f.contiguousBase-8||q.address===f.pointerTableBase-8),'no unproven header read');
   for(const [name,address,size] of [['config_manager_getter_full',0x0896c5fc,0x10],['config_contiguous_getter_full',0x08ac288c,0x40],
     ['config_pointer_getter_full',0x08ac28cc,0x34],['config_contiguous_wrapper_full',0x0896ce9c,0x30]]){
    assert(report.codeIdentity.checks.some(x=>x.name===name&&x.address===address&&x.size===size&&x.verified));
   }
  }
  assert.deepEqual(commands.filter(q=>['cpu.breakpoint.add','cpu.breakpoint.remove'].includes(q.event)).map(q=>[q.event,q.address]),
   [['cpu.breakpoint.add',ENTRY],['cpu.breakpoint.remove',ENTRY],['cpu.breakpoint.add',POST],['cpu.breakpoint.remove',POST]]);
  console.log(`PASS ${c.name}: raw config/manager/table memberships; cleanup`);
  return {scenario:c.name,outcome:'accepted',configProbe:c.configEnabled!==false,configWindows:c.configEnabled===false?0:4,cleanup:true};
 }finally{
  const resolved=path.resolve(out),relative=path.relative(path.resolve(os.tmpdir()),resolved);
  assert(relative&&!relative.startsWith('..')&&!path.isAbsolute(relative)&&path.basename(resolved).startsWith('weapon-config-probe-selftest-'));
  fs.rmSync(resolved,{recursive:true,force:true});
 }
}
(async()=>{
 const results=[];
 // Invalid opt-in combinations fail before network construction or output IO.
 let sockets=0,writes=0;
 const preflightFS={...fs,mkdirSync(){writes++;throw new Error('unexpected preflight write');},writeFileSync(){writes++;throw new Error('unexpected preflight write');}};
 const preflightRequire=name=>name==='fs'?preflightFS:require(name);
 assert.throws(()=>vm.runInNewContext(samplerSource,{require:preflightRequire,Buffer,process:{env:{MARKER_CONFIG_PROBE:'1',MARKER_BINDING_PROBE:'0'}},
   __dirname,__filename:sampler,WebSocket:class{constructor(){sockets++;}},console,setTimeout,clearTimeout}),/MARKER_CONFIG_PROBE requires MARKER_BINDING_PROBE=1/);
 assert.equal(sockets,0);assert.equal(writes,0);
 results.push({scenario:'config-opt-in-requires-binding',outcome:'rejected-before-IO',cleanup:'no resources acquired'});
 for(const c of cases)results.push(await test(c));
 assert.equal(hash(fs.readFileSync(sampler)),samplerSHA,'sampler changed during selftest');
 console.log(JSON.stringify({schema:'weapon-config-probe-offline-selftest/v1',passed:true,scenarios:results.length,
  accepted:results.filter(x=>x.outcome==='accepted').length,rejected:results.filter(x=>x.outcome.startsWith('rejected')).length,
  samplerSHA256:samplerSHA,testSHA256:hash(fs.readFileSync(__filename)),networkUsed:false,results}));
})().catch(e=>{console.error(e.stack||e);process.exitCode=1;});
