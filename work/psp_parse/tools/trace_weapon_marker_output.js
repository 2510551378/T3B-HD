// Existing PPSSPP debugger only. No process launch, desktop use or savestate IO.
// Exactly one owned CPU BP: helper entry, or its verified wrapper return.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const ENTRY = 0x08b44580, RETURN = 0x08b3e62c, BASE = 0x08804000;
const GEOMETRY_SHA = '168578abca4c4f5d22d5994ebced6b93a25d5167428bfd47f1a1150a8d42e65a';
const out = process.env.MARKER_OUTPUT_OUT_DIR || process.env.MARKER_OUT_DIR;
const port = Number(process.env.PPSSPP_DEBUGGER_PORT || 9900);
const maxStops = Number(process.env.MARKER_MAX_STOPS || 1200);
const maxRows = Number(process.env.MARKER_MAX_ROWS || 12);
const durationMs = Number(process.env.MARKER_DURATION_MS || 15000);
const returnTimeoutMs = Number(process.env.MARKER_RETURN_TIMEOUT_MS || 3000);
const held = JSON.parse(process.env.MARKER_BUTTONS_JSON || '{}');
const analog = process.env.MARKER_ANALOG_JSON ? JSON.parse(process.env.MARKER_ANALOG_JSON) : null;
if (!out || !Number.isInteger(port) || port<1 || port>65535 || !Number.isInteger(maxStops) || maxStops<1 || maxStops>20000 || !Number.isInteger(maxRows) || maxRows<1 || maxRows>240 || !Number.isFinite(durationMs) || durationMs<100 || durationMs>120000 || !Number.isFinite(returnTimeoutMs) || returnTimeoutMs<50 || returnTimeoutMs>10000) throw new Error('invalid marker output bounds');
if (!held || typeof held!=='object' || Array.isArray(held) || Object.values(held).some(v=>typeof v!=='boolean')) throw new Error('buttons must be a boolean object');
if (analog && (!Number.isFinite(analog.x) || !Number.isFinite(analog.y) || Math.abs(analog.x)>1 || Math.abs(analog.y)>1)) throw new Error('invalid analog input');
const release=Object.fromEntries([...new Set(['rtrigger','ltrigger','square','triangle','circle','cross',...Object.keys(held)])].map(k=>[k,false]));
const modulePath=path.resolve(__dirname,'../raw/ULJM05798_module_08804000.bin');
const moduleBytes=fs.readFileSync(modulePath);
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
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
// Column-major 4x4 comparison in JS f64; retain raw F32 output as the evidence.
const product=(a,b)=>Array.from({length:16},(_,i)=>{
  const row=i%4,col=Math.floor(i/4);let value=0;
  for(let k=0;k<4;k++)value+=a[row+4*k]*b[k+4*col];
  return value;
});
const errorAgainst=(actual,predicted)=>({max_abs:Math.max(...actual.map((v,i)=>Math.abs(v-predicted[i]))),
  rms:Math.sqrt(actual.reduce((s,v,i)=>s+(v-predicted[i])**2,0)/16),predicted_col_major_f64:predicted});

async function main(){
  fs.mkdirSync(out,{recursive:true});
  const reportFile=path.join(out,'marker_output.json');
  if(fs.existsSync(reportFile))throw new Error('refusing to overwrite an existing marker_output.json');
  const ws=new WebSocket(`ws://127.0.0.1:${port}/debugger`,'debugger.ppsspp.org');
  const pending=new Map(),stops=[],waiters=[];
  let serial=0,ownedBP=null,ownStop=false,interrupted=false,version=null,failure=null,inFlight=null;
  let helperStopCount=0,returnStopCount=0,firstStopTicks=null,lastStopTicks=null,firstHelperTicks=null,lastHelperTicks=null;
  const rows=[],rejects={},indices={},transitions=[],inputs=[],codeChecks=[],foreignReturns=[];
  const gprCategoryDiagnostics=[];
  const cleanup={errors:[]},initialBreakpoints=[];
  const reject=reason=>{rejects[reason]=(rejects[reason]||0)+1;};
  process.on('SIGINT',()=>{interrupted=true;});process.on('SIGTERM',()=>{interrupted=true;});
  ws.addEventListener('message',event=>{
    let message;try{message=JSON.parse(event.data);}catch{return;}
    const waiter=pending.get(message.ticket);
    if(waiter){pending.delete(message.ticket);clearTimeout(waiter.timer);message.event==='error'?waiter.reject(new Error(JSON.stringify(message))):waiter.resolve(message);return;}
    if(message.event==='cpu.stepping'){
      const next=waiters.shift();
      if(next){clearTimeout(next.timer);next.resolve(message);}else stops.push(message);
    }
  });
  ws.addEventListener('close',()=>{
    for(const item of pending.values()){clearTimeout(item.timer);item.reject(new Error('debugger closed'));}pending.clear();
    for(const item of waiters.splice(0)){clearTimeout(item.timer);item.reject(new Error('debugger closed'));}
  });
  const rpc=(event,fields={},timeoutMs=10000)=>new Promise((resolve,reject)=>{
    const ticket=`weapon-output-${++serial}`;
    const timer=setTimeout(()=>{pending.delete(ticket);reject(new Error(`timeout: ${event}`));},timeoutMs);
    pending.set(ticket,{resolve,reject,timer});ws.send(JSON.stringify({event,...fields,ticket}));
  });
  const nextStop=timeout=>stops.length?Promise.resolve(stops.shift()):new Promise((resolve,reject)=>{
    const waiter={resolve,reject,timer:setTimeout(()=>{const i=waiters.indexOf(waiter);if(i>=0)waiters.splice(i,1);reject(new Error('wait interval elapsed'));},timeout)};waiters.push(waiter);
  });
  const resume=()=>{ws.send(JSON.stringify({event:'cpu.resume'}));ownStop=false;};
  const read=async(address,size,replacements=true)=>{
    if(!pointer(address,size)||size>0x20000)throw new Error(`invalid guest read ${address.toString(16)} / ${size}`);
    const result=await rpc('memory.read',{address,size,replacements});const bytes=Buffer.from(result.base64||'','base64');
    if(bytes.length!==size)throw new Error('short guest read');return bytes;
  };
  const save=(name,bytes)=>{const file=path.resolve(out,name);fs.writeFileSync(file,bytes);return{file,bytes:bytes.length,sha256:sha(bytes)};};
  const matrix=(name,bytes)=>({...save(name,bytes),words:words(bytes),f32:floats(bytes),layout:'column-major 4x4; translation indices 12,13,14'});
  const input=async buttons=>{await rpc('input.buttons.send',{buttons});inputs.push({buttons,acknowledged:true});};
  const flush=()=>fs.writeFileSync(reportFile,JSON.stringify({schema:'weapon-marker-helper-output-capture/v1',entryPC:ENTRY,returnPC:RETURN,version,
    module:{file:modulePath,sha256:sha(moduleBytes)},expectedGeometrySHA256:GEOMETRY_SHA,
    bounds:{maxStops,maxRows,durationMs,returnTimeoutMs},helperStopCount,returnStopCount,firstStopTicks,lastStopTicks,firstHelperTicks,lastHelperTicks,
    observedHelperScope:'Entry hits only while entry BP is armed; helper calls while waiting for return are not enumerated.',
    indexCounts:indices,rejections:rejects,foreignReturns,inputs,initialBreakpoints,transitions,ownedBP,gprCategoryDiagnostics,
    codeIdentity:{verified:codeChecks.length>=2&&codeChecks.every(c=>c.verified),checks:codeChecks},
    inFlight,rows,cleanup,failure,semanticName:null,
    limits:['Output is captured before the wrapper copies it to its external destination; the original entry output pointer is used.',
      'Only verified source1 calls returning through 0x08b3e62c are paired.',
      'Comparisons are JS f64 matrix products against original F32 results; they do not certify VFPU rounding identity.',
      'Actual helper output and its consumers do not by themselves name a muzzle/FX socket.']},null,2));
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
    return{actor,sourceBase,metadata,table,header,packet,geometry};
  };
  try{
    await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('debugger open timeout')),10000);
      ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});ws.addEventListener('error',e=>{clearTimeout(timer);reject(e);},{once:true});});
    version=await rpc('version',{name:'weapon-marker-helper-output',version:'1'});
    const existing=await rpc('cpu.breakpoint.list');
    if(!Array.isArray(existing.breakpoints))throw new Error('missing breakpoint ownership inventory');
    initialBreakpoints.push(...existing.breakpoints);
    if(existing.breakpoints.some(bp=>bp.enabled||bp.address===ENTRY||bp.address===RETURN))throw new Error('existing active/conflicting CPU breakpoint; left unchanged');
    // Full function bodies, including the helper epilogue and wrapper return.
    await codeIdentity('helper_full',ENTRY,0x210);
    await codeIdentity('wrapper_full',0x08b3e610,0x12c);
    await input(release);if(analog)await rpc('input.analog.send',{...analog,x:0,y:0});
    stops.length=0;resume(); // Startup before arming; never flush an armed BP queue.
    await addBP(ENTRY);
    await input({...release,...held});if(analog)await rpc('input.analog.send',analog);
    const deadline=Date.now()+durationMs;
    while(!interrupted){
      if(!inFlight&&(Date.now()>=deadline||helperStopCount>=maxStops||rows.length>=maxRows))break;
      const stopDeadline=inFlight?inFlight.returnDeadline:deadline;
      if(Date.now()>=stopDeadline){if(inFlight)throw new Error('selected helper return timeout');break;}
      let stop;try{stop=await nextStop(Math.min(1000,Math.max(1,stopDeadline-Date.now())));}catch(e){if(e.message==='wait interval elapsed')continue;throw e;}
      const expectedPC=inFlight?RETURN:ENTRY;
      if(stop.pc!==expectedPC){ownStop=false;throw new Error(`unexpected external CPU stop ${stop.pc}; left paused`);}
      ownStop=true;
      if(!Number.isSafeInteger(stop.ticks)||(lastStopTicks!==null&&stop.ticks<lastStopTicks))throw new Error('invalid/nonmonotonic stop ticks');
      if(firstStopTicks===null)firstStopTicks=stop.ticks;lastStopTicks=stop.ticks;
      const g=await regs();
      if(!inFlight){
        helperStopCount++;if(firstHelperTicks===null)firstHelperTicks=stop.ticks;lastHelperTicks=stop.ticks;
        const output=g[4],actor=g[5],index=g[6],sp=g[29],ra=g[31];indices[index]=(indices[index]||0)+1;
        if(index!==1){resume();continue;}
        if(ra!==RETURN){reject('source1 has another caller');resume();continue;}
        if(!pointer(sp,0x240)||!pointer(output,64)||output!==sp+0x40){reject('wrapper output/SP contract differs');resume();continue;}
        const id=await identity(actor);if(!id){reject('not exact three-bone original weapon');resume();continue;}
        const sample=String(rows.length).padStart(4,'0');
        const preSourcesAll=await read(id.sourceBase,3*0x130),preSource=preSourcesAll.subarray(0x130,2*0x130),
          preWorld=await read(actor+0x220,64),stack=await read(sp,0x240);
        inFlight={sample:rows.length,entryTicks:stop.ticks,entryPC:ENTRY,output,actor,index,sp,ra,entryGPR:g,
          metadata:id.metadata,drawTable:id.table,sourceBase:id.sourceBase,geometrySHA256:GEOMETRY_SHA,
          geometry:save(`geometry_${sample}.bin`,id.geometry),metadataHeader:words(id.header),drawHeader:words(id.packet),
          preSourcesAll:save(`sources_all_pre_${sample}.bin`,preSourcesAll),
          preSource:save(`source_pre_${sample}.bin`,preSource),preSource40:matrix(`source40_pre_${sample}.bin`,preSource.subarray(0x40,0x80)),
          preWorld:matrix(`world_pre_${sample}.bin`,preWorld),entryStack:save(`entry_stack_${sample}.bin`,stack),
          returnDeadline:Date.now()+returnTimeoutMs,semanticName:null};flush();
        await removeBP();
        await codeIdentity(`return_${sample}`,RETURN,16);
        await addBP(RETURN);resume();
      }else{
        returnStopCount++;
        // Another thread may reach this shared return PC. Never pair its output.
        if(g[29]!==inFlight.sp){reject('foreign return stack');if(foreignReturns.length<32)foreignReturns.push({ticks:stop.ticks,sp:g[29],ra:g[31]});resume();continue;}
        if(g[31]!==inFlight.ra||[16,17,18].some(i=>g[i]!==inFlight.entryGPR[i]))throw new Error('same-SP return RA/callee-saved register mismatch');
        const id=await identity(inFlight.actor);
        if(!id||id.metadata!==inFlight.metadata||id.table!==inFlight.drawTable)throw new Error('weapon identity changed during selected helper');
        const sample=String(inFlight.sample).padStart(4,'0');
        const actual=await read(inFlight.output,64),postSourcesAllBytes=await read(id.sourceBase,3*0x130),
          postSource=postSourcesAllBytes.subarray(0x130,2*0x130),postWorld=await read(inFlight.actor+0x220,64);
        const actualOutput=matrix(`actual_output_${sample}.bin`,actual),postSourceRecord=save(`source_post_${sample}.bin`,postSource),
          postSource40=matrix(`source40_post_${sample}.bin`,postSource.subarray(0x40,0x80)),postWorldMatrix=matrix(`world_post_${sample}.bin`,postWorld),
          postSourcesAll=save(`sources_all_post_${sample}.bin`,postSourcesAllBytes);
        // Preserve the raw result even if a numeric validation below fails.
        inFlight.returnAttempt={ticks:stop.ticks,gpr:g,actualOutput,postSourcesAll,postSource:postSourceRecord,postSource40,postWorld:postWorldMatrix};flush();
        const af=floats(actual),sf=floats(postSource.subarray(0x40,0x80)),wf=floats(postWorld);
        if([...af,...sf,...wf].some(v=>!Number.isFinite(v)))throw new Error('nonfinite output/source/WORLD matrix');
        const complete={...inFlight,returnTicks:stop.ticks,returnPC:RETURN,returnGPR:g,returnSPVerified:true,returnRAVerified:true,
          postSourceBase:id.sourceBase,sourceBaseChangedDuringCall:id.sourceBase!==inFlight.sourceBase,
          actualOutput,postSourcesAll,postSource:postSourceRecord,postSource40,postWorld:postWorldMatrix,
          comparison:{world_times_source40:errorAgainst(af,product(wf,sf)),source40_times_world:errorAgainst(af,product(sf,wf))},semanticName:null};
        delete complete.returnDeadline;delete complete.returnAttempt;rows.push(complete);inFlight=null;flush();
        await removeBP();
        if(rows.length>=maxRows||helperStopCount>=maxStops||Date.now()>=deadline)break;
        await addBP(ENTRY);resume();
      }
    }
    if(inFlight)throw new Error(interrupted?'interrupted during selected helper':'selected helper incomplete');
  }catch(e){failure=String(e.stack||e);}
  finally{
    for(const action of [async()=>{await input(release);cleanup.buttonsReleased=true;},async()=>{if(analog){await rpc('input.analog.send',{...analog,x:0,y:0});cleanup.analogReleased=true;}},
      async()=>{await removeBP();cleanup.ownedBreakpointRemoved=true;},async()=>{if(ownStop){resume();cleanup.resumedOwnStop=true;}}]){
      try{if(ws.readyState===WebSocket.OPEN)await action();else cleanup.errors.push('debugger disconnected before cleanup');}catch(e){cleanup.errors.push(String(e));}
    }
    flush();ws.close();
  }
  console.log(JSON.stringify({out,helperStopCount,returnStopCount,rows:rows.length,rejections:rejects,cleanup,failure}));
  if(failure||cleanup.errors.length)process.exitCode=1;
}
main().catch(e=>{console.error(e.stack||e);process.exitCode=1;});
