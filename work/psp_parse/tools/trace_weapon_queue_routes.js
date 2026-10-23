// Bounded observer of an already-running debugger. No launch, UI or savestate IO.
// No exact-weapon selection; route names identify raw function entry PCs only.
'use strict';
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const producer={file:path.resolve(__filename),sha256:sha(fs.readFileSync(__filename))};
const BASE=0x08804000,MODULE_SHA='b5fc590366fc610f2cdd60104a4a28851bacd402c4600a4c296776e1dea0869f';
const definitions=[['enqueue',0x08bbdce8,0x19c],['range_draw',0x08bbda68,0xb8],['range_alt',0x08bbdb20,0xb8],
 ['entry_callback',0x08bbd7f0,0x38],['entry_callback_alt',0x08bbd828,0x3c],['controller_dispatch',0x08b5ac60,0x258],['enqueue_control',0x08bbdce8,0x19c]];
const targets=new Set(definitions.map(x=>x[1]));
const out=process.env.QUEUE_ROUTES_OUT_DIR,port=Number(process.env.PPSSPP_DEBUGGER_PORT||9900);
const phaseMs=Number(process.env.QUEUE_PHASE_MS||1500),maxStops=Number(process.env.QUEUE_PHASE_STOPS||6);
const rpcMs=Number(process.env.QUEUE_RPC_TIMEOUT_MS||1500),resumeMs=Number(process.env.QUEUE_RESUME_TIMEOUT_MS||1500);
const held=JSON.parse(process.env.QUEUE_BUTTONS_JSON||'{}');
const analog=process.env.QUEUE_ANALOG_JSON?JSON.parse(process.env.QUEUE_ANALOG_JSON):null;
if(!out||!Number.isInteger(port)||port<1||port>65535||!Number.isInteger(phaseMs)||phaseMs<100||phaseMs>10000||
 !Number.isInteger(maxStops)||maxStops<1||maxStops>24||!Number.isInteger(rpcMs)||rpcMs<50||rpcMs>10000||
 !Number.isInteger(resumeMs)||resumeMs<50||resumeMs>10000)throw new Error('invalid queue-route bounds');
if(!held||typeof held!=='object'||Array.isArray(held)||Object.values(held).some(v=>typeof v!=='boolean'))throw new Error('invalid queue-route held buttons');
if(analog&&(!Number.isFinite(analog.x)||!Number.isFinite(analog.y)||Math.abs(analog.x)>1||Math.abs(analog.y)>1))throw new Error('invalid queue-route analog');
const release=Object.fromEntries([...new Set(['square','rtrigger','ltrigger','triangle','cross','circle',...Object.keys(held)])].map(k=>[k,false]));
const modulePath=path.resolve(__dirname,'../raw/ULJM05798_module_08804000.bin'),moduleBytes=fs.readFileSync(modulePath);
if(sha(moduleBytes)!==MODULE_SHA)throw new Error('selected original module SHA256 differs');
const mapPath=path.resolve(__dirname,'../map.ppmap.txt'),mapRaw=fs.readFileSync(mapPath);
for(const [,pc,size] of definitions){
 const matching=mapRaw.toString('utf8').split(/\r?\n/).filter(line=>{const x=line.trim().split(/\s+/);return x.length>=5&&parseInt(x[0],16)+BASE===pc&&parseInt(x[1],16)===size;});
 if(matching.length!==1)throw new Error('queue-route map boundary differs');
}
const u32=x=>Number.isInteger(x)&&x>=0&&x<=0xffffffff;
const pointer=(x,n=4)=>u32(x)&&x%4===0&&Number.isInteger(n)&&n>=0&&x>=0x08000000&&x+n<=0x0c000000;
function decodedBytes(reply,address,size){
 if(!Array.isArray(reply.lines))throw new Error('missing original disassembly');
 const bytes=Buffer.alloc(size),seen=new Set();
 for(const line of reply.lines){
  if(!Number.isInteger(line.address)||!Number.isInteger(line.addressSize)||line.addressSize<4||line.addressSize%4)throw new Error('invalid original disassembly range');
  if(line.address>=address+size||line.address+line.addressSize<=address)continue;
  if(!['opcode','macro'].includes(line.type))throw new Error('non-opcode in identity range');
  const list=line.addressSize===4?[line.encoding]:line.macroEncoding;
  if(!Array.isArray(list)||list.length!==line.addressSize/4||list[0]!==line.encoding)throw new Error('missing original macro encoding');
  list.forEach((word,i)=>{const at=line.address+4*i;if(!u32(word))throw new Error('invalid original opcode');
   if(at<address||at>=address+size)return;
   if((at-address)%4||seen.has(at))throw new Error('overlapping original disassembly');
   bytes.writeUInt32LE(word,at-address);seen.add(at);
  });
 }
 if(seen.size!==size/4)throw new Error('incomplete original disassembly');return bytes;
}
async function main(){
 fs.mkdirSync(out,{recursive:true});const reportFile=path.resolve(out,'queue_routes.json');
 // Exclusive reservation precedes the connection. Never overwrite old evidence.
 fs.writeFileSync(reportFile,'{}\n',{flag:'wx'});
 const ws=new WebSocket(`ws://127.0.0.1:${port}/debugger`,'debugger.ppsspp.org');
 const startedAt=Date.now(),pending=new Map(),stops=[],rpcLog=[],events=[],errors=[],phases=[],codeChecks=[],inputs=[];
 let serial=0,ownedBP=null,ownStop=null,externalPause=false,asyncFailure=null,failure=null,interrupted=false;
 let wake=null,resumeWaiter=null,resumeFailed=false,version=null,activePhase=null,lastTicks=null;
 const cleanup={errors:[]},transitions=[],resumes=[];
 const save=(name,bytes)=>{const file=path.resolve(out,name);fs.writeFileSync(file,bytes,{flag:'wx'});return{file,bytes:bytes.length,sha256:sha(bytes)};};
 const flush=()=>fs.writeFileSync(reportFile,JSON.stringify({schema:'weapon-queue-route-capture/v1',producer,
  module:{file:modulePath,sha256:MODULE_SHA},map:{file:mapPath,sha256:sha(mapRaw)},version,startedAt,wallNow:Date.now(),
  bounds:{phaseMs,maxStops,rpcMs,resumeMs,stackBytes:0x100},phaseOrder:definitions.map(([name,pc,size])=>({name,pc,size})),
  phases,codeIdentity:{verified:codeChecks.length===6&&codeChecks.every(x=>x.verified),checks:codeChecks},
  rpcLog,events,errors,transitions,resumes,inputs,ownedBP,externalPause,cleanup,failure,semanticName:null,
  exactWeaponSelection:false,muzzleProven:false,GEConsumerProven:false,
  scope:'Entry stops during each recorded single-BP armed interval only; no queue/weapon/render semantic selection.',
  limits:['Sequential phases observe different guest-time windows, not simultaneous routes.',
   'Zero stops alone cannot prove absent calls; compare full status ACKs/ticks and armed wall intervals.',
   'Running status PC is approximate. Controller bytes are captured only at observed own stops.',
   'Raw C/P/N labels identify entry fields +0xc/+0x10/+0x14, not verified object semantics.',
   'A coincident external pause at the exact owned BP PC cannot be distinguished from its breakpoint stop.']},null,2));
 const signal=()=>{if(wake){const fn=wake;wake=null;fn();}};
 const guard=()=>{if(externalPause)throw new Error('external pause observed; left paused');if(asyncFailure)throw new Error(asyncFailure);if(interrupted)throw new Error('interrupted');};
 const failResume=(error)=>{if(resumeWaiter){const w=resumeWaiter;resumeWaiter=null;clearTimeout(w.timer);resumeFailed=true;w.reject(error);}};
 ws.addEventListener('message',event=>{
  let m;try{m=JSON.parse(event.data);}catch{asyncFailure='malformed debugger JSON';signal();return;}
  const wall=Date.now();
  if(m.event==='error'){
   errors.push({wall,raw:m});asyncFailure=`debugger error: ${JSON.stringify(m)}`;
   const waiter=pending.get(m.ticket);if(waiter){pending.delete(m.ticket);clearTimeout(waiter.timer);waiter.log.ack=m;waiter.log.wallAcknowledged=wall;waiter.reject(new Error(asyncFailure));}
   // Resume errors may have no ticket; retain them and fail the observation.
   failResume(new Error(asyncFailure));signal();flush();return;
  }
  const waiter=pending.get(m.ticket);
  if(waiter){pending.delete(m.ticket);clearTimeout(waiter.timer);waiter.log.ack=m;waiter.log.wallAcknowledged=wall;waiter.resolve(m);return;}
  if(m.event==='cpu.resume'){
   events.push({wall,raw:m,kind:'resume_notification'});
   if(resumeWaiter&&(!m.ticket||m.ticket===resumeWaiter.ticket)){
    const w=resumeWaiter;resumeWaiter=null;clearTimeout(w.timer);w.record.wallAcknowledged=wall;w.record.ack=m;
    w.record.ackKind=m.ticket?'ticketed':'unticketed';w.stop.resumed=true;if(ownStop===w.stop)ownStop=null;w.resolve(m);
   }
   signal();flush();return;
  }
  if(m.event==='cpu.stepping'){
   const item={wall,raw:m,ownedBreakpointAtReceipt:ownedBP,phaseIndex:activePhase?.index??null,captureAttempted:false,captured:false,resumed:false};
   events.push({wall,raw:m,kind:'stepping',ownedBreakpointAtReceipt:ownedBP});
   if(!u32(m.pc)||!Number.isSafeInteger(m.ticks)||m.ticks<0||(lastTicks!==null&&m.ticks<lastTicks))asyncFailure='invalid/nonmonotonic own/external stop';
   else if(ownedBP!==null&&m.pc===ownedBP){lastTicks=m.ticks;ownStop=item;stops.push(item);}
   else{externalPause=true;ownStop=null;failResume(new Error('external pause during resume; left paused'));}
   signal();flush();return;
  }
  events.push({wall,raw:m,kind:'unmatched_notification'});flush();
 });
 ws.addEventListener('close',()=>{
  for(const w of pending.values()){clearTimeout(w.timer);w.reject(new Error('debugger closed'));}pending.clear();
  failResume(new Error('debugger closed'));asyncFailure='debugger closed';signal();
 });
 process.on('SIGINT',()=>{interrupted=true;signal();});process.on('SIGTERM',()=>{interrupted=true;signal();});
 const rpc=(event,fields={})=>new Promise((resolve,reject)=>{
  const ticket=`queue-routes-${++serial}`,log={request:{event,...fields,ticket},wallRequested:Date.now()};rpcLog.push(log);
  const timer=setTimeout(()=>{pending.delete(ticket);log.timeoutAt=Date.now();reject(new Error(`timeout: ${event}`));},rpcMs);
  pending.set(ticket,{resolve,reject,timer,log});ws.send(JSON.stringify(log.request));
 });
 const read=async(address,size)=>{if(!pointer(address,size)||size>0x20000)throw new Error('invalid bounded guest read');
  const response=await rpc('memory.read',{address,size,replacements:true}),raw=Buffer.from(response.base64||'','base64');
  if(raw.length!==size)throw new Error('short guest read');return raw;
 };
 const status=async(phase,label)=>{
  const item={label,wallRequested:Date.now(),ack:null};(phase.statusSamples||(phase.statusSamples=[])).push(item);flush();
  try{const raw=await rpc('cpu.status');item.wallAcknowledged=Date.now();item.ack=raw;flush();
   if(typeof raw.stepping!=='boolean'||typeof raw.paused!=='boolean'||!u32(raw.pc)||!Number.isSafeInteger(raw.ticks)||raw.ticks<0)throw new Error('invalid cpu.status ACK');
   return raw;
  }catch(error){item.error=String(error);item.wallFinished=Date.now();flush();throw error;}
 };
 const removeBP=async()=>{if(ownedBP===null)return;const address=ownedBP;
  await rpc('cpu.breakpoint.remove',{address});ownedBP=null;transitions.push({operation:'remove',address,wall:Date.now()});
  if(activePhase)activePhase.bpRemovedAt=Date.now();flush();
 };
 const addBP=async(address)=>{guard();if(ownedBP!==null)throw new Error('single owned BP invariant');ownedBP=address;
  transitions.push({operation:'add_requested',address,wall:Date.now()});flush();await rpc('cpu.breakpoint.add',{address,enabled:true,log:false});
  transitions.push({operation:'add_acknowledged',address,wall:Date.now()});flush();
 };
 const resumeOwn=async(cleaning=false)=>{
  if(!ownStop||ownStop.resumed||externalPause||resumeFailed)return;
  if(!cleaning)guard();if(resumeWaiter)throw new Error('overlapping resume request');
  const stop=ownStop,ticket=`queue-resume-${++serial}`,record={ticket,wallRequested:Date.now(),ownStopPC:stop.raw.pc,ownStopTicks:stop.raw.ticks};resumes.push(record);flush();
  try{await new Promise((resolve,reject)=>{
   const timer=setTimeout(()=>{if(resumeWaiter?.ticket===ticket)resumeWaiter=null;record.timeoutAt=Date.now();resumeFailed=true;reject(new Error('cpu.resume acknowledgement timeout'));},resumeMs);
   resumeWaiter={resolve,reject,timer,ticket,record,stop};ws.send(JSON.stringify({event:'cpu.resume',ticket}));
  });}catch(error){record.error=String(error);flush();throw error;}
 };
 const codeIdentity=async(name,address,size)=>{
  const expected=moduleBytes.subarray(address-BASE,address-BASE+size),item={name,address,size,verified:false};codeChecks.push(item);
  item.expected=save(`${name}_expected.bin`,expected);item.raw=save(`${name}_raw.bin`,await read(address,size));
  const response=await rpc('memory.read',{address,size,replacements:false}),original=Buffer.from(response.base64||'','base64');
  if(original.length!==size)throw new Error('short original code read');item.original=save(`${name}_original.bin`,original);
  const disasm=await rpc('memory.disasm',{address,end:address+size,displaySymbols:false});item.disasm=save(`${name}_disasm.json`,Buffer.from(JSON.stringify(disasm),'utf8'));
  const decoded=decodedBytes(disasm,address,size);item.decoded=save(`${name}_decoded.bin`,decoded);
  item.verified=original.equals(expected)&&decoded.equals(expected);flush();if(!item.verified)throw new Error(`original code identity differs: ${name}`);
 };
 const captureStop=async(item,phase)=>{
  if(item.captureAttempted)return;item.captureAttempted=true;const queued=stops.indexOf(item);if(queued>=0)stops.splice(queued,1);
  const index=phase.rows.length,prefix=`p${phase.index}_${String(index).padStart(2,'0')}`;
  const row={pc:item.raw.pc,ticks:item.raw.ticks,wallStopReceived:item.wall,status:'capturing',args:null,semanticName:null};phase.rows.push(row);flush();
  const regs=await rpc('cpu.getAllRegs');row.registerReply=save(`${prefix}_regs.json`,Buffer.from(JSON.stringify(regs),'utf8'));
  const values=regs.categories?.[0]?.uintValues;
  if(!Array.isArray(values)||values.length<32||values.slice(0,32).some(x=>!u32(x)))throw new Error('invalid GPR category');
  row.gpr=values.slice(0,32);row.gprCategoryLength=values.length;
  if(values.length>=35&&values[32]!==item.raw.pc)throw new Error('GPR PC disagrees with own stop');
  row.args={a0:row.gpr[4],a1:row.gpr[5],a2:row.gpr[6]};flush();
  row.stack={address:row.gpr[29],size:0x100,raw:save(`${prefix}_stack.bin`,await read(row.gpr[29],0x100))};
  const global=await read(0x08c3a680,4),controller=global.readUInt32LE(0);
  row.controller={globalAddress:0x08c3a680,globalRaw:save(`${prefix}_controller_global.bin`,global),address:controller,status:'invalid_pointer_unfollowed'};
  if(pointer(controller,0x30)){
   const bytes=await read(controller,0x30);row.controller.raw=save(`${prefix}_controller.bin`,bytes);
   row.controller.status='read_at_own_stop';row.controller.rawByte2e=bytes[0x2e];row.controller.rawByte2f=bytes[0x2f];
  }
  if(phase.name.startsWith('entry_callback')){
   const address=row.gpr[4];row.callbackEntry={address,size:24,status:'invalid_pointer_unfollowed',fields:{}};
   if(pointer(address,24)){
    const e=await read(address,24);row.callbackEntry.raw=save(`${prefix}_entry24.bin`,e);row.callbackEntry.status='read';
    for(const [name,offset,size] of [['C',0xc,0x40],['P',0x10,0x1a4],['N',0x14,0x40]]){
     const target=e.readUInt32LE(offset),field={sourceOffset:offset,address:target,size,status:'invalid_pointer_unfollowed'};row.callbackEntry.fields[name]=field;
     if(pointer(target,size)){field.raw=save(`${prefix}_${name}.bin`,await read(target,size));field.status='read';}
    }
   }
  }
  row.status='read';item.captured=true;phase.ownStops++;flush();
 };
 const waitEvent=ms=>new Promise(resolve=>{const timer=setTimeout(()=>{if(wake===finish)wake=null;resolve();},ms);function finish(){clearTimeout(timer);resolve();}wake=finish;});
 try{
  await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('debugger open timeout')),rpcMs);
   ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});ws.addEventListener('error',e=>{clearTimeout(timer);reject(e);},{once:true});});
  version=await rpc('version',{name:'weapon-queue-routes',version:'1'});
  const inventory=await rpc('cpu.breakpoint.list');
  if(!Array.isArray(inventory.breakpoints)||inventory.breakpoints.some(x=>x.enabled||targets.has(x.address)))throw new Error('existing active/conflicting breakpoint; left unchanged');
  for(const [name,address,size] of definitions.slice(0,6)){guard();await codeIdentity(name,address,size);}
  await rpc('input.buttons.send',{buttons:release});inputs.push({wall:Date.now(),buttons:release});
  if(analog)await rpc('input.analog.send',{...analog,x:0,y:0});
  for(const [name,pc,size] of definitions){
   const phase={index:phases.length,name,pc,size,wallStarted:Date.now(),rows:[],ownStops:0,statusSamples:[]};phases.push(phase);activePhase=phase;flush();
   try{
    guard();const before=await status(phase,'before');
    if(before.paused||before.stepping){externalPause=true;throw new Error('phase begins externally paused; no resume issued');}
    guard();
    if(phase.index===0){const buttons={...release,...held};await rpc('input.buttons.send',{buttons});inputs.push({wall:Date.now(),buttons});if(analog)await rpc('input.analog.send',analog);}
    await addBP(pc);phase.armedAt=Date.now();phase.deadline=phase.armedAt+phaseMs;flush();
    while(Date.now()<phase.deadline&&phase.ownStops<maxStops){
     guard();const item=stops.shift();
     if(!item){await waitEvent(Math.max(1,Math.min(100,phase.deadline-Date.now())));continue;}
     if(item.phaseIndex!==phase.index||item.raw.pc!==pc)throw new Error('stale/out-of-phase own stop');
     await captureStop(item,phase);guard();
     if(phase.ownStops>=maxStops||Date.now()>=phase.deadline)await removeBP();
     await resumeOwn();
    }
    phase.endReason=phase.ownStops>=maxStops?'stop_limit':'wall_limit';
   }catch(error){phase.failure=String(error.stack||error);throw error;}
   finally{
    try{await removeBP();
     if(ownStop&&!ownStop.captureAttempted&&!externalPause)await captureStop(ownStop,phase);
     await resumeOwn(true);
    }catch(error){phase.settleError=String(error);if(!phase.failure)phase.failure=String(error);}
    try{const after=await status(phase,'after');
     if(after.paused||after.stepping){phase.pausedAtEnd=true;if(after.paused||!ownStop||ownStop.resumed)externalPause=true;else phase.ownedPauseAtEnd=true;}
     if(phase.statusSamples[0]?.ack&&after.ticks<phase.statusSamples[0].ack.ticks)phase.tickRegression=true;
    }catch(error){phase.endStatusError=String(error);}
    phase.wallFinished=Date.now();flush();
   }
   guard();if(phase.failure||phase.endStatusError||phase.tickRegression)throw new Error('phase failed or status/ticks invalid');
  }
 }catch(error){failure=String(error.stack||error);}
 finally{
  for(const action of [async()=>{await rpc('input.buttons.send',{buttons:release});cleanup.buttonsReleased=true;},
   async()=>{if(analog){await rpc('input.analog.send',{...analog,x:0,y:0});cleanup.analogReleased=true;}},
   async()=>{await removeBP();cleanup.ownedBreakpointRemoved=true;},
   async()=>{if(externalPause){cleanup.externalPausePreserved=true;return;}if(resumeFailed){cleanup.resumeSkippedAfterError=true;return;}
    if(ownStop){await resumeOwn(true);cleanup.resumedOwnStop=true;}}]){
   try{if(ws.readyState===WebSocket.OPEN)await action();else cleanup.errors.push('debugger disconnected before cleanup');}catch(error){cleanup.errors.push(String(error));}
  }
  if(!failure&&asyncFailure)failure=asyncFailure;
  if(!failure&&externalPause)failure='external pause observed; left paused';
  cleanup.unconsumedOwnStops=stops.map(x=>({pc:x.raw.pc,ticks:x.raw.ticks,captured:x.captured,resumed:x.resumed}));
  flush();ws.close();
 }
 console.log(JSON.stringify({out,phases:phases.map(p=>({name:p.name,ownStops:p.ownStops,endReason:p.endReason})),cleanup,failure}));
 if(failure||cleanup.errors.length)process.exitCode=1;
}
main().catch(error=>{console.error(error.stack||error);process.exitCode=1;});
