// Attribute original WORLD uploads to their runtime input matrices. Read-only.
const fs=require('fs'),path=require('path');
const out=process.env.BONE_PAIR_DIR,port=Number(process.env.PPSSPP_DEBUGGER_PORT||9900);
const wanted=Number(process.env.BONE_PAIR_FRAMES||8),held=JSON.parse(process.env.BONE_PAIR_BUTTONS_JSON||'{}');
if(!out||!Number.isInteger(wanted)||wanted<3||wanted>240)throw new Error('invalid capture arguments');
fs.mkdirSync(out,{recursive:true});
const BONE=0x08b5251c,WORLD=0x08c01088,CACHE=0x08b51c80;
const release={rtrigger:false,ltrigger:false,square:false,triangle:false,circle:false,cross:false};
async function main(){
 const ws=new WebSocket(`ws://127.0.0.1:${port}/debugger`,'debugger.ppsspp.org');
 const pending=new Map(),queue=[],waiters=[],installed=new Set();let serial=0;
 const samples=[],worlds=[],dumps=[],inputs=[];let version,ready=false,dumpPending=null,dumpError=null,dumpDone=false;
 ws.addEventListener('message',e=>{let m;try{m=JSON.parse(e.data);}catch{return;}
  const p=pending.get(m.ticket);if(p){pending.delete(m.ticket);clearTimeout(p.timer);m.event==='error'?p.reject(new Error(JSON.stringify(m))):p.resolve(m);return;}
  if(m.event==='cpu.stepping'){const w=waiters.shift();if(w){clearTimeout(w.timer);w.resolve(m);}else queue.push(m);}
 });
 ws.addEventListener('close',()=>{for(const p of pending.values()){clearTimeout(p.timer);p.reject(new Error('debugger closed'));}pending.clear();for(const w of waiters.splice(0)){clearTimeout(w.timer);w.reject(new Error('debugger closed'));}});
 const rpc=(event,args={},timeout=30000)=>new Promise((resolve,reject)=>{const ticket=`world-source-${++serial}`;
  const timer=setTimeout(()=>{pending.delete(ticket);reject(new Error(`timeout ${event}`));},timeout);pending.set(ticket,{resolve,reject,timer});ws.send(JSON.stringify({event,...args,ticket}));});
 const resume=()=>ws.send(JSON.stringify({event:'cpu.resume'}));
 const stopped=()=>queue.length?Promise.resolve(queue.shift()):new Promise((resolve,reject)=>{const w={resolve,reject,timer:setTimeout(()=>reject(new Error('CPU stop timeout')),30000)};waiters.push(w);});
 const u32=async address=>{const r=await rpc('memory.read_u32',{address});const v=r.uintValue??r.value;if(!Number.isInteger(v))throw new Error('bad u32');return v>>>0;};
 const read=async(address,size)=>{const r=await rpc('memory.read',{address,size});const b=Buffer.from(r.base64||'','base64');if(b.length!==size)throw new Error('incomplete memory.read');return b;};
 const add=async(address,condition)=>{await rpc('cpu.breakpoint.add',{address,condition,enabled:true,log:false});installed.add(address);};
 const flush=()=>fs.writeFileSync(path.join(out,'world_sources.json'),JSON.stringify({schema:'aya-world-source-trace/v1',version,held,inputs,samples,worlds,dumps},null,2));
 const buttons=async values=>{await rpc('input.buttons.send',{buttons:values});inputs.push(values);};
 try{
  await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
  version=await rpc('version',{name:'aya-world-sources',version:'1'});await buttons({...release,...held});ready=true;
  // Use one breakpoint at a time. This also bounds the attribution probe.
  await add(BONE,'a3 == 0x2b');
  for(let guard=0;guard<10000;guard++){
   const stop=await stopped();const regs=await rpc('cpu.getAllRegs'),g=regs.categories?.[0]?.uintValues;
   if(!g||g.length<32)throw new Error('missing GPRs');
   if(stop.pc===BONE){
    const object=g[4]>>>0,metadata=await u32(object+0x3e8);
    if((await u32(metadata+4))>>>16===44&&g[7]===43){
     const table=await u32(metadata+0x34);
     if(((await u32(table))&0xffff)===106){
      if(!ready){await buttons({...release,...held});ready=true;}
      const sourceBase=await u32(object+0x3c4),bytes=await read(sourceBase,44*0x130);
      const file=path.join(out,`source_${String(samples.length).padStart(4,'0')}.bin`);fs.writeFileSync(file,bytes);
      const objectFile=path.join(out,`object_${String(samples.length).padStart(4,'0')}.bin`);fs.writeFileSync(objectFile,await read(object,0x400));
      samples.push({frame:samples.length,ticks:stop.ticks,object,metadata,sourceBase,sourceFile:file,objectFile});
      await rpc('cpu.breakpoint.remove',{address:BONE});installed.delete(BONE);await add(WORLD,'a1 == 2');
     }
    }
   }else if(stop.pc===WORLD&&ready){
    const matrix=await read(g[6]>>>0,64),context=await read(g[4]>>>0,16),stack=await read(g[29]>>>0,128);
    const index=worlds.length,sourceMatrix=Array.from({length:16},(_,i)=>matrix.readUInt32LE(i*4));
    worlds.push({index,kind:'writer',ticks:stop.ticks,sourceFrame:samples.length-1,context:g[4]>>>0,type:g[5]>>>0,matrixPointer:g[6]>>>0,
      dlCursor:context.readUInt32LE(8),ra:g[31]>>>0,sp:g[29]>>>0,savedCallerRa:stack.readUInt32LE(0),
      sourceMatrix,gpr:g.map(x=>x>>>0),stack:Array.from({length:32},(_,i)=>stack.readUInt32LE(i*4))});
   }else if(stop.pc===CACHE&&ready){
    const command=await read((g[5]+4)>>>0,52),matrix=await read(g[8]>>>0,64),instance=await read(g[6]>>>0,0x120);
    if(command.readUInt32LE(0)!==0x3a000000)throw new Error('cache WORLD header mismatch');
    const commandWords=Array.from({length:12},(_,i)=>command.readUInt32LE(4+i*4));
    if(commandWords.some(w=>(w>>>24)!==0x3b))throw new Error('cache WORLD data mismatch');
    worlds.push({index:worlds.length,kind:'cache',ticks:stop.ticks,sourceFrame:samples.length-1,
      container:g[4]>>>0,instance:g[6]>>>0,commandBlock:g[5]>>>0,matrixPointer:g[8]>>>0,ra:g[31]>>>0,
      sourceMatrix:Array.from({length:16},(_,i)=>matrix.readUInt32LE(i*4)),worldPayload:commandWords.map(w=>w&0xffffff),
      instanceWords:Array.from({length:0x120/4},(_,i)=>instance.readUInt32LE(i*4)),gpr:g.map(x=>x>>>0)});
   }
   if((samples.length>=wanted||worlds.length>=80)&&!dumpPending){
    dumpPending=rpc('gpu.record.dump',{},60000).then(r=>{if(!r.uri?.startsWith('data:'))throw new Error('missing GE dump');
     const b=Buffer.from(r.uri.split(',')[1],'base64'),file=path.join(out,'observed.ppdmp');fs.writeFileSync(file,b);dumps.push({file,bytes:b.length});dumpDone=true;
    }).catch(e=>{dumpError=e;dumpDone=true;});
   }
   if(dumpError)throw dumpError;
   if(dumpDone)break;
   if(worlds.length&&worlds.length%8===0){flush();console.log(`source=${samples.length} world=${worlds.length}`);}
   resume();
  }
  if(!dumpDone||!dumps.length)throw new Error('capture did not complete GE dump');
 }finally{
  if(ws.readyState===WebSocket.OPEN){await buttons(release).catch(()=>{});
   for(const address of installed)await rpc('cpu.breakpoint.remove',{address}).catch(()=>{});resume();ws.close();}
  flush();for(const p of pending.values())clearTimeout(p.timer);for(const w of waiters)clearTimeout(w.timer);
 }
 console.log(`source samples=${samples.length}, WORLD uploads=${worlds.length}, GE dumps=${dumps.length}`);
}
main().catch(e=>{console.error(e.stack||e);process.exitCode=1;});
