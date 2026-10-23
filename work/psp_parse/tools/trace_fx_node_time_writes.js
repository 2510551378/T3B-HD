// Bounded observer: exact original rifle/FEP descriptor, then owned N+30 writes.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const BASE=0x08804000,DISPATCH=0x08b69d64,TARGET=0x08b9a514;
const watchMatrix=process.env.FX_WATCH_LOCAL_MATRIX==='1';
const out=process.env.MARKER_GE_EMIT_OUT_DIR,port=Number(process.env.PPSSPP_DEBUGGER_PORT);
const wanted=Number(process.env.MARKER_MAX_ROWS||12),maxStops=Number(process.env.MARKER_MAX_STOPS||1600);
const duration=Number(process.env.MARKER_DURATION_MS||30000);
if(!out||!Number.isInteger(port)||port<1||port>65535||!Number.isInteger(wanted)||wanted<1||wanted>24)throw new Error('invalid observation bounds');
const modulePath=path.resolve(__dirname,'../raw/ULJM05798_module_08804000.bin'),moduleBytes=fs.readFileSync(modulePath);
const fepPath=path.resolve(__dirname,'../out/WEAPON_MARKER_STATE_20261020/original_source_match_section.bin'),fep=fs.readFileSync(fepPath);
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
if(sha(moduleBytes)!=='b5fc590366fc610f2cdd60104a4a28851bacd402c4600a4c296776e1dea0869f'||sha(fep)!=='97443c71b1c1d644f323c6ff611afb740329cfe11a47a711f39dc59de06ec802')throw new Error('original module/FEP changed');
const producer={file:__filename,sha256:sha(fs.readFileSync(__filename))};
const held=JSON.parse(process.env.MARKER_BUTTONS_JSON||'{"square":true,"rtrigger":true}');
const release=Object.fromEntries([...new Set(['square','rtrigger','ltrigger','cross','circle','triangle',...Object.keys(held)])].map(k=>[k,false]));
const pointer=(a,n=4)=>Number.isInteger(a)&&a%4===0&&a>=0x08000000&&a+n<=0x0c000000;
const check=(v,msg)=>{if(!v)throw new Error(msg);};
const words=b=>Array.from({length:b.length/4},(_,i)=>b.readUInt32LE(i*4));
async function main(){
 fs.mkdirSync(out,{recursive:true});const reportFile=path.join(out,watchMatrix?'fx_local_matrix_writes.json':'fx_node_time_writes.json');
 check(!fs.existsSync(reportFile),'never replace observation');
 const ws=new WebSocket(`ws://127.0.0.1:${port}/debugger`,'debugger.ppsspp.org');
 const pending=new Map(),queue=[],waiters=[];let serial=0,cpu=null,memory=null,ownStop=false,external=false,selection=null,failure=null,version=null,entryStops=0;
 const transitions=[],rows=[],code=[],events=[],cleanup={errors:[]};let initialCPU=null,initialMemory=null;
 const save=(name,b)=>{const file=path.resolve(out,name);fs.writeFileSync(file,b);return{file,bytes:b.length,sha256:sha(b)};};
 const flush=()=>fs.writeFileSync(reportFile,JSON.stringify({schema:watchMatrix?'original-FX-local-matrix-write-observation/v1':'original-FX-node-time-write-observation/v1',watchMatrix,producer,version,module:{file:modulePath,sha256:sha(moduleBytes)},FEP:{file:fepPath,sha256:sha(fep)},
   selection,rows,code,events,transitions,initialCPU,initialMemory,entryStops,ownedCPU:cpu,ownedMemory:memory,externalOrUnverifiedPause:external,cleanup,failure,
   limits:['One previously verified descriptor10c78/type155 branch; source1 visual FX only, no bullet/AI or authored lifetime equivalence.', 'Each completed store effect is observed at the next write stop, not immediately after one instruction. The final pending store is unverified and not counted.']},null,2));
 ws.addEventListener('message',e=>{let m;try{m=JSON.parse(e.data);}catch{return;}
  const p=pending.get(m.ticket);if(p){pending.delete(m.ticket);clearTimeout(p.timer);m.event==='error'?p.reject(new Error(JSON.stringify(m))):p.resolve(m);return;}
  if(m.event==='cpu.stepping'){events.push(m);const p=waiters.shift();if(p){clearTimeout(p.timer);p.resolve(m);}else queue.push(m);}
 });
 ws.addEventListener('close',()=>{for(const p of pending.values()){clearTimeout(p.timer);p.reject(new Error('debugger closed'));}pending.clear();for(const p of waiters.splice(0)){clearTimeout(p.timer);p.reject(new Error('debugger closed'));}});
 const rpc=(event,fields={})=>new Promise((resolve,reject)=>{const ticket=`fx-time-${++serial}`,timer=setTimeout(()=>{pending.delete(ticket);reject(new Error('RPC timeout '+event));},10000);pending.set(ticket,{resolve,reject,timer});ws.send(JSON.stringify({event,...fields,ticket}));});
 const stop=(timeout=5000)=>queue.length?Promise.resolve(queue.shift()):new Promise((resolve,reject)=>{const p={resolve,reject,timer:setTimeout(()=>{const i=waiters.indexOf(p);if(i>=0)waiters.splice(i,1);reject(new Error('stop wait timeout'));},timeout)};waiters.push(p);});
 const read=async(address,size,replacements=true)=>{check(pointer(address,size)&&size<=0x20000,'invalid ordinary guest window');const r=await rpc('memory.read',{address,size,replacements});const b=Buffer.from(r.base64||'','base64');check(b.length===size,'short memory read');return b;};
 const snapshot=async(name,address,size)=>({address,size,raw:save(name,await read(address,size))});
 const registers=async()=>{const r=await rpc('cpu.getAllRegs'),g=r.categories?.[0]?.uintValues;check(Array.isArray(g)&&g.length>=32,'missing GPR category');return{all:r,g:g.slice(0,32)};};
 const fpu=all=>{const c=all.categories.find(c=>c.name==='FPU');check(c&&c.uintValues.length>=32,'missing original FPU bits');return c.uintValues;};
 const resume=()=>{check(!queue.length&&!external,'cannot resume queued/external stop');ws.send(JSON.stringify({event:'cpu.resume'}));ownStop=false;};
 const remove=async()=>{
  if(cpu!==null){const address=cpu;await rpc('cpu.breakpoint.remove',{address});cpu=null;transitions.push({operation:'CPU_remove',address});}
  if(memory!==null){const address=memory;await rpc('memory.breakpoint.remove',{address,size:4});memory=null;transitions.push({operation:'memory_remove',address});}
  flush();
 };
 const armCPU=async()=>{check(cpu===null&&memory===null,'single owned breakpoint');cpu=DISPATCH;transitions.push({operation:'CPU_add_requested',address:cpu});flush();await rpc('cpu.breakpoint.add',{address:cpu,enabled:true,log:false});};
 const armMemory=async()=>{check(cpu===null&&memory===null,'single owned breakpoint');memory=watchMatrix?selection.localMatrix:selection.N+0x30;transitions.push({operation:'memory_add_requested',address:memory});flush();await rpc('memory.breakpoint.add',{address:memory,size:4,enabled:true,log:false,read:false,write:true,change:true});};
 const identityCode=async(address,size,label)=>{
  check(address>=BASE&&address+size<=BASE+moduleBytes.length,'writer outside selected module');
  const expected=moduleBytes.subarray(address-BASE,address-BASE+size),physical=await read(address,size),original=await read(address,size,false);
  const d=await rpc('memory.disasm',{address,end:address+size,displaySymbols:false});const map=new Map();
  for(const l of d.lines){if(l.address>=address+size||l.address+l.addressSize<=address)continue;check(['opcode','macro'].includes(l.type)&&l.addressSize%4===0,'non-opcode identity');const ww=l.addressSize===4?[l.encoding]:l.macroEncoding;check(ww?.length===l.addressSize/4,'invalid macro');for(let j=0;j<ww.length;j++){const a=l.address+j*4;if(a>=address&&a<address+size){check(!map.has(a),'overlapping opcode');map.set(a,ww[j]);}}}
  const decoded=Buffer.alloc(size);for(let j=0;j<size;j+=4){check(map.has(address+j),'disassembly gap');decoded.writeUInt32LE(map.get(address+j),j);}
  const row={address,size,physical:save(label+'_physical.bin',physical),original:save(label+'_original.bin',original),disasm:save(label+'_disasm.json',Buffer.from(JSON.stringify(d,null,2))),decoded:save(label+'_decoded.bin',decoded),expected:save(label+'_expected.bin',expected)};
  code.push(row);flush();check(original.equals(expected)&&decoded.equals(expected),'original module identity differs');
 };
 const select=async(s,r)=>{
  if(r.g[10]!==TARGET)return false;
  const C=r.g[5];if(!pointer(C,0xa8))return false;const c=await read(C,0xa8),P=c.readUInt32LE(0x8c),N=c.readUInt32LE(0x90);
  if(!pointer(P,0x1ac)||!pointer(N,0x64)||N!==r.g[17])return false;
  const p=await read(P,0x1ac),n=await read(N,0x64),base=p.readUInt32LE(0x190),source=p.readUInt32LE(0x198);
  if(!pointer(base,fep.length)||source!==base+0x48f0||n.readUInt32LE(0x40)!==base+0x10c78)return false;
  const resource=await read(source,0xc0);if(!resource.equals(fep.subarray(0x48f0,0x49b0)))return false;
  const handle=p.readUInt32LE(0x144);if(!pointer(handle))return false;const actor=(await read(handle,4)).readUInt32LE(0);if(!pointer(actor,0x3ec))return false;
  const fields=await read(actor+0x3c4,40),metadata=fields.readUInt32LE(0x24);if(!pointer(metadata,64))return false;
  const mh=await read(metadata,64),table=mh.readUInt32LE(0x34);if(mh.readUInt16LE(6)!==3||!pointer(table,16))return false;
  const dh=await read(table,16);if(dh.readUInt16LE(4)!==243||dh.readUInt32LE(12)!==0x522||dh[9]>8)return false;
  const geom=await read(table+16+dh[9]*4,243*16),prefix=Buffer.alloc(4);prefix.writeUInt32LE(0x522);
  if(sha(Buffer.concat([prefix,geom]))!=='168578abca4c4f5d22d5994ebced6b93a25d5167428bfd47f1a1150a8d42e65a')return false;
  selection={C,P,N,descriptor:base+0x10c78,FEPbase:base,actor,handle,sourceBase:fields.readUInt32LE(0),metadata,drawTable:table,stop:s,
   allRegisters:save('selection_all_registers.json',Buffer.from(JSON.stringify(r.all,null,2))),context:save('selection_context.bin',c),state:save('selection_state.bin',p),node:save('selection_node.bin',n),
   geometry:save('selection_original_rifle_vertices.bin',geom),resource:save('selection_FEP_record192.bin',resource),identityRaw:{primaryHandle:await snapshot('selection_primary_handle.bin',handle,4),actorFields:{address:actor+0x3c4,size:40,raw:save('selection_actor_fields.bin',fields)},metadataHeader:{address:metadata,size:64,raw:save('selection_metadata_header.bin',mh)},drawHeader:{address:table,size:16,raw:save('selection_draw_header.bin',dh)}}};flush();
  if(watchMatrix){selection.localMatrix=n.readUInt32LE(0x50);check(pointer(selection.localMatrix,64),'local matrix pointer outside guest RAM');}
  const tableAddress=n.readUInt32LE(0x4c),slot=tableAddress+4*9;check(pointer(slot),'time-slot table outside guest RAM');
  const sb=await read(slot,4),ptr=sb.readUInt32LE(0);selection.dispatchTime={definitionIndex:9,slot:await snapshot('selection_time_slot.bin',slot,4),recordPointer:ptr,nodeTime30Bits:n.readUInt32LE(0x30),f12Bits:fpu(r.all)[12],f20Bits:fpu(r.all)[20]};
  if(ptr){const field=ptr+4,aligned=field&~3;check(field%2===0&&field>=0x08000000&&field+2<=0x0c000000,'unaligned/outside S16 start field');selection.dispatchTime.signedStart={fieldAddress:field,byteOffset:field-aligned,window:await snapshot('selection_time_start.bin',aligned,4)};}
  flush();return true;
 };
 const context=async(label)=>{
  const n=await read(selection.N,0x64),p=await read(selection.P,0x1b8),d=await read(selection.descriptor,0x48),c=await read(selection.C,0xa8);
  check(n.readUInt32LE(0x40)===selection.descriptor&&p.readUInt32LE(0x190)===selection.FEPbase&&p.readUInt32LE(0x198)===selection.FEPbase+0x48f0,'watched node identity changed');
  check(p.readUInt32LE(0x144)===selection.handle,'watched actor handle changed');const primary=await read(selection.handle,4);check(primary.readUInt32LE(0)===selection.actor,'watched actor changed');
  const result={primaryHandle:save(label+'_primary_handle.bin',primary),node:save(label+'_node.bin',n),state:save(label+'_state.bin',p),descriptor:save(label+'_descriptor.bin',d),context:save(label+'_context.bin',c),timeBits:n.readUInt32LE(0x30),watchedBits:n.readUInt32LE(0x30)};
  if(watchMatrix){check(n.readUInt32LE(0x50)===selection.localMatrix,'local matrix pointer changed');result.localMatrix=await snapshot(label+'_local_matrix.bin',selection.localMatrix,64);result.parameterWindow=await snapshot(label+'_parameters.bin',n.readUInt32LE(0x44),0x200);result.watchedBits=fs.readFileSync(result.localMatrix.raw.file).readUInt32LE(0);}
  return result;
 };
 try{
  await new Promise((resolve,reject)=>{const t=setTimeout(()=>reject(new Error('connect timeout')),10000);ws.addEventListener('open',()=>{clearTimeout(t);resolve();},{once:true});ws.addEventListener('error',reject,{once:true});});
  version=await rpc('version',{name:'original-FX-node-time-writer',version:'1'});
  initialCPU=await rpc('cpu.breakpoint.list');initialMemory=await rpc('memory.breakpoint.list');
  check(Array.isArray(initialCPU.breakpoints)&&Array.isArray(initialMemory.breakpoints),'no breakpoint inventory');
  check(!initialCPU.breakpoints.length&&!initialMemory.breakpoints.length,'existing breakpoints left unchanged');
  const status=await rpc('cpu.status');check(!status.stepping&&!status.paused,'existing CPU pause left unchanged');
  await identityCode(0x08b69b58,0x258,'render_dispatch');
  await rpc('input.buttons.send',{buttons:{...release,...held}});await armCPU();const deadline=Date.now()+duration;
  while(!selection&&entryStops<maxStops&&Date.now()<deadline){const s=await stop(Math.max(1,deadline-Date.now()));check(cpu===s.pc,'external CPU stop during selection');ownStop=true;entryStops++;const r=await registers();if(await select(s,r))break;resume();}
  check(selection,'no exact original node within bounded selection');await remove();await armMemory();resume();
  const writeDeadline=Date.now()+duration;
  while(rows.filter(x=>x.effectObservedAtNextWriteStop).length<wanted&&Date.now()<writeDeadline){
   const s=await stop(Math.max(1,writeDeadline-Date.now()));const r=await registers(),label='write_'+String(rows.length).padStart(4,'0')+'_event'+events.length;
   const before=await context(label+'_before');const item={stop:s,before,allRegisters:save(label+'_all_registers.json',Buffer.from(JSON.stringify(r.all,null,2)))};rows.push(item);flush();
   await identityCode((s.pc&~15)-0x100,0x400,label+'_code');
   const first=moduleBytes.readUInt32LE(s.pc-BASE),isBranch=[1,2,3,4,5,6,7,0x14,0x15,0x16,0x17].includes(first>>>26)||((first>>>26)===0&&[8,9].includes(first&63))||((first>>>26)===0x11&&((first>>>21)&31)===8);
   let writer=null;
   for(const pc of isBranch?[s.pc+4]:[s.pc]){
    const op=moduleBytes.readUInt32LE(pc-BASE),major=op>>>26,rs=(op>>>21)&31,rt=(op>>>16)&31,imm=(op<<16)>>16,address=(r.g[rs]+imm)>>>0;
    const watched=watchMatrix?selection.localMatrix:selection.N+0x30;
    if([0x39,0x2b].includes(major)&&address===watched){const value=major===0x39?fpu(r.all)[rt]:(rt===0?0:r.g[rt]);writer={pc,word:op,major,baseRegister:rs,valueRegister:rt,effectiveAddress:address,expectedBits:value,branchDelay:isBranch};}
    if(watchMatrix&&[0x3a,0x3e].includes(major)){
     const quad=major===0x3e,reg=rt|((op&(quad?1:3))<<5),offset=(op&0xfffc)-((op&0x8000)?0x10000:0),a=(r.g[rs]+offset)>>>0,count=quad?4:1;
     if(a<=watched&&watched<a+count*4){
      const cat=r.all.categories.find(c=>c.name==='VFPU');check(cat?.uintValues.length===128,'missing VFPU data');const physical=[];
      for(let encoded=0;encoded<128;encoded++){const m=((encoded>>>2)&7)*16,i=m+(encoded&3)*4+((encoded>>>5)&3);physical[i]=cat.uintValues[encoded];}
      const m=((reg>>>2)&7)*16,col=reg&3,row=(reg>>>5)&2,lanes=Array.from({length:count},(_,i)=>physical[quad?(reg&32?m+col+((row+i)&3)*4:m+col*4+((row+i)&3)):m+col*4+((reg>>>5)&3)]);
      writer={pc,word:op,major,baseRegister:rs,vectorRegister:reg,effectiveAddress:a,expectedWords:lanes,expectedBits:lanes[(watched-a)/4],branchDelay:isBranch};
     }
    }
   }
   check(memory===(watchMatrix?selection.localMatrix:selection.N+0x30)&&writer,'unsupported or external writer stop; evidence retained');ownStop=true;item.writer=writer;flush();
   const previous=rows.length>1?rows[rows.length-2]:null;
   if(previous){
    if(previous.stop.pc===s.pc&&previous.stop.ticks===s.ticks&&previous.before.watchedBits===item.before.watchedBits){
     transitions.push({operation:'duplicate_owned_stop',stop:s,before:item.before});rows.pop();
     check(transitions.filter(x=>x.operation==='duplicate_owned_stop').length<=8,'repeated owned stop without execution');flush();resume();continue;
    }
    previous.nextObservation={stop:s,before:item.before};flush();
    check(item.before.watchedBits===previous.writer.expectedBits,'next actual memory observation differs from prior original store source');
    previous.effectObservedAtNextWriteStop=true;previous.valueChanged=previous.before.watchedBits!==item.before.watchedBits;flush();
   }
   if(rows.filter(x=>x.effectObservedAtNextWriteStop).length>=wanted)break;resume();
  }
  check(rows.some(x=>x.effectObservedAtNextWriteStop),'no actual store effects paired at following write stop');
 }catch(e){failure=String(e.stack||e);if(!ownStop)external=true;}
 finally{
  for(const action of [async()=>{await rpc('input.buttons.send',{buttons:release});cleanup.buttonsReleased=true;},remove,async()=>{if(ownStop&&!external&&!queue.length){const status=await rpc('cpu.status');cleanup.finalCPUStatus=status;if(status.stepping){resume();cleanup.resumedOwnedStop=true;}else cleanup.alreadyRunningAfterRemove=true;}}]){try{if(ws.readyState===WebSocket.OPEN)await action();}catch(e){cleanup.errors.push(String(e));}}
  flush();ws.close();
 }
 console.log(JSON.stringify({out,rows:rows.length,entryStops,failure,cleanup}));if(failure||cleanup.errors.length)process.exitCode=1;
}
main().catch(e=>{console.error(e.stack||e);process.exitCode=1;});
