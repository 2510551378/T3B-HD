// Pause at dl_write_matrix, read GPRs and the wrapper's saved caller RA, then resume.
// This avoids relying on logFormat for the stack-saved return address.
const fs = require('fs');

const port = Number(process.env.PPSSPP_DEBUGGER_PORT || 9900);
const target = Number(process.env.MATRIX_PAUSE_TARGET || 0x08c01088);
const count = Number(process.env.MATRIX_PAUSE_COUNT || 80);
const out = process.env.MATRIX_PAUSE_OUT || 'matrix_paused_trace.json';

function send(ws, msg) { ws.send(JSON.stringify(msg)); }
function waitFor(ws, pred, timeoutMs = 10000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { cleanup(); reject(new Error('timeout')); }, timeoutMs);
    const onMessage = (e) => { let m; try { m = JSON.parse(e.data); } catch (_) { return; } if (!pred(m)) return; cleanup(); resolve(m); };
    const onClose = () => { cleanup(); reject(new Error('websocket closed')); };
    function cleanup() { clearTimeout(timer); ws.removeEventListener('message', onMessage); ws.removeEventListener('close', onClose); }
    ws.addEventListener('message', onMessage); ws.addEventListener('close', onClose);
  });
}

async function main() {
  const ws = new WebSocket(`ws://127.0.0.1:${port}/debugger`, 'debugger.ppsspp.org');
  await new Promise((resolve, reject) => { ws.addEventListener('open', resolve, { once: true }); ws.addEventListener('error', reject, { once: true }); });
  send(ws, { event: 'version', name: 'aya-matrix-paused-trace', version: '0.1' });
  const version = await waitFor(ws, m => m.event === 'version');
  send(ws, { event: 'cpu.breakpoint.add', address: target, enabled: true, log: false });
  await waitFor(ws, m => m.event === 'cpu.breakpoint.add');
  send(ws, { event: 'input.buttons.send', buttons: { square: true } });
  const rows = [];
  for (let i = 0; i < count; i++) {
    const stopped = await waitFor(ws, m => m.event === 'cpu.stepping' && m.pc === target, 20000);
    const ticket = `regs-${i}`;
    send(ws, { event: 'cpu.getAllRegs', ticket });
    const regs = await waitFor(ws, m => m.event === 'cpu.getAllRegs' && m.ticket === ticket);
    const gpr = regs.categories && regs.categories[0] && regs.categories[0].uintValues;
    if (!gpr || gpr.length < 32) throw new Error(`unexpected register response: ${JSON.stringify(regs)}`);
    const memTicket = `saved-ra-${i}`;
    send(ws, { event: 'memory.read_u32', address: gpr[29], ticket: memTicket });
    const saved = await waitFor(ws, m => m.event === 'memory.read_u32' && m.ticket === memTicket);
    rows.push({
      index: i,
      pc: stopped.pc,
      ticks: stopped.ticks,
      a0: gpr[4], a1: gpr[5], a2: gpr[6], a3: gpr[7],
      sp: gpr[29], ra: gpr[31], savedCallerRa: saved.uintValue ?? saved.value,
      savedResponse: saved,
    });
    send(ws, { event: 'cpu.resume' });
  }
  send(ws, { event: 'input.buttons.send', buttons: {} });
  send(ws, { event: 'cpu.breakpoint.remove', address: target });
  await waitFor(ws, m => m.event === 'cpu.breakpoint.remove');
  ws.close();
  fs.writeFileSync(out, JSON.stringify({ schema: 'aya-matrix-paused-trace/v1', target: `0x${target.toString(16)}`, count: rows.length, version, rows }, null, 2));
  console.log(`rows=${rows.length} -> ${out}`);
}

main().catch(err => { console.error(err.stack || err); process.exitCode = 1; });
