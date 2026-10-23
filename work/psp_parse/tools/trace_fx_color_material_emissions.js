// Exact rifle: parent color -> cached vertex palette -> actual CPU vertex writes.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const BASE=0x08804000,DISPATCH=0x08b69d64,TARGET=0x08b9a514;
const out=process.env.MARKER_GE_EMIT_OUT_DIR,port=Number(process.env.PPSSPP_DEBUGGER_PORT);
const geFrameCount=process.env.FX_COLOR_GE==='1'?Number(process.env.MARKER_GE_CAPTURE_FRAMES||16):0;
if(!Number.isInteger(geFrameCount)||geFrameCount<0||geFrameCount>16)throw new Error('invalid bounded GE count');
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
 fs.mkdirSync(out,{recursive:true});const reportFile=path.join(out,'fx_color_material_emissions.json');
 check(!fs.existsSync(reportFile),'never replace observation');
 const ws=new WebSocket(`ws://127.0.0.1:${port}/debugger`,'debugger.ppsspp.org');
 const pending=new Map(),queue=[],waiters=[];let serial=0,cpu=null,memory=null,ownStop=false,external=false,selection=null,failure=null,version=null,entryStops=0;
 const transitions=[],rows=[],code=[],events=[],cleanup={errors:[]},geCaptures=[];let initialCPU=null,initialMemory=null,geTask=null,geFailure=null;
 const save=(name,b)=>{const file=path.resolve(out,name);fs.writeFileSync(file,b);return{file,bytes:b.length,sha256:sha(b)};};
 const flush=()=>fs.writeFileSync(reportFile,JSON.stringify({schema:'original-FX-color-material-emission-observation/v1',producer,version,module:{file:modulePath,sha256:sha(moduleBytes)},FEP:{file:fepPath,sha256:sha(fep)},
   selection,rows,code,events,transitions,initialCPU,initialMemory,entryStops,geFrameCount,geCaptures,geFailure,ownedCPU:cpu,ownedMemory:memory,externalOrUnverifiedPause:external,cleanup,failure,
   limits:['Exact original rifle descriptor10c78/type155 only; actual CPU vertex-color writes. The observed multi-color branch does not emit GE material-color commands; GPU consumption/final pixels remain separate.', 'Parameter window is a retained bounded memory window, not an inferred allocation size.']},null,2));
 ws.addEventListener('message',e=>{let m;try{m=JSON.parse(e.data);}catch{return;}
  const p=pending.get(m.ticket);if(p){pending.delete(m.ticket);clearTimeout(p.timer);m.event==='error'?p.reject(new Error(JSON.stringify(m))):p.resolve(m);return;}
  if(m.event==='cpu.stepping'){events.push(m);const p=waiters.shift();if(p){clearTimeout(p.timer);p.resolve(m);}else queue.push(m);}
 });
 ws.addEventListener('close',()=>{for(const p of pending.values()){clearTimeout(p.timer);p.reject(new Error('debugger closed'));}pending.clear();for(const p of waiters.splice(0)){clearTimeout(p.timer);p.reject(new Error('debugger closed'));}});
 const rpc=(event,fields={},timeoutMs=10000)=>new Promise((resolve,reject)=>{const ticket=`fx-time-${++serial}`,timer=setTimeout(()=>{pending.delete(ticket);reject(new Error('RPC timeout '+event));},timeoutMs);pending.set(ticket,{resolve,reject,timer});ws.send(JSON.stringify({event,...fields,ticket}));});
 const stop=(timeout=5000)=>queue.length?Promise.resolve(queue.shift()):new Promise((resolve,reject)=>{const p={resolve,reject,timer:setTimeout(()=>{const i=waiters.indexOf(p);if(i>=0)waiters.splice(i,1);reject(new Error('stop wait timeout'));},timeout)};waiters.push(p);});
 const read=async(address,size,replacements=true)=>{check(Number.isInteger(address)&&address>=0x08000000&&address+size<=0x0c000000&&size>0&&size<=0x20000,'invalid bounded guest byte window');const r=await rpc('memory.read',{address,size,replacements});const b=Buffer.from(r.base64||'','base64');check(b.length===size,'short memory read');return b;};
 const snapshot=async(name,address,size)=>({address,size,raw:save(name,await read(address,size))});
 const recordFrames=async()=>{
  try{for(let sample=0;sample<geFrameCount;sample++){
   const requestedAt=Date.now(),response=await rpc('gpu.record.dump',{},60000);
   check(typeof response.uri==='string'&&response.uri.startsWith('data:')&&response.uri.includes(';base64,'),'missing GE data URI');
   const raw=Buffer.from(response.uri.slice(response.uri.indexOf(',')+1),'base64');check(raw.length>=32&&raw.length<=64*1024*1024,'GE data bound');
   geCaptures.push({sample,requestedAt,completedAt:Date.now(),raw:save('concurrent_GE_'+String(sample).padStart(4,'0')+'.ppdmp',raw)});flush();
  }}catch(e){geFailure=String(e.stack||e);flush();}
 };
 const commandSnapshot=async(name,cursor,size)=>{
  check(cursor%4===0&&size%4===0&&(cursor>=0x08000000&&cursor+size<=0x0c000000||cursor>=0x48000000&&cursor+size<=0x4c000000),'invalid DL address/alias');
  const address=cursor&~0x40000000;return{guestCursor:cursor,...await snapshot(name,address,size)};
 };
 const capturePose=async(label)=>{
  const slot=await read(0x08c3b588,4),view=slot.readUInt32LE(0);
  return{world:await snapshot(label+'_weapon_WORLD.bin',selection.actor+0x220,64),mainViewSlot:{address:0x08c3b588,size:4,raw:save(label+'_main_VIEW_slot.bin',slot)},mainView:await snapshot(label+'_main_VIEW.bin',view,64)};
 };
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
  version=await rpc('version',{name:'original-FX-color-material-emission',version:'1'});
  initialCPU=await rpc('cpu.breakpoint.list');initialMemory=await rpc('memory.breakpoint.list');
  check(Array.isArray(initialCPU.breakpoints)&&Array.isArray(initialMemory.breakpoints),'no breakpoint inventory');
  check(!initialCPU.breakpoints.length&&!initialMemory.breakpoints.length,'existing breakpoints left unchanged');
  const status=await rpc('cpu.status');check(!status.stepping&&!status.paused,'existing CPU pause left unchanged');
  await identityCode(0x08b69b58,0x258,'render_dispatch');
  await rpc('input.buttons.send',{buttons:{...release,...held}});await armCPU();const deadline=Date.now()+duration;
  while(!selection&&entryStops<maxStops&&Date.now()<deadline){const s=await stop(Math.max(1,deadline-Date.now()));check(cpu===s.pc,'external CPU stop during selection');ownStop=true;entryStops++;const r=await registers();if(await select(s,r))break;resume();}
  check(selection,'no exact original node within bounded selection');if(geFrameCount)geTask=recordFrames();await remove();
  await identityCode(0x08b9a514,0x808,'full_original_type155_renderer');
  await identityCode(0x08b60080,0x264,'original_color_binder');
  await identityCode(0x08c005bc,0x2c,'original_color_wrapper');
  await identityCode(0x08c01998,0x90,'original_material_emitter');
  await identityCode(0x08b60758,0x138,'original_cached_color_flush');
  await identityCode(0x08b5f684,0x1d0,'original_palette_modulate_and_vertex_patch');
  if(geFrameCount)await identityCode(0x08c01088,0x200,'original_VIEW_writer');
  const colorSnapshot=async(label)=>{
   const before=await context(label),n=await read(selection.N,0x64),d=await read(selection.descriptor,0x48),c=await read(selection.C,0xa8);
   const slot=d.readUInt32LE(0x1c)+5*4,ptr=(await read(slot,4)).readUInt32LE(0),def=await read(ptr,4);
   check(def.readUInt16LE(0)===16,'wrong source color definition');
   before.definitionSlot=await snapshot(label+'_color_def_slot.bin',slot,4);
   before.definition={address:ptr,size:4,raw:save(label+'_color_definition.bin',def)};
   before.colorParameters=await snapshot(label+'_source_color_parameters.bin',n.readUInt32LE(0x44)+def.readUInt16LE(2),0x30);
   const rendererDef=c.readUInt32LE(0x94),rd=await read(rendererDef,12),count=rd.readUInt32LE(4);
   check(rd.readUInt16LE(0)===155&&count<=16,'unexpected renderer definition/reference count');
   before.rendererDefinition={address:rendererDef,size:12,raw:save(label+'_renderer_definition.bin',rd)};
   before.rendererReferences=await snapshot(label+'_renderer_references.bin',rd.readUInt32LE(8),count*2+2);
   return before;
  };
  let currentStop=selection.stop,currentRegs={all:JSON.parse(fs.readFileSync(selection.allRegisters.file)),g:null},stages=0;
  currentRegs.g=currentRegs.all.categories[0].uintValues.slice(0,32);
  const captureDeadline=Date.now()+duration;
  while(rows.length<wanted&&Date.now()<captureDeadline){
   const label='color_'+String(rows.length).padStart(4,'0'),row={index:rows.length,dispatch:{stop:currentStop,allRegisters:save(label+'_dispatch_registers.json',Buffer.from(JSON.stringify(currentRegs.all,null,2))),before:await colorSnapshot(label+'_dispatch')}};
   rows.push(row);flush();
   const stage=async(address,name)=>{
    const s=await stop(Math.max(1,captureDeadline-Date.now()));check(cpu===address&&s.pc===address,'external color stage stop');ownStop=true;
    const r=await registers();row[name]={stop:s,allRegisters:save(label+'_'+name+'_registers.json',Buffer.from(JSON.stringify(r.all,null,2)))};flush();return r;
   };
   if(geFrameCount){
    await armCPU(0x08c01088);resume();const vr=await stage(0x08c01088,'viewEntry');
    const global=(await read(0x08ca31d8,4)).readUInt32LE(0),dc=await read(global,12),cursor=dc.readUInt32LE(8);
    check(vr.g[4]===global&&vr.g[5]===1&&vr.g[31]===0x08bfff8c,'unexpected VIEW writer ABI');
    row.viewEntry.DLGlobal=await snapshot(label+'_VIEW_DL_global.bin',0x08ca31d8,4);row.viewEntry.DLContext={address:global,size:12,raw:save(label+'_VIEW_DL_context.bin',dc)};
    row.viewEntry.cursor=cursor;row.viewEntry.input=await snapshot(label+'_VIEW_F32_input.bin',vr.g[6],64);row.viewEntry.weaponPose=await capturePose(label+'_view');
    await remove();await armCPU(0x08b9a8e0);resume();
   }else{await armCPU(0x08b9a8e0);resume();}
   const modulated=await stage(0x08b9a8e0,'modulated');check(modulated.g[17]===selection.C,'wrong render context');
   row.modulated.before=await colorSnapshot(label+'_modulated');
   if(geFrameCount){row.modulated.viewPacket=await commandSnapshot(label+'_actual_VIEW_packet.bin',row.viewEntry.cursor,52);row.modulated.weaponPose=await capturePose(label+'_modulated');}
   row.modulated.color=await snapshot(label+'_modulated_stack_color.bin',modulated.g[29],16);
   row.modulated.record=await snapshot(label+'_actual_renderer_record.bin',modulated.g[20],0x50);
   row.modulated.jumpTable=await snapshot(label+'_actual_color_jump_table.bin',0x08c2d8f0,28);flush();
   await remove();await armCPU(0x08b9aa84);resume();
   const transformed=await stage(0x08b9aa84,'transformed');
   row.transformed.color=await snapshot(label+'_transformed_stack_color.bin',transformed.g[29],16);flush();
   await remove();await armCPU(0x08b60080);resume();
   const bind=await stage(0x08b60080,'colorBind');check([0x08b603a0,0x08b60538].includes(bind.g[31])&&bind.g[5]<4096,'unexpected color binder caller/index');
   row.colorBind.inputColor=await snapshot(label+'_binder_input_RGBA.bin',bind.g[6],16);
   const table=(await read(bind.g[4],4)).readUInt32LE(0),slot=table+bind.g[5]*4,object=(await read(slot,4)).readUInt32LE(0),header=(await read(object,4)).readUInt32LE(0),h=await read(header,0x24);
   check(h.readInt32LE(0x10)>0,'no original material group');const group=h.readUInt32LE(0x1c),gb=await read(group,0x44),colorMode=gb.readInt32LE(0x10);
   row.colorBind.bank=await snapshot(label+'_bank.bin',bind.g[4],0x34);row.colorBind.slot=await snapshot(label+'_slot.bin',slot,4);
   row.colorBind.object=await snapshot(label+'_object.bin',object,0x20);row.colorBind.header={address:header,size:0x24,raw:save(label+'_header.bin',h)};
   row.colorBind.group={address:group,size:0x44,raw:save(label+'_material_group.bin',gb)};row.colorBind.colorMode=colorMode;
   check(colorMode>=2&&colorMode<=4096,'observer requires bounded multi-color source palette');
   row.colorBind.sourceColors=await snapshot(label+'_source_color_palette.bin',gb.readUInt32LE(0x14),colorMode*4);
   row.colorBind.convertedBefore=await snapshot(label+'_converted_colors_before.bin',gb.readUInt32LE(0x18),colorMode*4);
   const bankBefore=await read(bind.g[4],0x34),cache=bankBefore.readUInt32LE(0x24),count=bankBefore.readUInt32LE(0x28),capacity=bankBefore.readUInt32LE(0x30);
   check(count<=capacity&&capacity<=8192,'invalid color cache bounds');
   if(count<capacity)row.colorBind.nextCacheEntry=await snapshot(label+'_next_cache_entry.bin',cache+count*32,32);
   flush();const bindReturnPC=bind.g[31];await remove();await armCPU(bindReturnPC);resume();
   await stage(bindReturnPC,'binderReturn');
   row.binderReturn.bank=await snapshot(label+'_bank_after_bind.bin',bind.g[4],0x34);
   row.binderReturn.object=await snapshot(label+'_object_after_bind.bin',object,0x20);
   const bankAfter=fs.readFileSync(row.binderReturn.bank.raw.file),afterCount=bankAfter.readUInt32LE(0x28);
   check(afterCount===count||afterCount===count+1,'unexpected cache-count mutation');row.enqueued=afterCount===count+1;
   if(row.enqueued){
    row.binderReturn.enqueuedEntry=await snapshot(label+'_enqueued_cache_entry.bin',cache+count*32,32);flush();
    await remove();await armCPU(0x08b60758);resume();let flushRegs=null;
    while(stages<maxStops&&Date.now()<captureDeadline){
     const event=await stop(Math.max(1,captureDeadline-Date.now()));check(cpu===0x08b60758&&event.pc===cpu,'external cache flush stop');ownStop=true;stages++;
     const r=await registers();if(r.g[4]===bind.g[4]){
      const bank=await read(r.g[4],0x34),index=bank.readUInt32LE(0x2c),ptr=bank.readUInt32LE(0x24)+index*32;
      if(index===count&&(await read(ptr+16,4)).readUInt32LE(0)===object){
       row.flushEntry={stop:event,allRegisters:save(label+'_flush_entry_registers.json',Buffer.from(JSON.stringify(r.all,null,2))),bank:await snapshot(label+'_flush_bank.bin',r.g[4],0x34),cacheEntry:await snapshot(label+'_flush_cache_entry.bin',ptr,32)};flushRegs=r;break;
      }
     }resume();
    }
    check(flushRegs,'no exact queued-object flush within bounds');flush();await remove();await armCPU(0x08b5f684);resume();
    const convert=await stage(0x08b5f684,'paletteEntry');
    check(convert.g[4]===gb.readUInt32LE(0x18)&&convert.g[5]===colorMode&&convert.g[6]===gb.readUInt32LE(0x14)&&convert.g[7]===cache+count*32&&convert.g[31]===0x08b60808,'palette conversion ABI differs');
    row.paletteEntry.tint=await snapshot(label+'_actual_palette_tint.bin',convert.g[7],16);
    row.paletteEntry.source=await snapshot(label+'_actual_palette_source.bin',convert.g[6],colorMode*4);
    row.paletteEntry.outputBefore=await snapshot(label+'_actual_palette_output_before.bin',convert.g[4],colorMode*4);flush();
    await remove();await armCPU(0x08b60808);resume();await stage(0x08b60808,'paletteReturn');
    row.paletteReturn.output=await snapshot(label+'_actual_palette_output.bin',convert.g[4],colorMode*4);flush();
    await remove();await armCPU(0x08b5f780);resume();const patch=await stage(0x08b5f780,'vertexPatchEntry');
    check(patch.g[4]===object&&patch.g[31]===0x08b6082c,'unexpected vertex-color patch caller/object');
    const headerBytes=await read(patch.g[5],16),vtype=headerBytes.readUInt32LE(0),innerCount=headerBytes.readUInt32LE(8),innerPointer=headerBytes.readUInt32LE(12);
    check([0,2].includes(vtype&3)&&innerCount>0&&innerCount<=64,'unsupported vertex-color patch layout/count');
    const stride=(vtype&3)===2?16:12,colorOffset=(vtype&3)===2?4:0,records=await read(innerPointer,innerCount*16);
    row.vertexPatchEntry.header={address:patch.g[5],size:16,raw:save(label+'_patch_draw_header.bin',headerBytes)};
    row.vertexPatchEntry.records={address:innerPointer,size:innerCount*16,raw:save(label+'_patch_inner_records.bin',records)};row.vertexPatchEntry.draws=[];
    for(let i=0;i<innerCount;i++){
     const count=records.readUInt32LE(i*16+8),refs=records.readUInt32LE(i*16+4),vertices=records.readUInt32LE(i*16+12);
     check(count>0&&count<=4096,'patch vertex bound');row.vertexPatchEntry.draws.push({count,stride,colorOffset,
      references:await snapshot(label+'_draw'+i+'_color_references.bin',refs,count*4),vertices:await snapshot(label+'_draw'+i+'_vertices_before.bin',vertices,count*stride)});
    }flush();await remove();await armCPU(0x08b6082c);resume();await stage(0x08b6082c,'vertexPatchReturn');row.vertexPatchReturn.draws=[];
    for(let i=0;i<row.vertexPatchEntry.draws.length;i++){const d=row.vertexPatchEntry.draws[i];row.vertexPatchReturn.draws.push(await snapshot(label+'_draw'+i+'_vertices_after.bin',d.vertices.address,d.vertices.size));}flush();
    const exitPC=flushRegs.g[31];check(exitPC>=BASE&&exitPC<BASE+moduleBytes.length&&exitPC%4===0,'unrecognized flush return');
    await remove();await armCPU(exitPC);resume();await stage(exitPC,'flushReturn');
    row.flushReturn.bank=await snapshot(label+'_bank_after_flush.bin',bind.g[4],0x34);flush();
   }
   row.complete=true;flush();
   await remove();if(rows.length>=wanted)break;await armCPU(DISPATCH);resume();let found=false;
   while(stages<maxStops&&Date.now()<captureDeadline){
    const s=await stop(Math.max(1,captureDeadline-Date.now()));check(s.pc===DISPATCH&&cpu===DISPATCH,'external render selection stop');ownStop=true;stages++;
    const r=await registers();if(r.g[10]===TARGET&&r.g[5]===selection.C&&r.g[17]===selection.N){currentStop=s;currentRegs=r;found=true;break;}resume();
   }
   check(found,'no subsequent exact color render invocation');await remove();
  }
  check(rows.length===wanted&&rows.every(x=>x.complete),'bounded color-material observation incomplete');
  if(geTask){await remove();if(ownStop)resume();await geTask;check(geFailure===null&&geCaptures.length===geFrameCount,'incomplete concurrent GE recording');}
 }catch(e){failure=String(e.stack||e);if(!ownStop)external=true;}
 finally{
  for(const action of [async()=>{await rpc('input.buttons.send',{buttons:release});cleanup.buttonsReleased=true;},remove,async()=>{if(ownStop&&!external&&!queue.length){const status=await rpc('cpu.status');cleanup.finalCPUStatus=status;if(status.stepping){resume();cleanup.resumedOwnedStop=true;}else cleanup.alreadyRunningAfterRemove=true;}}]){try{if(ws.readyState===WebSocket.OPEN)await action();}catch(e){cleanup.errors.push(String(e));}}
  flush();ws.close();
 }
 console.log(JSON.stringify({out,rows:rows.length,entryStops,failure,cleanup}));if(failure||cleanup.errors.length)process.exitCode=1;
}
main().catch(e=>{console.error(e.stack||e);process.exitCode=1;});
