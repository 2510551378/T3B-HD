// Offline-testable observer of an existing PPSSPP debugger; no launch/UI/savestate IO.
// One owned BP: selector setter ENTRY -> common POST_WRITE, never both together.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const ENTRY=0x08b6513c,POST_WRITE=0x08b65214,BASE=0x08804000;
const BP_TARGETS=new Set([ENTRY,POST_WRITE]);
const GEOMETRY_SHA='168578abca4c4f5d22d5994ebced6b93a25d5167428bfd47f1a1150a8d42e65a';
const RESOURCE_SHA='04afeecb38df20d41a7c24da1686e31cf70a8e631aa51e48321c776ab21d89b6';
const STACK_BYTES=0x400;
const out=process.env.MARKER_SELECTOR_OUT_DIR||process.env.MARKER_OUT_DIR;
const port=Number(process.env.PPSSPP_DEBUGGER_PORT||9900);
const maxStops=Number(process.env.MARKER_MAX_STOPS||1200),maxRows=Number(process.env.MARKER_MAX_ROWS||12);
const durationMs=Number(process.env.MARKER_DURATION_MS||15000),returnTimeoutMs=Number(process.env.MARKER_STAGE_TIMEOUT_MS||3000);
const maxGroupDepth=Number(process.env.MARKER_MAX_GROUP_DEPTH||8);
const bindingProbe=process.env.MARKER_BINDING_PROBE==='1';
const configProbe=process.env.MARKER_CONFIG_PROBE==='1';
if(configProbe&&!bindingProbe)throw new Error('MARKER_CONFIG_PROBE requires MARKER_BINDING_PROBE=1');
const held=JSON.parse(process.env.MARKER_BUTTONS_JSON||'{}');
const analog=process.env.MARKER_ANALOG_JSON?JSON.parse(process.env.MARKER_ANALOG_JSON):null;
if(!out||!Number.isInteger(port)||port<1||port>65535||!Number.isInteger(maxStops)||maxStops<1||maxStops>20000||!Number.isInteger(maxRows)||maxRows<1||maxRows>240||!Number.isFinite(durationMs)||durationMs<100||durationMs>120000||!Number.isFinite(returnTimeoutMs)||returnTimeoutMs<50||returnTimeoutMs>10000||!Number.isInteger(maxGroupDepth)||maxGroupDepth<0||maxGroupDepth>16)throw new Error('invalid selector writer bounds');
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

const mapPath=path.resolve(__dirname,'../map.ppmap.txt'),mapBytes=fs.readFileSync(mapPath);
const symbols=mapBytes.toString('utf8').split(/\r?\n/).flatMap(line=>{
 const p=line.trim().split(/\s+/);if(p.length<5||p[0].startsWith('.')||!/^\w+$/.test(p[0]))return[];
 const off=parseInt(p[0],16),size=parseInt(p[1],16);return Number.isInteger(off)&&Number.isInteger(size)?[{address:BASE+off,size,name:p[4]}]:[];
});
const gameCallers=[];
for(let i=0;i+4<=moduleBytes.length;i+=4){const w=moduleBytes.readUInt32LE(i);if((w>>>26)===3&&((w&0x03ffffff)*4)===0x08b26c6c)gameCallers.push(BASE+i);}
if(gameCallers.length!==22)throw new Error('selected module game caller inventory changed');
const functions=[[ENTRY,0x118,'selector'],[0x08b646b4,0x11c,'primary'],[0x08b5b990,0xac,'bind_wrapper'],[0x08b59a98,0x5c,'global_wrapper'],[0x08b26c6c,0xe0,'game_wrapper'],[0x08bbbfac,0x108,'validator'],[0x08b3f140,0x1c,'handle_index'],[0x08b447cc,0x3c,'bone_bounds'],[0x08b65338,8,'callback_stub']];
async function main(){
 fs.mkdirSync(out,{recursive:true});const reportFile=path.join(out,'marker_selector_writer.json');
 if(fs.existsSync(reportFile))throw new Error('refusing to overwrite marker_selector_writer.json');
 const ws=new WebSocket(`ws://127.0.0.1:${port}/debugger`,'debugger.ppsspp.org');
 const pending=new Map(),stops=[],waiters=[];
 let serial=0,ownedBP=null,ownStop=false,interrupted=false,version=null,failure=null,inFlight=null;
 let entryStopCount=0,postWriteStopCount=0,targetEntryCount=0,firstStopTicks=null,lastStopTicks=null,firstEntryTicks=null,lastEntryTicks=null;
 const rows=[],noOpEntries=[],rejects={},transitions=[],inputs=[],codeChecks=[],initialBreakpoints=[],gprCategoryDiagnostics=[];
 const cleanup={errors:[]},checkedGameFunctions=new Set();
 const reject=reason=>{rejects[reason]=(rejects[reason]||0)+1;};
 process.on('SIGINT',()=>{interrupted=true;});process.on('SIGTERM',()=>{interrupted=true;});
 ws.addEventListener('message',event=>{
  let m;try{m=JSON.parse(event.data);}catch{return;}
  const waiter=pending.get(m.ticket);
  if(waiter){pending.delete(m.ticket);clearTimeout(waiter.timer);m.event==='error'?waiter.reject(new Error(JSON.stringify(m))):waiter.resolve(m);return;}
  if(m.event==='cpu.stepping'){m.ownedBreakpointAtReceipt=ownedBP;const next=waiters.shift();if(next){clearTimeout(next.timer);next.resolve(m);}else stops.push(m);}
 });
 ws.addEventListener('close',()=>{for(const x of pending.values()){clearTimeout(x.timer);x.reject(new Error('debugger closed'));}pending.clear();for(const x of waiters.splice(0)){clearTimeout(x.timer);x.reject(new Error('debugger closed'));}});
 const rpc=(event,fields={},timeoutMs=10000)=>new Promise((resolve,reject)=>{
  const ticket=`selector-writer-${++serial}`,timer=setTimeout(()=>{pending.delete(ticket);reject(new Error(`timeout: ${event}`));},timeoutMs);
  pending.set(ticket,{resolve,reject,timer});ws.send(JSON.stringify({event,...fields,ticket}));
 });
 const nextStop=timeout=>stops.length?Promise.resolve(stops.shift()):new Promise((resolve,reject)=>{
  const x={resolve,reject,timer:setTimeout(()=>{const i=waiters.indexOf(x);if(i>=0)waiters.splice(i,1);reject(new Error('wait interval elapsed'));},timeout)};waiters.push(x);
 });
 const resume=()=>{ws.send(JSON.stringify({event:'cpu.resume'}));ownStop=false;};
 const read=async(address,size,replacements=true)=>{
  if(!pointer(address,size)||size>0x20000)throw new Error(`invalid guest read ${address.toString(16)}/${size}`);
  const r=await rpc('memory.read',{address,size,replacements}),b=Buffer.from(r.base64||'','base64');if(b.length!==size)throw new Error('short guest read');return b;
 };
 const save=(name,bytes)=>{const file=path.resolve(out,name);fs.writeFileSync(file,bytes);return{file,bytes:bytes.length,sha256:sha(bytes)};};
 const input=async buttons=>{await rpc('input.buttons.send',{buttons});inputs.push({buttons,acknowledged:true});};
 const flush=()=>fs.writeFileSync(reportFile,JSON.stringify({schema:'weapon-marker-selector-writer-capture/v1',producer,version,
  entryPC:ENTRY,postWritePC:POST_WRITE,module:{file:modulePath,sha256:sha(moduleBytes)},map:{file:mapPath,sha256:sha(mapBytes)},
  expectedGeometrySHA256:GEOMETRY_SHA,expectedResourcePrefix64SHA256:RESOURCE_SHA,
  bounds:{maxStops,maxRows,durationMs,returnTimeoutMs,maxGroupDepth,entryStackBytes:STACK_BYTES,bindingProbe,configProbe},entryStopCount,postWriteStopCount,targetEntryCount,
  firstStopTicks,lastStopTicks,firstEntryTicks,lastEntryTicks,initialBreakpoints,inputs,transitions,ownedBP,gprCategoryDiagnostics,
  guestTickScope:firstStopTicks===null?'No observed entry/post-write guest ticks; only configured wall-time/stop bounds are available.':'First/last guest ticks cover observed own entry/post-write stops only.',
  codeIdentity:{verified:codeChecks.length>=functions.length&&codeChecks.every(c=>c.verified),checks:codeChecks},
  gameCallsites:gameCallers,inFlight,rows,noOpEntries,rejections:rejects,cleanup,failure,semanticName:null,
  scope:'Only observed setter entry stops while entry BP is armed; no-op entry is classified separately from an observed post-write.',
  negativeScope:targetEntryCount===0?'No eligible exact-resource/exact-weapon leaf entry within the recorded ticks/stops; this is not proof of no configuration path.':null,
  limits:['Only two SH selector setter paths are observed; alias/copy/SB/SW/SWL/SWR/VFPU/other-module writes are not covered.',
   'Group recursion is bounded; unknown caller or excess depth fails closed, without guessing.',
   'Actual setter calls can precede the loaded savestate or observation interval.',
   'No FX/muzzle/socket semantics are assigned.']},null,2));
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

 const abi=(condition,message)=>{if(!condition)throw new Error(`selector writer ABI mismatch: ${message}`);};
 const stateFields=b=>({sourceState190:b.readUInt32LE(0x190),sourceState194:b.readUInt32LE(0x194),sourceState198:b.readUInt32LE(0x198),
  primary:b.readUInt32LE(0x144),selectorSigned:b.readInt16LE(0x14c),selectorU16:b.readUInt16LE(0x14c),selectorWord14c:b.readUInt32LE(0x14c),flags154:b.readUInt32LE(0x154)});
 const callerChain=async(g,stack)=>{
  let rootS=g[29],ra=g[31],depth=0;const recursion=[];
  const at=a=>{const off=a-g[29];abi(off>=0&&off+4<=stack.length,'stack unwind outside saved window');return stack.readUInt32LE(off);};
  while(ra===0x08b651ac){
   abi(depth<maxGroupDepth,'group recursion depth exceeds configured maximum');
   const savedRA=at(rootS+0x18);recursion.push({depth,childEntrySP:rootS,childEntryRA:ra,parentLocalSP:rootS,savedRAAddress:rootS+0x18,savedRA});
   rootS+=0x20;ra=savedRA;depth++;
  }
  abi(ra===0x08b5b9f4,'unknown root selector caller');
  const globalRA=at(rootS+0x10),gameWrapperRA=at(rootS+0x20),gameRA=at(rootS+0x48);
  abi(globalRA===0x08b59ad8&&gameWrapperRA===0x08b26d04,'unknown bind/global wrapper saved-RA chain');
  abi(gameCallers.includes(gameRA-8),'unknown game caller');
  const fn=symbols.filter(s=>s.address<=gameRA-8&&gameRA-8<s.address+s.size);
  abi(fn.length===1&&fn[0].size>0&&fn[0].size<=0x8000,'missing/ambiguous/beyond-bound game function');
  return{recursionDepth:depth,recursion,leafEntrySP:g[29],leafEntryRA:g[31],rootSelectorEntrySP:rootS,rootSelectorEntryRA:ra,
   savedRA:{bind:{address:rootS+0x10,value:globalRA},global:{address:rootS+0x20,value:gameWrapperRA},game:{address:rootS+0x48,value:gameRA}},
   gameCallsite:gameRA-8,gameReturnPC:gameRA,gameFunction:fn[0]};
 };
 const bindingProvenance=async(g,stack,chain,sample)=>{
  // Opt-in observation for the actual shipped 08971edc <- 08976f1c path.
  // All addresses come from this stop's raw stack/registers, never old RAM addresses.
  abi(chain.gameCallsite===0x08971fe0,'binding probe encountered an unsupported game caller');
  const R=chain.rootSelectorEntrySP,G=R+0x30,Q=R+0x50,U=R+0x70;
  const at=a=>{const off=a-g[29];abi(off>=0&&off+4<=stack.length,'binding stack word outside raw window');return stack.readUInt32LE(off);};
  abi(at(Q+0x1c)===0x08977cc8,'binding upper saved RA');
  const context=at(G),primary=at(G+4),selector=at(G+8),slotContainer=at(G+0x14),config=at(Q+0xc),actor=at(Q+0x10),slotByteOffset=g[22];
  abi(selector===g[6]&&slotByteOffset%4===0,'binding selector/slot offset');
  const windows={};
  const window=async(name,address,size)=>{
   abi(pointer(address,size),`binding window ${name} outside bounded guest RAM`);
   const b=await read(address,size);windows[name]={address,size,raw:save(`binding_${name}_${sample}.bin`,b)};return b;
  };
  const locals=await window('upper_locals',U+0x370,0x10),cfg=await window('config_8c',config+0x8c,0x10);
  const actor80=await window('actor_80',actor+0x80,8);
  await window('actor_148c',actor+0x148c,4);await window('actor_1538',actor+0x1538,4);
  const mode=await window('actor_161c',actor+0x161c,4),container=await window('slot_container',slotContainer,8);
  const slotIndex=slotByteOffset/4,count=container.readUInt32LE(4),slotsBase=container.readUInt32LE(0);
  abi(count<=4096&&slotIndex<count,'binding slot index/count');
  await window('selected_slot',slotsBase+slotByteOffset,4);
  const primaryIndex=mode[2]!==0?1:0,arrayBase=actor80.readUInt32LE(0),arrayCount=actor80.readUInt32LE(4);
  abi(arrayCount<=4096&&primaryIndex<arrayCount,'binding primary array index/count');
  const primaryRecord=await window('primary_record',arrayBase+24*primaryIndex,24);
  abi(cfg.readUInt32LE(4)===selector&&locals.readUInt32LE(8)===selector,'binding source selector is not preserved');
  abi(locals.readUInt32LE(12)===primary&&primaryRecord.readUInt32LE(0)===primary,'binding primary source is not preserved');
  return{schema:'weapon-binding-source-provenance/v1',status:'read',rootSelectorEntrySP:R,gameWrapperLocalSP:G,gameFunctionLocalSP:Q,upperLocalSP:U,
   context,primary,selector,slotContainer,slotByteOffset,slotIndex,config,actor,primaryIndex,windows,
   requestedID:{config94:cfg.readUInt32LE(8),upper374:locals.readUInt32LE(4)},semanticName:null};
 };
 const configSourceProvenance=async(binding,sample)=>{
  // Reader ABI is original code, but membership is not a trace of which getter
  // branch executed. Upper 08977028 can replace s3 after its initial mode branch.
  const result={schema:'weapon-config-source-provenance/v1',status:'capturing',config:binding.config,
   recordBytes:0xe4,maxCount:108,windows:{},semanticName:null,
   branchExecuted:null,sourceHeaderCaptured:false,
   limits:['Membership in a current manager table is not proof of the executed getter branch.',
    'Upper 08977028 may replace s3 after initial mode selection; mode alone does not select the source.',
    'No loader/header ABI is verified, so no bytes preceding a table base are read.',
    'Full 0xe4 raw capture is a getter-stride window; no complete config field format is claimed.']};
  inFlight.configProvenance=result;flush();
  const window=async(name,address,size)=>{
   abi(pointer(address,size),`config window ${name} outside bounded guest RAM`);
   const bytes=await read(address,size);result.windows[name]={address,size,raw:save(`config_${name}_${sample}.bin`,bytes)};flush();return bytes;
  };
  const config=await window('config_record',binding.config,0xe4);
  abi(config.subarray(0x8c,0x9c).equals(fs.readFileSync(binding.windows.config_8c.raw.file)),
   'config full record disagrees with retained binding fragment');
  const global=await window('manager_global',0x08c3bc0c,4),globalObject=global.readUInt32LE(0);
  abi(pointer(globalObject,0x344),'config manager global object outside bounded guest RAM');
  const manager=globalObject+0x340;
  const fields=await window('manager_fields',manager+0x8be0,12);
  const contiguousBase=fields.readUInt32LE(0),pointerTableBase=fields.readUInt32LE(4),count=fields.readUInt32LE(8);
  result.globalObject=globalObject;result.manager=manager;result.contiguousBase=contiguousBase;
  result.pointerTableBase=pointerTableBase;result.count=count;flush();
  abi(count>=1&&count<=108,'config manager count outside 1..108');
  abi(pointer(contiguousBase,count*0xe4),'config contiguous table range outside bounded guest RAM');
  abi(pointer(pointerTableBase,count*4),'config pointer table range outside bounded guest RAM');
  const table=await window('pointer_table',pointerTableBase,count*4),slots=words(table),matches=[];
  slots.forEach((value,index)=>{
   if(value===binding.config)matches.push(index); // Other entries remain raw and are never followed.
  });
  const delta=binding.config-contiguousBase;
  const continuous=delta>=0&&delta%0xe4===0&&delta/0xe4<count;
  result.contiguousMembership={matched:continuous,index:continuous?delta/0xe4:null,deltaBytes:delta,
   equation:'config == contiguousBase + index*0xe4 with 0<=index<count'};
  result.pointerMembership={matched:matches.length>0,indices:matches,rawSlotValues:slots,
   slotValueClasses:slots.map(value=>value===0?'null':pointer(value,0xe4)?'bounded_record_candidate':'unfollowed_non_RAM_or_unaligned_value'),
   slotAddresses:matches.map(index=>pointerTableBase+index*4),payloadsRead:false};
  result.layoutMembership=continuous?(matches.length?'both':'contiguous_only'):(matches.length?'pointer_only':'unmatched');
  result.bindingContext=binding.context;result.bindingActor=binding.actor;
  result.actorMode1538=fs.readFileSync(binding.windows.actor_1538.raw.file).readUInt32LE(0);
  result.status='read';flush();return result;
 };
 try{
  await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('debugger open timeout')),10000);ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});ws.addEventListener('error',e=>{clearTimeout(timer);reject(e);},{once:true});});
  version=await rpc('version',{name:'weapon-marker-selector-writer',version:'1'});
  const existing=await rpc('cpu.breakpoint.list');if(!Array.isArray(existing.breakpoints))throw new Error('missing breakpoint inventory');initialBreakpoints.push(...existing.breakpoints);
  if(existing.breakpoints.some(bp=>bp.enabled||BP_TARGETS.has(bp.address)))throw new Error('existing active/conflicting CPU breakpoint; left unchanged');
  for(const [address,size,name] of functions)await codeIdentity(`${name}_full`,address,size);
  await input(release);if(analog)await rpc('input.analog.send',{...analog,x:0,y:0});
  stops.length=0;resume();await addBP(ENTRY);await input({...release,...held});if(analog)await rpc('input.analog.send',analog);
  const deadline=Date.now()+durationMs;
  while(!interrupted){
   if(!inFlight&&(Date.now()>=deadline||entryStopCount>=maxStops||rows.length>=maxRows))break;
   const stopDeadline=inFlight?inFlight.returnDeadline:deadline;
   if(Date.now()>=stopDeadline){if(inFlight)throw new Error('selected post-write timeout; validation/execution outcome unknown');break;}
   let stop;try{stop=await nextStop(Math.min(1000,Math.max(1,stopDeadline-Date.now())));}catch(e){if(e.message==='wait interval elapsed')continue;throw e;}
   const expected=inFlight?POST_WRITE:ENTRY;
   if(stop.pc!==expected){ownStop=false;throw new Error(`unexpected external CPU stop ${stop.pc}; left paused`);}
   ownStop=true;
   if(!Number.isSafeInteger(stop.ticks)||(lastStopTicks!==null&&stop.ticks<lastStopTicks))throw new Error('invalid/nonmonotonic stop ticks');
   if(firstStopTicks===null)firstStopTicks=stop.ticks;lastStopTicks=stop.ticks;
   const g=await regs();
   if(!inFlight){
    entryStopCount++;if(firstEntryTicks===null)firstEntryTicks=stop.ticks;lastEntryTicks=stop.ticks;
    const context=g[4],P=g[5],newSelector=g[6],S=g[29];
    if(!pointer(P,0x1a4)){reject('invalid state pointer');resume();continue;}
    const before=await read(P,0x1a4);
    if(before[0]!==0x65){reject(before[0]===0x6c?'group entry, not target leaf':'unknown leaf type');resume();continue;}
    const fields=stateFields(before);
    if(!pointer(fields.sourceState198,64)){reject('invalid resource prefix pointer');resume();continue;}
    const resource=await read(fields.sourceState198,64);
    if(sha(resource)!==RESOURCE_SHA){reject('not exact resource prefix');resume();continue;}
    if(!pointer(fields.primary)){reject('missing primary handle');resume();continue;}
    const primaryRaw=await read(fields.primary,4),actor=primaryRaw.readUInt32LE(0),id=await identity(actor);
    if(!id){reject('not exact original weapon');resume();continue;}
    targetEntryCount++;
    const sample=String(targetEntryCount-1).padStart(4,'0');
    inFlight={sample:targetEntryCount-1,entryPC:ENTRY,entryTicks:stop.ticks,entryGPR:g,entryArgs:{a0:context,a1:P,a2:newSelector},context,state:P,primary:fields.primary,
      entrySP:S,entryRA:g[31],newSelector,expectedStoredU16:newSelector&0xffff,oldSelectorSigned:fields.selectorSigned,oldSelectorU16:fields.selectorU16,
      beforeFields:fields,stateBefore:save(`state_before_${sample}.bin`,before),resourcePrefix:save(`resource_prefix_${sample}.bin`,resource),
      weapon:{actor,sourceBase:id.sourceBase,metadata:id.metadata,drawTable:id.table,metadataHeader:words(id.header),drawHeader:words(id.packet),geometrySHA256:GEOMETRY_SHA,
       geometry:save(`geometry_${sample}.bin`,id.geometry),
       identityRaw:{primary:{address:fields.primary,raw:save(`primary_handle_${sample}.bin`,primaryRaw)},
        actorFields:{address:actor+0x3c4,raw:save(`actor_fields_${sample}.bin`,id.fields)},
        metadata:{address:id.metadata,raw:save(`metadata_${sample}.bin`,id.header)},
        draw:{address:id.table,raw:save(`draw_header_${sample}.bin`,id.packet)}}},semanticName:null};flush();
    abi(pointer(S,STACK_BYTES),'entry stack outside guest RAM');
    const stack=await read(S,STACK_BYTES);inFlight.entryStack=save(`entry_stack_${sample}.bin`,stack);flush();
    const chain=await callerChain(g,stack);inFlight.callerChain=chain;flush();
    if(!checkedGameFunctions.has(chain.gameFunction.address)){
      await codeIdentity(`game_function_${chain.gameFunction.address.toString(16)}`,chain.gameFunction.address,chain.gameFunction.size);
      checkedGameFunctions.add(chain.gameFunction.address);
    }
    if(bindingProbe){
      if(!checkedGameFunctions.has(0x08976f1c)){
        await codeIdentity('binding_upper_full',0x08976f1c,0xe90);
        await codeIdentity('binding_primary_getter_full',0x08b38dd0,0x58);
        checkedGameFunctions.add(0x08976f1c);
      }
      inFlight.bindingProvenance=await bindingProvenance(g,stack,chain,sample);flush();
    }
    if(configProbe){
      if(!checkedGameFunctions.has(0x0896c5fc)){
        const configReaders=[[0x0896c5fc,0x10,'config_manager_getter_full'],
          [0x08ac288c,0x40,'config_contiguous_getter_full'],[0x08ac28cc,0x34,'config_pointer_getter_full'],
          [0x0896ce9c,0x30,'config_contiguous_wrapper_full']];
        for(const [address,size,name] of configReaders){
          abi(symbols.some(s=>s.address===address&&s.size===size),'config reader map function boundary');
          await codeIdentity(name,address,size);
        }
        checkedGameFunctions.add(0x0896c5fc);
      }
      await configSourceProvenance(inFlight.bindingProvenance,sample);
    }
    if((fields.selectorSigned>>>0)===newSelector){
      const noOp={...inFlight,classification:'no_op_entry',actualWriteObserved:false};noOpEntries.push(noOp);inFlight=null;flush();resume();continue;
    }
    inFlight.classification='changed_selector_entry';inFlight.expectedPostWriteSP=S-0x20;inFlight.expectedPostWriteRA=0x08b65208;flush();
    await removeBP();await codeIdentity(`post_write_${sample}`,POST_WRITE,16);
    inFlight.returnDeadline=Date.now()+returnTimeoutMs;flush();await addBP(POST_WRITE);resume();
   }else{
    postWriteStopCount++;
    abi(g[29]===inFlight.expectedPostWriteSP&&g[31]===inFlight.expectedPostWriteRA,'post-write SP/validator RA');
    abi(g[16]===inFlight.newSelector&&g[17]===inFlight.context&&g[18]===inFlight.state,'post-write selector/context/state registers');
    abi([19,20,21,22,23,30].every(i=>g[i]===inFlight.entryGPR[i]),'post-write untouched callee-saved registers');
    const stack=await read(g[29],0x20);abi(stack.readUInt32LE(0x18)===inFlight.entryRA,'post-write saved caller RA');
    const after=await read(inFlight.state,0x1a4),sample=String(inFlight.sample).padStart(4,'0');
    inFlight.postAttempt={pc:POST_WRITE,ticks:stop.ticks,gpr:g,stateAfter:save(`state_after_${sample}.bin`,after),postStack:save(`post_stack_${sample}.bin`,stack),fields:stateFields(after)};flush();
    abi(after.readUInt16LE(0x14c)===inFlight.expectedStoredU16,'actual selector does not equal stored u16(newSelector)');
    const before=fs.readFileSync(inFlight.stateBefore.file),differences=[];for(let i=0;i<after.length;i++)if(after[i]!==before[i])differences.push(i);
    abi(differences.every(i=>i===0x14c||i===0x14d),'unexpected state byte changed outside selector halfword');
    const complete={...inFlight,classification:'observed_selector_write',actualWriteObserved:true,postWrite:inFlight.postAttempt,changedByteOffsets:differences};
    delete complete.postAttempt;delete complete.returnDeadline;rows.push(complete);inFlight=null;flush();await removeBP();
    if(rows.length>=maxRows||entryStopCount>=maxStops||Date.now()>=deadline)break;
    await addBP(ENTRY);resume();
   }
  }
  if(inFlight)throw new Error(interrupted?'interrupted during selected writer':'selected writer incomplete');
 }catch(e){failure=String(e.stack||e);}
 finally{
    if(stops.length){
      cleanup.unconsumedStops=stops.map(s=>({pc:s.pc,ticks:s.ticks,ownedBreakpointAtReceipt:s.ownedBreakpointAtReceipt}));
      const last=stops.at(-1);
      // Resume only a positively identified own stop; preserve a queued external pause.
      ownStop=last.ownedBreakpointAtReceipt!==null&&last.pc===last.ownedBreakpointAtReceipt;
    }
    for(const action of [async()=>{await input(release);cleanup.buttonsReleased=true;},async()=>{if(analog){await rpc('input.analog.send',{...analog,x:0,y:0});cleanup.analogReleased=true;}},
      async()=>{await removeBP();cleanup.ownedBreakpointRemoved=true;},async()=>{if(ownStop){resume();cleanup.resumedOwnStop=true;}}]){
      try{if(ws.readyState===WebSocket.OPEN)await action();else cleanup.errors.push('debugger disconnected before cleanup');}catch(e){cleanup.errors.push(String(e));}
    }
    flush();ws.close();
  }
 console.log(JSON.stringify({out,entryStopCount,postWriteStopCount,targetEntryCount,rows:rows.length,noOps:noOpEntries.length,rejections:rejects,cleanup,failure}));
 if(failure||cleanup.errors.length)process.exitCode=1;
}
main().catch(e=>{console.error(e.stack||e);process.exitCode=1;});
