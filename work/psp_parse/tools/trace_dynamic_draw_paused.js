// Pause at the 0x8b5e3a8 draw-record callsite and capture its live pointers/data.
const fs = require('fs');

const port = Number(process.env.PPSSPP_DEBUGGER_PORT || 9900);
const target = Number(process.env.DRAW_TRACE_TARGET || 0x08b5e3a8);
const count = Number(process.env.DRAW_TRACE_COUNT || 60);
const out = process.env.DRAW_TRACE_OUT || 'dynamic_draw_trace.json';
const dumpCount = Number(process.env.DRAW_TRACE_DUMPS || 0);
const dumpDir = process.env.DRAW_TRACE_DUMP_DIR || 'dynamic_draw_dumps';
let buttons = { square: true };
let analog = null;
try { if (process.env.DRAW_TRACE_BUTTONS_JSON) buttons = JSON.parse(process.env.DRAW_TRACE_BUTTONS_JSON); } catch (_) {}
try { if (process.env.DRAW_TRACE_ANALOG_JSON) analog = JSON.parse(process.env.DRAW_TRACE_ANALOG_JSON); } catch (_) {}

function send(ws, msg) { ws.send(JSON.stringify(msg)); }
function waitFor(ws, pred, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { cleanup(); reject(new Error('timeout')); }, timeoutMs);
    const onMessage = (e) => { let m; try { m = JSON.parse(e.data); } catch (_) { return; } if (!pred(m)) return; cleanup(); resolve(m); };
    const onClose = () => { cleanup(); reject(new Error('websocket closed')); };
    function cleanup() { clearTimeout(timer); ws.removeEventListener('message', onMessage); ws.removeEventListener('close', onClose); }
    ws.addEventListener('message', onMessage); ws.addEventListener('close', onClose);
  });
}

async function readU32(ws, address, ticket) {
  if (!address) return null;
  send(ws, { event: 'memory.read_u32', address: address >>> 0, ticket });
  try {
    const msg = await waitFor(ws, m => (m.event === 'memory.read_u32' || m.event === 'error') && m.ticket === ticket);
    if (msg.event === 'error') return null;
    return msg.uintValue ?? msg.value ?? null;
  } catch (_) { return null; }
}

async function readWords(ws, base, count, tag, index) {
  const words = [];
  for (let i = 0; i < count; i++) words.push(await readU32(ws, (base + i * 4) >>> 0, `${tag}-${index}-${i}`));
  return words;
}

async function main() {
  const ws = new WebSocket(`ws://127.0.0.1:${port}/debugger`, 'debugger.ppsspp.org');
  await new Promise((resolve, reject) => { ws.addEventListener('open', resolve, { once: true }); ws.addEventListener('error', reject, { once: true }); });
  send(ws, { event: 'version', name: 'aya-dynamic-draw-trace', version: '0.1' });
  const version = await waitFor(ws, m => m.event === 'version');
  send(ws, { event: 'cpu.breakpoint.add', address: target, enabled: true, log: false });
  await waitFor(ws, m => m.event === 'cpu.breakpoint.add');
  send(ws, { event: 'input.buttons.send', buttons });
  if (analog) send(ws, { event: 'input.analog.send', ...analog });
  const rows = [];
  if (dumpCount > 0) fs.mkdirSync(dumpDir, { recursive: true });
  for (let i = 0; i < count; i++) {
    const stopped = await waitFor(ws, m => m.event === 'cpu.stepping' && m.pc === target, 30000);
    const ticket = `regs-${i}`;
    send(ws, { event: 'cpu.getAllRegs', ticket });
    const regs = await waitFor(ws, m => m.event === 'cpu.getAllRegs' && m.ticket === ticket);
    const gpr = regs.categories && regs.categories[0] && regs.categories[0].uintValues;
    if (!gpr || gpr.length < 32) throw new Error(`unexpected register response: ${JSON.stringify(regs)}`);
    const recordBase = gpr[19] >>> 0; // s3: draw record list
    const matrixBase = gpr[5] >>> 0; // a1: matrix/data pointer at 0x8b5e3a8
    const pointerBase = gpr[4] >>> 0; // a0: first record field / command payload
    let dumpFile = null;
    if (i < dumpCount) {
      const dumpTicket = `dump-${i}`;
      send(ws, { event: 'gpu.record.dump', ticket: dumpTicket });
      const dump = await waitFor(ws, m => m.event === 'gpu.record.dump' && m.ticket === dumpTicket, 30000);
      if (dump.uri && dump.uri.startsWith('data:')) {
        const comma = dump.uri.indexOf(',');
        dumpFile = `${dumpDir}/frame_${String(i).padStart(4, '0')}.ppdmp`;
        fs.writeFileSync(dumpFile, Buffer.from(dump.uri.slice(comma + 1), 'base64'));
      }
    }
    rows.push({
      index: i, pc: stopped.pc, ticks: stopped.ticks,
      a0: gpr[4] >>> 0, a1: gpr[5] >>> 0, a2: gpr[6] >>> 0, a3: gpr[7] >>> 0,
      t0: gpr[8] >>> 0, s1: gpr[17] >>> 0, s2: gpr[18] >>> 0, s3: recordBase,
      sp: gpr[29] >>> 0, ra: gpr[31] >>> 0,
      recordWords: await readWords(ws, recordBase, 4, 'record', i),
      matrixWords: await readWords(ws, matrixBase, 16, 'matrix', i),
      pointerWords: await readWords(ws, pointerBase, 4, 'payload', i),
      dumpFile,
    });
    send(ws, { event: 'cpu.resume' });
  }
  send(ws, { event: 'input.buttons.send', buttons: {} });
  if (analog) send(ws, { event: 'input.analog.send', stick: analog.stick, x: 0, y: 0 });
  send(ws, { event: 'cpu.breakpoint.remove', address: target });
  await waitFor(ws, m => m.event === 'cpu.breakpoint.remove');
  ws.close();
  fs.writeFileSync(out, JSON.stringify({ schema: 'aya-dynamic-draw-trace/v1', target: `0x${target.toString(16)}`, count: rows.length, buttons, analog, version, rows }, null, 2));
  console.log(`rows=${rows.length} -> ${out}`);
}

main().catch(err => { console.error(err.stack || err); process.exitCode = 1; });
