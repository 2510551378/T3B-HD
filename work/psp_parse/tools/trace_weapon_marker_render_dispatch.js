// Offline-testable observer of an existing PPSSPP debugger; no launch/UI/savestate IO.
// One owned BP: render ENTRY -> before-JALR DISPATCH -> callback RETURN, never both together.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const ENTRY=0x08b692f4,DISPATCH=0x08b694f4,RETURN=0x08b694fc,BASE=0x08804000;
const BP_TARGETS=new Set([ENTRY,DISPATCH,RETURN]);
const GEOMETRY_SHA='168578abca4c4f5d22d5994ebced6b93a25d5167428bfd47f1a1150a8d42e65a';
const RESOURCE_SHA='04afeecb38df20d41a7c24da1686e31cf70a8e631aa51e48321c776ab21d89b6';
const STACK_BYTES=0x30;
const out=process.env.MARKER_RENDER_OUT_DIR||process.env.MARKER_OUT_DIR;
const port=Number(process.env.PPSSPP_DEBUGGER_PORT||9900);
const maxStops=Number(process.env.MARKER_MAX_STOPS||1200),maxRows=Number(process.env.MARKER_MAX_ROWS||12);
const durationMs=Number(process.env.MARKER_DURATION_MS||15000),returnTimeoutMs=Number(process.env.MARKER_STAGE_TIMEOUT_MS||3000);

const held=JSON.parse(process.env.MARKER_BUTTONS_JSON||'{}');
const analog=process.env.MARKER_ANALOG_JSON?JSON.parse(process.env.MARKER_ANALOG_JSON):null;
if(!out||!Number.isInteger(port)||port<1||port>65535||!Number.isInteger(maxStops)||maxStops<1||maxStops>20000||!Number.isInteger(maxRows)||maxRows<1||maxRows>240||!Number.isFinite(durationMs)||durationMs<100||durationMs>120000||!Number.isFinite(returnTimeoutMs)||returnTimeoutMs<50||returnTimeoutMs>10000)throw new Error('invalid render observer bounds');
if(!held||typeof held!=='object'||Array.isArray(held)||Object.values(held).some(v=>typeof v!=='boolean'))throw new Error('buttons must be a boolean object');
if(analog&&(!Number.isFinite(analog.x)||!Number.isFinite(analog.y)||Math.abs(analog.x)>1||Math.abs(analog.y)>1))throw new Error('invalid analog input');
const release=Object.fromEntries([...new Set(['rtrigger','ltrigger','square','triangle','circle','cross',...Object.keys(held)])].map(k=>[k,false]));
const modulePath=path.resolve(__dirname,'../raw/ULJM05798_module_08804000.bin');
const moduleBytes=fs.readFileSync(modulePath);
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
// Capture the producer once at module load, before connecting to the debugger.
const producer={file:path.resolve(__filename),sha256:sha(fs.readFileSync(__filename))};
if(sha(moduleBytes)!=='b5fc590366fc610f2cdd60104a4a28851bacd402c4600a4c296776e1dea0869f')throw new Error('selected original module SHA256 mismatch');
const words=b=>Array.from({length:b.length/4},(_,i)=>b.readUInt32LE(i*4));
const floats=b=>Array.from({length:b.length/4},(_,i)=>b.readFloatLE(i*4));
const pointer=(a,n=4)=>Number.isInteger(a)&&a%4===0&&a>=0x08000000&&a+n<=0x0c000000;
const decodedBytes=(response,address,size)=>{
  if(!Array.isArray(response.lines))throw new Error('missing disassembly lines');
  const result=Buffer.alloc(size),seen=new Set();
  for(const line of response.lines){
    if(!Number.isInteger(line.address)||!Number.isInteger(line.addressSize)||line.addressSize<4||line.addressSize%4)throw new Error('invalid disassembly range');
    if(line.address>=address+size||line.address+line.addressSize<=address)continue;
    if(!['opcode','macro'].includes(line.type))throw new Error('non-opcode in code identity range');
    const list=line.addressSize===4?[line.encoding]:line.macroEncoding;
    if(!Array.isArray(list)||list.length!==line.addressSize/4||list[0]!==line.encoding)throw new Error('missing original macro encoding');
    list.forEach((value,i)=>{
      const at=line.address+4*i;
      if(!Number.isInteger(value)||value<0||value>0xffffffff)throw new Error('invalid original opcode');
      if(at<address||at>=address+size)return;
      if((at-address)%4||seen.has(at))throw new Error('overlapping original opcode');
      result.writeUInt32LE(value,at-address);seen.add(at);
    });
  }
  if(seen.size!==size/4)throw new Error('incomplete original opcode coverage');
  return result;
};


const SECTION_SHA='97443c71b1c1d644f323c6ff611afb740329cfe11a47a711f39dc59de06ec802';
const sectionPath=path.resolve(__dirname,'../out/WEAPON_MARKER_STATE_20261020/original_source_match_section.bin');
const section=fs.readFileSync(sectionPath);
if(sha(section)!==SECTION_SHA)throw new Error('selected original FEP SHA mismatch');
const functions=[[ENTRY,0x24c,'render_dispatch'],[0x08b69540,0x24,'render_wrapper']];
const TYPES={152:{target:0x08b9809c,size:0x3f0,parameterBytes:0x20,dataBytes:7},155:{target:0x08b9a514,size:0x808,parameterBytes:0x4c,dataBytes:0x20}};
async function main(){
 fs.mkdirSync(out,{recursive:true});const reportFile=path.join(out,'marker_render_dispatch.json');
 if(fs.existsSync(reportFile))throw new Error('refusing to overwrite marker_render_dispatch.json');
 const ws=new WebSocket(`ws://127.0.0.1:${port}/debugger`,'debugger.ppsspp.org');
 const pending=new Map(),stops=[],waiters=[];
 let serial=0,ownedBP=null,ownStop=false,externalPauseSeen=false,interrupted=false,version=null,failure=null,inFlight=null;
 let entryStopCount=0,dispatchStopCount=0,returnStopCount=0,targetEntryCount=0,firstStopTicks=null,lastStopTicks=null;
 const rows=[],rejects={},transitions=[],inputs=[],codeChecks=[],initialBreakpoints=[],gprCategoryDiagnostics=[];
 const cleanup={errors:[]};
 const reject=reason=>{rejects[reason]=(rejects[reason]||0)+1;};
 process.on('SIGINT',()=>{interrupted=true;});process.on('SIGTERM',()=>{interrupted=true;});
 ws.addEventListener('message',event=>{
  let m;try{m=JSON.parse(event.data);}catch{return;}
  const p=pending.get(m.ticket);
  if(p){pending.delete(m.ticket);clearTimeout(p.timer);m.event==='error'?p.reject(new Error(JSON.stringify(m))):p.resolve(m);return;}
  if(m.event==='cpu.stepping'){
   m.ownedBreakpointAtReceipt=ownedBP;
   if(ownedBP===null||m.pc!==ownedBP)externalPauseSeen=true;
   const next=waiters.shift();if(next){clearTimeout(next.timer);next.resolve(m);}else stops.push(m);
  }
 });
 ws.addEventListener('close',()=>{
  for(const p of pending.values()){clearTimeout(p.timer);p.reject(new Error('debugger closed'));}pending.clear();
  for(const p of waiters.splice(0)){clearTimeout(p.timer);p.reject(new Error('debugger closed'));}
 });
 const rpc=(event,fields={},timeoutMs=10000)=>new Promise((resolve,reject)=>{
  const ticket=`marker-render-dispatch-${++serial}`,timer=setTimeout(()=>{pending.delete(ticket);reject(new Error(`timeout: ${event}`));},timeoutMs);
  pending.set(ticket,{resolve,reject,timer});ws.send(JSON.stringify({event,...fields,ticket}));
 });
 const nextStop=timeout=>stops.length?Promise.resolve(stops.shift()):new Promise((resolve,reject)=>{
  const p={resolve,reject,timer:setTimeout(()=>{const i=waiters.indexOf(p);if(i>=0)waiters.splice(i,1);reject(new Error('wait interval elapsed'));},timeout)};waiters.push(p);
 });
 // Queued stops are never cleared or resumed past. The loop must consume them.
 const resume=()=>{if(stops.length||externalPauseSeen)return false;ws.send(JSON.stringify({event:'cpu.resume'}));ownStop=false;return true;};
 const read=async(address,size,replacements=true)=>{
  if(!pointer(address,size)||size>0x20000)throw new Error(`invalid guest read ${address.toString(16)}/${size}`);
  const r=await rpc('memory.read',{address,size,replacements}),b=Buffer.from(r.base64||'','base64');
  if(b.length!==size)throw new Error('short guest read');return b;
 };
 const save=(name,bytes)=>{const file=path.resolve(out,name);fs.writeFileSync(file,bytes);return{file,bytes:bytes.length,sha256:sha(bytes)};};
 const input=async buttons=>{await rpc('input.buttons.send',{buttons});inputs.push({buttons,acknowledged:true});};
 const flush=()=>fs.writeFileSync(reportFile,JSON.stringify({schema:'weapon-marker-render-dispatch-capture/v1',producer,version,
  entryPC:ENTRY,dispatchPC:DISPATCH,returnPC:RETURN,module:{file:modulePath,sha256:sha(moduleBytes)},originalFep:{file:sectionPath,sha256:SECTION_SHA},
  expectedGeometrySHA256:GEOMETRY_SHA,expectedResourcePrefix64SHA256:RESOURCE_SHA,
  bounds:{maxStops,maxRows,durationMs,returnTimeoutMs,stackBytes:STACK_BYTES,maxDescriptorListCount:32,maxIndex:95,supportedTypes:TYPES},
  entryStopCount,dispatchStopCount,returnStopCount,targetEntryCount,firstStopTicks,lastStopTicks,initialBreakpoints,inputs,transitions,ownedBP,gprCategoryDiagnostics,
  codeIdentity:{verified:codeChecks.length>=functions.length&&codeChecks.every(c=>c.verified),checks:codeChecks},
  inFlight,rows,rejections:rejects,cleanup,failure,externalPauseSeen,semanticName:null,geDrawObserved:false,
  negativeScope:targetEntryCount===0?'No exact-resource/exact-weapon pass1 render entry within bounded stops/ticks; not proof of no render consumer.':null,
  limits:['A completed callback invocation/return is not a captured GE draw or identified visual effect.',
   'Only the original bank1 type14 enqueue consumer path and types152/155 are supported.',
   'Data snapshots follow original handler read extents: type152 7bytes, type155 32bytes; no assumed 64byte output matrix.',
   'Before-JALR a2 is a method descriptor; t0 is the parameter copied by its delay slot.']},null,2));
 const codeIdentity=async(name,address,size)=>{
    const expected=moduleBytes.subarray(address-BASE,address-BASE+size);
    if(expected.length!==size)throw new Error('identity code outside module');
    const check={name,address,size,expected:save(`${name}_expected.bin`,expected),verified:false};codeChecks.push(check);
    const raw=await read(address,size);check.raw=save(`${name}_raw.bin`,raw);check.rawHex=raw.toString('hex');
    const original=await read(address,size,false);check.original=save(`${name}_original.bin`,original);
    check.originalHex=original.toString('hex');flush();
    const disasm=await rpc('memory.disasm',{address,end:address+size,displaySymbols:false});
    check.disasm=save(`${name}_disasm.json`,Buffer.from(JSON.stringify(disasm,null,2),'utf8'));
    const decoded=decodedBytes(disasm,address,size);check.decoded=save(`${name}_decoded.bin`,decoded);
    check.differences=words(original).flatMap((v,i)=>v===expected.readUInt32LE(i*4)?[]:[{address:address+i*4,expected:expected.readUInt32LE(i*4),original:v}]);
    check.verified=original.equals(expected)&&decoded.equals(expected);flush();
    if(!check.verified)throw new Error(`original opcode identity failed: ${name}`);
  };
  const removeBP=async()=>{
    if(ownedBP===null)return;
    const address=ownedBP;await rpc('cpu.breakpoint.remove',{address});ownedBP=null;
    transitions.push({operation:'remove',address,ownedActiveCount:0});flush();
  };
  const addBP=async address=>{
    if(ownedBP!==null)throw new Error('single-BP invariant violated before add');
    // Remember an attempted add before its ACK, so timeout cleanup also removes it.
    ownedBP=address;transitions.push({operation:'add_requested',address,ownedActiveCount:1});flush();
    await rpc('cpu.breakpoint.add',{address,enabled:true,log:false});
    transitions.push({operation:'add_acknowledged',address,ownedActiveCount:1});flush();
  };
  const regs=async()=>{
    const result=await rpc('cpu.getAllRegs'),category=result.categories?.[0],values=category?.uintValues;
    const name=category?.name??null,length=Array.isArray(values)?values.length:null;
    let observation=gprCategoryDiagnostics.find(d=>d.name===name&&d.length===length);
    if(!observation){observation={name,length,categoryId:category?.id??null,categoryKeys:category?Object.keys(category):[],categoryCount:result.categories?.length??null,reads:0,usedGPRRange:[0,31]};gprCategoryDiagnostics.push(observation);}
    observation.reads++;flush();
    if(!Array.isArray(values)||values.length<32)throw new Error('invalid CPU GPRs: fewer than 32 registers');
    const g=values.slice(0,32); // Some builds append PC/HI/LO to the category.
    if(g.some(v=>!Number.isInteger(v)||v<0||v>0xffffffff))throw new Error('invalid CPU GPRs: non-u32 value in first 32');
    return g;
  };
  const identity=async actor=>{
    if(!pointer(actor,0x3ec))return null;
    const fields=await read(actor+0x3c4,40),sourceBase=fields.readUInt32LE(0),metadata=fields.readUInt32LE(0x24);
    if(!pointer(sourceBase,3*0x130)||!pointer(metadata,64))return null;
    const header=await read(metadata,64),table=header.readUInt32LE(0x34);
    if(header.readUInt16LE(6)!==3||!pointer(table,16))return null;
    const packet=await read(table,16),updates=packet[9];
    if(packet.readUInt16LE(0)!==1||packet.readUInt16LE(4)!==243||packet[10]*2!==16||packet.readUInt32LE(12)!==0x522||updates>8)return null;
    const geometry=await read(table+16+updates*4,243*16),prefix=Buffer.alloc(4);prefix.writeUInt32LE(0x522);
    if(sha(Buffer.concat([prefix,geometry]))!==GEOMETRY_SHA)return null;
    return{actor,sourceBase,metadata,table,fields,header,packet,geometry};
  };

 const abi=(ok,msg)=>{if(!ok)throw new Error(`render dispatch ABI mismatch: ${msg}`);};
 const window=async(name,address,size,matrix=false)=>{
  const b=await read(address,size),result={address,size,raw:save(name,b)};
  if(matrix){result.words=words(b);result.f32=floats(b);abi(result.f32.every(Number.isFinite),'nonfinite matrix');}
  return{bytes:b,record:result};
 };
 const originalPointer=(base,word,offset)=>word===offset||(offset!==0&&word===base+offset);
 const collectDescriptor=async(D,base,sample)=>{
  const off=D-base;
  abi([0x10ba0,0x10be8,0x10c30,0x10c78].includes(off),'unsupported actual node+40 descriptor path');
  const dw=await window(`descriptor_${sample}.bin`,D,0x48),d=dw.bytes,lists=[];
  inFlight.entry.descriptor=dw.record;inFlight.descriptorPath={offset:off,lists};flush();
  for(const [role,co,po] of [['pre',0x19,0x3c],['post',0x14,0x28],['render',0x15,0x2c]]){
   const count=d[co],expectedCount=section[off+co],sourceList=section.readUInt32LE(off+po),actualList=d.readUInt32LE(po);
   abi(count===expectedCount&&count<=32,'descriptor count mismatch/bound');
   abi(actualList===base+sourceList,'descriptor live list pointer relocation');
   const listAddress=base+sourceList;
   abi(sourceList+count*2<=section.length,'descriptor list outside FEP');
   const size=(count*2+3)&~3,list=await window(`descriptor_${role}_list_${sample}.bin`,listAddress,size),items=[];
   const defsOff=section.readUInt32LE(off+0x1c);
   abi(d.readUInt32LE(0x1c)===base+defsOff,'descriptor live definition table pointer relocation');
   const listRow={role,count,list:list.record,definitions:items};lists.push(listRow);flush();
   for(let j=0;j<count;j++){
    const index=list.bytes.readUInt16LE(j*2);
    abi(index===section.readUInt16LE(sourceList+j*2)&&index<96,'descriptor index mismatch/bound');
    abi(defsOff+4*index+4<=section.length,'definition table outside FEP');
    const ptr=await window(`descriptor_${role}_ptr_${j}_${sample}.bin`,base+defsOff+index*4,4),bo=section.readUInt32LE(defsOff+index*4);
    abi(ptr.bytes.readUInt32LE(0)===base+bo&&bo+12<=section.length,'definition live pointer mismatch/bound');
    const def=await window(`descriptor_${role}_def_${j}_${sample}.bin`,base+bo,12),v=def.bytes,expected=section.subarray(bo,bo+12);
    items.push({ordinal:j,index,offset:bo,type:v.readUInt16LE(0),mutableDataOffset:v.readUInt16LE(2),pointer:ptr.record,raw:def.record});flush();
    const sourcePtr=expected.readUInt32LE(8),expectedPtr=sourcePtr?base+sourcePtr:0;
    abi(v.subarray(0,8).equals(expected.subarray(0,8))&&v.readUInt32LE(8)===expectedPtr,'definition original-byte/live-pointer identity');
   }
  }
 };
 const collectResource=async(before,sample)=>{
  const base=before.readUInt32LE(0x190),tableRecord=before.readUInt32LE(0x194),record=before.readUInt32LE(0x198);
  abi(pointer(base,section.length),'FEP source base outside guest RAM');
  const h=await window(`source_header_${sample}.bin`,base,0x50);
  inFlight.resource={source190:base,source194:tableRecord,source198:record,header:h.record};flush();
  const hb=h.bytes;
  abi(hb.subarray(0,8).equals(section.subarray(0,8))&&hb.readUInt32LE(0x14)===section.length,'FEP magic/version/size identity');
  abi(hb.readUInt16LE(0x1c)===93&&hb.readUInt16LE(0x1e)===93,'FEP table counts');
  abi(originalPointer(base,hb.readUInt32LE(8),section.readUInt32LE(8)),'FEP header offset8Pointer identity');
  // Preserve the existing bounded header offset-or-relocated contract. Actual
  // D/table1/list/definition consumer pointers below must be absolute live ones.
  for(const p of [0x28,0x2c])abi(originalPointer(base,hb.readUInt32LE(p),section.readUInt32LE(p)),'FEP header table offset/pointer identity');
  abi(tableRecord===base+0xfb4&&record===base+0x48f0,'selected FEP state pointer chain');
  const slot=await window(`source_table1_slot4_${sample}.bin`,base+0x1c4+16,4),tr=await window(`source_table1_record4_${sample}.bin`,tableRecord,0x34);
  const rr=await window(`source_record192_${sample}.bin`,record,0xc0);
  Object.assign(inFlight.resource,{table1Slot4:slot.record,table1Record4:tr.record,record192:rr.record,prefix64:inFlight.resourcePrefix64});flush();
  abi(slot.bytes.readUInt32LE(0)===base+0xfb4&&rr.bytes.equals(section.subarray(0x48f0,0x49b0)),'original FEP record/live-slot identity');
  const pointerList=tr.bytes.readUInt32LE(0x20),expectedList=section.readUInt32LE(0xfb4+0x20);
  abi(tr.bytes.readUInt16LE(0x12)===4&&pointerList===base+expectedList,'table1 live nested list identity');
  const nested=await window(`source_nested_list_${sample}.bin`,base+expectedList,16);
  inFlight.resource.nestedList=nested.record;flush();
  abi(words(nested.bytes).every((v,i)=>v===base+section.readUInt32LE(expectedList+i*4)),'table1 live nested descriptor pointer chain');
  return base;
 };

 const savedOffsets=[[16,4],[17,8],[18,0xc],[19,0x10],[20,0x14],[21,0x18],[22,0x1c],[23,0x20]];
 const verifyStack=(stack,entry)=>{
  abi(stack.readUInt32LE(0x24)===entry.entryRA,'dispatch saved caller RA');
  for(const [r,o] of savedOffsets)abi(stack.readUInt32LE(o)===entry.entryGPR[r],`dispatch saved register ${r}`);
 };
 const advance=async(phase,address)=>{
  await removeBP();await codeIdentity(`${phase}_${inFlight.sample}`,address,8);
  inFlight.phase=phase;inFlight.expectedPC=address;inFlight.returnDeadline=Date.now()+returnTimeoutMs;flush();await addBP(address);resume();
 };
 const captureWeapon=async(id,handle,primaryRaw,label)=>({
  actor:id.actor,sourceBase:id.sourceBase,metadata:id.metadata,drawTable:id.table,geometrySHA256:GEOMETRY_SHA,geometry:save(`geometry_${label}.bin`,id.geometry),
  identityRaw:{primary:{address:handle,raw:save(`primary_handle_${label}.bin`,primaryRaw)},actorFields:{address:id.actor+0x3c4,raw:save(`actor_fields_${label}.bin`,id.fields)},metadata:{address:id.metadata,raw:save(`metadata_${label}.bin`,id.header)},draw:{address:id.table,raw:save(`draw_header_${label}.bin`,id.packet)}}
 });
 try{
  await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('debugger open timeout')),10000);ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});ws.addEventListener('error',e=>{clearTimeout(timer);reject(e);},{once:true});});
  version=await rpc('version',{name:'weapon-marker-render-dispatch',version:'1'});
  const existing=await rpc('cpu.breakpoint.list');abi(Array.isArray(existing.breakpoints),'missing breakpoint inventory');initialBreakpoints.push(...existing.breakpoints);
  if(existing.breakpoints.some(bp=>bp.enabled||BP_TARGETS.has(bp.address)))throw new Error('existing active/conflicting CPU breakpoint; left unchanged');
  for(const [a,n,name]of functions)await codeIdentity(`${name}_full`,a,n);
  await input(release);if(analog)await rpc('input.analog.send',{...analog,x:0,y:0});
  if(externalPauseSeen||stops.length)throw new Error('external CPU pause during setup; left paused');
  await addBP(ENTRY);await input({...release,...held});if(analog)await rpc('input.analog.send',analog);resume();
  const deadline=Date.now()+durationMs;
  while(!interrupted){
   if(!inFlight&&(Date.now()>=deadline||entryStopCount>=maxStops||rows.length>=maxRows))break;
   const end=inFlight?inFlight.returnDeadline:deadline;
   if(Date.now()>=end){if(inFlight)throw new Error(`selected ${inFlight.phase} timeout; callback outcome unknown`);break;}
   let stop;try{stop=await nextStop(Math.min(1000,Math.max(1,end-Date.now())));}catch(e){if(e.message==='wait interval elapsed')continue;throw e;}
   const expected=inFlight?inFlight.expectedPC:ENTRY;
   if(stop.pc!==expected||stop.ownedBreakpointAtReceipt!==expected){ownStop=false;externalPauseSeen=true;throw new Error('unexpected external CPU stop; left paused');}
   ownStop=true;abi(Number.isSafeInteger(stop.ticks)&&(lastStopTicks===null||stop.ticks>=lastStopTicks),'invalid/nonmonotonic guest ticks');
   if(firstStopTicks===null)firstStopTicks=stop.ticks;lastStopTicks=stop.ticks;
   const g=await regs();
   if(!inFlight){
    entryStopCount++;const C=g[4],P=g[5],N=g[6],pass=g[7],Q=g[29];
    if(pass!==1){reject('outside pass1 scope');resume();continue;}
    if(!pointer(C,0xa8)||!pointer(P,0x1ac)||!pointer(N,0x64)){reject('invalid context/state/node pointer');resume();continue;}
    const context=await read(C,0xa8),state=await read(P,0x1ac),node=await read(N,0x64),record=state.readUInt32LE(0x198);
    if(!pointer(record,64)){reject('invalid resource pointer');resume();continue;}
    const prefix=await read(record,64);if(sha(prefix)!==RESOURCE_SHA){reject('not exact resource prefix');resume();continue;}
    const handle=state.readUInt32LE(0x144);if(!pointer(handle)){reject('missing primary handle');resume();continue;}
    const primary=await read(handle,4),id=await identity(primary.readUInt32LE(0));if(!id){reject('not exact original weapon');resume();continue;}
    targetEntryCount++;const sample=String(targetEntryCount-1).padStart(4,'0'),D=node.readUInt32LE(0x40);
    inFlight={sample:targetEntryCount-1,entryPC:ENTRY,entryTicks:stop.ticks,entryGPR:g,entrySP:Q,entryRA:g[31],entryArgs:{C,P,N,pass},C,P,N,D,
     entry:{context:{address:C,size:context.length,raw:save(`context_entry_${sample}.bin`,context)},state:{address:P,size:state.length,raw:save(`state_entry_${sample}.bin`,state)},node:{address:N,size:node.length,raw:save(`node_entry_${sample}.bin`,node)}},
     resourcePrefix64:{address:record,size:64,raw:save(`resource_prefix64_${sample}.bin`,prefix)},weapon:await captureWeapon(id,handle,primary,sample),semanticName:null,geDrawObserved:false};flush();
    inFlight.entry.stack=(await window(`entry_stack_${sample}.bin`,Q,0x30)).record;flush();
    abi(g[31]===0x08b69558,'unknown render entry caller RA');
    // ENTRY's shared context may still name a previous queued state/node;
    // the original dispatcher writes C+8c and C+90 before its JALR stage.
    const base=await collectResource(state,sample);
    inFlight.entry.descriptor=(await window(`descriptor_candidate_${sample}.bin`,D,0x48)).record;flush();
    await collectDescriptor(D,base,sample);
    const render=inFlight.descriptorPath.lists.find(x=>x.role==='render');abi(render.count===1,'unsupported render list count');
    inFlight.renderList=render;await advance('dispatch',DISPATCH);
   }else if(inFlight.phase==='dispatch'){
    dispatchStopCount++;const f=inFlight,sample=String(f.sample).padStart(4,'0');
    f.dispatchAttempt={pc:DISPATCH,ticks:stop.ticks,gpr:g,sp:g[29]};flush();
    abi(g[29]===f.entrySP-0x30&&g[16]===f.C&&g[17]===f.N&&g[19]===f.D,'dispatch SP/C/N/D');
    const stack=await window(`dispatch_stack_${sample}.bin`,g[29],0x30),c=await window(`context_dispatch_${sample}.bin`,f.C,0xa8),n=await window(`node_dispatch_${sample}.bin`,f.N,0x64);
    Object.assign(f.dispatchAttempt,{stack:stack.record,context:c.record,node:n.record});flush();verifyStack(stack.bytes,f);
    abi(g[18]===1&&g[20]===0&&g[21]===f.renderList.list.address&&g[22]===0x08c3acc0&&g[23]===0x08c3a820,'dispatch pass/index/list/registry base registers');
    abi(c.bytes.readUInt32LE(0x8c)===f.P&&c.bytes.readUInt32LE(0x90)===f.N&&n.bytes.readUInt32LE(0x40)===f.D,'dispatch current object identity');
    const item=f.renderList.definitions[0],B=c.bytes.readUInt32LE(0x94);
    abi(B===item.raw.address,'current B differs from exact D render definition');
    const bw=await window(`definition_dispatch_${sample}.bin`,B,12),actualType=bw.bytes.readUInt16LE(0),spec=TYPES[actualType];
    Object.assign(f.dispatchAttempt,{currentB:B,definition:bw.record,definitionIndex:item.index,actualType,target:g[10],parameterPointer:g[8],mutableDataPointer:g[7],expectedDelaySlotA2:g[8]});flush();
    abi(spec&&[152,155].includes(actualType),'unsupported actual render type');
    abi(bw.bytes.equals(fs.readFileSync(item.raw.raw.file)),'definition changed between entry and dispatch');
    const slotAddress=0x08c3a820+4*actualType,slot=await window(`registry_slot_${sample}.bin`,slotAddress,4),object=slot.bytes.readUInt32LE(0);
    f.dispatchAttempt.registry={slot:slot.record};flush();
    const ow=await window(`registry_object_${sample}.bin`,object,4),vt=ow.bytes.readUInt32LE(0);
    f.dispatchAttempt.registry.object=ow.record;flush();
    const vw=await window(`registry_vtable_${sample}.bin`,vt,0x28);f.dispatchAttempt.registry.vtable=vw.record;flush();
    const mw=await window(`registry_method20_${sample}.bin`,vt+0x20,8);f.dispatchAttempt.registry.method20=mw.record;flush();
    const filterAddress=0x08c3acc0+actualType,filter=await window(`registry_filter_${sample}.bin`,filterAddress&~3,4);
    const adjustment=mw.bytes.readInt16LE(0),target=mw.bytes.readUInt32LE(4),filterByte=filter.bytes[filterAddress&3];
    Object.assign(f.dispatchAttempt.registry,{filter:{fieldAddress:filterAddress,byte:filterByte,raw:filter.record},thisAdjustment:adjustment,target});flush();
    const expectedObject=moduleBytes.readUInt32LE(slotAddress-BASE),expectedVtable=moduleBytes.readUInt32LE(expectedObject-BASE);
    abi(object===expectedObject&&vt===expectedVtable&&mw.bytes.equals(moduleBytes.subarray(expectedVtable+0x20-BASE,expectedVtable+0x28-BASE)),'registry object/vtable/method original identity');
    abi(target===spec.target&&g[10]===target,'actual jalr target differs from original type registry');
    abi(g[4]===((object+adjustment)>>>0)&&g[5]===f.C&&g[6]===vt+0x20&&(filterByte&1)===0,'pre-delay-slot callback object/context/method/filter');
    const parameterSlot=n.bytes.readUInt32LE(0x48)+4*item.index,pw=await window(`parameter_slot_${sample}.bin`,parameterSlot,4),dataBase=n.bytes.readUInt32LE(0x44);
    f.dispatchAttempt.parameterSlot=pw.record;f.dispatchAttempt.mutableDataBase=dataBase;f.dispatchAttempt.sourceD2Observed=fs.readFileSync(f.entry.descriptor.raw.file).readUInt16LE(2);flush();
    abi(pw.bytes.readUInt32LE(0)===g[8]&&g[7]===dataBase+bw.bytes.readUInt16LE(2),'actual callback parameter/data pointer provenance');
    f.dispatchAttempt.parameterBefore=(await window(`parameter_before_${sample}.bin`,g[8],spec.parameterBytes)).record;
    f.dispatchAttempt.mutableDataBefore=(await window(`mutable_data_before_${sample}.bin`,g[7],spec.dataBytes)).record;flush();
    await codeIdentity(`actual_handler_type${actualType}_${sample}`,target,spec.size);
    f.dispatch={...f.dispatchAttempt};delete f.dispatchAttempt;flush();await advance('callback_return',RETURN);
   }else if(inFlight.phase==='callback_return'){
    returnStopCount++;const f=inFlight,sample=String(f.sample).padStart(4,'0'),spec=TYPES[f.dispatch.actualType];
    f.returnAttempt={pc:RETURN,ticks:stop.ticks,gpr:g,sp:g[29],ra:g[31]};flush();
    abi(g[29]===f.entrySP-0x30&&g[31]===RETURN,'callback return SP/RA');
    abi([16,17,18,19,20,21,22,23,30].every(r=>g[r]===f.dispatch.gpr[r]),'callback return callee-saved registers');
    const stack=await window(`return_stack_${sample}.bin`,g[29],0x30),c=await window(`context_return_${sample}.bin`,f.C,0xa8),p=await window(`state_return_${sample}.bin`,f.P,0x1ac),n=await window(`node_return_${sample}.bin`,f.N,0x64);
    Object.assign(f.returnAttempt,{stack:stack.record,context:c.record,state:p.record,node:n.record});flush();verifyStack(stack.bytes,f);
    abi(c.bytes.readUInt32LE(0x8c)===f.P&&c.bytes.readUInt32LE(0x90)===f.N&&c.bytes.readUInt32LE(0x94)===f.dispatch.currentB&&n.bytes.readUInt32LE(0x40)===f.D,'callback return current object identity');
    const handle=p.bytes.readUInt32LE(0x144),primary=await read(handle,4),id=await identity(primary.readUInt32LE(0));
    abi(id&&id.actor===f.weapon.actor&&id.sourceBase===f.weapon.sourceBase&&id.metadata===f.weapon.metadata&&id.table===f.weapon.drawTable,'callback return exact weapon identity');
    f.returnAttempt.weapon=await captureWeapon(id,handle,primary,`return_${sample}`);
    abi(p.bytes.readUInt32LE(0x190)===f.resource.source190&&p.bytes.readUInt32LE(0x194)===f.resource.source194&&p.bytes.readUInt32LE(0x198)===f.resource.source198,'callback return FEP pointer identity');
    const rr=await window(`resource192_return_${sample}.bin`,f.resource.source198,0xc0);f.returnAttempt.resourceRecord192=rr.record;flush();
    abi(rr.bytes.equals(section.subarray(0x48f0,0x49b0)),'callback return original FEP192 identity');
    f.returnAttempt.parameterAfter=(await window(`parameter_after_${sample}.bin`,f.dispatch.parameterPointer,spec.parameterBytes)).record;
    f.returnAttempt.mutableDataAfter=(await window(`mutable_data_after_${sample}.bin`,f.dispatch.mutableDataPointer,spec.dataBytes)).record;
    const complete={...f,classification:'observed_handler_invocation_return',returned:f.returnAttempt};
    for(const k of ['returnAttempt','phase','expectedPC','returnDeadline'])delete complete[k];rows.push(complete);inFlight=null;flush();await removeBP();
    if(rows.length>=maxRows||entryStopCount>=maxStops||Date.now()>=deadline)break;await addBP(ENTRY);resume();
   }else throw new Error('unknown render observation stage');
  }
  if(inFlight)throw new Error(interrupted?'interrupted during render observation':'render observation incomplete');
 }catch(e){failure=String(e.stack||e);}
 finally{
  if(stops.length){cleanup.unconsumedStops=stops.map(s=>({pc:s.pc,ticks:s.ticks,ownedBreakpointAtReceipt:s.ownedBreakpointAtReceipt}));ownStop=!externalPauseSeen&&stops.every(s=>s.ownedBreakpointAtReceipt!==null&&s.pc===s.ownedBreakpointAtReceipt);}
  for(const action of [async()=>{await input(release);cleanup.buttonsReleased=true;},async()=>{if(analog){await rpc('input.analog.send',{...analog,x:0,y:0});cleanup.analogReleased=true;}},async()=>{await removeBP();cleanup.ownedBreakpointRemoved=true;},async()=>{if(ownStop&&!externalPauseSeen){stops.length=0;resume();cleanup.resumedOwnStop=true;}}]){
   try{if(ws.readyState===WebSocket.OPEN)await action();else cleanup.errors.push('debugger disconnected before cleanup');}catch(e){cleanup.errors.push(String(e));}
  }flush();ws.close();
 }
 console.log(JSON.stringify({out,entryStopCount,dispatchStopCount,returnStopCount,targetEntryCount,rows:rows.length,rejections:rejects,cleanup,failure}));if(failure||cleanup.errors.length)process.exitCode=1;
}
main().catch(e=>{console.error(e.stack||e);process.exitCode=1;});
