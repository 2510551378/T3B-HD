// Capture complete source passes plus visual/input evidence. No save writes.
// cpu.resume is a notification. input.buttons.send({}) does not release keys.
const fs = require('fs');
const path = require('path');
const port = Number(process.env.PPSSPP_DEBUGGER_PORT || 9900);
const wanted = Number(process.env.BONE_PAIR_FRAMES || 12);
const out = process.env.BONE_PAIR_DIR;
const held = JSON.parse(process.env.BONE_PAIR_BUTTONS_JSON || '{}');
const analog = process.env.BONE_PAIR_ANALOG_JSON ? JSON.parse(process.env.BONE_PAIR_ANALOG_JSON) : null;
const preRollFrames=Number(process.env.BONE_PREROLL_FRAMES||0);
const preRollAnalog=process.env.BONE_PREROLL_ANALOG?JSON.parse(process.env.BONE_PREROLL_ANALOG):null;
if(!Number.isInteger(preRollFrames)||preRollFrames<0||preRollFrames>240||(preRollFrames&&!preRollAnalog))throw new Error('invalid pre-roll configuration');
const bindingPath=process.env.BONE_WORLD_BINDING;
const binding=bindingPath?JSON.parse(fs.readFileSync(bindingPath,'utf8')):null;
if(binding&&!binding.passed)throw new Error('WORLD binding is not verified');
const bindingIdentity=binding?{file:bindingPath,sha256:require('crypto').createHash('sha256').update(fs.readFileSync(bindingPath)).digest('hex')}:null;
const dense = process.env.BONE_SOURCE_DENSE === '1'||!!binding;
const target = binding?binding.caller:0x08b5251c;
const condition = binding?'a0 == 2':'a3 == 0x2b';
const release = {rtrigger:false,ltrigger:false,square:false,triangle:false,circle:false,cross:false};
if (!out || !Number.isInteger(wanted) || wanted < 1 || wanted > 240) throw new Error('invalid capture arguments');
fs.mkdirSync(out, {recursive:true});

async function main() {
  const ws = new WebSocket(`ws://127.0.0.1:${port}/debugger`, 'debugger.ppsspp.org');
  const pending = new Map(), stops = [], waiters = [];
  let serial = 0, breakpoint = false, version;
  const frames = [], inputEvents = [], worldGEDumps=[],preRollStates=[];
  let preRollRemaining=preRollFrames;
  let liveWorldDump=null,worldDumpError=null;
  ws.addEventListener('message', e => {
    let message; try {message = JSON.parse(e.data);} catch {return;}
    const request = pending.get(message.ticket);
    if (request) {pending.delete(message.ticket);clearTimeout(request.timer);message.event==='error'?request.reject(new Error(JSON.stringify(message))):request.resolve(message);return;}
    if (message.event === 'cpu.stepping') {
      const waiter = waiters.shift();
      if (waiter) {clearTimeout(waiter.timer);waiter.resolve(message);} else stops.push(message);
    }
  });
  ws.addEventListener('close', () => {
    for (const request of pending.values()) {clearTimeout(request.timer);request.reject(new Error('debugger closed'));} pending.clear();
    for (const waiter of waiters.splice(0)) {clearTimeout(waiter.timer);waiter.reject(new Error('debugger closed'));}
  });
  const rpc = (event, fields = {}, timeout = 30000) => new Promise((resolve,reject) => {
    const ticket = `verified-action-${++serial}`;
    const timer = setTimeout(() => {pending.delete(ticket);reject(new Error(`timeout: ${event}`));},timeout);
    pending.set(ticket,{resolve,reject,timer});ws.send(JSON.stringify({event,...fields,ticket}));
  });
  const resume = () => ws.send(JSON.stringify({event:'cpu.resume'}));
  const stop = () => stops.length ? Promise.resolve(stops.shift()) : new Promise((resolve,reject) => {
    const waiter = {resolve,reject,timer:setTimeout(() => {const i=waiters.indexOf(waiter);if(i>=0)waiters.splice(i,1);reject(new Error('no bone-43 stop'));},30000)};waiters.push(waiter);
  });
  const u32 = async address => {const response=await rpc('memory.read_u32',{address});const value=response.uintValue??response.value;if(!Number.isInteger(value))throw new Error(`invalid read ${address.toString(16)}`);return value>>>0;};
  const words = (address,count) => Promise.all(Array.from({length:count},(_,i)=>u32(address+i*4)));
  const buttons = async (values, ticks) => {const response=await rpc('input.buttons.send',{buttons:values});inputEvents.push({ticks,buttons:values,acknowledged:response.event==='input.buttons.send'});};
  const addBreakpoint = async () => {await rpc('cpu.breakpoint.add',{address:target,condition,enabled:true,log:false});breakpoint=true;};
  const removeBreakpoint = async () => {if(breakpoint){await rpc('cpu.breakpoint.remove',{address:target});breakpoint=false;}};
  const image = async name => {
    const errors=[];
    for(const event of ['gpu.buffer.renderColor','gpu.buffer.screenshot']){
      try {
        const response=await rpc(event,{type:'uri'});
        if(!response.uri?.startsWith('data:image/png;base64,'))throw new Error('no PNG data URI');
        const file=path.join(out,name);fs.writeFileSync(file,Buffer.from(response.uri.split(',')[1],'base64'));
        return {file,event,width:response.width,height:response.height};
      } catch(error) {errors.push(String(error));}
    }
    return {errors};
  };
  const manifest = () => ({schema:'aya-bone-ge-pairs/v2',target,condition,version,buttons:held,analog,denseSource:dense,worldSourceBinding:bindingIdentity,
    preRoll:{requestedFrames:preRollFrames,completedFrames:preRollFrames-preRollRemaining,analog:preRollAnalog,states:preRollStates},
    captureMethod:binding?'44 source records and body/weapon WORLD at geometry-verified weapon upload callsite; asynchronous GE dumps require exact alignment':dense?'all 44 source records read atomically at completed bone43; first/last GE dump only; tick gaps must be checked':'all 44 source payloads at completed bone43; GE dump after resume; frame atomicity must be checked',
    inputEvents,frames,unassignedWorldGEDumps:worldGEDumps});
  try {
    await new Promise((resolve,reject) => {ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
    version=await rpc('version',{name:'aya-verified-action',version:'1'});
    await buttons(release,null);
    if(analog)await rpc('input.analog.send',{stick:analog.stick,x:0,y:0});
    await addBreakpoint();
    if(binding)resume();
    let first=true;
    for(let guard=0;(frames.length<wanted||(binding&&liveWorldDump))&&guard<wanted*128+512;guard++) {
      const stepping=await stop();
      if(stepping.pc!==target){resume();continue;}
      const response=await rpc('cpu.getAllRegs');
      const g=response.categories?.[0]?.uintValues;
      if(!g||g.length<32)throw new Error('no CPU GPRs');
      let weaponIdentity=null;
      if(binding){
        // JAL delay slot at caller+4 moves s7 into a1; it has not executed.
        if(g[4]!==2||g[23]!==g[17]+binding.object_matrix_offset)throw new Error('weapon WORLD callsite contract changed');
        const weaponMetadata=await u32(g[17]+0x3e8),table=await u32(weaponMetadata+0x34);
        if(((await u32(table))&0xffff)!==1){resume();continue;}
        const h=await rpc('memory.read',{address:table+4,size:12}),header=Buffer.from(h.base64||'','base64');
        if(header.length!==12)throw new Error('incomplete weapon packet header');
        const count=header.readUInt16LE(0),vtype=header.readUInt32LE(8),updates=header[5],stride=header[6]*2;
        if(count!==243||vtype!==0x522){resume();continue;}
        const r=await rpc('memory.read',{address:table+16+updates*4,size:count*stride}),raw=Buffer.from(r.base64||'','base64');
        if(raw.length!==count*stride)throw new Error('incomplete weapon geometry');
        const prefix=Buffer.alloc(4);prefix.writeUInt32LE(vtype);const hash=require('crypto').createHash('sha256').update(prefix).update(raw).digest('hex');
        if(hash!==binding.weapon_geometry_sha256){resume();continue;}
        const palette=updates?Buffer.from((await rpc('memory.read',{address:table+16,size:updates*4})).base64||'','base64'):null;
        let sourceIndex=null;if(palette)for(let i=0;i<updates;i++)if(palette.readInt16LE(i*4)===0)sourceIndex=palette.readInt16LE(i*4+2);
        weaponIdentity={object:g[17],metadata:weaponMetadata,drawTable:table,drawTableBytes:(16+updates*4+count*stride+3)&~3,geometry_sha256:hash,boneCount:(await u32(weaponMetadata+4))>>>16,sourceIndex};
      }
      const object=binding?binding.aya_object:g[4]>>>0,index=g[7]>>>0;
      const metadata=await u32(object+0x3e8);
      const count=(await u32(metadata+4))>>>16;
      if(count!==44||(!binding&&index!==43)){resume();continue;}
      const drawTable=await u32(metadata+0x34);
      if(((await u32(drawTable))&0xffff)!==106){resume();continue;}
      if(first){
        const baseline=await image('baseline.png');
        fs.writeFileSync(path.join(out,'baseline.json'),JSON.stringify({ticks:stepping.ticks,object,metadata,baseline},null,2));
        await buttons({...release,...held,...(preRollFrames?{square:false}:{})},stepping.ticks);
        if(preRollFrames)await rpc('input.analog.send',preRollAnalog);else if(analog)await rpc('input.analog.send',analog);
        first=false;resume();continue;
      }
      if(preRollRemaining>0){
        const r=await rpc('memory.read',{address:object+0x220,size:64}),raw=Buffer.from(r.base64||'','base64');
        preRollStates.push({ticks:stepping.ticks,bodyWorldWords:Array.from({length:16},(_,i)=>raw.readUInt32LE(i*4))});
        preRollRemaining--;
        if(!preRollRemaining){await buttons({...release,...held},stepping.ticks);await rpc('input.analog.send',analog||{stick:preRollAnalog.stick,x:0,y:0});}
        resume();continue;
      }
      const sourceBase=await u32(object+0x3c4),records=[];
      let worldSource=null;
      if(binding){
        const readWorld=async address=>{const r=await rpc('memory.read',{address,size:64});const b=Buffer.from(r.base64||'','base64');if(b.length!==64)throw new Error('incomplete WORLD source');return Array.from({length:16},(_,i)=>b.readUInt32LE(i*4));};
        const bodyWords=await readWorld(object+0x220),weaponWords=await readWorld(g[23]);
        const selected=[0,1,2,4,5,6,8,9,10,12,13,14],pack=words=>selected.map(i=>(words[i]>>>8)&0xffffff);
        worldSource={uploader:binding.world_uploader,caller:binding.caller,weaponObject:g[17],weaponMatrixPointer:g[23],weaponIdentity,
          bodyWords,weaponWords,bodyPayload:pack(bodyWords),weaponPayload:pack(weaponWords),
          matrixInputContract:'column-major F32 4x4; WORLD writes high24 of column xyz; wrapper type2'};
        if(weaponIdentity.sourceIndex!==null&&weaponIdentity.sourceIndex>=0&&weaponIdentity.sourceIndex<weaponIdentity.boneCount){
          const weaponSourceBase=await u32(g[17]+0x3c4),address=weaponSourceBase+weaponIdentity.sourceIndex*0x130;
          const r=await rpc('memory.read',{address,size:0x130}),raw=Buffer.from(r.base64||'','base64');if(raw.length!==0x130)throw new Error('incomplete weapon source bone');
          const file=path.join(out,`weapon_source_${String(frames.length).padStart(4,'0')}.bin`);fs.writeFileSync(file,raw);
          worldSource.weaponBoneSource={base:weaponSourceBase,address,index:weaponIdentity.sourceIndex,file,bytes:raw.length,payload:Array.from({length:12},(_,i)=>raw.readUInt32LE(0xc0+i*4)&0xffffff)};
          if(weaponIdentity.boneCount<=64){
            const r=await rpc('memory.read',{address:weaponSourceBase,size:weaponIdentity.boneCount*0x130}),all=Buffer.from(r.base64||'','base64');
            if(all.length!==weaponIdentity.boneCount*0x130||!all.subarray(weaponIdentity.sourceIndex*0x130,(weaponIdentity.sourceIndex+1)*0x130).equals(raw))throw new Error('weapon full/scalar bone mismatch');
            const file=path.join(out,`weapon_skeleton_${String(frames.length).padStart(4,'0')}.bin`);fs.writeFileSync(file,all);
            worldSource.weaponSkeletonSource={base:weaponSourceBase,file,bytes:all.length,boneCount:weaponIdentity.boneCount};
            if(!frames.length){
              const getWords=async(address,size)=>{const r=await rpc('memory.read',{address,size}),b=Buffer.from(r.base64||'','base64');if(b.length!==size)throw new Error('incomplete weapon metadata');return Array.from({length:size/4},(_,i)=>b.readUInt32LE(i*4));};
              const header=await getWords(weaponIdentity.metadata,64),descriptors=header[6];
              fs.writeFileSync(path.join(out,'weapon_metadata_snapshot.json'),JSON.stringify({schema:'original-actor-metadata-snapshot/v1',target,capturePoint:'weapon WORLD upload callsite',object:g[17],ticks:stepping.ticks,metadata:weaponIdentity.metadata,sourceBase:weaponSourceBase,boneCount:weaponIdentity.boneCount,header,descriptors,descriptorWords:await getWords(descriptors,weaponIdentity.boneCount*16),drawTable:weaponIdentity.drawTable,drawWords:await getWords(weaponIdentity.drawTable,weaponIdentity.drawTableBytes),records:Array.from({length:weaponIdentity.boneCount},(_,index)=>({index,words:Array.from({length:0x130/4},(_,i)=>all.readUInt32LE(index*0x130+i*4))}))},null,2));
            }
          }
        }
      }
      let sourceBlock=null;
      if(dense){
        const block=await rpc('memory.read',{address:sourceBase,size:44*0x130});
        const bytes=Buffer.from(block.base64||'','base64');
        if(bytes.length!==44*0x130)throw new Error('incomplete dense source block');
        // Cross-check the bulk API against scalar reads before trusting it.
        if(bytes.readUInt32LE(0xc0)!==await u32(sourceBase+0xc0)||bytes.readUInt32LE(43*0x130+0xec)!==await u32(sourceBase+43*0x130+0xec))throw new Error('bulk/scalar source mismatch');
        for(let index=0;index<44;index++)records.push({index,matrix:Array.from({length:12},(_,i)=>bytes.readUInt32LE(index*0x130+0xc0+i*4))});
        const file=path.join(out,`source_${String(frames.length).padStart(4,'0')}.bin`);fs.writeFileSync(file,bytes);sourceBlock={file,bytes:bytes.length};
      }else for(let start=0;start<44;start+=4){
        const rows=await Promise.all(Array.from({length:Math.min(4,44-start)},async(_,j)=>({index:start+j,matrix:await words(sourceBase+(start+j)*0x130+0xc0,12)})));
        records.push(...rows);
      }
      const frame=frames.length;
      const screenshot=(frame===0||frame===wanted-1||frame===Math.floor(wanted/2))?await image(`frame_${String(frame).padStart(4,'0')}.png`):null;
      let dumpRecord=null;
      if(!binding&&(!dense||frame===0||frame===wanted-1)){
        await removeBreakpoint();resume();
        const dump=await rpc('gpu.record.dump',{},60000);
        if(!dump.uri?.startsWith('data:'))throw new Error('no GE frame dump URI');
        const file=path.join(out,`frame_${String(frame).padStart(4,'0')}.ppdmp`),data=Buffer.from(dump.uri.split(',')[1],'base64');
        fs.writeFileSync(file,data);dumpRecord={file,bytes:data.length};
        if(frames.length+1<wanted)await addBreakpoint();
      }
      frames.push({frame,ticks:stepping.ticks,object,sourceBase,metadata,records,sourceBlock,worldSource,screenshot,dump:dumpRecord});
      if(binding&&(frame===0||frame===wanted-3)){
        if(liveWorldDump)throw new Error('previous asynchronous GE dump still pending');
        const requestedAtSample=frame;
        liveWorldDump=rpc('gpu.record.dump',{},60000).then(d=>{
          if(!d.uri?.startsWith('data:'))throw new Error('no asynchronous GE dump URI');
          const file=path.join(out,`world_ge_${requestedAtSample}.ppdmp`),data=Buffer.from(d.uri.split(',')[1],'base64');fs.writeFileSync(file,data);
          worldGEDumps.push({file,bytes:data.length,requestedAtSample,receivedAfterSamples:frames.length});
        }).catch(e=>{worldDumpError=e;}).finally(()=>{liveWorldDump=null;});
      }
      if(worldDumpError)throw worldDumpError;
      fs.writeFileSync(path.join(out,'manifest_runtime.json'),JSON.stringify(manifest(),null,2));
      console.log(`sample ${frames.length}/${wanted}, ticks=${stepping.ticks}, GE=${dumpRecord?.bytes??'not requested'}`);
      if(dense&&!dumpRecord)resume();
    }
    if(frames.length<wanted||(!binding&&frames.length!==wanted)||worldDumpError)throw worldDumpError||new Error(`incomplete capture ${frames.length}/${wanted}`);
    const holdMs=Number(process.env.BONE_ACTION_HOLD_MS||0);
    if(holdMs>0){
      ws.send(JSON.stringify({event:'cpu.stepping'}));
      const paused=await stop();
      console.log(`INSPECTION_READY pc=${paused.pc} hold=${holdMs}ms`);
      await new Promise(resolve=>setTimeout(resolve,Math.min(60000,holdMs)));
    }
  } finally {
    if(ws.readyState===WebSocket.OPEN){
      await buttons(release,frames.at(-1)?.ticks??null).catch(()=>{});
      if(analog||preRollAnalog)await rpc('input.analog.send',{stick:(analog||preRollAnalog).stick,x:0,y:0}).catch(()=>{});
      await removeBreakpoint().catch(()=>{});resume();ws.close();
    }
    fs.writeFileSync(path.join(out,'manifest_runtime.json'),JSON.stringify(manifest(),null,2));
    for(const p of pending.values())clearTimeout(p.timer);
    for(const w of waiters)clearTimeout(w.timer);
  }
}
main().catch(error=>{console.error(error.stack||error);process.exitCode=1;});
