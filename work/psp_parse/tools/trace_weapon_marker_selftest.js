// Offline protocol/ABI fixture only: no socket or PPSSPP process is opened.
const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const vm = require('vm');

async function test(scenario) {
  const root = path.resolve(__dirname,'..');
  const capture = path.join(root,'out/AYA_BONE_GE_ACTIONS/slot0_fire_reverse120_world60');
  const snapshot = JSON.parse(fs.readFileSync(path.join(capture,'weapon_metadata_snapshot.json'),'utf8'));
  const manifest = JSON.parse(fs.readFileSync(path.join(capture,'manifest_aligned.json'),'utf8'));
  const moduleBytes = fs.readFileSync(path.join(root,'raw/ULJM05798_module_08804000.bin'));
  const out = fs.mkdtempSync(path.join(os.tmpdir(),'weapon-marker-selftest-'));
  const pack = words => {const b=Buffer.alloc(words.length*4);words.forEach((v,i)=>b.writeUInt32LE(v>>>0,i*4));return b;};
  const actor = Buffer.alloc(0x1000), stack = Buffer.alloc(0x240), state = Buffer.alloc(0x150);
  const sp = 0x09ff0000, statePointer = 0x09d00000, handle = 0x09d10000;
  actor.writeUInt32LE(snapshot.sourceBase,0x3c4);actor.writeUInt32LE(snapshot.metadata,0x3e8);
  pack(manifest.frames[0].worldSource.weaponWords).copy(actor,0x220);
  stack.writeUInt32LE(0x08bbccd0,0x84);
  stack.writeUInt32LE(0x08b6314c,0x90+0x17c);
  stack.writeUInt32LE(statePointer,0x90+0x170);
  state.writeUInt32LE(handle,0x144);state.writeUInt32LE(0,0x148);state.writeInt16LE(1,0x14c);state.writeInt16LE(2,0x14e);
  const segments = [[0x08804000,moduleBytes],[snapshot.object,actor],[snapshot.metadata,pack(snapshot.header)],
    [snapshot.drawTable,pack(snapshot.drawWords)],[snapshot.sourceBase,Buffer.concat(snapshot.records.map(r=>pack(r.words)))],
    [sp,stack],[statePointer,state],[handle,pack([snapshot.object])]];
  const commands=[];
  class MockWebSocket {
    static OPEN=1;
    constructor(url) {assert(url.startsWith('ws://127.0.0.1:'));this.readyState=0;this.handlers=new Map();queueMicrotask(()=>{this.readyState=1;this.emit('open',{});});}
    addEventListener(event,fn,options={}) {const list=this.handlers.get(event)||[];list.push({fn,once:options.once});this.handlers.set(event,list);}
    emit(event,value) {for(const listener of [...(this.handlers.get(event)||[])]){listener.fn(value);if(listener.once)this.handlers.set(event,this.handlers.get(event).filter(x=>x!==listener));}}
    send(text) {
      const q=JSON.parse(text);commands.push(q);
      if(q.event==='cpu.resume')return;
      let result={event:q.event,ticket:q.ticket};
      if(q.event==='version')result.version='offline-fixture';
      else if(q.event==='memory.read') {
        const segment=segments.find(([a,b])=>q.address>=a&&q.address+q.size<=a+b.length);
        assert(segment,`fixture missing guest range ${q.address.toString(16)} ${q.size}`);
        const bytes=Buffer.from(segment[1].subarray(q.address-segment[0],q.address-segment[0]+q.size));
        if(q.address===0x08b44580||q.address===0x08b3e610){
          if(scenario!=='baseline'&&q.replacements!==false)bytes.writeUInt32LE(q.address===0x08b44580?0x68064f5e:0x68064ee6,0);
          if(scenario==='wrong-original'&&q.replacements===false)bytes.writeUInt32LE(0x27bdfeb4,0);
        }
        result.base64=bytes.toString('base64');
      } else if(q.event==='memory.disasm') {
        const start=q.address, end=q.end;result.lines=[];
        // Include an actual 8-byte macro to exercise original macro coverage.
        for(let address=start;address<end;address+=address===start?8:4){
          const first=moduleBytes.readUInt32LE(address-0x08804000);
          const line={type:address===start?'macro':'opcode',address,addressSize:address===start?8:4,encoding:first,macroEncoding:address===start?[first,moduleBytes.readUInt32LE(address+4-0x08804000)]:null};
          result.lines.push(line);
        }
        if(scenario==='wrong-disasm'){result.lines[0].encoding=0x27bdfeb4;result.lines[0].macroEncoding[0]=0x27bdfeb4;}
        if(scenario==='missing-disasm')result.lines.pop();
      } else if(q.event==='cpu.getAllRegs') {
        const g=Array(32).fill(0);g[4]=sp-0x100;g[5]=snapshot.object;g[6]=scenario==='no-weapon'?5:1;g[18]=handle;g[29]=sp;g[31]=0x08b3e62c;
        result.categories=[{uintValues:g}];
      } else assert(['input.buttons.send','input.analog.send','cpu.breakpoint.add','cpu.breakpoint.remove'].includes(q.event),`unexpected RPC ${q.event}`);
      queueMicrotask(()=>{this.emit('message',{data:JSON.stringify(result)});if(q.event==='cpu.breakpoint.add')this.emit('message',{data:JSON.stringify({event:'cpu.stepping',pc:0x08b44580,ticks:71723907735})});});
    }
    close() {this.readyState=3;this.emit('close',{});}
  }
  const fakeProcess={env:{MARKER_OUT_DIR:out,MARKER_MAX_STOPS:'1',MARKER_MAX_ROWS:'1',MARKER_DURATION_MS:'1000',
    MARKER_BUTTONS_JSON:JSON.stringify({rtrigger:true,square:true,select:true}),MARKER_ANALOG_JSON:JSON.stringify({stick:'left',x:.25,y:-.5})},on(){},exitCode:0};
  try {
    const result=vm.runInNewContext(fs.readFileSync(path.join(__dirname,'trace_weapon_marker_consumers.js'),'utf8'),{
      require,Buffer,WebSocket:MockWebSocket,process:fakeProcess,__dirname,console:{log(){},error:console.error},setTimeout,clearTimeout,Date,Promise
    });
    await result;
    const report=JSON.parse(fs.readFileSync(path.join(out,'marker_consumers.json'),'utf8'));
    const shouldFail=['wrong-original','wrong-disasm','missing-disasm'].includes(scenario);
    assert.equal(fakeProcess.exitCode,shouldFail?1:0);
    if(shouldFail){
      assert.equal(report.codeIdentity.verified,false);assert.equal(report.rows.length,0);assert(report.failure);
      assert.equal(commands.filter(q=>q.event==='cpu.breakpoint.add').length,0);
      assert(commands.filter(q=>q.event==='input.buttons.send').every(q=>Object.values(q.buttons).every(v=>v===false)));
      assert(fs.existsSync(report.codeIdentity.blocks[0].originalFile));
      assert.equal(report.cleanup.errors.length,0);
      console.log(`PASS: ${scenario} fails closed before BP/held input; diagnostics and release preserved`);
      return;
    }
    assert.equal(report.codeIdentity.verified,true);
    assert.equal(report.codeIdentity.blocks.length,2);
    assert(report.codeIdentity.blocks.every(block=>block.originalDifferences.length===0&&block.decodedDifferences.length===0));
    if(scenario==='jit-recovered')assert(report.codeIdentity.blocks.every(block=>block.differences.length>0));
    if(scenario==='no-weapon'){
      assert.equal(report.rows.length,0);assert.equal(report.stopCount,1);assert.equal(report.indexCounts['5'],1);
      assert.equal(report.firstStopTicks,71723907735);assert.equal(report.lastStopTicks,71723907735);
      assert.equal(report.cleanup.errors.length,0);assert(report.cleanup.buttonsReleased&&report.cleanup.breakpointRemoved);
      console.log('PASS: no retained weapon row still records all-helper stop ticks and completes cleanup');return;
    }
    assert.equal(report.rows.length,1);const row=report.rows[0];
    assert.equal(report.firstStopTicks,71723907735);assert.equal(report.lastStopTicks,71723907735);
    assert.equal(row.a1_drawable,snapshot.object);assert.equal(row.a2_index,1);assert.equal(row.sourceAddress,snapshot.sourceBase+0x130);
    assert.equal(row.wrapperActorHandle.address,handle);assert.equal(row.attachmentStateCandidate.address,statePointer);
    assert.equal(row.attachmentStateCandidate.primaryActorHandle144,handle);assert.equal(row.attachmentStateCandidate.secondaryActorHandle148,0);assert.equal(row.attachmentStateCandidate.primaryHandleMatchesWrapper,true);
    assert.equal(row.attachmentStateCandidate.selector14c,1);assert.equal(row.attachmentStateCandidate.selector14e,2);
    assert.equal(row.unwind[2].address,0x08b6314c);assert.equal(row.semanticName,null);
    assert(report.captureStage.includes('before'));assert.equal(report.cleanup.errors.length,0);
    const finalButtons=commands.filter(q=>q.event==='input.buttons.send').at(-1).buttons;
    assert(Object.values(finalButtons).every(v=>v===false));assert.equal(finalButtons.select,false);
    const finalAnalog=commands.filter(q=>q.event==='input.analog.send').at(-1);assert.equal(finalAnalog.x,0);assert.equal(finalAnalog.y,0);
    assert.deepEqual(commands.filter(q=>q.event==='cpu.breakpoint.remove').map(q=>q.address),[0x08b44580]);
    assert.equal(commands.filter(q=>q.event==='cpu.breakpoint.add').length,1);
    console.log(`PASS: ${scenario} original opcode identity, offline RPC queue, direct actor ABI, geometry SHA, stack and cleanup; no emulator connection`);
  } finally {
    const cleanupTarget=path.resolve(out), relative=path.relative(path.resolve(os.tmpdir()),cleanupTarget);
    assert(relative&&!relative.startsWith('..')&&!path.isAbsolute(relative)&&path.basename(cleanupTarget).startsWith('weapon-marker-selftest-'));
    fs.rmSync(cleanupTarget,{recursive:true,force:true});
  }
}
(async()=>{for(const scenario of ['baseline','jit-recovered','no-weapon','wrong-original','wrong-disasm','missing-disasm'])await test(scenario);})().catch(error=>{console.error(error.stack||error);process.exitCode=1;});
