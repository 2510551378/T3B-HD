// Offline-testable observer of an existing PPSSPP debugger; no launch/UI/savestate IO.
// One owned BP: enqueue ENTRY -> caller RETURN, never both together.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const ENTRY=0x08bbdce8,RETURN=0x08b935f0,BASE=0x08804000;
const BP_TARGETS=new Set([ENTRY,RETURN]);
const GEOMETRY_SHA='168578abca4c4f5d22d5994ebced6b93a25d5167428bfd47f1a1150a8d42e65a';
const RESOURCE_SHA='04afeecb38df20d41a7c24da1686e31cf70a8e631aa51e48321c776ab21d89b6';
const STACK_BYTES=0xd0;
const out=process.env.MARKER_ENQUEUE_OUT_DIR||process.env.MARKER_OUT_DIR;
const port=Number(process.env.PPSSPP_DEBUGGER_PORT||9900);
const maxStops=Number(process.env.MARKER_MAX_STOPS||1200),maxRows=Number(process.env.MARKER_MAX_ROWS||12);
const durationMs=Number(process.env.MARKER_DURATION_MS||15000),returnTimeoutMs=Number(process.env.MARKER_STAGE_TIMEOUT_MS||3000);

const held=JSON.parse(process.env.MARKER_BUTTONS_JSON||'{}');
const analog=process.env.MARKER_ANALOG_JSON?JSON.parse(process.env.MARKER_ANALOG_JSON):null;
if(!out||!Number.isInteger(port)||port<1||port>65535||!Number.isInteger(maxStops)||maxStops<1||maxStops>20000||!Number.isInteger(maxRows)||maxRows<1||maxRows>240||!Number.isFinite(durationMs)||durationMs<100||durationMs>120000||!Number.isFinite(returnTimeoutMs)||returnTimeoutMs<50||returnTimeoutMs>10000)throw new Error('invalid enqueue observer bounds');
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
const functions=[[ENTRY,0x19c,'enqueue'],[0x08b92fcc,0x63c,'type14_post'],[0x08b68f14,0x118,'post_dispatch'],[0x08b6902c,0x78,'post_walk'],[0x08b69994,0xc0,'bank1_update'],[0x08b69dbc,0xc8c,'updater']];
const HEADS=0x08cb1460,TAILS=0x08cb1960;
async function main(){
 fs.mkdirSync(out,{recursive:true});const reportFile=path.join(out,'marker_enqueue.json');
 if(fs.existsSync(reportFile))throw new Error('refusing to overwrite marker_enqueue.json');
 const ws=new WebSocket(`ws://127.0.0.1:${port}/debugger`,'debugger.ppsspp.org');
 const pending=new Map(),stops=[],waiters=[];
 let serial=0,ownedBP=null,ownStop=false,externalPauseSeen=false,interrupted=false,version=null,failure=null,inFlight=null;
 let entryStopCount=0,returnStopCount=0,targetEntryCount=0,firstStopTicks=null,lastStopTicks=null;
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
  const ticket=`marker-enqueue-${++serial}`,timer=setTimeout(()=>{pending.delete(ticket);reject(new Error(`timeout: ${event}`));},timeoutMs);
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
 const flush=()=>fs.writeFileSync(reportFile,JSON.stringify({schema:'weapon-marker-enqueue-capture/v1',producer,version,
  entryPC:ENTRY,returnPC:RETURN,module:{file:modulePath,sha256:sha(moduleBytes)},originalFep:{file:sectionPath,sha256:SECTION_SHA},
  expectedGeometrySHA256:GEOMETRY_SHA,expectedResourcePrefix64SHA256:RESOURCE_SHA,
  bounds:{maxStops,maxRows,durationMs,returnTimeoutMs,entryStackBytes:STACK_BYTES,maxDescriptorListCount:32,maxIndex:95,maxParents:2,bucketCount:320},
  entryStopCount,returnStopCount,targetEntryCount,firstStopTicks,lastStopTicks,initialBreakpoints,inputs,transitions,ownedBP,gprCategoryDiagnostics,
  codeIdentity:{verified:codeChecks.length>=functions.length&&codeChecks.every(c=>c.verified),checks:codeChecks},
  inFlight,rows,rejections:rejects,cleanup,failure,externalPauseSeen,semanticName:null,geDrawObserved:false,
  negativeScope:targetEntryCount===0?'No exact-resource/exact-weapon enqueue entry within this bounded stop/tick interval; not evidence of no render consumer.':null,
  limits:['Enqueue is not a GE draw; downstream renderer/GE/visual semantics remain unobserved.',
   'Only selected original FEP table1[4] four nested D paths and the exact type14 caller stack are supported.',
   'Only two immediate parent nodes are read; no recursive object traversal.',
   'First/last guest ticks cover observed own entry/return stops; wall-time bounds do not prove gameplay coverage.']},null,2));
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

 const abi=(ok,msg)=>{if(!ok)throw new Error(`enqueue ABI mismatch: ${msg}`);};
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
 const collectMatrices=async(node,sample)=>{
  const matrices={},parents=[];
  inFlight.entry.matrices=matrices;inFlight.entry.parents=parents;
  for(const [offset,name] of [[0x50,'transform50'],[0x54,'transform54']]){
   const address=node.readUInt32LE(offset);
   if(address)matrices[name]=(await window(`node_${name}_${sample}.bin`,address,64,true)).record;
   else matrices[name]=null;
  }
  for(const offset of [0x18,0x1c]){
   const address=node.readUInt32LE(offset);if(!address)continue;
   abi(address!==inFlight.N,'self parent node');
   const w=await window(`parent_${offset.toString(16)}_${sample}.bin`,address,0x64),p={nodeFieldOffset:offset,node:w.record,matrices:{}};
   parents.push(p);flush();
   for(const o of [0x50,0x54]){const addr=w.bytes.readUInt32LE(o);p.matrices[o]=addr?(await window(`parent_${offset.toString(16)}_${o.toString(16)}_${sample}.bin`,addr,64,true)).record:null;}
  }
 };
 try{
  await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('debugger open timeout')),10000);ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});ws.addEventListener('error',e=>{clearTimeout(timer);reject(e);},{once:true});});
  version=await rpc('version',{name:'weapon-marker-enqueue',version:'1'});
  const existing=await rpc('cpu.breakpoint.list');abi(Array.isArray(existing.breakpoints),'missing breakpoint inventory');initialBreakpoints.push(...existing.breakpoints);
  if(existing.breakpoints.some(bp=>bp.enabled||BP_TARGETS.has(bp.address)))throw new Error('existing active/conflicting CPU breakpoint; left unchanged');
  for(const [a,n,name] of functions)await codeIdentity(`${name}_full`,a,n);
  await input(release);if(analog)await rpc('input.analog.send',{...analog,x:0,y:0});
  if(externalPauseSeen||stops.length)throw new Error('external CPU pause during setup; left paused');
  await addBP(ENTRY);await input({...release,...held});if(analog)await rpc('input.analog.send',analog);resume();
  const deadline=Date.now()+durationMs;
  while(!interrupted){
   if(!inFlight&&(Date.now()>=deadline||entryStopCount>=maxStops||rows.length>=maxRows))break;
   const end=inFlight?inFlight.returnDeadline:deadline;
   if(Date.now()>=end){if(inFlight)throw new Error('selected enqueue return timeout; outcome unknown');break;}
   let stop;try{stop=await nextStop(Math.min(1000,Math.max(1,end-Date.now())));}catch(e){if(e.message==='wait interval elapsed')continue;throw e;}
   const expected=inFlight?RETURN:ENTRY;
   if(stop.pc!==expected||stop.ownedBreakpointAtReceipt!==expected){ownStop=false;externalPauseSeen=true;throw new Error('unexpected external CPU stop; left paused');}
   ownStop=true;
   abi(Number.isSafeInteger(stop.ticks)&&(lastStopTicks===null||stop.ticks>=lastStopTicks),'invalid/nonmonotonic guest ticks');
   if(firstStopTicks===null)firstStopTicks=stop.ticks;lastStopTicks=stop.ticks;
   const g=await regs();
   if(!inFlight){
    entryStopCount++;
    const E=g[4],C=g[5],Q=g[29];
    if(!pointer(C,0xa8)){reject('invalid context pointer');resume();continue;}
    const context=await read(C,0xa8),P=context.readUInt32LE(0x8c),N=context.readUInt32LE(0x90);
    if(!pointer(P,0x1ac)){reject('invalid state pointer');resume();continue;}
    const before=await read(P,0x1ac),res=before.readUInt32LE(0x198);
    if(!pointer(res,64)){reject('invalid resource pointer');resume();continue;}
    const prefix=await read(res,64);
    if(sha(prefix)!==RESOURCE_SHA){reject('not exact resource prefix');resume();continue;}
    const handle=before.readUInt32LE(0x144);
    if(!pointer(handle)){reject('missing primary handle');resume();continue;}
    const primaryRaw=await read(handle,4),actor=primaryRaw.readUInt32LE(0),id=await identity(actor);
    if(!id){reject('not exact original weapon');resume();continue;}
    targetEntryCount++;const sample=String(targetEntryCount-1).padStart(4,'0');
    inFlight={sample:targetEntryCount-1,entryPC:ENTRY,entryTicks:stop.ticks,entryGPR:g,entrySP:Q,entryRA:g[31],entryArgs:{a0:E,a1:C,a2:g[6],a3:g[7]},E,C,P,N,
     entry:{context:{address:C,size:context.length,raw:save(`context_before_${sample}.bin`,context)},state:{address:P,size:before.length,raw:save(`state_before_${sample}.bin`,before)}},
     resourcePrefix64:{address:res,size:64,raw:save(`resource_prefix64_${sample}.bin`,prefix)},
     weapon:{actor,sourceBase:id.sourceBase,metadata:id.metadata,drawTable:id.table,geometrySHA256:GEOMETRY_SHA,geometry:save(`geometry_${sample}.bin`,id.geometry),
      identityRaw:{primary:{address:handle,raw:save(`primary_handle_${sample}.bin`,primaryRaw)},actorFields:{address:actor+0x3c4,raw:save(`actor_fields_${sample}.bin`,id.fields)},metadata:{address:id.metadata,raw:save(`metadata_${sample}.bin`,id.header)},draw:{address:id.table,raw:save(`draw_header_${sample}.bin`,id.packet)}}},
     semanticName:null,geDrawObserved:false};flush();
    inFlight.entryStack=(await window(`entry_stack_${sample}.bin`,Q,STACK_BYTES)).record;
    const stack=fs.readFileSync(inFlight.entryStack.raw.file);
    inFlight.callerChain={entryRA:g[31],savedReturns:[0x74,0xa0,0xb8,0xc8].map(o=>({offset:o,address:Q+o,value:stack.readUInt32LE(o)}))};flush();
    abi(g[31]===RETURN,'unknown type14 enqueue caller RA');
    abi([0x08b68ff0,0x08b69080,0x08b69a40,0x08b6a9e8].every((v,i)=>v===inFlight.callerChain.savedReturns[i].value),'unknown post callback stack chain');
    const n=await window(`node_before_${sample}.bin`,N,0x64),e=await window(`entry_before_${sample}.bin`,E,0x18);
    inFlight.entry.node=n.record;inFlight.entry.queueEntry=e.record;flush();
    abi(n.bytes.readUInt32LE(0x3c)===E,'node queue-entry pointer mismatch');
    const base=await collectResource(before,sample);
    // Save even an unsupported D prefix before rejecting its path.
    const D=n.bytes.readUInt32LE(0x40);inFlight.entry.descriptor=(await window(`descriptor_candidate_${sample}.bin`,D,0x48)).record;flush();
    await collectDescriptor(D,base,sample);await collectMatrices(n.bytes,sample);
    const heads=await window(`bucket_heads_before_${sample}.bin`,HEADS,0x500),tails=await window(`bucket_tails_before_${sample}.bin`,TAILS,0x500);
    const staticTables=await window(`bucket_mode_tables_${sample}.bin`,0x08c2de70,0x220);
    // LUI 08c3 + signed immediate de72/de8a => 08c2de72/08c2de8a.
    inFlight.bucketSources={beforeHeads:heads.record,beforeTails:tails.record,staticModeTables:staticTables.record,
     selectedTable1ByteA:before.readUInt32LE(0x194)+0xa,rawTable1:inFlight.resource.table1Record4};flush();
    abi(g[6]<=255&&g[7]<=255,'type14 bucket arguments outside original byte ABI');
    await removeBP();await codeIdentity(`return_${sample}`,RETURN,0x18);
    inFlight.returnDeadline=Date.now()+returnTimeoutMs;flush();await addBP(RETURN);resume();
   }else{
    returnStopCount++;const f=inFlight,sample=String(f.sample).padStart(4,'0');
    f.returnAttempt={pc:RETURN,ticks:stop.ticks,gpr:g,sp:g[29],ra:g[31]};flush();
    abi(g[29]===f.entrySP&&g[31]===RETURN,'enqueue return SP/RA');
    abi([16,17,18,19,20,21,22,23,30].every(i=>g[i]===f.entryGPR[i]),'enqueue return callee-saved registers');
    const e=await window(`entry_after_${sample}.bin`,f.E,0x18),c=await window(`context_after_${sample}.bin`,f.C,0xa8),p=await window(`state_after_${sample}.bin`,f.P,0x1ac),n=await window(`node_after_${sample}.bin`,f.N,0x64);
    Object.assign(f.returnAttempt,{queueEntry:e.record,context:c.record,state:p.record,node:n.record});flush();
    const bucket=e.bytes.readUInt16LE(0xa);abi(bucket<320,'return bucket outside captured arrays');
    const head=await window(`bucket_head_after_${sample}.bin`,HEADS+bucket*4,4),tail=await window(`bucket_tail_after_${sample}.bin`,TAILS+bucket*4,4);
    const beforeHeads=fs.readFileSync(f.bucketSources.beforeHeads.raw.file),beforeTails=fs.readFileSync(f.bucketSources.beforeTails.raw.file),oldTail=beforeTails.readUInt32LE(bucket*4),oldHead=beforeHeads.readUInt32LE(bucket*4);
    const oldTailAfter=oldTail?(await window(`old_tail_after_${sample}.bin`,oldTail,8)).record:null;
    Object.assign(f.returnAttempt,{bucket,head:head.record,tail:tail.record,oldHeadBefore:oldHead,oldTailBefore:oldTail,oldTailAfter});flush();
    abi(g[2]===bucket,'return v0 does not equal actual bucket');
    abi(e.bytes[8]===1&&e.bytes.readUInt32LE(0xc)===f.C&&e.bytes.readUInt32LE(0x10)===f.P&&e.bytes.readUInt32LE(0x14)===f.N,'enqueue output identity');
    abi(e.bytes.readUInt32LE(4)===0&&e.bytes.readUInt32LE(0)===oldTail&&tail.bytes.readUInt32LE(0)===f.E,'queue new tail/link mismatch');
    abi((oldTail===0&&oldHead===0&&head.bytes.readUInt32LE(0)===f.E)||(oldTail!==0&&oldHead!==0&&head.bytes.readUInt32LE(0)===oldHead),'queue head/empty bucket mismatch');
    if(oldTail){abi(oldTail!==f.E,'target was already old tail');const old=fs.readFileSync(oldTailAfter.raw.file);abi(old.readUInt32LE(4)===f.E,'old tail next mismatch');}
    abi(c.bytes.readUInt32LE(0x8c)===f.P&&c.bytes.readUInt32LE(0x90)===f.N&&n.bytes.readUInt32LE(0x3c)===f.E,'context/node changed identity');
    abi(p.bytes.equals(fs.readFileSync(f.entry.state.raw.file)),'enqueue unexpectedly modified state bytes');
    f.returnAttempt.linkValidation={validated:true,emptyBucket:oldTail===0};
    const complete={...f,classification:'observed_enqueue',returned:f.returnAttempt};delete complete.returnAttempt;delete complete.returnDeadline;
    rows.push(complete);inFlight=null;flush();await removeBP();
    if(rows.length>=maxRows||entryStopCount>=maxStops||Date.now()>=deadline)break;
    await addBP(ENTRY);resume();
   }
  }
  if(inFlight)throw new Error(interrupted?'interrupted during selected enqueue':'selected enqueue incomplete');
 }catch(e){failure=String(e.stack||e);}
 finally{
  if(stops.length){cleanup.unconsumedStops=stops.map(s=>({pc:s.pc,ticks:s.ticks,ownedBreakpointAtReceipt:s.ownedBreakpointAtReceipt}));
   ownStop=!externalPauseSeen&&stops.every(s=>s.ownedBreakpointAtReceipt!==null&&s.pc===s.ownedBreakpointAtReceipt);}
  for(const action of [async()=>{await input(release);cleanup.buttonsReleased=true;},async()=>{if(analog){await rpc('input.analog.send',{...analog,x:0,y:0});cleanup.analogReleased=true;}},
   async()=>{await removeBP();cleanup.ownedBreakpointRemoved=true;},async()=>{if(ownStop&&!externalPauseSeen){stops.length=0;resume();cleanup.resumedOwnStop=true;}}]){
   try{if(ws.readyState===WebSocket.OPEN)await action();else cleanup.errors.push('debugger disconnected before cleanup');}catch(e){cleanup.errors.push(String(e));}
  }
  flush();ws.close();
 }
 console.log(JSON.stringify({out,entryStopCount,returnStopCount,targetEntryCount,rows:rows.length,rejections:rejects,cleanup,failure}));
 if(failure||cleanup.errors.length)process.exitCode=1;
}
main().catch(e=>{console.error(e.stack||e);process.exitCode=1;});
