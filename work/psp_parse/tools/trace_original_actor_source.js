// Original actor source hierarchy and motion, selected by ordered mesh identity.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const out=process.env.BONE_PAIR_DIR,port=Number(process.env.PPSSPP_DEBUGGER_PORT||9900),wanted=Number(process.env.BONE_PAIR_FRAMES||60);
const held=JSON.parse(process.env.BONE_PAIR_BUTTONS_JSON||'{}');
const GROUP='eed4c94e2a8885a866ebfb0ba29f47701d6795b00275cab52896ae4135a5205c',target=0x08b526b4;
const release={rtrigger:false,ltrigger:false,square:false,triangle:false,circle:false,cross:false};
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
if(!out||wanted<4||wanted>240)throw new Error('invalid capture arguments');
fs.mkdirSync(out,{recursive:true});
async function main(){
 const ws=new WebSocket(`ws://127.0.0.1:${port}/debugger`,'debugger.ppsspp.org');
 const pending=new Map(),stops=[],waiters=[],frames=[],inputs=[],dumps=[];let serial=0,installed=false,liveDump=null,dumpError=null,version;
 ws.addEventListener('message',e=>{let m;try{m=JSON.parse(e.data);}catch{return;}
  const p=pending.get(m.ticket);if(p){pending.delete(m.ticket);clearTimeout(p.timer);m.event==='error'?p.reject(new Error(JSON.stringify(m))):p.resolve(m);return;}
  if(m.event==='cpu.stepping'){const w=waiters.shift();if(w){clearTimeout(w.timer);w.resolve(m);}else stops.push(m);}
 });
 ws.addEventListener('close',()=>{for(const p of pending.values()){clearTimeout(p.timer);p.reject(new Error('debugger closed'));}for(const w of waiters){clearTimeout(w.timer);w.reject(new Error('debugger closed'));}});
 const rpc=(event,args={},timeout=30000)=>new Promise((resolve,reject)=>{const ticket=`actor-${++serial}`,timer=setTimeout(()=>{pending.delete(ticket);reject(new Error(`timeout ${event}`));},timeout);pending.set(ticket,{resolve,reject,timer});ws.send(JSON.stringify({event,...args,ticket}));});
 const resume=()=>ws.send(JSON.stringify({event:'cpu.resume'}));
 const stop=()=>stops.length?Promise.resolve(stops.shift()):new Promise((resolve,reject)=>{const w={resolve,reject,timer:setTimeout(()=>reject(new Error('actor stop timeout')),30000)};waiters.push(w);});
 const read=async(address,size)=>{const r=await rpc('memory.read',{address,size});const b=Buffer.from(r.base64||'','base64');if(b.length!==size)throw new Error('incomplete read');return b;};
 const u32=async address=>(await read(address,4)).readUInt32LE(0);
 const words=b=>Array.from({length:b.length/4},(_,i)=>b.readUInt32LE(i*4));
 const pack=w=>[0,1,2,4,5,6,8,9,10,12,13,14].map(i=>(w[i]>>>8)&0xffffff);
 const buttons=async(values,ticks)=>{await rpc('input.buttons.send',{buttons:values});inputs.push({ticks,buttons:values});};
 const flush=()=>fs.writeFileSync(path.join(out,'manifest_runtime.json'),JSON.stringify({schema:'original-actor-source-capture/v1',target,condition:'a0 == 2',version,geometryGroup:GROUP,buttons:held,inputs,frames,unassignedGEDumps:dumps},null,2));
 let selected=null;
 try{
  await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
  version=await rpc('version',{name:'original-actor-source',version:'1'});await buttons({...release,...held},null);
  await rpc('cpu.breakpoint.add',{address:target,condition:'a0 == 2',enabled:true,log:false});installed=true;resume();
  for(let guard=0;(frames.length<wanted||liveDump)&&guard<5000;guard++){
   const s=await stop();if(s.pc!==target){resume();continue;}
   const regs=await rpc('cpu.getAllRegs'),g=regs.categories?.[0]?.uintValues;if(!g)throw new Error('missing GPRs');
   const object=g[17]>>>0;if(g[4]!==2||g[23]!==object+0x220)throw new Error('WORLD callsite contract changed');
   const metadata=await u32(object+0x3e8),header=words(await read(metadata,64));
   const boneCount=header[1]>>>16,drawTable=header[13];
   if(!boneCount||boneCount>64||((await u32(drawTable))&0xffff)!==28){resume();continue;}
   if(!selected||selected.object!==object||selected.metadata!==metadata){
    let cursor=drawTable+4;const signatures=[];
    for(let i=0;i<28;i++){
     const h=await read(cursor,12),n=h.readUInt16LE(0),updates=h[5],stride=h[6]*2,vtype=h.readUInt32LE(8);
     if(!n||updates>8||stride<1||stride>256)throw new Error('invalid actor packet');
     const p=Buffer.alloc(4);p.writeUInt32LE(vtype);signatures.push(Buffer.from(sha(Buffer.concat([p,await read(cursor+12+updates*4,n*stride)])),'hex'));
     cursor=(cursor+12+updates*4+n*stride+3)&~3;
    }
    if(sha(Buffer.concat(signatures))!==GROUP){resume();continue;}
    selected={object,metadata,drawTable,bytes:cursor-drawTable};
    selected.drawBytes=await read(drawTable,selected.bytes);selected.drawSHA=sha(selected.drawBytes);
   }else if(sha(await read(drawTable,selected.bytes))!==selected.drawSHA)throw new Error('actor geometry or palette table changed');
   const sourceBase=await u32(object+0x3c4),raw=await read(sourceBase,boneCount*0x130),records=[];
   for(let i=0;i<boneCount;i++)records.push({index:i,matrix:words(raw.subarray(i*0x130+0xc0,i*0x130+0xf0))});
   const file=path.join(out,`source_${String(frames.length).padStart(4,'0')}.bin`);fs.writeFileSync(file,raw);
   const actorWorldWords=words(await read(object+0x220,64));
   if(!frames.length){
    const descriptors=header[6],descriptorWords=words(await read(descriptors,boneCount*16));
    fs.writeFileSync(path.join(out,'metadata_snapshot.json'),JSON.stringify({schema:'original-actor-metadata-snapshot/v1',version,target,capturePoint:'WORLD callsite before JAL delay slot; GE alignment still required',ticks:s.ticks,object,sourceBase,metadata,boneCount,header,descriptors,descriptorWords,drawTable,drawWords:words(selected.drawBytes),geometryGroup:GROUP,records:Array.from({length:boneCount},(_,i)=>({index:i,words:words(raw.subarray(i*0x130,(i+1)*0x130))}))},null,2));
   }
   const frame=frames.length;
   frames.push({frame,ticks:s.ticks,object,metadata,sourceBase,boneCount,records,sourceBlock:{file,bytes:raw.length},actorWorldWords,actorWorldPayload:pack(actorWorldWords),geometryGroup:GROUP,dump:null});
   if(frame===0||frame===wanted-3){
    if(liveDump)throw new Error('GE request overlap');
    liveDump=rpc('gpu.record.dump',{},60000).then(r=>{if(!r.uri?.startsWith('data:'))throw new Error('no GE URI');const data=Buffer.from(r.uri.split(',')[1],'base64'),file=path.join(out,`actor_ge_${frame}.ppdmp`);fs.writeFileSync(file,data);dumps.push({file,bytes:data.length,requestedAtSample:frame,receivedAfterSamples:frames.length});}).catch(e=>{dumpError=e;}).finally(()=>{liveDump=null;});
   }
   if(dumpError)throw dumpError;flush();if(frame%10===0)console.log(`actor sample ${frame+1}/${wanted}, bones=${boneCount}, object=${object.toString(16)}`);resume();
  }
  if(frames.length<wanted||dumpError)throw dumpError||new Error('incomplete actor capture');
 }finally{
  if(ws.readyState===WebSocket.OPEN){await buttons(release,frames.at(-1)?.ticks??null).catch(()=>{});if(installed)await rpc('cpu.breakpoint.remove',{address:target}).catch(()=>{});resume();ws.close();}
  flush();for(const p of pending.values())clearTimeout(p.timer);for(const w of waiters)clearTimeout(w.timer);
 }
}
main().catch(e=>{console.error(e.stack||e);process.exitCode=1;});
