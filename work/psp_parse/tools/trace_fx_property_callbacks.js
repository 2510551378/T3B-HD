// Exact rifle selection, then bounded property-dispatch/callback/return triples.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const BASE=0x08804000,DISPATCH=0x08b69d64,TARGET=0x08b9a514;
const mode=process.env.FX_PROPERTY_MODE||'reset';
if(!['reset','key'].includes(mode))throw new Error('invalid property mode');
const propertyPC=mode==='reset'?0x08b68ce4:0x08b68ad4,returnPC=propertyPC+8;
const colorDetails=process.env.FX_PROPERTY_COLOR_DETAILS==='1';
const randomDetails=process.env.FX_PROPERTY_RANDOM_DETAILS==='1';
const vectorDetails=process.env.FX_PROPERTY_VECTOR_DETAILS==='1';
const vectorEvalRows=Number(process.env.FX_PROPERTY_VECTOR_EVAL_ROWS||0);
const vectorTransitions=process.env.FX_PROPERTY_VECTOR_TRANSITIONS==='1';
const localMatrixRows=Number(process.env.FX_PROPERTY_LOCAL_MATRIX_ROWS||0);
if(!Number.isInteger(localMatrixRows)||localMatrixRows<0||localMatrixRows>8||(localMatrixRows&&mode!=='key'))throw new Error('invalid local matrix capture request');
if(!Number.isInteger(vectorEvalRows)||vectorEvalRows<0||vectorEvalRows>12||(vectorEvalRows&&(!vectorDetails||mode!=='key')))throw new Error('invalid bounded vector evaluation request');
const out=process.env.MARKER_GE_EMIT_OUT_DIR,port=Number(process.env.PPSSPP_DEBUGGER_PORT);
const wanted=Number(process.env.MARKER_MAX_ROWS||12),maxStops=Number(process.env.MARKER_MAX_STOPS||1600);
const duration=Number(process.env.FX_PROPERTY_DURATION_MS||process.env.MARKER_DURATION_MS||30000);
if(!Number.isInteger(duration)||duration<1000||duration>60000)throw new Error('invalid bounded property duration');
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
 fs.mkdirSync(out,{recursive:true});const reportFile=path.join(out,'fx_property_callbacks.json');
 check(!fs.existsSync(reportFile),'never replace observation');
 const ws=new WebSocket(`ws://127.0.0.1:${port}/debugger`,'debugger.ppsspp.org');
 const pending=new Map(),queue=[],waiters=[];let serial=0,cpu=null,memory=null,ownStop=false,external=false,selection=null,failure=null,version=null,entryStops=0;
 const transitions=[],rows=[],vectorEvaluations=[],vectorStateSeries=[],localMatrixCalls=[],code=[],events=[],cleanup={errors:[]};let initialCPU=null,initialMemory=null;
 const save=(name,b)=>{const file=path.resolve(out,name);fs.writeFileSync(file,b);return{file,bytes:b.length,sha256:sha(b)};};
 const flush=()=>fs.writeFileSync(reportFile,JSON.stringify({schema:'original-FX-property-callback-observation/v1',mode,colorDetails,randomDetails,vectorDetails,producer,version,module:{file:modulePath,sha256:sha(moduleBytes)},FEP:{file:fepPath,sha256:sha(fep)},
   selection,rows,vectorEvalRows,vectorTransitions,vectorEvaluations,vectorStateSeries,localMatrixRows,localMatrixCalls,code,events,transitions,initialCPU,initialMemory,entryStops,ownedCPU:cpu,ownedMemory:memory,externalOrUnverifiedPause:external,cleanup,failure,
   limits:['Only descriptor10c78 on the exact original rifle; property callback/return observations do not establish a full FX lifecycle.', 'Parameter window is a retained bounded memory window, not an inferred allocation size.']},null,2));
 ws.addEventListener('message',e=>{let m;try{m=JSON.parse(e.data);}catch{return;}
  const p=pending.get(m.ticket);if(p){pending.delete(m.ticket);clearTimeout(p.timer);m.event==='error'?p.reject(new Error(JSON.stringify(m))):p.resolve(m);return;}
  if(m.event==='cpu.stepping'){events.push(m);const p=waiters.shift();if(p){clearTimeout(p.timer);p.resolve(m);}else queue.push(m);}
 });
 ws.addEventListener('close',()=>{for(const p of pending.values()){clearTimeout(p.timer);p.reject(new Error('debugger closed'));}pending.clear();for(const p of waiters.splice(0)){clearTimeout(p.timer);p.reject(new Error('debugger closed'));}});
 const rpc=(event,fields={})=>new Promise((resolve,reject)=>{const ticket=`fx-time-${++serial}`,timer=setTimeout(()=>{pending.delete(ticket);reject(new Error('RPC timeout '+event));},10000);pending.set(ticket,{resolve,reject,timer});ws.send(JSON.stringify({event,...fields,ticket}));});
 const stop=(timeout=5000)=>queue.length?Promise.resolve(queue.shift()):new Promise((resolve,reject)=>{const p={resolve,reject,timer:setTimeout(()=>{const i=waiters.indexOf(p);if(i>=0)waiters.splice(i,1);reject(new Error('stop wait timeout'));},timeout)};waiters.push(p);});
 const read=async(address,size,replacements=true)=>{check(Number.isInteger(address)&&address>=0x08000000&&address+size<=0x0c000000&&size>0&&size<=0x20000,'invalid bounded guest byte window');const r=await rpc('memory.read',{address,size,replacements});const b=Buffer.from(r.base64||'','base64');check(b.length===size,'short memory read');return b;};
 const snapshot=async(name,address,size)=>({address,size,raw:save(name,await read(address,size))});
 const registers=async()=>{const r=await rpc('cpu.getAllRegs'),g=r.categories?.[0]?.uintValues;check(Array.isArray(g)&&g.length>=32,'missing GPR category');return{all:r,g:g.slice(0,32)};};
 const fpu=all=>{const c=all.categories.find(c=>c.name==='FPU');check(c&&c.uintValues.length>=32,'missing original FPU bits');return c.uintValues;};
 const resume=()=>{check(!queue.length&&!external,'cannot resume queued/external stop');ws.send(JSON.stringify({event:'cpu.resume'}));ownStop=false;};
 const remove=async()=>{
  if(cpu!==null){const address=cpu;await rpc('cpu.breakpoint.remove',{address});cpu=null;transitions.push({operation:'CPU_remove',address});}
  if(memory!==null){const address=memory;await rpc('memory.breakpoint.remove',{address,size:4});memory=null;transitions.push({operation:'memory_remove',address});}
  flush();
 };
 const armCPU=async(address=DISPATCH)=>{check(cpu===null&&memory===null,'single owned breakpoint');cpu=address;transitions.push({operation:'CPU_add_requested',address:cpu});flush();await rpc('cpu.breakpoint.add',{address:cpu,enabled:true,log:false});};
 const armMemory=async()=>{check(cpu===null&&memory===null,'single owned breakpoint');memory=selection.N+0x30;transitions.push({operation:'memory_add_requested',address:memory});flush();await rpc('memory.breakpoint.add',{address:memory,size:4,enabled:true,log:false,read:false,write:true,change:true});};
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
  const tableAddress=n.readUInt32LE(0x4c),slot=tableAddress+4*9;check(pointer(slot),'time-slot table outside guest RAM');
  const sb=await read(slot,4),ptr=sb.readUInt32LE(0);selection.dispatchTime={definitionIndex:9,slot:await snapshot('selection_time_slot.bin',slot,4),recordPointer:ptr,nodeTime30Bits:n.readUInt32LE(0x30),f12Bits:fpu(r.all)[12],f20Bits:fpu(r.all)[20]};
  if(ptr){const field=ptr+4,aligned=field&~3;check(field%2===0&&field>=0x08000000&&field+2<=0x0c000000,'unaligned/outside S16 start field');selection.dispatchTime.signedStart={fieldAddress:field,byteOffset:field-aligned,window:await snapshot('selection_time_start.bin',aligned,4)};}
  flush();return true;
 };
 const context=async(label)=>{
  const n=await read(selection.N,0x64),p=await read(selection.P,0x1b8),d=await read(selection.descriptor,0x48),c=await read(selection.C,0xa8);
  check(n.readUInt32LE(0x40)===selection.descriptor&&p.readUInt32LE(0x190)===selection.FEPbase&&p.readUInt32LE(0x198)===selection.FEPbase+0x48f0,'watched node identity changed');
  check(p.readUInt32LE(0x144)===selection.handle,'watched actor handle changed');const primary=await read(selection.handle,4);check(primary.readUInt32LE(0)===selection.actor,'watched actor changed');
  return{primaryHandle:save(label+'_primary_handle.bin',primary),node:save(label+'_node.bin',n),state:save(label+'_state.bin',p),descriptor:save(label+'_descriptor.bin',d),context:save(label+'_context.bin',c),timeBits:n.readUInt32LE(0x30)};
 };
 try{
  await new Promise((resolve,reject)=>{const t=setTimeout(()=>reject(new Error('connect timeout')),10000);ws.addEventListener('open',()=>{clearTimeout(t);resolve();},{once:true});ws.addEventListener('error',reject,{once:true});});
  version=await rpc('version',{name:'original-FX-property-callback',version:'1'});
  initialCPU=await rpc('cpu.breakpoint.list');initialMemory=await rpc('memory.breakpoint.list');
  check(Array.isArray(initialCPU.breakpoints)&&Array.isArray(initialMemory.breakpoints),'no breakpoint inventory');
  check(!initialCPU.breakpoints.length&&!initialMemory.breakpoints.length,'existing breakpoints left unchanged');
  const status=await rpc('cpu.status');check(!status.stepping&&!status.paused,'existing CPU pause left unchanged');
  await identityCode(0x08b69b58,0x258,'render_dispatch');
  await rpc('input.buttons.send',{buttons:{...release,...held}});await armCPU();const deadline=Date.now()+duration;
  while(!selection&&entryStops<maxStops&&Date.now()<deadline){const s=await stop(Math.max(1,deadline-Date.now()));check(cpu===s.pc,'external CPU stop during selection');ownStop=true;entryStops++;const r=await registers();if(await select(s,r))break;resume();}
  check(selection,'no exact original node within bounded selection');await remove();
  await identityCode(0x08b689b8,0x414,'boundary_dispatchers');
  if(localMatrixRows){for(const [address,size,label]of[[0x08b92fcc,0x6cc,'local_matrix_callback'],[0x08b92b54,0x84,'local_matrix_leaf'],[0x08b66bb4,0x3b4,'matrix_consumer'],[0x08b6589c,0x104,'matrix_mode1_helper'],[0x08b9a514,0x808,'selected_handler155']])await identityCode(address,size,label);}
  if(vectorDetails){await identityCode(0x08b943d4,0x134,'complete_vector_callbacks');await identityCode(0x08b65f48,0x224,'vector_change_helper');await identityCode(0x08b662e0,0x200,'vector_wrap_helper');await identityCode(0x08bfcff4,0x68,'vector_add_sub_helpers');}
  if(colorDetails){await identityCode(0x08b8f898,0x1c8,'complete_color_callbacks');await identityCode(0x08b943d4,0x134,'rotation_prefix_boundary');await identityCode(0x08b94968,0x94,'complete_scale_callbacks');await identityCode(0x08b6ac94,0x144,'original_property_record_finder');}
  const extra=async(label)=>{
   const before=await context(label),nb=await read(selection.N,0x64),db=await read(selection.descriptor,0x48);
   const count=db[8],table=db.readUInt32LE(0x1c),parameter=nb.readUInt32LE(0x44);
   check(count>0&&count<=32&&pointer(table,count*4)&&pointer(parameter,0x200),'invalid property arrays');
   before.parameterWindow=await snapshot(label+'_parameter_window.bin',parameter,0x200);
   before.definitionTable=await snapshot(label+'_definition_table.bin',table,count*4);
   before.parameterTable=await snapshot(label+'_parameter_table.bin',nb.readUInt32LE(0x48),count*4);
   before.timeTable=await snapshot(label+'_time_table.bin',nb.readUInt32LE(0x4c),count*4);
   return before;
  };
  await armCPU(propertyPC);resume();let stages=0,pendingRow=null;
  const propertyDeadline=Date.now()+duration;
  while(rows.filter(x=>x.complete).length<wanted&&stages<maxStops&&Date.now()<propertyDeadline){
   const stopEvent=await stop(Math.max(1,propertyDeadline-Date.now()));
   check(stopEvent.pc===cpu,'external property stage stop');ownStop=true;stages++;
   const regs=await registers();
   if(!pendingRow){
    if(mode==='reset'?(regs.g[20]!==selection.N||regs.g[30]!==selection.C):(regs.g[17]!==selection.N||regs.g[16]!==selection.C)){resume();continue;}
    const label='property_'+String(rows.length).padStart(4,'0');
    const target=regs.g[mode==='reset'?9:10];
    let index=mode==='reset'?regs.g[18]/4:-1,type=mode==='reset'?regs.g[19]:-1;
    if(mode==='key'){const c=await read(selection.C,0xa8),d=await read(selection.descriptor,0x48),table=await read(d.readUInt32LE(0x1c),d[8]*4);index=words(table).indexOf(c.readUInt32LE(0x94));check(index>=0,'active definition absent');type=(await read(c.readUInt32LE(0x94),4)).readUInt16LE(0);}
    check(Number.isInteger(index)&&index>=0&&index<32&&type<1024&&target>=BASE&&target<BASE+moduleBytes.length,'invalid actual property dispatch');
    const before=await extra(label+'_dispatch'),tableBytes=fs.readFileSync(before.definitionTable.raw.file);
    check(index<tableBytes.length/4,'definition index out of range');
    const definition=tableBytes.readUInt32LE(index*4),defBytes=await read(definition,4);
    check(defBytes.readUInt16LE(0)===type,'actual property class differs');
    const object=regs.g[4],vt=(await read(object,4)).readUInt32LE(0);
    const row={index:rows.length,definitionIndex:index,type,target,label,dispatch:{stop:stopEvent,allRegisters:save(label+'_dispatch_registers.json',Buffer.from(JSON.stringify(regs.all,null,2))),before},
     definition:await snapshot(label+'_definition.bin',definition,4),registrySlot:await snapshot(label+'_registry_slot.bin',0x08c3a820+type*4,4),
     typeObject:await snapshot(label+'_type_object.bin',object,0x20),vtable:await snapshot(label+'_vtable.bin',vt,0x40),
     record:regs.g[6]?await snapshot(label+'_record.bin',regs.g[6],0x80):null,oldRecord:regs.g[mode==='reset'?8:11]?await snapshot(label+'_old_record.bin',regs.g[mode==='reset'?8:11],0x80):null,
     parameterAddress:regs.g[mode==='reset'?17:7],callbackInputRecord:regs.g[6],oldInputRecord:regs.g[mode==='reset'?8:11]};
    rows.push(row);pendingRow=row;flush();
    await identityCode(target,randomDetails&&[23,24].includes(type)?(type===23?0x38c:0x3e8):0x200,label+'_callback_code');await remove();await armCPU(target);resume();
   }else if(!pendingRow.entry){
    const row=pendingRow;check(regs.g[5]===selection.C&&regs.g[6]===row.callbackInputRecord&&regs.g[7]===row.parameterAddress&&regs.g[8]===row.oldInputRecord&&regs.g[31]===returnPC,'callback ABI/return differs');
    row.entry={stop:stopEvent,allRegisters:save(row.label+'_entry_registers.json',Buffer.from(JSON.stringify(regs.all,null,2))),before:await extra(row.label+'_entry')};flush();
    if(vectorDetails&&row.type===6){
     row.vector={kind:mode,stage:'helper_dispatch',stages:[]};await remove();await armCPU(mode==='key'?0x08b943ec:0x08b944b4);resume();
    }
    else if(randomDetails&&mode==='key'&&[23,24].includes(row.type)){
     const def=(await read(selection.C,0xa8)).readUInt32LE(0x94),header=await read(def,0x20),table=header.readUInt32LE(8),index=header.readUInt32LE(4);
     check(index<64&&table>=0x08000000&&table+index*2+2<=0x0c000000,'invalid callback target-offset lookup');
     const offsetRaw=await read(table+index*2,2),offset=offsetRaw.readUInt16LE(0),node=await read(selection.N,0x64);
     row.random={kind:row.type===23?'VFPU-vector':'scalar-LCG',activeDefinitionHeader:{address:def,size:32,raw:save(row.label+'_active_definition_header.bin',header)},
      targetOffset:{address:table+index*2,size:2,raw:save(row.label+'_target_offset.bin',offsetRaw)},resolvedBase:selection.N+0x60+offset,
      tables:await snapshot(row.label+'_modifier_tables.bin',0x08c3b500,0x20),vectorCache:await snapshot(row.label+'_vector_cache.bin',0x08cb0fa0,0x14),
      vectorConstants:await snapshot(row.label+'_vector_constants.bin',0x08c2dcf0,16),channels:[],stage:'loop'};
     if(row.type===24)await identityCode(0x08afc000,0x34,row.label+'_LCG_helper');
     if(node.readUInt16LE(2)&2){row.random.skippedByNodeFlag=true;row.random.complete=true;await remove();await armCPU(returnPC);resume();}
     else{await remove();await armCPU(row.type===23?0x08bb8d5c:0x08bb95bc);resume();}
    }
    else if(colorDetails&&mode==='reset'&&row.type===16){row.nested={};await remove();await armCPU(0x08b8fa48);resume();}
    else{await remove();await armCPU(returnPC);resume();}
   }else if(pendingRow.nested&&!pendingRow.nested.complete){
    const row=pendingRow,nested=row.nested;
    const observed={stop:stopEvent,allRegisters:save(row.label+'_nested_'+(!nested.dispatch?'dispatch':!nested.entry?'entry':'return')+'_registers.json',Buffer.from(JSON.stringify(regs.all,null,2))),snapshot:await extra(row.label+'_nested_'+(!nested.dispatch?'dispatch':!nested.entry?'entry':'return'))};
    if(!nested.dispatch){check(stopEvent.pc===0x08b8fa48&&regs.g[8]===0x08b8f954,'unexpected nested color target');nested.dispatch=observed;await remove();await armCPU(0x08b8f954);resume();}
    else if(!nested.entry){check(stopEvent.pc===0x08b8f954&&regs.g[31]===0x08b8fa50&&regs.g[7]===row.parameterAddress,'nested color ABI differs');nested.entry=observed;await remove();await armCPU(0x08b8fa50);resume();}
    else{check(stopEvent.pc===0x08b8fa50,'unexpected nested return');nested.return=observed;nested.complete=true;await remove();await armCPU(returnPC);resume();}
    flush();
   }else if(pendingRow.vector&&!pendingRow.vector.complete){
    const row=pendingRow,state=row.vector,stage=state.stage,label=row.label+'_vector_'+stage;
    const observed={stage,stop:stopEvent,allRegisters:save(label+'_registers.json',Buffer.from(JSON.stringify(regs.all,null,2))),snapshot:await extra(label),stack:await snapshot(label+'_stack.bin',regs.g[29]-0x100,0x180)};
    state.stages.push(observed);const next=async(pc)=>{flush();await remove();await armCPU(pc);resume();};
    if(stage==='helper_dispatch'){
     check(stopEvent.pc===(mode==='key'?0x08b943ec:0x08b944b4),'Unexpected vector helper dispatch');state.stage='helper_entry';await next(mode==='key'?0x08b65f48:0x08b662e0);
    }else if(stage==='helper_entry'){
     check(regs.g[4]===row.callbackInputRecord&&regs.g[5]===row.parameterAddress&&regs.g[6]===row.oldInputRecord&&regs.g[31]===(mode==='key'?0x08b943f4:0x08b944bc),'Vector helper ABI differs');state.stage='helper_return';await next(regs.g[31]);
    }else if(stage==='helper_return'){
     if(mode==='key'){state.complete=true;state.stage='complete';await next(returnPC);}
     else{state.stage='evaluate_dispatch';await next(0x08b944dc);}
    }else if(stage==='evaluate_dispatch'){
     check(stopEvent.pc===0x08b944dc&&regs.g[8]===0x08b94438,'Unexpected nested vector evaluator');state.stage='evaluate_entry';await next(0x08b94438);
    }else if(stage==='evaluate_entry'){
     check(regs.g[7]===row.parameterAddress&&regs.g[31]===0x08b944e4,'Nested vector evaluator ABI differs');state.stage='evaluate_return';await next(0x08b944e4);
    }else if(stage==='evaluate_return'){state.complete=true;state.stage='complete';await next(returnPC);}
    else throw new Error('Unsupported vector observation stage '+stage);
   }else if(pendingRow.random&&!pendingRow.random.complete){
    const row=pendingRow,state=row.random,type23=row.type===23;
    const stage=state.stage,rngIndex=stage==='rng_entry'?state.channels.at(-1).rng.length:stage==='rng_return'?state.channels.at(-1).rng.length-1:null;
    const label=row.label+'_random_'+String(state.channels.length).padStart(2,'0')+'_'+stage+(rngIndex===null?'':'_'+rngIndex);
    const capture=async()=>({stop:stopEvent,allRegisters:save(label+'_registers.json',Buffer.from(JSON.stringify(regs.all,null,2))),snapshot:await extra(label),stack:await snapshot(label+'_stack.bin',regs.g[29],0x80)});
    const next=async(pc)=>{flush();await remove();await armCPU(pc);resume();};
    if(stage==='loop'){
     const channel=regs.g[type23?24:18];check(channel<3,'modifier channel outside original loop');
     const tables=fs.readFileSync(state.tables.raw.file),record=fs.readFileSync(row.record.raw.file),base=type23?0:16;
     const enabledOffset=tables[base+channel],modeOffset=tables[base+3+channel],vectorOffset=tables[base+6+channel];
     check(Math.max(enabledOffset,modeOffset,vectorOffset+11)<record.length,'modifier operand outside retained record');
     const active={channel,enabledOffset,modeOffset,vectorOffset,enabled:record[enabledOffset]!==0,mode:record[modeOffset],loop:await capture(),rng:[]};state.channels.push(active);
     if(!active.enabled){state.stage='advanced';await next(type23?0x08bb9024:0x08bb9890);}
     else if(type23){state.stage='vector_random';const pc=active.mode===1?0x08bb8ebc:active.mode===2?0x08bb8f68:0x08bb8e24;await next(pc);}
     else{active.expectedRNGCalls=record[12]?3:1;state.stage='rng_entry';await next(0x08afc000);}
    }else if(stage==='vector_random'){
     state.channels.at(-1).vectorRandom=await capture();state.stage='ready';await next(0x08bb8f90);
    }else if(stage==='rng_entry'||stage==='rng_return'){
     const active=state.channels.at(-1),rootRaw=await read(0x08c37594,4),root=rootRaw.readUInt32LE(0);check(pointer(root+0x58),'LCG seed outside guest RAM');
     const snap=await capture();snap.seedRoot={address:0x08c37594,size:4,raw:save(label+'_seed_root.bin',rootRaw)};snap.seed=await snapshot(label+'_seed.bin',root+0x58,4);
     if(stage==='rng_entry'){
      check(regs.g[31]>=0x08bb961c&&regs.g[31]<=0x08bb97d0,'Unexpected original LCG caller');
      active.rng.push({entry:snap,returnPC:regs.g[31]});state.stage='rng_return';await next(regs.g[31]);
     }else{
      const call=active.rng.at(-1);check(stopEvent.pc===call.returnPC,'LCG return differs');call.return=snap;
      if(active.rng.length<active.expectedRNGCalls){state.stage='rng_entry';await next(0x08afc000);}
      else{state.stage='ready';await next(0x08bb97f0);}
     }
    }else if(stage==='ready'){
     state.channels.at(-1).ready=await capture();state.stage='advanced';await next(type23?0x08bb9024:0x08bb9890);
    }else if(stage==='advanced'){
     state.channels.at(-1).advanced=await capture();const channel=regs.g[type23?24:18];
     if(channel<3){state.stage='loop';await next(type23?0x08bb8d5c:0x08bb95bc);}
     else{state.complete=true;state.stage='complete';await next(returnPC);}
    }else throw new Error('Unsupported modifier stage '+stage);
   }else{
    const row=pendingRow;row.return={stop:stopEvent,allRegisters:save(row.label+'_return_registers.json',Buffer.from(JSON.stringify(regs.all,null,2))),after:await extra(row.label+'_return')};row.complete=true;pendingRow=null;flush();
    if(rows.filter(x=>x.complete).length>=wanted)break;
    await remove();await armCPU(propertyPC);resume();
   }
  }
  check(rows.length===wanted&&rows.every(x=>x.complete),'bounded property capture incomplete');
  if(vectorEvalRows){
   const sourceRow=rows.find(r=>r.type===6);check(sourceRow,'No original vector binding for evaluations');
   const series=vectorTransitions?vectorStateSeries:vectorEvaluations;
   const nextTarget=()=>vectorTransitions&&series.length%3===2?0x08b9447c:0x08b94438;
   await remove();await armCPU(0x08b94438);resume();let pendingEvaluation=null,stops=0;const deadline=Date.now()+duration;
   while(series.length<vectorEvalRows&&stops<maxStops&&Date.now()<deadline){
    const event=await stop(Math.max(1,deadline-Date.now()));check(event.pc===cpu,'External vector evaluation stop');ownStop=true;stops++;const regs=await registers();
    if(!pendingEvaluation){
     if(regs.g[5]!==selection.C||regs.g[7]!==sourceRow.parameterAddress){resume();continue;}
     const c=await read(selection.C,0xa8);if(c.readUInt32LE(0x90)!==selection.N){resume();continue;}
     check(regs.g[31]>=BASE&&regs.g[31]<BASE+moduleBytes.length,'Vector evaluator return outside selected module');
     const label='vector_evaluate_'+String(series.length).padStart(4,'0');pendingEvaluation={index:series.length,sourceRow:sourceRow.index,parameterAddress:regs.g[7],returnPC:regs.g[31],kind:event.pc===0x08b9447c?'vector_wrap':'vector_evaluate',
      entry:{stop:event,allRegisters:save(label+'_entry_registers.json',Buffer.from(JSON.stringify(regs.all,null,2))),snapshot:await extra(label+'_entry'),stack:await snapshot(label+'_entry_stack.bin',regs.g[29]-0x180,0x200)}};
     if(event.pc===0x08b9447c){pendingEvaluation.currentRecord=await snapshot(label+'_current_record.bin',regs.g[6],0x80);pendingEvaluation.previousRecord=await snapshot(label+'_previous_record.bin',regs.g[8],0x80);}
     flush();await remove();await armCPU(pendingEvaluation.returnPC);resume();
    }else{
     const call=pendingEvaluation,label='vector_evaluate_'+String(call.index).padStart(4,'0');check(event.pc===call.returnPC,'Unexpected vector evaluation return');
     call.return={stop:event,allRegisters:save(label+'_return_registers.json',Buffer.from(JSON.stringify(regs.all,null,2))),snapshot:await extra(label+'_return')};call.complete=true;series.push(call);pendingEvaluation=null;flush();
     if(series.length>=vectorEvalRows)break;
     await remove();await armCPU(nextTarget());resume();
    }
   }
   check(series.length===vectorEvalRows,'Incomplete bounded vector evaluation series');
  }
  if(localMatrixRows){
   const sourceRow=rows.find(r=>r.type===14);check(sourceRow,'No original local matrix definition');const node=await read(selection.N,0x64),matrix=node.readUInt32LE(0x50);check(pointer(matrix,64),'Invalid node local matrix');
   const points=[0x08b92b84,0x08b92b88,0x08b92b94,0x08b92b9c,0x08b92ba8,0x08b92bac];
   let current=null,stage='type14_entry',stops=0;await remove();await armCPU(0x08b92fcc);resume();const deadline=Date.now()+duration;
   while(localMatrixCalls.length<localMatrixRows&&stops<maxStops&&Date.now()<deadline){
    const event=await stop(Math.max(1,deadline-Date.now()));check(event.pc===cpu,'External local matrix stop');ownStop=true;stops++;const regs=await registers();
    if(stage==='type14_entry'&&(regs.g[5]!==selection.C||regs.g[7]!==sourceRow.parameterAddress)){resume();continue;}
    if(stage==='leaf_entry'&&regs.g[4]!==matrix){resume();continue;}
    if(stage==='consumer_entry'&&(regs.g[4]!==selection.C||regs.g[5]!==selection.N||regs.g[6]!==matrix)){resume();continue;}
    const index=localMatrixCalls.length,label='local_matrix_'+String(index).padStart(4,'0')+'_'+stage;
    const obs={stage,stop:event,allRegisters:save(label+'_registers.json',Buffer.from(JSON.stringify(regs.all,null,2))),snapshot:await extra(label),
     matrix:await snapshot(label+'_matrix.bin',matrix,64),stack:await snapshot(label+'_stack.bin',regs.g[29]-0x100,0x300)};
    const next=async(pc)=>{flush();await remove();await armCPU(pc);resume();};
    if(stage==='type14_entry'){
     current={index,sourceRow:sourceRow.index,node:selection.N,localMatrix:matrix,entry:obs,outerReturnPC:regs.g[31],trig:[]};
     current.record=await snapshot(label+'_record.bin',regs.g[6],0x80);const definition=(await read(selection.C,0xa8)).readUInt32LE(0x94);current.definition=await snapshot(label+'_definition.bin',definition,0x20);
     stage='leaf_entry';await next(0x08b92b54);
    }else if(stage==='leaf_entry'){
     check(regs.g[31]===0x08b934e4,'Unexpected local matrix leaf caller');current.leafEntry=obs;current.scale=await snapshot(label+'_scale.bin',regs.g[5],16);current.angles=await snapshot(label+'_angles.bin',regs.g[6],16);current.position=await snapshot(label+'_position.bin',regs.g[7],16);
     current.componentIndices=await snapshot(label+'_component_indices.bin',fs.readFileSync(current.definition.raw.file).readUInt32LE(8),8);
     stage='trig0';await next(points[0]);
    }else if(stage.startsWith('trig')){
     const i=Number(stage.slice(4));check(event.pc===points[i],'Unexpected VROT continuation');current.trig.push(obs);
     if(i+1<points.length){stage='trig'+(i+1);await next(points[i+1]);}else{stage='leaf_return';await next(0x08b934e4);}
    }else if(stage==='leaf_return'){
     current.leafReturn=obs;stage='type14_return';await next(current.outerReturnPC);
    }else if(stage==='type14_return'){
     current.return=obs;stage='consumer_entry';await next(0x08b66bb4);
    }else if(stage==='consumer_entry'){
     check(fs.readFileSync(obs.matrix.raw.file).equals(fs.readFileSync(current.return.matrix.raw.file)),'Local matrix changed before actual renderer consumed it');
     current.consumerEntry=obs;current.consumerOutput=regs.g[8];current.consumerReturnPC=regs.g[31];
     const slot=await read(0x08c3b58c,4);current.consumerGlobalSlot={address:0x08c3b58c,size:4,raw:save(label+'_global_slot.bin',slot)};current.consumerGlobal=await snapshot(label+'_global.bin',slot.readUInt32LE(0),64);current.consumerParent=await snapshot(label+'_parent.bin',selection.P+0x60,64);
     stage='consumer_return';await next(regs.g[31]);
    }else if(stage==='consumer_return'){
     current.consumerReturn=obs;current.world=await snapshot(label+'_world.bin',current.consumerOutput,64);current.complete=true;localMatrixCalls.push(current);current=null;flush();
     if(localMatrixCalls.length>=localMatrixRows)break;stage='type14_entry';await next(0x08b92fcc);
    }else throw new Error('Unsupported local matrix stage '+stage);
   }
   check(localMatrixCalls.length===localMatrixRows,'Incomplete bounded local matrix series');
  }
 }catch(e){failure=String(e.stack||e);if(!ownStop)external=true;}
 finally{
  for(const action of [async()=>{await rpc('input.buttons.send',{buttons:release});cleanup.buttonsReleased=true;},remove,async()=>{if(ownStop&&!external&&!queue.length){const status=await rpc('cpu.status');cleanup.finalCPUStatus=status;if(status.stepping){resume();cleanup.resumedOwnedStop=true;}else cleanup.alreadyRunningAfterRemove=true;}}]){try{if(ws.readyState===WebSocket.OPEN)await action();}catch(e){cleanup.errors.push(String(e));}}
  flush();ws.close();
 }
 console.log(JSON.stringify({out,rows:rows.length,entryStops,failure,cleanup}));if(failure||cleanup.errors.length)process.exitCode=1;
}
main().catch(e=>{console.error(e.stack||e);process.exitCode=1;});
