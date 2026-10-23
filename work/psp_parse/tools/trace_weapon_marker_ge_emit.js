// Offline-testable observer of an existing PPSSPP debugger; no launch/UI/savestate IO.
// One owned BP follows nine render/matrix/VIEW/geometry/CPU-PRIM stages.
// CPU display-list writes are observed; GE execution is outside this probe.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const ENTRY=0x08b69b58,DISPATCH=0x08b69d64,RETURN=0x08b69d6c,BASE=0x08804000;
const MATRIX_ENTRY=0x08b66bb4,VIEW_ENTRY=0x08c01088,EMIT_ENTRY=0x08bfff98;
const BP_TARGETS=new Set([ENTRY,DISPATCH,RETURN,MATRIX_ENTRY,VIEW_ENTRY,EMIT_ENTRY,0x08b982b4,0x08b9a76c,0x08b6270c,0x08b6050c,0x08bba214,0x08b5e3b0]);
const GEOMETRY_SHA='168578abca4c4f5d22d5994ebced6b93a25d5167428bfd47f1a1150a8d42e65a';
const RESOURCE_SHA='04afeecb38df20d41a7c24da1686e31cf70a8e631aa51e48321c776ab21d89b6';
const STACK_BYTES=0x30;
const capturePose=process.env.MARKER_CAPTURE_SOURCE_WORLD==='1';
const captureFullHandler=process.env.MARKER_CAPTURE_FULL_HANDLER_DL==='1';
const geFrameCount=Number(process.env.MARKER_GE_CAPTURE_FRAMES||0);
const geArmMode=process.env.MARKER_GE_CAPTURE_ARM||'immediate';
if(!['immediate','target'].includes(geArmMode))throw new Error('invalid GE arm mode');
if(!Number.isInteger(geFrameCount)||geFrameCount<0||geFrameCount>16)throw new Error('invalid GE capture bound');
const out=process.env.MARKER_GE_EMIT_OUT_DIR||process.env.MARKER_OUT_DIR;
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
const functions=[[ENTRY,0x258,'render_alt_dispatch'],[0x08bbd828,0x3c,'render_alt_wrapper'],[MATRIX_ENTRY,0x3b4,'matrix_helper'],[0x08b6589c,0x104,'matrix_mode1_helper'],[VIEW_ENTRY,0x268,'matrix_writer'],[EMIT_ENTRY,0xd0,'prim_writer'],[0x08bbb8d4,0x5c,'view_compose'],[0x08bfff6c,0x2c,'matrix_wrapper'],[0x08c01e9c,0x58,'stall_update']];
const PATHS={152:{handlerFrame:0xd0,matrixReturn:0x08b982b4,viewCallerRA:0x08b982bc,geometryHelper:0x08b6270c,geometryRA:0x08b98410,sourceTableField:0x38,containerField:0xa0,emitDelta:0x70,emitReturn:0x08bba214,callbackRAOffset:0xcc,chain:[[0,0x08b5d53c,0x08b5d558],[0x44,0x08b5ddd4],[0x50,0x08b6274c],[0x60,0x08b98410]],code:[[0x08b6270c,0x4c,'geometry152'],[0x08b5ddb0,0x30,'geometry_wrapper152'],[0x08b5d258,0x350,'geometry_body152'],[0x08bba1fc,0x24,'emit_wrapper152']]},155:{handlerFrame:0x110,matrixReturn:0x08b9a76c,viewCallerRA:0x08b9a840,geometryHelper:0x08b6050c,geometryRA:0x08b9acc0,sourceTableField:0x34,containerField:0xa4,emitDelta:0x80,emitReturn:0x08b5e3b0,callbackRAOffset:0x104,chain:[[0x10,0x08b5ee08],[0x50,0x08b60558],[0x70,0x08b9acc0]],code:[[0x08b6050c,0x68,'geometry155'],[0x08b5ecac,0x1d4,'geometry_body155'],[0x08b5e368,0x74,'emit_wrapper155']]}};
const TYPES={152:{target:0x08b9809c,size:0x3f0,parameterBytes:0x20,dataBytes:7},155:{target:0x08b9a514,size:0x808,parameterBytes:0x4c,dataBytes:0x20}};
async function main(){
 fs.mkdirSync(out,{recursive:true});const reportFile=path.join(out,'marker_ge_emit.json');
 if(fs.existsSync(reportFile))throw new Error('refusing to overwrite marker_ge_emit.json');
 const ws=new WebSocket(`ws://127.0.0.1:${port}/debugger`,'debugger.ppsspp.org');
 const pending=new Map(),stops=[],waiters=[];
 let serial=0,ownedBP=null,ownStop=false,externalPauseSeen=false,interrupted=false,version=null,failure=null,inFlight=null,lastAllRegisters=null;
 let entryStopCount=0,dispatchStopCount=0,returnStopCount=0,targetEntryCount=0,firstStopTicks=null,lastStopTicks=null;
 const rows=[],rejects={},transitions=[],inputs=[],codeChecks=[],initialBreakpoints=[],gprCategoryDiagnostics=[];
 const cleanup={errors:[]},stageStopCounts={},geCaptures=[];
 let geTask=null,geFailure=null;
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
  const ticket=`marker-ge-cpu-emit-${++serial}`,timer=setTimeout(()=>{pending.delete(ticket);reject(new Error(`timeout: ${event}`));},timeoutMs);
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
 const flush=()=>fs.writeFileSync(reportFile,JSON.stringify({schema:'weapon-marker-render-dispatch-capture/v1',probe:'cpu-ge-emit-v1',route:'alternate69b58',producer,version,
  entryPC:ENTRY,dispatchPC:DISPATCH,returnPC:RETURN,module:{file:modulePath,sha256:sha(moduleBytes)},originalFep:{file:sectionPath,sha256:SECTION_SHA},
  expectedGeometrySHA256:GEOMETRY_SHA,expectedResourcePrefix64SHA256:RESOURCE_SHA,
  bounds:{maxStops,maxRows,durationMs,returnTimeoutMs,stackBytes:STACK_BYTES,emitStackBytes:0x1a0,maxViewCommandBytes:0x1000,maxEmittedVertices:4096,maxEmittedVertexBytes:0x20000,maxRuntimeGeometryId:4095,maxSourceTableIndex:31,maxDescriptorListCount:32,maxIndex:95,supportedTypes:TYPES},
  entryStopCount,dispatchStopCount,returnStopCount,stageStopCounts,targetEntryCount,firstStopTicks,lastStopTicks,initialBreakpoints,inputs,transitions,ownedBP,gprCategoryDiagnostics,
  codeIdentity:{verified:codeChecks.length>=functions.length&&codeChecks.every(c=>c.verified),checks:codeChecks},
  inFlight,rows,rejections:rejects,cleanup,failure,externalPauseSeen,semanticName:null,geDrawObserved:false,cpuCommandWriteObserved:rows.length>0,
  capturePose,captureFullHandler,geFrameCount,geArmMode,geCaptures,geFailure,
  negativeScope:targetEntryCount===0?'No exact-resource/exact-weapon pass1 render entry within bounded stops/ticks; not proof of no render consumer.':null,
  limits:['Only the first matching CPU PRIM per handler is sampled; no GPU execution or final visual semantic is proved.',
   'Only the alternate 69b58 route for the original bank1 type14 enqueue consumer and types152/155 are supported.',
   'Data snapshots follow original handler read extents: type152 7bytes, type155 32bytes; no assumed 64byte output matrix.',
   'Before-JALR a2 is a method descriptor; t0 is the parameter copied by its delay slot.',
   'N+4c indexed time-slot can alter f12 at69d20..34; FPR/VFPU values and actual branch are not sampled.']},null,2));
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
    lastAllRegisters=result;
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
 const captureWeaponPose=async(f,label)=>{
  const sources=await window(`weapon_sources_${label}.bin`,f.weapon.sourceBase,3*0x130);
  const world=await window(`weapon_world_${label}.bin`,f.weapon.actor+0x220,64,true);
  abi(sources.bytes.readUInt32LE(0x124)===0&&sources.bytes.readUInt32LE(0x254)===f.weapon.sourceBase&&sources.bytes.readUInt32LE(0x384)===f.weapon.sourceBase,'original rifle source parents');
  return{actor:f.weapon.actor,sourceBase:f.weapon.sourceBase,sourceStride:0x130,sources:sources.record,world:world.record,semanticName:null};
 };
 const recordFrames=async()=>{
  try{
   for(let sample=0;sample<geFrameCount;sample++){
    const requestedAt=Date.now(),response=await rpc('gpu.record.dump',{},60000);
    abi(typeof response.uri==='string'&&response.uri.startsWith('data:')&&response.uri.includes(';base64,'),'GE recording lacks base64 data URI');
    const bytes=Buffer.from(response.uri.slice(response.uri.indexOf(',')+1),'base64');
    abi(bytes.length>=32&&bytes.length<=64*1024*1024,'GE capture byte bound');
    geCaptures.push({sample,requestedAt,completedAt:Date.now(),raw:save(`concurrent_GE_${String(sample).padStart(4,'0')}.ppdmp`,bytes)});flush();
   }
  }catch(e){geFailure=String(e.stack||e);flush();}
 };
 const commandReadAddress=(address,size=4)=>{
  abi(Number.isInteger(address)&&address%4===0&&Number.isInteger(size)&&size>0&&size<=0x20000&&
   (address>=0x08000000&&address+size<=0x0c000000||address>=0x48000000&&address+size<=0x4c000000),'display-list cursor/command outside RAM or uncached RAM alias');
  return address&~0x40000000;
 };
 const commandWindow=async(name,address,size)=>{
  const readAddress=commandReadAddress(address,size),w=await window(name,readAddress,size);
  // Keep the native CPU address in the window; record the distinct address
  // actually supplied to memory.read. Ordinary window/read remain unchanged.
  w.record.address=address;w.record.readAddress=readAddress;return w;
 };
 const dlSnapshot=async(label)=>{
  const slot=await window(`${label}_global.bin`,0x08ca31d8,4),address=slot.bytes.readUInt32LE(0),context=await window(`${label}_context.bin`,address,0x20);
  const cursor=context.bytes.readUInt32LE(8),readCursor=commandReadAddress(cursor);
  return{address,cursor,readCursor,global:slot.record,context:context.record};
 };
 const vertexStride=v=>{
  abi(((v>>>11)&3)===0&&((v>>>18)&7)===0,'indexed/morphed emitted geometry unsupported');
  let n=0,a=1;const field=(align,size,count)=>{abi(align>0&&size>0,'unsupported emitted vertex format');n=(n+align-1)&~(align-1);n+=size*count;a=Math.max(a,align);};
  const wt=(v>>>9)&3,uv=v&3,col=(v>>>2)&7,nrm=(v>>>5)&3,pos=(v>>>7)&3;
  if(wt)field([0,1,2,4][wt],[0,1,2,4][wt],((v>>>14)&7)+1);
  if(uv)field([0,1,2,4][uv],[0,2,4,8][uv],1);
  if(col)field([0,0,0,0,2,2,2,4][col],[0,0,0,0,2,2,2,4][col],1);
  if(nrm)field([0,1,2,4][nrm],[0,3,6,12][nrm],1);
  abi(pos!==0,'emitted geometry has no position');field([0,1,2,4][pos],[0,3,6,12][pos],1);
  return(n+a-1)&~(a-1);
 };
 const captureHandlerDL=async(f,sample)=>{
  const end=await dlSnapshot(`full_handler_end_${sample}`),start=f.emit.entry.dl;
  f.fullHandler={end,prims:[],metadata:null};flush();
  abi(end.address===start.address&&end.cursor>=start.cursor,'handler DL context/cursor changed');
  const size=end.cursor-start.cursor;abi(size>=16&&size<=0x20000&&size%4===0,'handler DL byte bound');
  const packet=await commandWindow(`full_handler_commands_${sample}.bin`,start.cursor,size);
  f.fullHandler.commands=packet.record;flush();
  let vtype=f.emit.entry.gpr[5],base=null,address=null,fresh=false,previous=null;
  const expected=[];
  if(f.dispatch.actualType===155){
   const object=await window(`full_object_${sample}.bin`,f.geometrySource.object,32);
   abi(object.bytes.readUInt32LE(0)===fs.readFileSync(f.geometrySource.objectRaw.raw.file).readUInt32LE(0),'geometry object header pointer changed');
   const header=await window(`full_header_${sample}.bin`,object.bytes.readUInt32LE(0),0x20);
   const groupCount=header.bytes.readUInt32LE(0x18),groupsAddress=header.bytes.readUInt32LE(0x1c);
   abi(groupCount>0&&groupCount<=16,'geometry group count bound');
   const groups=await window(`full_groups_${sample}.bin`,groupsAddress,groupCount*0x44);
   f.fullHandler.metadata={object:object.record,header:header.record,groups:groups.record,groupStride:0x44,drawHeaders:[],drawRecords:[]};flush();
   for(let j=0;j<groupCount;j++){
    const count=groups.bytes.readUInt32LE(j*0x44+0x1c),at=groups.bytes.readUInt32LE(j*0x44+0x20);
    abi(count>0&&count<=64,'draw header count bound');
    const headers=await window(`full_draw_headers_${sample}_${j}.bin`,at,count*16);
    f.fullHandler.metadata.drawHeaders.push({group:j,raw:headers.record});flush();
    for(let k=0;k<count;k++){
     const vt=headers.bytes.readUInt32LE(k*16),n=headers.bytes.readUInt32LE(k*16+8),rp=headers.bytes.readUInt32LE(k*16+12);
     abi(n>0&&n<=64&&expected.length+n<=256,'inner draw record count bound');
     const records=await window(`full_draw_records_${sample}_${j}_${k}.bin`,rp,n*16);
     f.fullHandler.metadata.drawRecords.push({group:j,header:k,headerAddress:at+k*16,vtype:vt,raw:records.record});flush();
     for(let q=0;q<n;q++)expected.push({recordAddress:rp+q*16,vtype:vt,primitive:records.bytes.readUInt32LE(q*16),count:records.bytes.readUInt32LE(q*16+8),vertexAddress:records.bytes.readUInt32LE(q*16+12)});
    }
   }
   abi(expected[0].recordAddress===f.emit.entry.drawRecord.address,'first primitive is not original object first record');
  }
  const ww=words(packet.bytes);
  for(let i=0;i<ww.length;i++){
   const cmd=ww[i]>>>24,value=ww[i]&0xffffff;
   abi(![8,9,10,11,12,14,15,0x13,0x14].includes(cmd),'unsupported control/offset command in contiguous handler DL');
   if(cmd===0x12)vtype=value;
   else if(cmd===0x10)base=(value&0xff0000)<<8;
   else if(cmd===1){abi(base!==null,'VADDR before captured BASE');address=(base|value)>>>0;fresh=true;}
   else if(cmd===4){
    const primitive=(value>>>16)&7,resolved=primitive===7?previous:primitive,count=value&65535;
    abi(resolved!==null&&resolved<=6&&count>0&&count<=4096&&fresh,'unsupported PRIM or implicit VADDR');
    previous=resolved;fresh=false;const stride=vertexStride(vtype),bytes=count*stride;
    abi(bytes<=0x20000&&f.fullHandler.prims.length<256,'handler vertex/count byte bound');
    const n=f.fullHandler.prims.length,vertices=await window(`full_vertices_${sample}_${n}.bin`,address,bytes);
    const row={commandWord:i,primitive:resolved,primitiveRaw:primitive,vtype,count,vertexAddress:address,vertexStride:stride,vertices:vertices.record};
    if(expected.length){const x=expected[n];abi(x&&x.vtype===vtype&&x.primitive===resolved&&x.count===count&&x.vertexAddress===address,'CPU PRIM does not match original object record');row.originalRecord=x.recordAddress;}
    f.fullHandler.prims.push(row);flush();
   }
  }
  abi(f.fullHandler.prims.length>0&&(!expected.length||f.fullHandler.prims.length===expected.length),'full handler/object primitive count mismatch');
  abi(f.fullHandler.prims[0].vertices.raw.sha256===f.emit.entry.vertices.raw.sha256,'first emitted vertices changed by callback return');
  f.fullHandler.coverage='all_inline_PRIM_commands_from_first_emitter_to_callback_return';flush();
 };
 const expectedPrimWords=g=>{
  const result=[];if(g[5])result.push((0x12000000|(g[5]&0xffffff))>>>0);
  if(g[7])result.push((0x10000000|(((g[7]>>>24)&15)<<16))>>>0,(0x02000000|(g[7]&0xffffff))>>>0);
  if(g[8])result.push((0x10000000|(((g[8]>>>24)&15)<<16))>>>0,(0x01000000|(g[8]&0xffffff))>>>0);
  result.push((0x04000000|((g[4]&7)<<16)|g[6])>>>0);return result;
 };
 const verifyHandlerFrame=(f,b)=>{
  const offsets=f.dispatch.actualType===152?[[16,0xb4],[17,0xb8],[18,0xbc],[19,0xc0],[20,0xc4],[21,0xc8]]:[[16,0xe0],[17,0xe4],[18,0xe8],[19,0xec],[20,0xf0],[21,0xf4],[22,0xf8],[23,0xfc],[30,0x100]];
  abi(b.readUInt32LE(f.path.callbackRAOffset)===RETURN,'matrix-stage handler saved callback RA');
  for(const [r,o]of offsets)abi(b.readUInt32LE(o)===f.dispatch.gpr[r],`handler saved dispatcher register ${r}`);
 };
 const prepareGeometryPath=async(f,sample)=>{
  const typ=f.dispatch.actualType,p=fs.readFileSync(f.dispatch.parameterBefore.raw.file),data=fs.readFileSync(f.dispatch.mutableDataBefore.raw.file),path=PATHS[typ];
  // Only the two paths justified by the actual retained alt6 fields are in scope.
  if(typ===152)abi(data.readUInt16LE(4)!==0xffff&&data[6]===0&&p[0x1d]===1&&p[0x1f]===1,'unsupported type152 geometry/matrix branch');
  else abi(p[0x48]===0&&p[0x4b]===1,'unsupported type155 geometry branch');
  f.path={...path,resourceSourceIndex:p.readInt32LE(0xc)};f.handlerSP=f.dispatch.sp-path.handlerFrame;flush();
  for(const [a,n,name]of path.code)await codeIdentity(`${name}_${sample}`,a,n);
  const base=f.resource.source190,header=await window(`geometry_source_header_${sample}.bin`,base,0x50),table=header.bytes.readUInt32LE(path.sourceTableField),originalTable=section.readUInt32LE(path.sourceTableField),index=f.path.resourceSourceIndex;
  f.geometrySource={header:header.record,sourceField:path.sourceTableField,table,index};flush();
  abi(table===base+originalTable&&index>=0&&index<32&&originalTable+index*4+4<=section.length,'geometry resource source table/index');
  const slot=await window(`geometry_source_slot_${sample}.bin`,table+index*4,4),source=slot.bytes.readUInt32LE(0),originalSource=section.readUInt32LE(originalTable+index*4);
  f.geometrySource.slot=slot.record;flush();abi(source===base+originalSource&&originalSource+0x18<=section.length,'geometry resource source record pointer');
  const record=await window(`geometry_source_record_${sample}.bin`,source,0x18),id=record.bytes.readInt32LE(0x10),context=await window(`geometry_source_context_${sample}.bin`,f.C,0xa8),container=context.bytes.readUInt32LE(path.containerField);
  Object.assign(f.geometrySource,{source,record:record.record,runtimeId:id,context:context.record,container});flush();
  abi(id>=0&&id<4096,'unresolved/out-of-bound runtime geometry resource ID');
  const cw=await window(`geometry_container_${sample}.bin`,container,0x24),objects=cw.bytes.readUInt32LE(0),objectSlot=await window(`geometry_object_slot_${sample}.bin`,objects+id*4,4),object=objectSlot.bytes.readUInt32LE(0),ow=await window(`geometry_object_${sample}.bin`,object,0x20);
  Object.assign(f.geometrySource,{containerRaw:cw.record,objectSlot:objectSlot.record,object,objectRaw:ow.record});flush();
 };
 try{
  await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('debugger open timeout')),10000);ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});ws.addEventListener('error',e=>{clearTimeout(timer);reject(e);},{once:true});});
  version=await rpc('version',{name:'weapon-marker-ge-cpu-emit',version:'1'});
  const existing=await rpc('cpu.breakpoint.list');abi(Array.isArray(existing.breakpoints),'missing breakpoint inventory');initialBreakpoints.push(...existing.breakpoints);
  if(existing.breakpoints.some(bp=>bp.enabled||BP_TARGETS.has(bp.address)))throw new Error('existing active/conflicting CPU breakpoint; left unchanged');
  for(const [a,n,name]of functions)await codeIdentity(`${name}_full`,a,n);
  if(capturePose)await codeIdentity('mode0_657f8_full',0x08b657f8,0xa4);
  await input(release);if(analog)await rpc('input.analog.send',{...analog,x:0,y:0});
  if(externalPauseSeen||stops.length)throw new Error('external CPU pause during setup; left paused');
  await addBP(ENTRY);await input({...release,...held});if(analog)await rpc('input.analog.send',analog);
  if(geFrameCount&&geArmMode==='immediate')geTask=recordFrames();resume();
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
   const g=await regs();stageStopCounts[inFlight?.phase||'entry']=(stageStopCounts[inFlight?.phase||'entry']||0)+1;
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
    if(geFrameCount&&geArmMode==='target'&&!geTask)geTask=recordFrames();
    inFlight.entry.stack=(await window(`entry_stack_${sample}.bin`,Q,0x30)).record;flush();
    abi(g[31]===0x08bbd858,'unknown render entry caller RA');
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
    f.dispatch={...f.dispatchAttempt};delete f.dispatchAttempt;flush();await prepareGeometryPath(f,sample);await advance('matrix_entry',MATRIX_ENTRY);
   }else if(inFlight.phase==='matrix_entry'){
    const f=inFlight,sample=String(f.sample).padStart(4,'0'),H=f.handlerSP;
    f.matrix={entry:{pc:MATRIX_ENTRY,ticks:stop.ticks,gpr:g,sp:g[29],ra:g[31],allRegisters:{raw:save(`matrix_all_registers_${sample}.json`,Buffer.from(JSON.stringify(lastAllRegisters,null,2),'utf8')),f12Decoded:false,f12Value:null,f12Availability:lastAllRegisters.categories.length===1?'unavailable_gpr_only':'raw_categories_uninterpreted'}}};flush();
    abi(g[29]===H&&g[31]===f.path.matrixReturn&&g[4]===f.C&&g[5]===f.N&&g[8]===H+0x10,'matrix helper entry SP/RA/C/N/output');
    const n=await window(`matrix_node_${sample}.bin`,f.N,0x64),p=await window(`matrix_state_${sample}.bin`,f.P,0x1ac),c=await window(`matrix_context_${sample}.bin`,f.C,0xa8),frame=await window(`matrix_handler_stack_${sample}.bin`,H,f.path.handlerFrame);
    Object.assign(f.matrix.entry,{node:n.record,state:p.record,context:c.record,handlerStack:frame.record,mode:g[7],inputPointer:g[6],outputPointer:g[8]});flush();verifyHandlerFrame(f,frame.bytes);
    abi(c.bytes.readUInt32LE(0x8c)===f.P&&c.bytes.readUInt32LE(0x90)===f.N&&c.bytes.readUInt32LE(0x94)===f.dispatch.currentB,'matrix helper current context identity');
    const modeGlobalSlot=await window(`matrix_mode_global_slot_${sample}.bin`,0x08c3b58c,4);f.matrix.entry.globalSlot=modeGlobalSlot.record;flush();
    f.matrix.entry.globalMatrix=(await window(`matrix_mode_global_${sample}.bin`,modeGlobalSlot.bytes.readUInt32LE(0),64,true)).record;flush();
    abi(n.bytes.readUInt32LE(0x1c)===0&&g[6]===n.bytes.readUInt32LE(0x50),'unsupported matrix parent/input path');
    f.matrix.entry.input=(await window(`matrix_input_${sample}.bin`,g[6],64,true)).record;
    f.matrix.entry.p60=(await window(`matrix_p60_${sample}.bin`,f.P+0x60,64,true)).record;
    if(capturePose)f.matrix.entry.weaponPose=await captureWeaponPose(f,`matrix_${sample}`);
    f.matrix.entry.outputBefore=(await window(`matrix_output_before_${sample}.bin`,g[8],64)).record;
    const bw=fs.readFileSync(f.dispatch.definition.raw.file),list=bw.readUInt32LE(8),lw=await window(`matrix_component_indices_${sample}.bin`,list,4),index=lw.bytes.readUInt16LE(2);
    abi(index<96,'matrix component index bound');
    const slot=await window(`matrix_component_slot_${sample}.bin`,n.bytes.readUInt32LE(0x48)+4*index,4),componentPointer=slot.bytes.readUInt32LE(0),fieldAddress=componentPointer+1;
    // The original handlers use LBU +1 from a byte-structured component. Its
    // actual pointer need not be word-aligned; keep all guest reads aligned.
    f.matrix.entry.modeSource={indices:lw.record,index,slot:slot.record,componentPointer,fieldAddress};flush();
    abi(componentPointer>=0x08000000&&fieldAddress<0x0c000000,'matrix component mode field outside guest RAM');
    const alignedAddress=fieldAddress&~3,byteOffset=fieldAddress-alignedAddress,component=await window(`matrix_component_${sample}.bin`,alignedAddress,4);
    Object.assign(f.matrix.entry.modeSource,{byteOffset,component:component.record});flush();abi(component.bytes[byteOffset]===g[7],'matrix mode provenance');
    await advance('matrix_return',f.path.matrixReturn);
   }else if(inFlight.phase==='matrix_return'){
    const f=inFlight,sample=String(f.sample).padStart(4,'0');
    f.matrix.returned={pc:f.path.matrixReturn,ticks:stop.ticks,gpr:g,sp:g[29],ra:g[31]};flush();
    abi(g[29]===f.handlerSP&&g[31]===f.path.matrixReturn,'matrix helper return SP/RA');
    abi([16,17,18,19,20,21,22,23,30].every(r=>g[r]===f.matrix.entry.gpr[r]),'matrix helper callee-saved registers');
    f.matrix.returned.output=(await window(`matrix_output_after_${sample}.bin`,f.matrix.entry.outputPointer,64,true)).record;flush();await advance('view_entry',VIEW_ENTRY);
   }else if(inFlight.phase==='view_entry'){
    const f=inFlight,sample=String(f.sample).padStart(4,'0'),dl=await dlSnapshot(`view_dl_${sample}`);
    f.view={entry:{pc:VIEW_ENTRY,ticks:stop.ticks,gpr:g,sp:g[29],ra:g[31],dl}};flush();
    abi(g[29]===f.handlerSP-0x60&&g[31]===0x08bfff8c&&g[4]===dl.address&&g[5]===1&&g[6]===f.handlerSP-0x50,'VIEW writer SP/RA/context/kind/input');
    const stack=await window(`view_stack_${sample}.bin`,g[29],0x60),handlerMatrix=await window(`view_handler_matrix_${sample}.bin`,f.handlerSP+0x10,64,true);
    f.view.entry.stack=stack.record;f.view.entry.handlerMatrix=handlerMatrix.record;flush();
    abi(stack.bytes.readUInt32LE(0)===0x08bbb924&&stack.bytes.readUInt32LE(0x50)===f.path.viewCallerRA,'VIEW writer saved wrapper/handler RA');
    const input=await window(`view_input_${sample}.bin`,g[6],64,true),globalSlot=await window(`view_global_slot_${sample}.bin`,0x08c3b588,4),global=await window(`view_global_matrix_${sample}.bin`,globalSlot.bytes.readUInt32LE(0),64,true);
    f.view.entry.input=input.record;f.view.entry.globalSlot=globalSlot.record;f.view.entry.globalMatrix=global.record;
    f.view.entry.packetBefore=(await commandWindow(`view_packet_before_${sample}.bin`,dl.cursor,0x34)).record;
    const w=words(input.bytes);f.view.expectedWords=[0x3c000000,...[0,1,2,4,5,6,8,9,10,12,13,14].map(i=>(0x3d000000|(w[i]>>>8))>>>0)];flush();await advance('geometry_entry',f.path.geometryHelper);
   }else if(inFlight.phase==='geometry_entry'){
    const f=inFlight,sample=String(f.sample).padStart(4,'0'),typ=f.dispatch.actualType,dl=await dlSnapshot(`geometry_dl_${sample}`);
    f.geometryHelper={entry:{pc:f.path.geometryHelper,ticks:stop.ticks,gpr:g,sp:g[29],ra:g[31],dl}};flush();
    abi(g[29]===f.handlerSP&&g[31]===f.path.geometryRA,'geometry helper SP/RA');
    abi(g[5]===f.geometrySource.runtimeId,'geometry helper resource ID provenance');
    if(typ===152)abi(g[4]===f.C&&g[6]===0&&g[7]===f.handlerSP,'geometry152 context/subindex/vector ABI');
    else abi(g[4]===f.geometrySource.container&&g[6]===f.handlerSP,'geometry155 container/vector ABI');
    const cw=await window(`geometry_context_${sample}.bin`,f.C,0xa8);f.geometryHelper.entry.context=cw.record;
    abi(cw.bytes.readUInt32LE(f.path.containerField)===f.geometrySource.container,'geometry container changed');
    f.geometryHelper.entry.auxiliaryVector=(await window(`geometry_auxiliary_vector_${sample}.bin`,f.handlerSP,16)).record;
    const start=f.view.entry.dl.cursor,delta=dl.cursor-start;
    abi(dl.address===f.view.entry.dl.address&&delta>=0x34&&delta<=0x1000&&delta%4===0,'VIEW to geometry cursor range');
    const packet=await commandWindow(`view_packet_after_${sample}.bin`,start,0x34),commands=await commandWindow(`view_to_geometry_commands_${sample}.bin`,start,delta);
    f.view.packetAtGeometry=packet.record;f.view.commandsThroughGeometry=commands.record;flush();
    abi(words(packet.bytes).every((v,i)=>v===f.view.expectedWords[i]),'actual VIEW CPU packet differs from writer input');
    await advance('emit_entry',EMIT_ENTRY);
   }else if(inFlight.phase==='emit_entry'){
    const f=inFlight,sample=String(f.sample).padStart(4,'0'),dl=await dlSnapshot(`emit_dl_${sample}`),S=f.handlerSP-f.path.emitDelta;
    f.emit={entry:{pc:EMIT_ENTRY,ticks:stop.ticks,gpr:g,sp:g[29],ra:g[31],dl}};flush();
    abi(g[29]===S&&g[31]===f.path.emitReturn,'CPU PRIM emitter caller SP/RA');
    const stack=await window(`emit_stack_${sample}.bin`,S,0x1a0);f.emit.entry.stack=stack.record;flush();
    for(const [o,...allowed]of f.path.chain)abi(allowed.includes(stack.bytes.readUInt32LE(o)),`geometry-to-emitter saved RA +${o.toString(16)}`);
    abi(stack.bytes.readUInt32LE(f.path.emitDelta+f.path.callbackRAOffset)===RETURN,'emitter stack handler callback RA');
    abi(g[4]<=7&&g[5]<=0xffffff&&g[6]>0&&g[6]<=4096&&g[7]===0&&pointer(g[8]),'unsupported PRIM arguments');
    const stride=vertexStride(g[5]),size=stride*g[6];abi(size<=0x20000,'emitted vertex byte bound');
    f.emit.entry.vertexStride=stride;f.emit.entry.vertices=(await window(`emitted_vertices_${sample}.bin`,g[8],size)).record;
    if(capturePose)f.emit.entry.weaponPose=await captureWeaponPose(f,`emit_${sample}`);
    if(f.dispatch.actualType===155){
     const record=await window(`emitted_draw_record_${sample}.bin`,g[19],16);f.emit.entry.drawRecord=record.record;flush();
     abi(record.bytes.readUInt32LE(0)===g[4]&&record.bytes.readUInt32LE(8)===g[6]&&record.bytes.readUInt32LE(12)===g[8]&&g[17]===g[5],'type155 original draw record arguments');
    }
    f.emit.expectedWords=expectedPrimWords(g);f.emit.entry.packetBefore=(await commandWindow(`emit_packet_before_${sample}.bin`,dl.cursor,f.emit.expectedWords.length*4)).record;flush();await advance('emit_return',f.path.emitReturn);
   }else if(inFlight.phase==='emit_return'){
    const f=inFlight,sample=String(f.sample).padStart(4,'0'),dl=await dlSnapshot(`emit_return_dl_${sample}`);
    f.emit.returned={pc:f.path.emitReturn,ticks:stop.ticks,gpr:g,sp:g[29],ra:g[31],dl};flush();
    abi(g[29]===f.emit.entry.sp&&g[31]===f.path.emitReturn,'CPU PRIM emitter return SP/RA');
    abi([16,17,18,19,20,21,22,23,30].every(r=>g[r]===f.emit.entry.gpr[r]),'CPU PRIM emitter callee-saved registers');
    const n=f.emit.expectedWords.length*4;abi(dl.address===f.emit.entry.dl.address&&dl.cursor===f.emit.entry.dl.cursor+n,'CPU PRIM emitter cursor delta');
    const packet=await commandWindow(`emit_packet_after_${sample}.bin`,f.emit.entry.dl.cursor,n);f.emit.returned.packet=packet.record;flush();
    abi(words(packet.bytes).every((v,i)=>v===f.emit.expectedWords[i]),'actual CPU PRIM packet differs from emitter arguments');
    await advance('callback_return',RETURN);
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
    if(captureFullHandler)await captureHandlerDL(f,sample);
    const complete={...f,classification:'observed_handler_invocation_return',cpuEmissionClassification:'observed_geometry_cpu_commands',cpuCommandWriteObserved:true,emitCoverage:'first_matching_cpu_prim_per_handler',returned:f.returnAttempt};
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
  }flush();
  if(geTask)await geTask;
  if(geFailure&&!failure)failure=geFailure;flush();ws.close();
 }
 console.log(JSON.stringify({out,entryStopCount,dispatchStopCount,returnStopCount,targetEntryCount,rows:rows.length,rejections:rejects,cleanup,failure}));if(failure||cleanup.errors.length)process.exitCode=1;
}
main().catch(e=>{console.error(e.stack||e);process.exitCode=1;});
