// VM/MockWebSocket only. No network, emulator process, UI or savestate access.
'use strict';
const fs=require('fs'),path=require('path'),os=require('os'),vm=require('vm'),assert=require('assert'),crypto=require('crypto');
const root=path.resolve(__dirname,'..'),filename=path.join(__dirname,'trace_weapon_queue_routes.js');
const source=fs.readFileSync(filename,'utf8'),moduleBytes=fs.readFileSync(path.join(root,'raw/ULJM05798_module_08804000.bin'));
const BASE=0x08804000,SP=0x09ff0000,CTRL=0x09d00000,E=0x09b00000,C=0x09b01000,P=0x09b02000,N=0x09b03000;
const order=[0x08bbdce8,0x08bbda68,0x08bbdb20,0x08bbd7f0,0x08bbd828,0x08b5ac60,0x08bbdce8];
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const pack=values=>{const b=Buffer.alloc(values.length*4);values.forEach((x,i)=>b.writeUInt32LE(x>>>0,i*4));return b;};
const cases=[
 'all-routes-unticketed-resume','all-routes-ticketed-resume','zero-stops-running-status','range-zero-enqueue-controls-live',
 'burst-three-stops','gpr32','gpr36','controller-null','controller-sentinel','controller-raw-unknown-values',
 'callback-fields-null-sentinel','callback-entry-invalid','initial-external-stepping','initial-UI-paused','external-phase-stop',
 'external-during-resume','resume-unticketed-error','resume-ticketed-error','resume-no-ACK','stray-unticketed-error',
 'invalid-status-bool','invalid-status-ticks','status-ticketed-error','status-timeout','phase-tick-regression',
 'short-GPR','bad-GPR-u32','bad-GPR-PC','bad-SP','short-stack','stack-RPC-error','short-controller',
 'bad-original-code','bad-disasm-code','missing-disasm-coverage','existing-active-BP','existing-disabled-target-BP',
 'add-timeout-own-stop','add-timeout-external-stop','remove-error-once','callback-short-P','overwrite-refused'
];
async function test(name){
 const out=fs.mkdtempSync(path.join(os.tmpdir(),'queue-routes-selftest-'));
 const active=new Set(),commands=[];let running=true,uiPaused=false,pc=0x08804100,ticks=1000,phase=-1,stopNumber=0,closed=false,created=0;
 let maxActive=0,externalCommandIndex=null,removeFailures=0,statusCount=0;const messages=[];
 const stack=Buffer.from(Array.from({length:0x100},(_,i)=>i)),controller=Buffer.alloc(0x30,0x53),entry=Buffer.alloc(24);
 controller[0x2e]=name==='controller-raw-unknown-values'?255:0;controller[0x2f]=name==='controller-raw-unknown-values'?123:1;
 const controllerPointer=name==='controller-null'?0:name==='controller-sentinel'?0xdeadbeef:CTRL;
 entry.writeUInt32LE(1,8);entry.writeUInt32LE(C,0xc);entry.writeUInt32LE(P,0x10);entry.writeUInt32LE(N,0x14);
 if(name==='callback-fields-null-sentinel'){entry.writeUInt32LE(0,0xc);entry.writeUInt32LE(0xdeadbeef,0x10);entry.writeUInt32LE(0x0bfffffc,0x14);}
 const segments=[[0x08c3a680,pack([controllerPointer])],[BASE,moduleBytes],[SP,stack],[CTRL,controller],[E,entry],
  [C,Buffer.alloc(0x40,0xc1)],[P,Buffer.alloc(0x1a4,0xc2)],[N,Buffer.alloc(0x40,0xc3)]];
 const failing=!['all-routes-unticketed-resume','all-routes-ticketed-resume','zero-stops-running-status','range-zero-enqueue-controls-live',
  'burst-three-stops','gpr32','gpr36','controller-null','controller-sentinel','controller-raw-unknown-values',
  'callback-fields-null-sentinel','callback-entry-invalid'].includes(name);
 if(name==='overwrite-refused')fs.writeFileSync(path.join(out,'queue_routes.json'),'previous evidence');
 class MockWebSocket{
  static OPEN=1;
  constructor(url,protocol){created++;assert.equal(url,'ws://127.0.0.1:9900/debugger');assert.equal(protocol,'debugger.ppsspp.org');
   this.readyState=0;this.handlers=new Map();queueMicrotask(()=>{this.readyState=1;this.emit('open',{});});}
  addEventListener(event,fn,options={}){const a=this.handlers.get(event)||[];a.push({fn,once:options.once});this.handlers.set(event,a);}
  emit(event,value){for(const l of [...(this.handlers.get(event)||[])]){l.fn(value);if(l.once)this.handlers.set(event,this.handlers.get(event).filter(x=>x!==l));}}
  reply(raw){messages.push(raw);this.emit('message',{data:JSON.stringify(raw)});}
  stop(address,external=false){running=false;pc=address;ticks+=100;
   if(external)externalCommandIndex=commands.length;
   this.reply({event:'cpu.stepping',pc,ticks});
  }
  send(text){const q=JSON.parse(text);commands.push(q);const result={event:q.event,ticket:q.ticket};
   if(q.event==='cpu.resume'){
    assert(!running,'observer must never resume already-running CPU');
    if(name==='external-during-resume'){queueMicrotask(()=>this.stop(0x08804200,true));return;}
    if(name==='resume-unticketed-error'||name==='resume-ticketed-error'){
     running=true;queueMicrotask(()=>this.reply({event:'error',...(name.includes('ticketed')&&!name.includes('unticketed')?{ticket:q.ticket}:{}),error:'CPU not stepping injected'}));return;
    }
    running=true;
    if(name==='resume-no-ACK')return;
    queueMicrotask(()=>{
     this.reply({event:'cpu.resume',...(name==='all-routes-ticketed-resume'?{ticket:q.ticket}:{})});
     if(name==='burst-three-stops'&&active.size&&stopNumber<3){stopNumber++;this.stop([...active][0]);}
    });return;
   }
   if(q.event==='version')result.version='offline-queue-routes';
   else if(q.event==='cpu.breakpoint.list')result.breakpoints=name==='existing-active-BP'?[{address:0x08804100,enabled:true}]:name==='existing-disabled-target-BP'?[{address:order[1],enabled:false}]:[];
   else if(q.event==='cpu.breakpoint.add'){
    assert.equal(active.size,0,'single owned breakpoint invariant');active.add(q.address);maxActive=Math.max(maxActive,active.size);phase++;stopNumber=0;
    assert.equal(q.address,order[phase],'fixed phase order');
    if(name==='add-timeout-own-stop'){queueMicrotask(()=>this.stop(q.address));return;}
    if(name==='add-timeout-external-stop'){queueMicrotask(()=>this.stop(0x08804200,true));return;}
    if(name==='stray-unticketed-error')queueMicrotask(()=>this.reply({event:'error',error:'stray injected debugger error'}));
    else if(name==='external-phase-stop')queueMicrotask(()=>this.stop(0x08804200,true));
    else if(name!=='zero-stops-running-status'&&!(name==='range-zero-enqueue-controls-live'&&phase>0&&phase<6))queueMicrotask(()=>{stopNumber++;this.stop(q.address);});
   }else if(q.event==='cpu.breakpoint.remove'){
    assert(active.has(q.address),'remove only attempted owned breakpoint');
    if(name==='remove-error-once'&&removeFailures++===0){result.event='error';result.error='injected remove failure';}
    else active.delete(q.address);
   }else if(q.event==='cpu.status'){
    statusCount++;
    if(name==='status-timeout')return;
    if(name==='status-ticketed-error'){result.event='error';result.error='injected status failure';}
    else{
     if(name==='initial-external-stepping'&&statusCount===1){running=false;pc=0x08804200;}
     if(name==='initial-UI-paused'&&statusCount===1)uiPaused=true;
     if(running)ticks+=10;
     Object.assign(result,{stepping:!running,paused:uiPaused,pc,ticks});
     if(name==='invalid-status-bool')result.stepping='false';
     if(name==='invalid-status-ticks')result.ticks=1.5;
     if(name==='phase-tick-regression'&&statusCount===2)result.ticks=1;
    }
   }else if(q.event==='cpu.getAllRegs'){
    const g=Array(32).fill(0);for(let i=1;i<32;i++)g[i]=0x100+i;
    g[4]=phase===3||phase===4?(name==='callback-entry-invalid'?0:E):phase===5?CTRL:0x12345678;
    g[5]=0xabcdef01;g[6]=17;g[29]=name==='bad-SP'?0:SP;g[31]=0x08804008;
    if(name==='short-GPR')g.length=31;if(name==='bad-GPR-u32')g[4]=-1;
    if(name!=='gpr32'&&name!=='short-GPR')g.push(name==='bad-GPR-PC'?pc+4:pc,0,0);if(name==='gpr36')g.push(0);
    result.categories=[{name:'GPR',uintValues:g}];
   }else if(q.event==='memory.read'){
    const segment=segments.find(([a,b])=>q.address>=a&&q.address+q.size<=a+b.length);assert(segment,`missing fixture ${q.address.toString(16)}/${q.size}`);
    if(name==='stack-RPC-error'&&q.address===SP){result.event='error';result.error='injected stack read failure';}
    else{
     let b=Buffer.from(segment[1].subarray(q.address-segment[0],q.address-segment[0]+q.size));
     if(segment[0]===BASE){if(q.replacements!==false)b.writeUInt32LE(0x68001234,0);if(name==='bad-original-code'&&q.replacements===false)b[0]^=1;}
     if(name==='short-stack'&&q.address===SP||name==='short-controller'&&q.address===CTRL||name==='callback-short-P'&&q.address===P)b=b.subarray(0,b.length-1);
     result.base64=b.toString('base64');
    }
   }else if(q.event==='memory.disasm'){
    result.lines=[];
    for(let at=q.address;at<q.end;at+=at===q.address?8:4){const w=moduleBytes.readUInt32LE(at-BASE);result.lines.push({type:at===q.address?'macro':'opcode',address:at,addressSize:at===q.address?8:4,encoding:w,
     ...(at===q.address?{macroEncoding:[w,moduleBytes.readUInt32LE(at+4-BASE)]}:{})});}
    if(name==='bad-disasm-code')result.lines[0].macroEncoding[1]^=1;
    if(name==='missing-disasm-coverage')result.lines.pop();
   }else assert(['input.buttons.send','input.analog.send'].includes(q.event),`unallowed RPC ${q.event}`);
   queueMicrotask(()=>this.reply(result));
  }
  close(){closed=true;this.readyState=3;this.emit('close',{});}
 }
 const env={QUEUE_ROUTES_OUT_DIR:out,QUEUE_PHASE_MS:'100',QUEUE_PHASE_STOPS:name==='burst-three-stops'?'3':'1',QUEUE_RPC_TIMEOUT_MS:'60',QUEUE_RESUME_TIMEOUT_MS:'60',
  QUEUE_BUTTONS_JSON:JSON.stringify({square:true,rtrigger:true}),QUEUE_ANALOG_JSON:JSON.stringify({stick:'left',x:0.3,y:-0.4})};
 const fakeProcess={env,on(){},exitCode:0},consoleErrors=[];
 const within=filename=>{const rel=path.relative(out,path.resolve(filename));assert(!rel.startsWith('..')&&!path.isAbsolute(rel),'VM writes outside temporary output');};
 const guardedFS={...fs,writeFileSync(p,...args){within(p);return fs.writeFileSync(p,...args);},mkdirSync(p,...args){within(p);return fs.mkdirSync(p,...args);}};
 const limitedRequire=name=>{assert(['fs','path','crypto'].includes(name));return name==='fs'?guardedFS:require(name);};
 try{
  await vm.runInNewContext(source,{require:limitedRequire,Buffer,WebSocket:MockWebSocket,process:fakeProcess,__dirname,__filename:filename,
   console:{log(){},error(x){consoleErrors.push(String(x));}},setTimeout,clearTimeout,Date,Promise});
  if(name==='overwrite-refused'){
   assert.equal(created,0);assert.equal(fs.readFileSync(path.join(out,'queue_routes.json'),'utf8'),'previous evidence');assert.equal(fakeProcess.exitCode,1);
   console.log(`PASS ${name}: no connection; prior evidence unchanged`);return;
  }
  const r=JSON.parse(fs.readFileSync(path.join(out,'queue_routes.json'),'utf8'));
  assert.equal(fakeProcess.exitCode,failing?1:0,`${name}: ${r.failure}`);assert.equal(active.size,0);assert(maxActive<=1);assert(closed);
  assert.equal(r.ownedBP,null);assert.equal(r.cleanup.errors.length,0);assert(r.cleanup.buttonsReleased&&r.cleanup.analogReleased&&r.cleanup.ownedBreakpointRemoved);
  assert.equal(r.producer.sha256,hash(Buffer.from(source)));assert.equal(r.exactWeaponSelection,false);assert.equal(r.muzzleProven,false);assert.equal(r.GEConsumerProven,false);assert.equal(r.semanticName,null);
  assert(!commands.some(q=>['cpu.stepping','cpu.setReg','memory.write'].includes(q.event)));
  const buttons=commands.filter(q=>q.event==='input.buttons.send').at(-1),analog=commands.filter(q=>q.event==='input.analog.send').at(-1);
  assert(Object.values(buttons.buttons).every(x=>x===false));assert.equal(analog.x,0);assert.equal(analog.y,0);
  if(externalCommandIndex!==null)assert(!commands.slice(externalCommandIndex).some(q=>q.event==='cpu.resume'),'never resume external pause');
  if(failing){
   assert(r.failure,name);
   if(['resume-unticketed-error','resume-ticketed-error','stray-unticketed-error','status-ticketed-error','stack-RPC-error','remove-error-once'].includes(name))assert(r.errors.length>0,'retain debugger raw errors');
   if(name.startsWith('resume-')){assert(r.resumes.some(x=>x.error));assert(r.cleanup.resumeSkippedAfterError);assert.equal(commands.filter(x=>x.event==='cpu.resume').length,1);}
   if(name.startsWith('initial-')){assert.equal(commands.filter(x=>x.event==='cpu.resume').length,0);assert(r.cleanup.externalPausePreserved);}
   if(['existing-active-BP','existing-disabled-target-BP','bad-original-code','bad-disasm-code','missing-disasm-coverage'].includes(name))assert.equal(commands.filter(x=>x.event==='cpu.breakpoint.add').length,0);
   console.log(`PASS ${name}: failure retained, single-BP and cleanup/external pause`);return;
  }
  assert.equal(r.failure,null);assert.equal(r.phases.length,7);assert.equal(r.codeIdentity.checks.length,6);assert(r.codeIdentity.verified);
  assert.deepEqual(r.phases.map(x=>x.pc),order);
  let total=0;
  for(const phaseReport of r.phases){
   assert.equal(phaseReport.statusSamples.length,2);assert.equal(phaseReport.statusSamples[0].label,'before');assert.equal(phaseReport.statusSamples[1].label,'after');
   for(const s of phaseReport.statusSamples){assert(s.wallRequested<=s.wallAcknowledged);assert.equal(s.ack.event,'cpu.status');assert.equal(s.ack.stepping,false);assert.equal(s.ack.paused,false);assert(Number.isSafeInteger(s.ack.ticks));}
   const expected=name==='zero-stops-running-status'?0:name==='range-zero-enqueue-controls-live'&&phaseReport.index>0&&phaseReport.index<6?0:name==='burst-three-stops'?3:1;
   assert.equal(phaseReport.ownStops,expected);assert.equal(phaseReport.rows.length,expected);total+=expected;
   assert(phaseReport.bpRemovedAt>=phaseReport.armedAt);assert(phaseReport.wallFinished>=phaseReport.wallStarted);
   for(const row of phaseReport.rows){
    assert.equal(row.status,'read');assert.equal(row.gpr.length,32);assert.equal(row.pc,phaseReport.pc);assert.equal(row.gpr[29],SP);
    assert.equal(row.stack.raw.bytes,256);assert(fs.readFileSync(row.stack.raw.file).equals(stack));
    assert.equal(hash(fs.readFileSync(row.registerReply.file)),row.registerReply.sha256);
    assert.equal(row.controller.globalAddress,0x08c3a680);assert.equal(row.controller.globalRaw.bytes,4);
    if(name==='controller-null'||name==='controller-sentinel')assert.equal(row.controller.status,'invalid_pointer_unfollowed');
    else{assert.equal(row.controller.status,'read_at_own_stop');assert(fs.readFileSync(row.controller.raw.file).equals(controller));assert.equal(row.controller.rawByte2e,controller[0x2e]);assert.equal(row.controller.rawByte2f,controller[0x2f]);}
    if(phaseReport.name.startsWith('entry_callback')){
     if(name==='callback-entry-invalid')assert.equal(row.callbackEntry.status,'invalid_pointer_unfollowed');
     else{assert.equal(row.callbackEntry.raw.bytes,24);for(const field of Object.values(row.callbackEntry.fields)){
      if(name==='callback-fields-null-sentinel')assert.equal(field.status,'invalid_pointer_unfollowed');else{assert.equal(field.status,'read');assert.equal(hash(fs.readFileSync(field.raw.file)),field.raw.sha256);}
     }}
    }
   }
  }
  assert.equal(r.resumes.length,total);assert(r.resumes.every(x=>x.ack&&x.wallAcknowledged>=x.wallRequested));
  assert.equal(commands.filter(x=>x.event==='cpu.resume').length,total,'resume only a real own stop');
  assert.equal(commands.filter(x=>x.event==='memory.read'&&x.address===0x08c3a680).length,total,'controller only own-stop snapshots');
  for(const check of r.codeIdentity.checks){assert(fs.readFileSync(check.original.file).equals(fs.readFileSync(check.expected.file)));assert(fs.readFileSync(check.decoded.file).equals(fs.readFileSync(check.expected.file)));}
  console.log(`PASS ${name}: seven phases, full status ACKs/raw stop windows, owned resumes`);
 }finally{
  const resolved=path.resolve(out),rel=path.relative(path.resolve(os.tmpdir()),resolved);assert(rel&&!rel.startsWith('..')&&!path.isAbsolute(rel)&&path.basename(resolved).startsWith('queue-routes-selftest-'));
  fs.rmSync(resolved,{recursive:true,force:true});
 }
}
(async()=>{for(const name of cases)await test(name);assert.equal(hash(fs.readFileSync(filename)),hash(Buffer.from(source)));
 console.log(JSON.stringify({schema:'weapon-queue-route-offline-selftest/v1',passed:true,scenarios:cases.length,producerSHA256:hash(Buffer.from(source)),selftestSHA256:hash(fs.readFileSync(__filename)),networkUsed:false}));
})().catch(error=>{console.error(error.stack||error);process.exitCode=1;});
