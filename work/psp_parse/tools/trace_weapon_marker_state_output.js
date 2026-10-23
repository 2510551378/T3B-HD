// Existing PPSSPP debugger only. No process launch, desktop use or savestate IO.
// Exactly one owned BP: entry -> helper return -> generic return -> state return.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const ENTRY = 0x08b44580, RETURN = 0x08b3e62c, BASE = 0x08804000;
const GENERIC_RETURN=0x08b630dc,STATE_RETURNS=[0x08b63550,0x08b6379c],OUTER_RETURNS=[0x08b639c8,0x08b69aec,0x08b69f00];
const BP_TARGETS=new Set([ENTRY,RETURN,GENERIC_RETURN,...STATE_RETURNS]);
const GEOMETRY_SHA = '168578abca4c4f5d22d5994ebced6b93a25d5167428bfd47f1a1150a8d42e65a';
const out = process.env.MARKER_STATE_OUT_DIR || process.env.MARKER_OUTPUT_OUT_DIR || process.env.MARKER_OUT_DIR;
const port = Number(process.env.PPSSPP_DEBUGGER_PORT || 9900);
const maxStops = Number(process.env.MARKER_MAX_STOPS || 1200);
const maxRows = Number(process.env.MARKER_MAX_ROWS || 12);
const durationMs = Number(process.env.MARKER_DURATION_MS || 15000);
const returnTimeoutMs = Number(process.env.MARKER_STAGE_TIMEOUT_MS || process.env.MARKER_RETURN_TIMEOUT_MS || 3000);
const fepProbeEnabled=process.env.MARKER_FEP_PROBE==='1';
if(process.env.MARKER_FEP_PROBE!==undefined&&!['0','1'].includes(process.env.MARKER_FEP_PROBE))throw new Error('MARKER_FEP_PROBE must be 0 or 1');
const held = JSON.parse(process.env.MARKER_BUTTONS_JSON || '{}');
const analog = process.env.MARKER_ANALOG_JSON ? JSON.parse(process.env.MARKER_ANALOG_JSON) : null;
if (!out || !Number.isInteger(port) || port<1 || port>65535 || !Number.isInteger(maxStops) || maxStops<1 || maxStops>20000 || !Number.isInteger(maxRows) || maxRows<1 || maxRows>240 || !Number.isFinite(durationMs) || durationMs<100 || durationMs>120000 || !Number.isFinite(returnTimeoutMs) || returnTimeoutMs<50 || returnTimeoutMs>10000) throw new Error('invalid marker output bounds');
if (!held || typeof held!=='object' || Array.isArray(held) || Object.values(held).some(v=>typeof v!=='boolean')) throw new Error('buttons must be a boolean object');
if (analog && (!Number.isFinite(analog.x) || !Number.isFinite(analog.y) || Math.abs(analog.x)>1 || Math.abs(analog.y)>1)) throw new Error('invalid analog input');
const release=Object.fromEntries([...new Set(['rtrigger','ltrigger','square','triangle','circle','cross',...Object.keys(held)])].map(k=>[k,false]));
const modulePath=path.resolve(__dirname,'../raw/ULJM05798_module_08804000.bin');
const moduleBytes=fs.readFileSync(modulePath);
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
// Capture the producer once at module load, before connecting to the debugger.
const producer={file:path.resolve(__filename),sha256:sha(fs.readFileSync(__filename))};
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
  const reportFile=path.join(out,'marker_state_output.json');
  if(fs.existsSync(reportFile))throw new Error('refusing to overwrite an existing marker_state_output.json');
  const ws=new WebSocket(`ws://127.0.0.1:${port}/debugger`,'debugger.ppsspp.org');
  const pending=new Map(),stops=[],waiters=[];
  let serial=0,ownedBP=null,ownStop=false,interrupted=false,version=null,failure=null,inFlight=null;
  let helperStopCount=0,returnStopCount=0,genericStopCount=0,stateStopCount=0,firstStopTicks=null,lastStopTicks=null,firstHelperTicks=null,lastHelperTicks=null;
  const rows=[],rejects={},indices={},transitions=[],inputs=[],codeChecks=[],foreignReturns=[];
  const gprCategoryDiagnostics=[];
  const cleanup={errors:[]},initialBreakpoints=[];
  const fepProbe={enabled:fepProbeEnabled,attempted:false,status:fepProbeEnabled?'not_attempted':'disabled',windows:[],failure:null,semanticName:null,
    scope:'Explicit opt-in, first selected entry only; fixed windows for the unique ISO 0x56bfc4b0 prefix match, not a generic FEP parser or loaded-source proof.',
    isoEvidence:{sectionAbsoluteOffset:0x56bf7bc0,sectionBytes:0xbe240,recordRelativeOffset:0x48f0,recordPrefix64SHA256:'04afeecb38df20d41a7c24da1686e31cf70a8e631aa51e48321c776ab21d89b6'}};
  const reject=reason=>{rejects[reason]=(rejects[reason]||0)+1;};
  process.on('SIGINT',()=>{interrupted=true;});process.on('SIGTERM',()=>{interrupted=true;});
  ws.addEventListener('message',event=>{
    let message;try{message=JSON.parse(event.data);}catch{return;}
    const waiter=pending.get(message.ticket);
    if(waiter){pending.delete(message.ticket);clearTimeout(waiter.timer);message.event==='error'?waiter.reject(new Error(JSON.stringify(message))):waiter.resolve(message);return;}
    if(message.event==='cpu.stepping'){
      // An owned BP can stop before its add ACK; retain ownership on queued events.
      message.ownedBreakpointAtReceipt=ownedBP;
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
  const flush=()=>fs.writeFileSync(reportFile,JSON.stringify({schema:'weapon-marker-state-output-capture/v1',entryPC:ENTRY,returnPC:RETURN,genericReturnPC:GENERIC_RETURN,stateReturnPCs:STATE_RETURNS,version,
    module:{file:modulePath,sha256:sha(moduleBytes)},producer,expectedGeometrySHA256:GEOMETRY_SHA,
    bounds:{maxStops,maxRows,durationMs,returnTimeoutMs},helperStopCount,returnStopCount,genericStopCount,stateStopCount,firstStopTicks,lastStopTicks,firstHelperTicks,lastHelperTicks,
    observedHelperScope:'Entry hits only while entry BP is armed; helper calls while waiting for return are not enumerated.',
    indexCounts:indices,rejections:rejects,foreignReturns,inputs,initialBreakpoints,transitions,ownedBP,gprCategoryDiagnostics,
    codeIdentity:{verified:codeChecks.length>=6&&codeChecks.every(c=>c.verified),checks:codeChecks},
    inFlight,rows,cleanup,fepProbe,failure,semanticName:null,
    limits:['Helper output, exact generic copy and final state transform are separate stages; final state is not forced equal to helper output.',
      'Only exact weapon source1 calls through the verified wrapper/generic/state caller chain are paired.',
      'Resource data is bounded identity-only bytes; no FX, emitter or muzzle semantics are assigned.',
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
  const stateSnapshot=async(label,P)=>{
    const bytes=await read(P,0x1a4),state=save(`${label}_state.bin`,bytes),state60=matrix(`${label}_state60.bin`,bytes.subarray(0x60,0xa0));
    const address=bytes.readUInt32LE(0x198),resource={fieldAddress:P+0x198,address,requestedBytes:64,semanticName:null};
    if(address===0)resource.status='null';
    else if(!pointer(address,64))resource.status='out_of_range_or_unaligned';
    else{try{resource.bytes=save(`${label}_resource_identity.bin`,await read(address,64));resource.status='read';}catch(e){resource.status='read_error';resource.error=String(e);}}
    return{state,state60,resource,bytes};
  };
  const abi=(condition,message)=>{if(!condition)throw new Error(`state-chain ABI mismatch: ${message}`);};
  const probeFep=async(stateBytes,sample)=>{
    if(!fepProbeEnabled||fepProbe.attempted)return;
    Object.assign(fepProbe,{attempted:true,status:'reading',sample,
      sourceState190:stateBytes.readUInt32LE(0x190),sourceState194:stateBytes.readUInt32LE(0x194),sourceState198:stateBytes.readUInt32LE(0x198)});flush();
    try{
      const base=fepProbe.sourceState190;
      if(!pointer(base,0xbe240))throw new Error('FEP probe state+190 base/declared extent outside guest RAM or unaligned');
      if(fepProbe.sourceState194!==base+0xfb4||fepProbe.sourceState198!==base+0x48f0)throw new Error('FEP probe state190/194/198 does not match this fixed-window source candidate');
      const window=async(name,offset,size)=>{
        const address=base+offset;
        if(!pointer(address,size))throw new Error(`FEP probe invalid window ${name}`);
        const item={name,offset,address,size,status:'reading'};fepProbe.windows.push(item);flush();
        try{const bytes=await read(address,size);Object.assign(item,{status:'read',raw:save(`fep_${name}.bin`,bytes)});flush();return bytes;}
        catch(e){item.status='failed';item.error=String(e);flush();throw e;}
      };
      // No other FEP window is read until the actual state-declared header passes.
      const header=await window('header_tables',0,0x400);
      const check=(name,actual,expected)=>({name,actual,accepted:expected,passed:expected.includes(actual)});
      fepProbe.headerChecks=[check('magic',header.readUInt32LE(0),[0x07504546]),check('version',header.readUInt32LE(4),[0x00090001]),
        check('offset8Pointer',header.readUInt32LE(8),[0x48,base+0x48]),check('sectionBytes',header.readUInt32LE(0x14),[0xbe240]),
        check('table0Count',header.readUInt16LE(0x1c),[93]),check('table1Count',header.readUInt16LE(0x1e),[93]),
        check('table0Pointer',header.readUInt32LE(0x28),[0x50,base+0x50]),check('table1Pointer',header.readUInt32LE(0x2c),[0x1c4,base+0x1c4])];flush();
      if(fepProbe.headerChecks.some(c=>!c.passed))throw new Error('FEP probe header identity/layout gate failed; remaining windows not read');
      await window('type0_descriptor4',0xab8,12);
      await window('pointer_list',0x48e0,16);
      await window('table1_record4',0xfb4,64);
      await window('record',0x48f0,0xc0);
      fepProbe.status='captured';flush();
    }catch(e){fepProbe.status='failed';fepProbe.failure=String(e);flush();throw e;}
  };
  const advance=async(phase,pc)=>{
    await removeBP();
    await codeIdentity(`${phase}_${String(inFlight.sample).padStart(4,'0')}`,pc,16);
    inFlight.phase=phase;inFlight.expectedPC=pc;inFlight.returnDeadline=Date.now()+returnTimeoutMs;flush();
    await addBP(pc);resume();
  };
  try{
    await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('debugger open timeout')),10000);
      ws.addEventListener('open',()=>{clearTimeout(timer);resolve();},{once:true});ws.addEventListener('error',e=>{clearTimeout(timer);reject(e);},{once:true});});
    version=await rpc('version',{name:'weapon-marker-state-output',version:'1'});
    const existing=await rpc('cpu.breakpoint.list');
    if(!Array.isArray(existing.breakpoints))throw new Error('missing breakpoint ownership inventory');
    initialBreakpoints.push(...existing.breakpoints);
    if(existing.breakpoints.some(bp=>bp.enabled||BP_TARGETS.has(bp.address)))throw new Error('existing active/conflicting CPU breakpoint; left unchanged');
    // Full function bodies, including the helper epilogue and wrapper return.
    await codeIdentity('helper_full',ENTRY,0x210);
    await codeIdentity('wrapper_full',0x08b3e610,0x12c);
    await codeIdentity('generic_full',0x08bbc93c,0x43c);
    await codeIdentity('state_full',0x08b62e98,0x654);
    await codeIdentity('parent_full',0x08b634ec,0x438);
    await codeIdentity('copy64_full',0x08bfd23c,0x44);
    await input(release);if(analog)await rpc('input.analog.send',{...analog,x:0,y:0});
    stops.length=0;resume(); // Startup before arming; never flush an armed BP queue.
    await addBP(ENTRY);
    await input({...release,...held});if(analog)await rpc('input.analog.send',analog);
    const deadline=Date.now()+durationMs;
    while(!interrupted){
      if(!inFlight&&(Date.now()>=deadline||helperStopCount>=maxStops||rows.length>=maxRows))break;
      const stopDeadline=inFlight?inFlight.returnDeadline:deadline;
      if(Date.now()>=stopDeadline){if(inFlight)throw new Error(`selected ${inFlight.phase} timeout`);break;}
      let stop;try{stop=await nextStop(Math.min(1000,Math.max(1,stopDeadline-Date.now())));}catch(e){if(e.message==='wait interval elapsed')continue;throw e;}
      const expectedPC=inFlight?inFlight.expectedPC:ENTRY;
      if(stop.pc!==expectedPC){ownStop=false;throw new Error(`unexpected external CPU stop ${stop.pc}; left paused`);}
      ownStop=true;
      if(!Number.isSafeInteger(stop.ticks)||(lastStopTicks!==null&&stop.ticks<lastStopTicks))throw new Error('invalid/nonmonotonic stop ticks');
      if(firstStopTicks===null)firstStopTicks=stop.ticks;lastStopTicks=stop.ticks;
      const g=await regs();
      if(!inFlight){
        helperStopCount++;if(firstHelperTicks===null)firstHelperTicks=stop.ticks;lastHelperTicks=stop.ticks;
        const output=g[4],actor=g[5],index=g[6],sp=g[29],ra=g[31];indices[index]=(indices[index]||0)+1;
        if(index!==1){resume();continue;}
        const id=await identity(actor);if(!id){reject('not exact three-bone original weapon');resume();continue;}
        abi(ra===RETURN,'unknown exact-weapon wrapper caller');
        abi(pointer(sp,0x3ac)&&pointer(output,64)&&output===sp+0x40,'wrapper output/SP relation');
        const sample=String(rows.length).padStart(4,'0');
        const preSourcesAll=await read(id.sourceBase,3*0x130),preSource=preSourcesAll.subarray(0x130,2*0x130),
          preWorld=await read(actor+0x220,64),stack=await read(sp,0x3ac);
        const at=offset=>stack.readUInt32LE(offset),P=at(0x200),stateRA=at(0x360),outerRA=at(0x3a8),savedFlags=at(0x338);
        abi(at(0x84)===0x08bbccd0&&at(0x20c)===GENERIC_RETURN,'unknown wrapper/generic chain');
        abi(STATE_RETURNS.includes(stateRA)&&OUTER_RETURNS.includes(outerRA),'unknown state/outer caller');
        abi(pointer(P,0x1a4)&&g[20]===P+0x10&&g[21]===P+0x90,'P stack/s4/s5 cross-check');
        abi(at(0x1fc)===P+0x60&&at(0x33c)===P,'saved state output/parent state');
        abi(at(0x80)===sp+0x210&&g[16]===sp+0x1b0&&g[17]===1,'wrapper external/generic outputs');
        abi(pointer(g[18])&&g[22]===g[18]&&(await read(g[18],4)).readUInt32LE(0)===actor,'primary handle->drawable');
        // 08b62ee0 is SRA fp,t3,16, retaining sign-extension in the u32 GPR.
        abi(g[30]===((savedFlags>>16)>>>0)&&g[23]===(g[30]&0x40)&&g[23]===0,'saved high flags and selected generic branch');
        const statePre=await stateSnapshot(`entry_${sample}`,P);
        abi(statePre.bytes.readUInt32LE(0x144)===g[18]&&statePre.bytes.readUInt32LE(0x148)===0&&statePre.bytes.readInt16LE(0x14c)===1,'state primary/secondary handle and selector');
        abi(statePre.bytes.readUInt32LE(0x154)===savedFlags,'state+154 and saved flags');
        inFlight={sample:rows.length,entryTicks:stop.ticks,entryPC:ENTRY,output,actor,index,sp,ra,entryGPR:g,H:sp,P,statePointer:P,stateRA,outerRA,
          flags:{savedWord:savedFlags,liveState154:statePre.bytes.readUInt32LE(0x154),highWord:g[30]},
          savedRA:{wrapper:{stackOffset:0x84,address:at(0x84)},generic:{stackOffset:0x20c,address:at(0x20c)},state:{stackOffset:0x360,address:stateRA},outer:{stackOffset:0x3a8,address:outerRA}},
          frames:{wrapperSP:sp,genericSP:sp+0x90,stateSP:sp+0x210,parentSP:sp+0x370},
          metadata:id.metadata,drawTable:id.table,sourceBase:id.sourceBase,geometrySHA256:GEOMETRY_SHA,
          geometry:save(`geometry_${sample}.bin`,id.geometry),metadataHeader:words(id.header),drawHeader:words(id.packet),
          preSourcesAll:save(`sources_all_pre_${sample}.bin`,preSourcesAll),
          preSource:save(`source_pre_${sample}.bin`,preSource),preSource40:matrix(`source40_pre_${sample}.bin`,preSource.subarray(0x40,0x80)),
          preWorld:matrix(`world_pre_${sample}.bin`,preWorld),entryStack:save(`entry_stack_${sample}.bin`,stack),
          entryState:statePre.state,stateBefore:statePre.state60,resourceIdentity:{entry:statePre.resource},
          helperOutputBefore:matrix(`helper_output_before_${sample}.bin`,stack.subarray(0x40,0x80)),
          wrapperExternalBefore:matrix(`wrapper_external_before_${sample}.bin`,stack.subarray(0x1b0,0x1f0)),
          genericOutputBefore:matrix(`generic_before_${sample}.bin`,stack.subarray(0x210,0x250)),semanticName:null};flush();
        await probeFep(statePre.bytes,rows.length);
        await advance('helper_return',RETURN);
      }else if(inFlight.phase==='helper_return'){
        returnStopCount++;
        abi(g[29]===inFlight.H&&g[31]===inFlight.ra&&[16,17,18,19,20,21,22,23,30].every(i=>g[i]===inFlight.entryGPR[i]),'helper return SP/RA/saved registers');
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
        const helperState=await stateSnapshot(`helper_return_${sample}`,inFlight.P);
        Object.assign(inFlight,{returnTicks:stop.ticks,returnPC:RETURN,returnGPR:g,returnSPVerified:true,returnRAVerified:true,
          postSourceBase:id.sourceBase,sourceBaseChangedDuringCall:id.sourceBase!==inFlight.sourceBase,
          actualOutput,postSourcesAll,postSource:postSourceRecord,postSource40,postWorld:postWorldMatrix,
          comparison:{world_times_source40:errorAgainst(af,product(wf,sf)),source40_times_world:errorAgainst(af,product(sf,wf))},stateAfterHelper:helperState.state});
        inFlight.resourceIdentity.helperReturn=helperState.resource;delete inFlight.returnAttempt;flush();
        await advance('generic_return',GENERIC_RETURN);
      }else if(inFlight.phase==='generic_return'){
        genericStopCount++;
        const H=inFlight.H,P=inFlight.P;
        abi(g[29]===H+0x210&&g[31]===GENERIC_RETURN,'generic return SP/RA');
        abi(g[16]===P+0x60&&g[17]===P&&g[18]===H+0x250&&g[20]===P+0x10&&g[21]===P+0x90&&g[22]===inFlight.entryGPR[22]&&g[23]===inFlight.entryGPR[23]&&g[30]===inFlight.entryGPR[30],'generic return restored state registers');
        const entryStack=fs.readFileSync(inFlight.entryStack.file);
        for(const [reg,offset] of [[16,0x1fc],[17,0x200],[18,0x204],[19,0x208]])abi(g[reg]===entryStack.readUInt32LE(offset),`generic return restored register ${reg}`);
        const sample=String(inFlight.sample).padStart(4,'0'),context=await read(H+0x210,0x160);
        inFlight.genericContext=save(`generic_context_${sample}.bin`,context);
        inFlight.genericOutput=matrix(`generic_output_${sample}.bin`,context.subarray(0,64));
        const actual=fs.readFileSync(inFlight.actualOutput.file),equal=context.subarray(0,64).equals(actual);
        inFlight.genericReturn={pc:GENERIC_RETURN,ticks:stop.ticks,sp:g[29],ra:g[31],gpr:g,helperOutputByteEqual:equal};flush();
        abi(equal,'generic C output differs from helper64 bytes');
        abi(context.readUInt32LE(0x128)===inFlight.flags.savedWord,'generic context saved flags changed');
        const genericState=await stateSnapshot(`generic_return_${sample}`,P);
        inFlight.stateAfterGeneric=genericState.state;inFlight.resourceIdentity.genericReturn=genericState.resource;flush();
        await advance('state_return',inFlight.stateRA);
      }else if(inFlight.phase==='state_return'){
        stateStopCount++;
        const H=inFlight.H,stack=fs.readFileSync(inFlight.entryStack.file),P=inFlight.P;
        abi(g[29]===H+0x370&&g[31]===inFlight.stateRA,'state return SP/RA');
        for(const [reg,offset] of [[16,0x33c],[17,0x340],[18,0x344],[19,0x348],[20,0x34c],[21,0x350],[22,0x354],[23,0x358],[30,0x35c]])abi(g[reg]===stack.readUInt32LE(offset),`state return restored register ${reg}`);
        abi(g[16]===P,'state return parent s0=P');
        const sample=String(inFlight.sample).padStart(4,'0'),finalState=await stateSnapshot(`state_return_${sample}`,P);
        inFlight.stateAfterReturn=finalState.state;inFlight.stateFinal=finalState.state60;inFlight.resourceIdentity.stateReturn=finalState.resource;
        inFlight.stateReturn={pc:inFlight.stateRA,ticks:stop.ticks,sp:g[29],ra:g[31],gpr:g};
        const complete={...inFlight};delete complete.phase;delete complete.expectedPC;delete complete.returnDeadline;rows.push(complete);inFlight=null;flush();
        await removeBP();
        if(rows.length>=maxRows||helperStopCount>=maxStops||Date.now()>=deadline)break;
        await addBP(ENTRY);resume();
      }else throw new Error('unknown in-flight stage');
    }
    if(inFlight)throw new Error(interrupted?'interrupted during selected helper':'selected helper incomplete');
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
  console.log(JSON.stringify({out,helperStopCount,returnStopCount,genericStopCount,stateStopCount,rows:rows.length,rejections:rejects,cleanup,failure}));
  if(failure||cleanup.errors.length)process.exitCode=1;
}
main().catch(e=>{console.error(e.stack||e);process.exitCode=1;});
