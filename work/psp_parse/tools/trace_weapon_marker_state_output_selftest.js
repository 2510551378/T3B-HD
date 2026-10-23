// Offline VM + MockWebSocket only: no network, emulator process or desktop API.
const fs=require('fs'),path=require('path'),os=require('os'),vm=require('vm'),assert=require('assert'),crypto=require('crypto');
const ENTRY=0x08b44580,RETURN=0x08b3e62c,GENERIC=0x08b630dc,STATE_A=0x08b63550,STATE_B=0x08b6379c,BASE=0x08804000;
const scenarios=['paired','paired-state-b','paired-35','paired-36','paired-signed-flags','short-gpr','negative-gpr','fractional-gpr','overflow-gpr',
  'no-weapon','wrong-geometry','existing-bp','disabled-state-bp','bad-initial-code','bad-return-code','bad-generic-code','bad-state-code','bad-disasm',
  'unknown-wrapper','unknown-generic','unknown-state','unknown-outer','wrong-p','wrong-flags','bad-helper-sp','bad-generic-sp','bad-state-sp',
  'bad-helper-ra','bad-generic-ra','bad-state-ra','bad-helper-saved','bad-generic-saved','bad-state-saved','generic-copy-mismatch','generic-flags-mismatch',
  'missing-helper','missing-generic','missing-state','helper-read-error','generic-read-error','state-read-error',
  'external-helper','external-generic','external-state','resource-null','resource-invalid','resource-read-error','add-ack-timeout','add-ack-timeout-own-stop','add-ack-timeout-external-stop',
  'fep-relocated','fep-relative','fep-once','fep-bad-base','fep-bad-header','fep-bad-offset8-pointer','fep-read-error','fep-state-identity-mismatch'];
async function test(scenario){
  const root=path.resolve(__dirname,'..');
  const snapshot=JSON.parse(fs.readFileSync(path.join(root,'out/AYA_BONE_GE_ACTIONS/slot0_fire_reverse120_world60/weapon_metadata_snapshot.json'),'utf8'));
  const moduleBytes=fs.readFileSync(path.join(root,'raw/ULJM05798_module_08804000.bin'));
  const pack=values=>{const b=Buffer.alloc(values.length*4);values.forEach((v,i)=>b.writeUInt32LE(v>>>0,i*4));return b;};
  const matrix=values=>{const b=Buffer.alloc(64);values.forEach((v,i)=>b.writeFloatLE(v,i*4));return b;};
  const identity=matrix([1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]);
  const postWorld=matrix([1,0,0,0,0,1,0,0,0,0,1,0,100,200,300,1]);
  const postSource40=matrix([2,0,0,0,0,2,0,0,0,0,2,0,-3,4,5,1]);
  const actual=matrix([2,0,0,0,0,2,0,0,0,0,2,0,97,204,305,1]);
  // Deliberately unequal: the sampler must not force the final state to the helper result.
  const finalMatrix=matrix([3,0,0,0,0,4,0,0,0,0,5,0,12,13,14,1]);
  const isFep=scenario.startsWith('fep-'),FEP_BASE=0x08d4d280;
  const H=0x09ff0000,P=0x097d2540,handle=0x09bd23c0,resourceAddress=isFep?FEP_BASE+0x48f0:0x09010000,flags=scenario==='paired-signed-flags'?0x80000060:0x60;
  const statePC=scenario==='paired-state-b'?STATE_B:STATE_A;
  const output=H+0x40,actor=Buffer.alloc(0x1000),stack=Buffer.alloc(0x3ac),state=Buffer.alloc(0x1a4),resource=Buffer.alloc(64);
  actor.writeUInt32LE(snapshot.sourceBase,0x3c4);actor.writeUInt32LE(snapshot.metadata,0x3e8);identity.copy(actor,0x220);
  const sources=Buffer.concat(snapshot.records.map(r=>pack(r.words)));identity.copy(sources,0x130+0x40);
  const expectedPreSourcesAll=Buffer.from(sources);
  const put=(offset,value)=>stack.writeUInt32LE(value>>>0,offset);
  put(0x80,H+0x210);put(0x84,0x08bbccd0);put(0x1fc,P+0x60);put(0x200,P);put(0x204,H+0x250);put(0x208,0x0913fcf0);put(0x20c,GENERIC);
  put(0x338,flags);put(0x33c,P);put(0x340,0x09110000);put(0x344,0x09120000);put(0x348,0x09130000);put(0x34c,0x09140000);
  put(0x350,0x09150000);put(0x354,0x09160000);put(0x358,0x09170000);put(0x35c,0);put(0x360,statePC);put(0x3a4,0x09180000);put(0x3a8,0x08b69aec);
  if(scenario==='unknown-generic')put(0x20c,GENERIC+4);
  if(scenario==='unknown-state')put(0x360,STATE_A+4);
  if(scenario==='unknown-outer')put(0x3a8,0x08804100);
  if(scenario==='wrong-p')put(0x200,P+4);
  if(scenario==='wrong-flags')put(0x338,flags+1);
  identity.copy(state,0x60);state.writeUInt32LE(handle,0x144);state.writeUInt32LE(0,0x148);state.writeInt16LE(1,0x14c);state.writeUInt32LE(flags,0x154);
  const resourcePointer=scenario==='resource-null'?0:scenario==='resource-invalid'?0x01234567:resourceAddress;
  state.writeUInt32LE(resourcePointer,0x198);
  state.writeUInt32LE(scenario==='fep-bad-base'?0x0c000000:FEP_BASE,0x190);state.writeUInt32LE(FEP_BASE+0xfb4+(scenario==='fep-state-identity-mismatch'?4:0),0x194);
  const fep=Buffer.alloc(0x5000),relocation=scenario==='fep-relative'?0:FEP_BASE;
  fep.writeUInt32LE(scenario==='fep-bad-header'?0:0x07504546,0);fep.writeUInt32LE(0x00090001,4);
  fep.writeUInt32LE(relocation+(scenario==='fep-bad-offset8-pointer'?0x4c:0x48),8);fep.writeUInt32LE(0x01ff0000,0xc);fep.writeUInt32LE(0xbe240,0x14);
  fep.writeUInt16LE(93,0x1c);fep.writeUInt16LE(93,0x1e);fep.writeUInt32LE(relocation+0x50,0x28);fep.writeUInt32LE(relocation+0x1c4,0x2c);
  for(const [offset,value] of [[0x30,0x338],[0x34,0x3f4],[0x38,0x4bc],[0x3c,0x588],[0x40,0x590],[0x44,0x598],[0x4c,0x5a0]])fep.writeUInt32LE(relocation+value,offset);
  fep.writeUInt32LE(relocation+0xab8,0x60);fep.writeUInt32LE(relocation+0xfb4,0x1d4);
  pack([0x286800,0x10004,relocation+0x48e0]).copy(fep,0xab8);fep.writeUInt32LE(relocation+0x48f0,0x48e0);
  pack([2,2,0,3,0x40001,0xc000e,1,0x10b34,0x10b38,0x10b48,0x10b64,0x10b94,0x10b98]).copy(fep,0xfb4);
  Buffer.from('0068280001000000000002010000000000000000000000800000008000000000000000000000008000000080000000000000803f0000803f0000803f00000000','hex').copy(fep,0x48f0);
  const segments=[[BASE,moduleBytes],[snapshot.object,actor],[snapshot.metadata,pack(snapshot.header)],
    [snapshot.drawTable,pack(snapshot.drawWords)],[snapshot.sourceBase,sources],[H,stack],[P,state],[handle,pack([snapshot.object])],
    ...(isFep?[[FEP_BASE,fep]]:[[resourceAddress,resource]])];
  const out=fs.mkdtempSync(path.join(os.tmpdir(),'weapon-state-selftest-'));
  const commands=[],active=new Set();let phase='setup',maxActive=0,externalAt=null,helperMutated=false,entrySerial=0;
  const gprAt=()=>{
    const g=Array(32).fill(0);g[4]=phase==='entry'?output:0xdead0000;g[5]=phase==='entry'?snapshot.object:0;g[6]=scenario==='no-weapon'?5:1;
    g[16]=H+0x1b0;g[17]=1;g[18]=handle;g[19]=0x0913fcf0;g[20]=P+0x10;g[21]=P+0x90;g[22]=handle;g[23]=0;g[30]=(flags>>16)>>>0;g[29]=H;g[31]=RETURN;
    if(phase==='generic'){
      g[16]=P+0x60;g[17]=P;g[18]=H+0x250;g[19]=stack.readUInt32LE(0x208);g[29]=H+0x210;g[31]=GENERIC;
    }
    if(phase==='state'){
      for(const [reg,offset] of [[16,0x33c],[17,0x340],[18,0x344],[19,0x348],[20,0x34c],[21,0x350],[22,0x354],[23,0x358],[30,0x35c]])g[reg]=stack.readUInt32LE(offset);
      g[29]=H+0x370;g[31]=statePC;
    }
    if(scenario==='unknown-wrapper'&&phase==='entry')g[31]=RETURN+4;
    if(scenario===`bad-${phase}-sp`)g[29]+=4;
    if(scenario===`bad-${phase}-ra`)g[31]+=4;
    if(scenario===`bad-${phase}-saved`)g[19]+=4;
    if(scenario==='paired-35')g.push(RETURN,0x12345678,0xffffffff);
    if(scenario==='paired-36')g.push(RETURN,0x12345678,0xffffffff,0);
    if(scenario==='short-gpr')g.length=31;
    if(scenario==='negative-gpr')g[4]=-1;
    if(scenario==='fractional-gpr')g[6]=1.25;
    if(scenario==='overflow-gpr')g[29]=0x100000000;
    return g;
  };
  const mutate=stage=>{
    if(stage==='helper'&&!helperMutated){
      postWorld.copy(actor,0x220);postSource40.copy(sources,0x130+0x40);
      sources.writeFloatLE(7,0xc0+0x30);sources.writeFloatLE(44,2*0x130+0x40+0x30);actual.copy(stack,0x40);helperMutated=true;
    }
    if(stage==='generic'){
      actual.copy(stack,0x210);if(scenario==='generic-copy-mismatch')stack[0x210]^=1;
      // This was zero at entry and must be captured freshly at the generic pause.
      matrix([7,0,0,0,0,8,0,0,0,0,9,0,10,11,12,1]).copy(stack,0x250);
      if(scenario==='generic-flags-mismatch')put(0x338,flags+1);
    }
    if(stage==='state')finalMatrix.copy(state,0x60);
    state.writeUInt32LE({helper:1,generic:2,state:3}[stage]||0,0x1a0);if(!isFep)resource.fill({helper:1,generic:2,state:3}[stage]||0);
  };
  class MockWebSocket{
    static OPEN=1;
    constructor(){this.readyState=0;this.handlers=new Map();queueMicrotask(()=>{this.readyState=1;this.emit('open',{});});}
    addEventListener(event,fn,options={}){const a=this.handlers.get(event)||[];a.push({fn,once:options.once});this.handlers.set(event,a);}
    emit(event,value){for(const l of [...(this.handlers.get(event)||[])]){l.fn(value);if(l.once)this.handlers.set(event,this.handlers.get(event).filter(v=>v!==l));}}
    stop(pc,ticks){this.emit('message',{data:JSON.stringify({event:'cpu.stepping',pc,ticks})});}
    send(text){
      const q=JSON.parse(text);commands.push(q);
      if(q.event==='cpu.resume'){
        const pc=[...active][0],stage=pc===RETURN?'helper':pc===GENERIC?'generic':[STATE_A,STATE_B].includes(pc)?'state':null;
        if(stage){
          if(scenario===`missing-${stage}`)return;
          queueMicrotask(()=>{
            if(scenario===`external-${stage}`){externalAt=commands.length;this.stop(0x08804100,200);return;}
            mutate(stage);phase=stage;this.stop(pc,{helper:200,generic:300,state:400}[stage]+(entrySerial-1)*400);
          });
        }
        return;
      }
      const result={event:q.event,ticket:q.ticket};
      if(q.event==='version')result.version='offline-fixture';
      else if(q.event==='cpu.breakpoint.list')result.breakpoints=scenario==='existing-bp'?[{address:ENTRY,enabled:true}]:scenario==='disabled-state-bp'?[{address:STATE_B,enabled:false}]:[];
      else if(q.event==='cpu.breakpoint.add'){
        assert.equal(active.size,0,'a second owned active BP is forbidden');active.add(q.address);maxActive=Math.max(maxActive,active.size);
        if(scenario.startsWith('add-ack-timeout')){
          if(scenario==='add-ack-timeout-own-stop'){phase='entry';queueMicrotask(()=>this.stop(ENTRY,100));}
          if(scenario==='add-ack-timeout-external-stop')queueMicrotask(()=>{externalAt=commands.length;this.stop(0x08804100,100);});
          return;
        }
        // Deliver entry before add ACK, exercising the stepping queue.
        if(q.address===ENTRY){phase='entry';entrySerial++;queueMicrotask(()=>this.stop(ENTRY,100+(entrySerial-1)*400));}
      }else if(q.event==='cpu.breakpoint.remove'){assert(active.has(q.address));active.delete(q.address);}
      else if(q.event==='memory.read'){
        const readError=scenario==='helper-read-error'&&phase==='helper'&&q.address===output||
          scenario==='generic-read-error'&&phase==='generic'&&q.address===H+0x210||
          scenario==='state-read-error'&&phase==='state'&&q.address===P||scenario==='resource-read-error'&&q.address===resourceAddress||scenario==='fep-read-error'&&q.address===FEP_BASE+0x48e0;
        if(readError){result.event='error';result.error='injected read error';}
        else{
          const segment=segments.find(([a,b])=>q.address>=a&&q.address+q.size<=a+b.length);assert(segment,`missing ${q.address.toString(16)} size ${q.size}`);
          const b=Buffer.from(segment[1].subarray(q.address-segment[0],q.address-segment[0]+q.size));
          const isCode=q.address>=BASE&&q.address+q.size<=BASE+moduleBytes.length;
          if(isCode){
            if(q.replacements!==false)b.writeUInt32LE(0x68012345,0);
            const badCode=scenario==='bad-initial-code'&&q.address===ENTRY||scenario==='bad-return-code'&&q.address===RETURN||
              scenario==='bad-generic-code'&&q.address===GENERIC||scenario==='bad-state-code'&&q.address===statePC;
            if(badCode&&q.replacements===false)b.writeUInt32LE(0x12345678,0);
          }
          if(scenario==='wrong-geometry'&&q.size===243*16)b[0]^=1;
          result.base64=b.toString('base64');
        }
      }else if(q.event==='memory.disasm'){
        result.lines=[];
        for(let a=q.address;a<q.end;a+=a===q.address?8:4){
          const first=moduleBytes.readUInt32LE(a-BASE);result.lines.push({type:a===q.address?'macro':'opcode',address:a,addressSize:a===q.address?8:4,
            encoding:first,macroEncoding:a===q.address?[first,moduleBytes.readUInt32LE(a+4-BASE)]:null});
        }
        if(scenario==='bad-disasm')result.lines[0].macroEncoding[1]^=1;
      }else if(q.event==='cpu.getAllRegs')result.categories=[{name:'MIPS GPR',uintValues:gprAt()}];
      else assert(['input.buttons.send','input.analog.send'].includes(q.event),`unknown RPC ${q.event}`);
      queueMicrotask(()=>this.emit('message',{data:JSON.stringify(result)}));
    }
    close(){this.readyState=3;this.emit('close',{});}
  }
  const fakeProcess={env:{MARKER_STATE_OUT_DIR:out,MARKER_MAX_STOPS:scenario==='fep-once'?'2':'1',MARKER_MAX_ROWS:scenario==='fep-once'?'2':'1',MARKER_DURATION_MS:'1000',MARKER_STAGE_TIMEOUT_MS:'60',
    MARKER_BUTTONS_JSON:JSON.stringify({square:true,select:true}),MARKER_ANALOG_JSON:JSON.stringify({stick:'left',x:0.2,y:0.3})},on(){},exitCode:0};
  if(isFep)fakeProcess.env.MARKER_FEP_PROBE='1';
  // Only shorten the injected missing-ACK timer; the sampler still exercises its actual timeout/cleanup code.
  const mockTimeout=(fn,ms,...args)=>setTimeout(fn,scenario.startsWith('add-ack-timeout')&&ms===10000?60:ms,...args);
  try{
    const filename=path.join(__dirname,'trace_weapon_marker_state_output.js');
    const promise=vm.runInNewContext(fs.readFileSync(filename,'utf8'),{require,Buffer,WebSocket:MockWebSocket,process:fakeProcess,__dirname,__filename:filename,
      console:{log(){},error:console.error},setTimeout:mockTimeout,clearTimeout,Date,Promise});await promise;
    const report=JSON.parse(fs.readFileSync(path.join(out,'marker_state_output.json'),'utf8'));
    const success=['paired','paired-state-b','paired-35','paired-36','paired-signed-flags','resource-null','resource-invalid','resource-read-error','fep-relocated','fep-relative','fep-once'].includes(scenario),noRows=['no-weapon','wrong-geometry'].includes(scenario);
    assert.equal(fakeProcess.exitCode,success||noRows?0:1,`${scenario}: exit status`);assert.equal(active.size,0);assert(maxActive<=1);assert.equal(report.ownedBP,null);
    assert.equal(report.producer.file,path.resolve(filename));assert.equal(report.producer.sha256,crypto.createHash('sha256').update(fs.readFileSync(filename)).digest('hex'));
    if(!isFep){assert.equal(report.fepProbe.enabled,false);assert.equal(report.fepProbe.status,'disabled');assert(!commands.some(q=>q.event==='memory.read'&&q.address>=FEP_BASE&&q.address<FEP_BASE+0x5000),'default must not add FEP reads');}
    assert.equal(report.cleanup.errors.length,0);assert(report.cleanup.buttonsReleased&&report.cleanup.analogReleased);
    const lastButtons=commands.filter(q=>q.event==='input.buttons.send').at(-1).buttons;assert(Object.values(lastButtons).every(v=>v===false));assert.equal(lastButtons.select,false);
    const lastAnalog=commands.filter(q=>q.event==='input.analog.send').at(-1);assert.equal(lastAnalog.x,0);assert.equal(lastAnalog.y,0);
    if(!success&&!noRows){
      assert(report.failure);assert.equal(report.rows.length,0);
      if(scenario.startsWith('external-')||scenario==='add-ack-timeout-external-stop')assert(!commands.slice(externalAt).some(q=>q.event==='cpu.resume'),'must preserve external pause');
      if(scenario==='add-ack-timeout-own-stop'){assert.equal(report.cleanup.unconsumedStops.length,1);assert.equal(report.cleanup.resumedOwnStop,true);assert.equal(commands.filter(q=>q.event==='cpu.resume').length,2);}
      if(['existing-bp','disabled-state-bp','bad-initial-code','bad-disasm'].includes(scenario))assert.equal(commands.filter(q=>q.event==='cpu.breakpoint.add').length,0);
      const failedCode={'bad-return-code':RETURN,'bad-generic-code':GENERIC,'bad-state-code':statePC}[scenario];
      if(failedCode)assert(!commands.some(q=>q.event==='cpu.breakpoint.add'&&q.address===failedCode));
      if(scenario==='generic-copy-mismatch')assert.equal(report.inFlight.genericReturn.helperOutputByteEqual,false);
      if(scenario.startsWith('missing-'))assert(report.failure.includes('timeout'));
      if(isFep){
        assert.equal(report.fepProbe.status,'failed');assert(report.fepProbe.failure);
        if(['fep-bad-base','fep-state-identity-mismatch'].includes(scenario))assert.equal(report.fepProbe.windows.length,0);
        if(scenario==='fep-bad-header'){assert.equal(report.fepProbe.windows.length,1);assert.equal(report.fepProbe.headerChecks[0].passed,false);}
        if(scenario==='fep-bad-offset8-pointer'){assert.equal(report.fepProbe.windows.length,1);const gate=report.fepProbe.headerChecks.find(c=>c.name==='offset8Pointer');assert(gate&&!gate.passed);}
        if(scenario==='fep-read-error'){assert.equal(report.fepProbe.windows.length,3);assert.equal(report.fepProbe.windows[2].status,'failed');}
      }
      console.log(`PASS ${scenario}: fail closed, one-BP ownership, release and cleanup`);return;
    }
    if(noRows){assert.equal(report.rows.length,0);assert.equal(report.helperStopCount,1);assert.equal(report.returnStopCount,0);console.log(`PASS ${scenario}: no false pairing`);return;}
    const expectedRows=scenario==='fep-once'?2:1;
    assert.equal(report.rows.length,expectedRows);const row=report.rows[0];assert.equal(row.entryTicks,100);assert.equal(row.returnTicks,200);assert.equal(row.genericReturn.ticks,300);assert.equal(row.stateReturn.ticks,400);
    const expectedCategoryLength=scenario==='paired-35'?35:scenario==='paired-36'?36:32;
    assert(report.gprCategoryDiagnostics.every(d=>d.name==='MIPS GPR'&&d.length===expectedCategoryLength));
    for(const g of [row.entryGPR,row.returnGPR,row.genericReturn.gpr,row.stateReturn.gpr])assert.equal(g.length,32);
    assert(row.returnSPVerified&&row.returnRAVerified);assert.equal(row.output,output);assert.equal(row.actualOutput.bytes,64);
    assert.deepEqual(fs.readFileSync(row.actualOutput.file),actual);assert.deepEqual(fs.readFileSync(row.postWorld.file),postWorld);assert.deepEqual(fs.readFileSync(row.postSource40.file),postSource40);
    assert.equal(row.preSourcesAll.bytes,0x390);assert.equal(row.postSourcesAll.bytes,0x390);
    const preAll=fs.readFileSync(row.preSourcesAll.file),postAll=fs.readFileSync(row.postSourcesAll.file);
    assert.deepEqual(preAll,expectedPreSourcesAll);assert.deepEqual(postAll,sources);
    assert.deepEqual(preAll.subarray(0x130,0x260),fs.readFileSync(row.preSource.file));assert.deepEqual(postAll.subarray(0x130,0x260),fs.readFileSync(row.postSource.file));
    assert.equal(postAll.readFloatLE(0xc0+0x30),7);assert.equal(postAll.readFloatLE(2*0x130+0x40+0x30),44);
    assert.equal(row.comparison.world_times_source40.max_abs,0);assert(row.comparison.source40_times_world.max_abs>100);assert.equal(row.semanticName,null);
    assert.equal(row.H,H);assert.equal(row.P,P);assert.equal(row.stateRA,statePC);assert.equal(row.outerRA,0x08b69aec);assert.equal(row.flags.savedWord,flags);assert.equal(row.entryStack.bytes,0x3ac);
    assert.equal(row.genericContext.bytes,0x160);assert.equal(row.genericReturn.helperOutputByteEqual,true);assert.deepEqual(fs.readFileSync(row.genericOutput.file),actual);
    const context=fs.readFileSync(row.genericContext.file);assert.equal(context.readFloatLE(0x40),7);assert.equal(context.readUInt32LE(0x128),flags);
    const entryStack=fs.readFileSync(row.entryStack.file);assert.equal(entryStack.readFloatLE(0x250),0,'generic context must be fresh, not copied from entry');
    assert.deepEqual(fs.readFileSync(row.stateFinal.file),finalMatrix);assert(!fs.readFileSync(row.stateFinal.file).equals(actual));
    for(const [field,value] of [['entryState',0],['stateAfterHelper',1],['stateAfterGeneric',2],['stateAfterReturn',3]])assert.equal(fs.readFileSync(row[field].file).readUInt32LE(0x1a0),value);
    for(const [i,stage] of ['entry','helperReturn','genericReturn','stateReturn'].entries()){
      const r=row.resourceIdentity[stage];assert.equal(r.fieldAddress,P+0x198);assert.equal(r.semanticName,null);
      const expectedStatus=scenario==='resource-null'?'null':scenario==='resource-invalid'?'out_of_range_or_unaligned':scenario==='resource-read-error'?'read_error':'read';assert.equal(r.status,expectedStatus);
      if(expectedStatus==='read')assert.deepEqual(fs.readFileSync(r.bytes.file),isFep?fep.subarray(0x48f0,0x4930):Buffer.alloc(64,i));
    }
    if(isFep){
      const probe=report.fepProbe;assert.equal(probe.status,'captured');assert.equal(probe.sample,0);assert.equal(probe.sourceState190,FEP_BASE);assert.equal(probe.sourceState194,FEP_BASE+0xfb4);assert.equal(probe.sourceState198,FEP_BASE+0x48f0);
      assert(probe.headerChecks.every(v=>v.passed));assert.equal(probe.windows.length,5);
      for(const [w,[offset,size]] of probe.windows.map((w,i)=>[w,[[0,0x400],[0xab8,12],[0x48e0,16],[0xfb4,64],[0x48f0,0xc0]][i]])){
        assert.equal(w.address,FEP_BASE+offset);assert.equal(w.offset,offset);assert.equal(w.size,size);assert.equal(w.status,'read');assert.deepEqual(fs.readFileSync(w.raw.file),fep.subarray(offset,offset+size));
        // Header/descriptor/list/table1 windows are each read once, even in a two-row capture.
        assert.equal(commands.filter(q=>q.event==='memory.read'&&q.address===w.address&&q.size===size).length,1);
      }
    }
    assert.equal(report.codeIdentity.checks.length,6+3*expectedRows);assert(report.codeIdentity.verified);assert.equal(report.firstStopTicks,100);assert.equal(report.lastStopTicks,400*expectedRows);
    const operations=commands.filter(q=>['cpu.breakpoint.add','cpu.breakpoint.remove'].includes(q.event)).map(q=>[q.event,q.address]);
    const expectedOperations=[['cpu.breakpoint.add',ENTRY],['cpu.breakpoint.remove',ENTRY],['cpu.breakpoint.add',RETURN],['cpu.breakpoint.remove',RETURN],
      ['cpu.breakpoint.add',GENERIC],['cpu.breakpoint.remove',GENERIC],['cpu.breakpoint.add',statePC],['cpu.breakpoint.remove',statePC]];
    assert.deepEqual(operations,Array.from({length:expectedRows},()=>expectedOperations).flat());
    console.log(`PASS ${scenario}: entry/helper/generic/state, fresh context, distinct final state, raw identity and cleanup`);
  }finally{
    const resolved=path.resolve(out),relative=path.relative(path.resolve(os.tmpdir()),resolved);
    assert(relative&&!relative.startsWith('..')&&!path.isAbsolute(relative)&&path.basename(resolved).startsWith('weapon-state-selftest-'));
    fs.rmSync(resolved,{recursive:true,force:true});
  }
}
(async()=>{for(const scenario of scenarios)await test(scenario);console.log(`PASS all ${scenarios.length} offline state-output scenarios`);})().catch(e=>{console.error(e.stack||e);process.exitCode=1;});
