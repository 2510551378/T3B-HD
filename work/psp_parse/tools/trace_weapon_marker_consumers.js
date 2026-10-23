// One helper-entry BP only. Connects to an existing PPSSPP; never launches it.
// a0=output matrix pointer, a1=drawable object (NOT handle), a2=bone index.
// Entry snapshots precede the helper's lazy update and are not output matrices.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const target = 0x08b44580;
const weaponSHA = '168578abca4c4f5d22d5994ebced6b93a25d5167428bfd47f1a1150a8d42e65a';
const out = process.env.MARKER_OUT_DIR;
const port = Number(process.env.PPSSPP_DEBUGGER_PORT || 9900);
const maxStops = Number(process.env.MARKER_MAX_STOPS || 1200);
const maxRows = Number(process.env.MARKER_MAX_ROWS || 24);
const durationMs = Number(process.env.MARKER_DURATION_MS || 15000);
const held = JSON.parse(process.env.MARKER_BUTTONS_JSON || '{}');
const analog = process.env.MARKER_ANALOG_JSON ? JSON.parse(process.env.MARKER_ANALOG_JSON) : null;
if (!out || !Number.isInteger(maxStops) || maxStops < 1 || maxStops > 20000 || !Number.isInteger(maxRows) || maxRows < 1 || maxRows > 240 || !Number.isFinite(durationMs) || durationMs < 100 || durationMs > 120000) throw new Error('invalid marker capture bounds/output');
if (!held || typeof held !== 'object' || Array.isArray(held) || Object.values(held).some(v => typeof v !== 'boolean')) throw new Error('buttons must be a boolean object');
if (analog && (!Number.isFinite(analog.x) || !Number.isFinite(analog.y) || Math.abs(analog.x) > 1 || Math.abs(analog.y) > 1)) throw new Error('invalid analog input');
const release = Object.fromEntries([...new Set(['rtrigger','ltrigger','square','triangle','circle','cross', ...Object.keys(held)])].map(k => [k, false]));
const modulePath = path.resolve(__dirname, '../raw/ULJM05798_module_08804000.bin');
const moduleBytes = fs.readFileSync(modulePath);
const moduleBase = 0x08804000;
const moduleEnd = moduleBase + moduleBytes.length;
const expectedEntry = moduleBytes.subarray(target - moduleBase, target - moduleBase + 44);
const expectedWrapper = moduleBytes.subarray(0x08b3e610 - moduleBase, 0x08b3e610 - moduleBase + 28);
const digest = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const ramPointer = (address, size = 4) => Number.isInteger(address) && address >= 0x08000000 && address + size <= 0x0c000000 && address % 4 === 0;
const words = bytes => Array.from({length: bytes.length / 4}, (_, i) => bytes.readUInt32LE(i * 4));
const floats = bytes => Array.from({length: bytes.length / 4}, (_, i) => bytes.readFloatLE(i * 4));
// Official v1.20.4 memory.disasm emits Read_Instruction encodings, including
// every original word of macros. Never infer an original opcode from 0x68 bits.
const originalDisasmBytes = (response, address, size) => {
  if (!Array.isArray(response.lines)) throw new Error('missing original disassembly lines');
  const recovered = Buffer.alloc(size), seen = new Set();
  for (const line of response.lines) {
    if (!Number.isInteger(line.address) || !Number.isInteger(line.addressSize) || line.addressSize < 4 || line.addressSize % 4) throw new Error('invalid original disassembly range');
    if (line.address + line.addressSize <= address || line.address >= address + size) continue;
    if (!['opcode','macro'].includes(line.type)) throw new Error('code identity range contains non-instruction disassembly');
    const encodings = line.addressSize === 4 ? [line.encoding] : line.macroEncoding;
    if (!Array.isArray(encodings) || encodings.length !== line.addressSize / 4 || encodings[0] !== line.encoding) throw new Error('missing original macro opcodes');
    for (let i=0;i<encodings.length;i++) {
      const at=line.address+i*4, value=encodings[i];
      if (!Number.isInteger(value) || value < 0 || value > 0xffffffff) throw new Error('invalid original opcode encoding');
      if (at < address || at >= address+size) continue;
      if ((at-address)%4 || seen.has(at)) throw new Error('overlapping or unaligned original opcodes');
      recovered.writeUInt32LE(value,at-address); seen.add(at);
    }
  }
  if (seen.size !== size/4) throw new Error('incomplete original opcode coverage');
  return recovered;
};

async function main() {
  fs.mkdirSync(out, {recursive:true});
  const ws = new WebSocket(`ws://127.0.0.1:${port}/debugger`, 'debugger.ppsspp.org');
  const pending = new Map(), stops = [], waiters = [];
  let serial = 0, breakpoint = false, ownStop = false, interrupted = false;
  let version = null, failure = null, stopCount = 0, firstStopTicks = null, lastStopTicks = null;
  const rows = [], rejections = {}, indices = {}, cleanup = {errors:[]}, inputEvents = [];
  const codeIdentity = {verified:false,method:'exact module == memory.read(replacements:false) == memory.disasm original encoding/macroEncoding',blocks:[],
    contracts:['https://github.com/hrydgard/ppsspp/blob/v1.20.4/Core/Debugger/WebSocket/MemorySubscriber.cpp#L173-L214',
      'https://github.com/hrydgard/ppsspp/blob/v1.20.4/Core/Debugger/WebSocket/DisasmSubscriber.cpp#L68-L90',
      'https://github.com/hrydgard/ppsspp/blob/v1.20.4/Core/MemMap.cpp#L409-L460']};
  process.on('SIGINT', () => {interrupted = true;});
  process.on('SIGTERM', () => {interrupted = true;});
  ws.addEventListener('message', event => {
    let m; try {m = JSON.parse(event.data);} catch {return;}
    const request = pending.get(m.ticket);
    if (request) {pending.delete(m.ticket); clearTimeout(request.timer); m.event === 'error' ? request.reject(new Error(JSON.stringify(m))) : request.resolve(m); return;}
    if (m.event === 'cpu.stepping') {
      const waiter = waiters.shift();
      if (waiter) {clearTimeout(waiter.timer); waiter.resolve(m);} else stops.push(m);
    }
  });
  ws.addEventListener('close', () => {
    for (const p of pending.values()) {clearTimeout(p.timer); p.reject(new Error('debugger closed'));} pending.clear();
    for (const w of waiters.splice(0)) {clearTimeout(w.timer); w.reject(new Error('debugger closed'));}
  });
  const rpc = (event, fields = {}, timeoutMs = 10000) => new Promise((resolve, reject) => {
    const ticket = `weapon-marker-${++serial}`;
    const timer = setTimeout(() => {pending.delete(ticket); reject(new Error(`timeout: ${event}`));}, timeoutMs);
    pending.set(ticket, {resolve, reject, timer}); ws.send(JSON.stringify({event, ...fields, ticket}));
  });
  const resume = () => {ws.send(JSON.stringify({event:'cpu.resume'})); ownStop = false;};
  const nextStop = timeout => stops.length ? Promise.resolve(stops.shift()) : new Promise((resolve,reject) => {
    const waiter = {resolve, reject, timer:setTimeout(() => {const i = waiters.indexOf(waiter); if (i >= 0) waiters.splice(i,1); reject(new Error('marker wait interval elapsed'));}, timeout)};
    waiters.push(waiter);
  });
  const read = async (address, size, replacements = true) => {
    if (!ramPointer(address, size) || size > 0x20000) throw new Error(`invalid guest read ${address.toString(16)} size=${size}`);
    const r = await rpc('memory.read', {address, size, replacements});
    const b = Buffer.from(r.base64 || '', 'base64');
    if (b.length !== size) throw new Error(`short guest read ${address.toString(16)} ${b.length}/${size}`);
    return b;
  };
  const input = async values => {await rpc('input.buttons.send', {buttons:values}); inputEvents.push({buttons:values, acknowledged:true});};
  const countReject = reason => {rejections[reason] = (rejections[reason] || 0) + 1;};
  const flush = () => fs.writeFileSync(path.join(out,'marker_consumers.json'), JSON.stringify({
    schema:'weapon-marker-consumer-entry-capture/v1', target, version,
    module:{file:modulePath, sha256:digest(moduleBytes)}, expectedGeometrySHA256:weaponSHA,
    abi:{a0:'output matrix address (not yet produced)', a1:'drawable actor object; no extra dereference', a2:'source bone index'},
    captureStage:'helper entry, before 0x08b460a0 lazy-update; source+40/WORLD are pre-call snapshots',
    bounds:{maxStops,maxRows,durationMs}, inputEvents, stopCount, firstStopTicks, lastStopTicks, indexCounts:indices, rejections,
    rows, codeIdentity, cleanup, failure,
    limits:['No helper output matrix is captured. Entry snapshots may precede a lazy update.',
            'Only this matrix-query entry is watched; direct +40 pointer queries and other accesses are outside this probe.',
            'Source1/2 semantic names require caller/FX evidence; geometry identity alone does not name a socket.']
  },null,2));
  try {
    await new Promise((resolve,reject) => {ws.addEventListener('open',resolve,{once:true}); ws.addEventListener('error',reject,{once:true});});
    version = await rpc('version', {name:'weapon-marker-consumer-entry', version:'1'});
    const codeSpecs=[{name:'helper_entry',address:target,expected:expectedEntry},{name:'handle_wrapper',address:0x08b3e610,expected:expectedWrapper}];
    const actualBlocks=await Promise.all(codeSpecs.map(spec=>read(spec.address,spec.expected.length)));
    for(let i=0;i<codeSpecs.length;i++){
      const spec=codeSpecs[i],actual=actualBlocks[i];
      const expectedFile=path.resolve(out,`${spec.name}_expected.bin`),actualFile=path.resolve(out,`${spec.name}_actual.bin`);
      fs.writeFileSync(expectedFile,spec.expected);fs.writeFileSync(actualFile,actual);
      const differences=[];
      for(let offset=0;offset<actual.length;offset+=4){const expectedWord=spec.expected.readUInt32LE(offset),actualWord=actual.readUInt32LE(offset);if(expectedWord!==actualWord)differences.push({address:spec.address+offset,offset,expectedWord,actualWord});}
      codeIdentity.blocks.push({name:spec.name,address:spec.address,bytes:actual.length,expectedFile,actualFile,
        expectedHex:spec.expected.toString('hex'),actualHex:actual.toString('hex'),expectedSHA256:digest(spec.expected),actualSHA256:digest(actual),differences});
    }
    flush();
    // Recovery reads are sequential: replacements:false temporarily clears and
    // restores the emulator's own replacements under its documented CPU lock.
    for(let i=0;i<codeSpecs.length;i++){
      const spec=codeSpecs[i],block=codeIdentity.blocks[i];
      const original=await read(spec.address,spec.expected.length,false);
      block.originalFile=path.resolve(out,`${spec.name}_original.bin`);
      fs.writeFileSync(block.originalFile,original);
      block.originalHex=original.toString('hex');block.originalSHA256=digest(original);
      block.originalDifferences=words(original).flatMap((value,j)=>value===spec.expected.readUInt32LE(j*4)?[]:[{address:spec.address+j*4,expectedWord:spec.expected.readUInt32LE(j*4),originalWord:value}]);
      flush();
      const disasm=await rpc('memory.disasm',{address:spec.address,end:spec.address+spec.expected.length,displaySymbols:false});
      block.disasmFile=path.resolve(out,`${spec.name}_disasm.json`);
      fs.writeFileSync(block.disasmFile,JSON.stringify(disasm,null,2));
      const decoded=originalDisasmBytes(disasm,spec.address,spec.expected.length);
      block.decodedFile=path.resolve(out,`${spec.name}_disasm_original.bin`);
      fs.writeFileSync(block.decodedFile,decoded);
      block.decodedHex=decoded.toString('hex');block.decodedSHA256=digest(decoded);
      block.decodedDifferences=words(decoded).flatMap((value,j)=>value===spec.expected.readUInt32LE(j*4)?[]:[{address:spec.address+j*4,expectedWord:spec.expected.readUInt32LE(j*4),decodedWord:value}]);
      block.verified=original.equals(spec.expected)&&decoded.equals(spec.expected);
      flush();
      if(!block.verified)throw new Error('runtime original helper/wrapper opcodes do not match the selected original module; exact raw/original/disasm diagnostics saved');
    }
    codeIdentity.verified=codeIdentity.blocks.every(block=>block.verified);
    flush();
    await input(release);
    if (analog) await rpc('input.analog.send', {...analog, x:0, y:0});
    // Start before arming: once armed, never resume until its queued stop is consumed.
    // This prevents an early hit during input RPCs from becoming a stale stepping event.
    stops.length = 0;
    resume();
    await rpc('cpu.breakpoint.add', {address:target, enabled:true, log:false}); breakpoint = true;
    await input({...release, ...held});
    if (analog) await rpc('input.analog.send', analog);
    const deadline = Date.now() + durationMs;
    while (!interrupted && Date.now() < deadline && stopCount < maxStops && rows.length < maxRows) {
      let stepping;
      try {stepping = await nextStop(Math.min(1000, Math.max(1,deadline-Date.now())));} catch (e) {if (e.message === 'marker wait interval elapsed') continue; throw e;}
      if (stepping.pc !== target) throw new Error(`unexpected external CPU stop at ${stepping.pc}; left paused`);
      ownStop = true; stopCount++;
      if (!Number.isSafeInteger(stepping.ticks) || (lastStopTicks!==null && stepping.ticks<lastStopTicks)) throw new Error('missing/unsafe/non-monotonic helper stop ticks');
      if(firstStopTicks===null)firstStopTicks=stepping.ticks;
      lastStopTicks=stepping.ticks;
      const r = await rpc('cpu.getAllRegs');
      const g = r.categories?.[0]?.uintValues;
      if (!g || g.length < 32) throw new Error('missing CPU GPRs');
      const output = g[4] >>> 0, actor = g[5] >>> 0, index = g[6] >>> 0, sp = g[29] >>> 0, ra = g[31] >>> 0;
      indices[index] = (indices[index] || 0) + 1;
      if (index !== 1 && index !== 2) {resume(); continue;}
      if (!ramPointer(actor,0x3ec)) {countReject('invalid drawable pointer'); resume(); continue;}
      const actorFields = await read(actor+0x3c4,40);
      const sourceBase = actorFields.readUInt32LE(0), metadata = actorFields.readUInt32LE(0x24);
      if (!ramPointer(metadata,64) || !ramPointer(sourceBase,3*0x130)) {countReject('invalid metadata/source pointers'); resume(); continue;}
      const header = await read(metadata,64);
      const boneCount = header.readUInt16LE(6), table = header.readUInt32LE(0x34);
      if (boneCount !== 3 || !ramPointer(table,16)) {countReject('not three-bone drawable'); resume(); continue;}
      const packet = await read(table,16);
      const drawCount = packet.readUInt16LE(0), vertexCount = packet.readUInt16LE(4), updates = packet[9], stride = packet[10]*2, vtype = packet.readUInt32LE(12);
      if (drawCount !== 1 || vertexCount !== 243 || stride !== 16 || vtype !== 0x522 || updates > 8) {countReject('weapon packet shape differs'); resume(); continue;}
      const palette = updates ? await read(table+16,updates*4) : Buffer.alloc(0);
      const geometry = await read(table+16+updates*4,vertexCount*stride);
      const prefix = Buffer.alloc(4); prefix.writeUInt32LE(vtype);
      const geometrySHA256 = digest(Buffer.concat([prefix,geometry]));
      if (geometrySHA256 !== weaponSHA) {countReject('weapon geometry SHA256 differs'); resume(); continue;}
      const sourceAddress = sourceBase + index*0x130;
      const [source,world,stack] = await Promise.all([read(sourceAddress,0x130),read(actor+0x220,64),read(sp,0x240)]);
      const id = String(rows.length).padStart(4,'0');
      fs.writeFileSync(path.join(out,`marker_source_${id}.bin`),source);
      fs.writeFileSync(path.join(out,`marker_stack_${id}.bin`),stack);
      const unwind = [{kind:'direct helper return',address:ra}];
      const stackAddresses = words(stack).flatMap((value,i) => value >= moduleBase && value < moduleEnd && value%4===0 ? [{stackOffset:i*4,value}] : []);
      let state = null, handle = null;
      if (ra === 0x08b3e62c) {
        const outerRA = stack.readUInt32LE(0x84);
        unwind.push({kind:'wrapper 0x08b3e610 saved RA',stackOffset:0x84,address:outerRA});
        const layouts = {0x08bbc688:{frame:0x08bbc584,raOffset:0xfc,s1Offset:0xf0}, 0x08bbca40:{frame:0x08bbc93c,raOffset:0x17c,s1Offset:0x170},
                         0x08bbccd0:{frame:0x08bbc93c,raOffset:0x17c,s1Offset:0x170}, 0x08bbce3c:{frame:0x08bbcd78,raOffset:0xfc,s1Offset:0xf0}};
        const layout = layouts[outerRA];
        if (layout) {
          const parentRA = stack.readUInt32LE(0x90+layout.raOffset);
          unwind.push({kind:`attachment function ${layout.frame.toString(16)} saved RA`,stackOffset:0x90+layout.raOffset,address:parentRA});
          const possibleHandle = g[18] >>> 0; // attachment function s2, unchanged by the wrapper.
          if (ramPointer(possibleHandle) && (await read(possibleHandle,4)).readUInt32LE(0) === actor) handle = {address:possibleHandle,firstWordEqualsActor:true};
          if ([0x08b630c4,0x08b630dc,0x08b63134,0x08b6314c,0x08b63160].includes(parentRA)) {
            const statePointer = stack.readUInt32LE(0x90+layout.s1Offset);
            if (ramPointer(statePointer,0x150)) {
              const fields = await read(statePointer+0x140,0x10);
              state = {address:statePointer,raw140:words(fields),primaryActorHandle144:fields.readUInt32LE(4),secondaryActorHandle148:fields.readUInt32LE(8),
                primaryHandleMatchesWrapper:handle!==null&&fields.readUInt32LE(4)===handle.address,
                selector14c:fields.readInt16LE(12),selector14e:fields.readInt16LE(14)};
            }
          }
        }
      }
      rows.push({sample:rows.length,ticks:stepping.ticks,pc:target,a0_output:output,a1_drawable:actor,a2_index:index,ra,sp,
        metadata,metadataHeader:words(header),sourceBase,sourceAddress,boneCount,drawTable:table,drawHeader:words(packet),paletteHex:palette.toString('hex'),geometrySHA256,
        sourceFile:path.resolve(out,`marker_source_${id}.bin`),sourceSHA256:digest(source),sourceMatrix40Words:words(source.subarray(0x40,0x80)),sourceMatrix40F32:floats(source.subarray(0x40,0x80)),
        worldWords:words(world),worldF32:floats(world),stackFile:path.resolve(out,`marker_stack_${id}.bin`),stackSHA256:digest(stack),unwind,stackCodeAddressCandidates:stackAddresses,
        wrapperActorHandle:handle,attachmentStateCandidate:state,semanticName:null});
      flush(); resume();
    }
  } catch (e) {failure = String(e.stack || e);}
  finally {
    for (const operation of [async()=>{await input(release);cleanup.buttonsReleased=true;},async()=>{if(analog){await rpc('input.analog.send',{...analog,x:0,y:0});cleanup.analogReleased=true;}},
      async()=>{if(breakpoint){await rpc('cpu.breakpoint.remove',{address:target});breakpoint=false;cleanup.breakpointRemoved=true;}},async()=>{if(ownStop){resume();cleanup.resumedOwnStop=true;}}]) {
      try {if(ws.readyState===WebSocket.OPEN)await operation();else cleanup.errors.push('debugger disconnected before cleanup');} catch(e){cleanup.errors.push(String(e));}
    }
    flush(); ws.close();
  }
  console.log(JSON.stringify({out,stopCount,rows:rows.length,rejections,cleanup,failure}));
  if(failure||cleanup.errors.length)process.exitCode=1;
}
main().catch(error=>{console.error(error.stack||error);process.exitCode=1;});
