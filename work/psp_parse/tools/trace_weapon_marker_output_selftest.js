// Offline VM + MockWebSocket only. No network, emulator process or desktop API.
const fs=require('fs'),path=require('path'),os=require('os'),vm=require('vm'),assert=require('assert');
const ENTRY=0x08b44580,RETURN=0x08b3e62c,BASE=0x08804000;
async function test(scenario){
  const root=path.resolve(__dirname,'..');
  const snapshot=JSON.parse(fs.readFileSync(path.join(root,'out/AYA_BONE_GE_ACTIONS/slot0_fire_reverse120_world60/weapon_metadata_snapshot.json'),'utf8'));
  const moduleBytes=fs.readFileSync(path.join(root,'raw/ULJM05798_module_08804000.bin'));
  const pack=values=>{const b=Buffer.alloc(values.length*4);values.forEach((v,i)=>b.writeUInt32LE(v>>>0,i*4));return b;};
  const matrix=values=>{const b=Buffer.alloc(64);values.forEach((v,i)=>b.writeFloatLE(v,i*4));return b;};
  const identity=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1];
  const postWorld=matrix([1,0,0,0,0,1,0,0,0,0,1,0,100,200,300,1]);
  const postSource40=matrix([2,0,0,0,0,2,0,0,0,0,2,0,-3,4,5,1]);
  const actual=matrix([2,0,0,0,0,2,0,0,0,0,2,0,97,204,305,1]);
  const sp=0x09ff0000,output=sp+0x40,actor=Buffer.alloc(0x1000),stack=Buffer.alloc(0x240);
  actor.writeUInt32LE(snapshot.sourceBase,0x3c4);actor.writeUInt32LE(snapshot.metadata,0x3e8);matrix(identity).copy(actor,0x220);
  const sources=Buffer.concat(snapshot.records.map(r=>pack(r.words)));matrix(identity).copy(sources,0x130+0x40);
  const expectedPreSourcesAll=Buffer.from(sources);
  const segments=[[BASE,moduleBytes],[snapshot.object,actor],[snapshot.metadata,pack(snapshot.header)],
    [snapshot.drawTable,pack(snapshot.drawWords)],[snapshot.sourceBase,sources],[sp,stack]];
  const out=fs.mkdtempSync(path.join(os.tmpdir(),'weapon-output-selftest-'));
  const commands=[],active=new Set();let phase='setup',foreignSent=false,mutated=false,maxActive=0,externalAt=null;
  const mutate=()=>{if(mutated)return;postWorld.copy(actor,0x220);postSource40.copy(sources,0x130+0x40);
    // Change unselected records too: a copied entry snapshot must not pass as post.
    sources.writeFloatLE(7,0xc0+0x30);sources.writeFloatLE(44,2*0x130+0x40+0x30);
    actual.copy(stack,0x40);mutated=true;};
  class MockWebSocket{
    static OPEN=1;
    constructor(){this.readyState=0;this.handlers=new Map();queueMicrotask(()=>{this.readyState=1;this.emit('open',{});});}
    addEventListener(event,fn,options={}){const a=this.handlers.get(event)||[];a.push({fn,once:options.once});this.handlers.set(event,a);}
    emit(event,value){for(const l of [...(this.handlers.get(event)||[])]){l.fn(value);if(l.once)this.handlers.set(event,this.handlers.get(event).filter(v=>v!==l));}}
    stop(pc,ticks){this.emit('message',{data:JSON.stringify({event:'cpu.stepping',pc,ticks})});}
    send(text){
      const q=JSON.parse(text);commands.push(q);
      if(q.event==='cpu.resume'){
        if(active.has(RETURN)){
          if(scenario==='missing-return')return;
          queueMicrotask(()=>{
            if(scenario==='external-stop'){externalAt=commands.length;this.stop(0x08804100,200);return;}
            if(scenario==='foreign-return'&&!foreignSent){foreignSent=true;phase='foreign';this.stop(RETURN,150);return;}
            mutate();phase='return';this.stop(RETURN,200);
          });
        }
        return;
      }
      const result={event:q.event,ticket:q.ticket};
      if(q.event==='version')result.version='offline-fixture';
      else if(q.event==='cpu.breakpoint.list')result.breakpoints=scenario==='existing-bp'?[{address:ENTRY,enabled:true}]:[];
      else if(q.event==='cpu.breakpoint.add'){
        assert.equal(active.size,0,'second active BP is forbidden');active.add(q.address);maxActive=Math.max(maxActive,active.size);
        if(q.address===ENTRY){phase='entry';queueMicrotask(()=>this.stop(ENTRY,100));}
      }else if(q.event==='cpu.breakpoint.remove'){assert(active.has(q.address));active.delete(q.address);}
      else if(q.event==='memory.read'){
        if(scenario==='return-read-error'&&phase==='return'&&q.address===output){result.event='error';result.error='injected read error';}
        else{
          const segment=segments.find(([a,b])=>q.address>=a&&q.address+q.size<=a+b.length);assert(segment,`missing ${q.address.toString(16)} size ${q.size}`);
          const b=Buffer.from(segment[1].subarray(q.address-segment[0],q.address-segment[0]+q.size));
          if(q.address===ENTRY||q.address===0x08b3e610||q.address===RETURN){
            if(q.replacements!==false)b.writeUInt32LE(0x68012345,0);
            if((scenario==='bad-initial-code'&&q.address===ENTRY||scenario==='bad-return-code'&&q.address===RETURN)&&q.replacements===false)b.writeUInt32LE(0x12345678,0);
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
      }else if(q.event==='cpu.getAllRegs'){
        const g=Array(32).fill(0);g[4]=phase==='entry'?output:0xdead0000;g[5]=phase==='entry'?snapshot.object:0;g[6]=scenario==='no-weapon'?5:1;
        g[16]=0x1234;g[17]=0x5678;g[18]=0x9abc;g[29]=phase==='foreign'?sp+0x100:sp;g[31]=scenario==='bad-return-ra'&&phase==='return'?RETURN+4:RETURN;
        if(scenario==='paired-35')g.push(RETURN,0x12345678,0xffffffff);
        if(scenario==='paired-36')g.push(RETURN,0x12345678,0xffffffff,0);
        if(scenario==='short-gpr')g.length=31;
        if(scenario==='negative-gpr')g[4]=-1;
        if(scenario==='fractional-gpr')g[6]=1.25;
        if(scenario==='overflow-gpr')g[29]=0x100000000;
        result.categories=[{name:'MIPS GPR',uintValues:g}];
      }else assert(['input.buttons.send','input.analog.send'].includes(q.event),`unknown RPC ${q.event}`);
      queueMicrotask(()=>this.emit('message',{data:JSON.stringify(result)}));
    }
    close(){this.readyState=3;this.emit('close',{});}
  }
  const fakeProcess={env:{MARKER_OUTPUT_OUT_DIR:out,MARKER_MAX_STOPS:'1',MARKER_MAX_ROWS:'1',MARKER_DURATION_MS:'1000',MARKER_RETURN_TIMEOUT_MS:scenario==='missing-return'?'60':'1000',
    MARKER_BUTTONS_JSON:JSON.stringify({square:true,select:true}),MARKER_ANALOG_JSON:JSON.stringify({stick:'left',x:0.2,y:0.3})},on(){},exitCode:0};
  try{
    const promise=vm.runInNewContext(fs.readFileSync(path.join(__dirname,'trace_weapon_marker_output.js'),'utf8'),{require,Buffer,WebSocket:MockWebSocket,process:fakeProcess,__dirname,
      console:{log(){},error:console.error},setTimeout,clearTimeout,Date,Promise});await promise;
    const report=JSON.parse(fs.readFileSync(path.join(out,'marker_output.json'),'utf8'));
    const fail=['existing-bp','bad-initial-code','bad-return-code','bad-return-ra','missing-return','return-read-error','external-stop','short-gpr','negative-gpr','fractional-gpr','overflow-gpr'].includes(scenario);
    assert.equal(fakeProcess.exitCode,fail?1:0);assert.equal(active.size,0);assert(maxActive<=1);assert.equal(report.ownedBP,null);
    assert.equal(report.cleanup.errors.length,0);assert(report.cleanup.buttonsReleased&&report.cleanup.analogReleased);
    const lastButtons=commands.filter(q=>q.event==='input.buttons.send').at(-1).buttons;assert(Object.values(lastButtons).every(v=>v===false));assert.equal(lastButtons.select,false);
    const lastAnalog=commands.filter(q=>q.event==='input.analog.send').at(-1);assert.equal(lastAnalog.x,0);assert.equal(lastAnalog.y,0);
    if(fail){assert(report.failure);assert.equal(report.rows.length,0);
      if(scenario==='external-stop')assert(!commands.slice(externalAt).some(q=>q.event==='cpu.resume'),'must preserve external pause');
      if(['existing-bp','bad-initial-code'].includes(scenario))assert.equal(commands.filter(q=>q.event==='cpu.breakpoint.add').length,0);
      if(scenario==='bad-return-code')assert(!commands.some(q=>q.event==='cpu.breakpoint.add'&&q.address===RETURN));
      console.log(`PASS ${scenario}: fail closed, one-BP ownership, release and cleanup`);return;}
    if(['no-weapon','wrong-geometry'].includes(scenario)){assert.equal(report.rows.length,0);assert.equal(report.helperStopCount,1);assert.equal(report.returnStopCount,0);console.log(`PASS ${scenario}: no false pairing`);return;}
    assert.equal(report.rows.length,1);const row=report.rows[0];assert.equal(row.entryTicks,100);assert.equal(row.returnTicks,200);
    const expectedCategoryLength=scenario==='paired-35'?35:scenario==='paired-36'?36:32;
    assert(report.gprCategoryDiagnostics.every(d=>d.name==='MIPS GPR'&&d.length===expectedCategoryLength));
    assert.equal(row.entryGPR.length,32);assert.equal(row.returnGPR.length,32);
    assert(row.returnSPVerified&&row.returnRAVerified);assert.equal(row.output,output);assert.equal(row.actualOutput.bytes,64);
    assert.deepEqual(fs.readFileSync(row.actualOutput.file),actual);assert.deepEqual(fs.readFileSync(row.postWorld.file),postWorld);assert.deepEqual(fs.readFileSync(row.postSource40.file),postSource40);
    assert.equal(row.preSourcesAll.bytes,0x390);assert.equal(row.postSourcesAll.bytes,0x390);
    const preAll=fs.readFileSync(row.preSourcesAll.file),postAll=fs.readFileSync(row.postSourcesAll.file);
    assert.deepEqual(preAll,expectedPreSourcesAll);assert.deepEqual(postAll,sources);
    assert.deepEqual(preAll.subarray(0x130,0x260),fs.readFileSync(row.preSource.file));
    assert.deepEqual(postAll.subarray(0x130,0x260),fs.readFileSync(row.postSource.file));
    assert.equal(postAll.readFloatLE(0xc0+0x30),7);assert.equal(postAll.readFloatLE(2*0x130+0x40+0x30),44);
    assert.equal(row.comparison.world_times_source40.max_abs,0);assert(row.comparison.source40_times_world.max_abs>100);assert.equal(row.semanticName,null);
    assert.equal(report.codeIdentity.checks.length,3);assert(report.codeIdentity.verified);
    const operations=commands.filter(q=>['cpu.breakpoint.add','cpu.breakpoint.remove'].includes(q.event)).map(q=>[q.event,q.address]);
    assert.deepEqual(operations,[['cpu.breakpoint.add',ENTRY],['cpu.breakpoint.remove',ENTRY],['cpu.breakpoint.add',RETURN],['cpu.breakpoint.remove',RETURN]]);
    if(scenario==='foreign-return'){assert.equal(report.foreignReturns.length,1);assert.equal(report.returnStopCount,2);}
    console.log(`PASS ${scenario}: queued early entry, alternating BP, saved output ptr, post-update matrices and exact known product`);
  }finally{
    const resolved=path.resolve(out),relative=path.relative(path.resolve(os.tmpdir()),resolved);
    assert(relative&&!relative.startsWith('..')&&!path.isAbsolute(relative)&&path.basename(resolved).startsWith('weapon-output-selftest-'));
    fs.rmSync(resolved,{recursive:true,force:true});
  }
}
(async()=>{for(const scenario of ['paired','paired-35','paired-36','short-gpr','negative-gpr','fractional-gpr','overflow-gpr','foreign-return','no-weapon','wrong-geometry','existing-bp','bad-initial-code','bad-return-code','bad-return-ra','missing-return','return-read-error','external-stop'])await test(scenario);})().catch(e=>{console.error(e.stack||e);process.exitCode=1;});
