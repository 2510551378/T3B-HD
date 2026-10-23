// Capture the matrix after the VFPU multiply in the real 0x2B BONE loop.
// At 0x08b52378 the 16-word GE matrix has just been stored at $t0; $a3 is
// the source bone index and $a0 is the 44-bone Aya object.
const fs = require('fs');
const port = Number(process.env.PPSSPP_DEBUGGER_PORT || 50500);
const target = Number(process.env.BONE_OUTPUT_TARGET || 0x08b52378);
const framesWanted = Number(process.env.BONE_OUTPUT_FRAMES || 24);
const out = process.env.BONE_OUTPUT_OUT || 'bone_ge_outputs.json';
function send(ws, msg) { ws.send(JSON.stringify(msg)); }
function waitFor(ws, pred, timeoutMs = 30000) { return new Promise((resolve, reject) => {
  const timer = setTimeout(() => { cleanup(); reject(new Error('timeout')); }, timeoutMs);
  const onMessage = e => { let m; try { m = JSON.parse(e.data); } catch (_) { return; } if (!pred(m)) return; cleanup(); resolve(m); };
  const onClose = () => { cleanup(); reject(new Error('websocket closed')); };
  function cleanup() { clearTimeout(timer); ws.removeEventListener('message', onMessage); ws.removeEventListener('close', onClose); }
  ws.addEventListener('message', onMessage); ws.addEventListener('close', onClose);
}); }
async function regs(ws, ticket) { send(ws, { event: 'cpu.getAllRegs', ticket }); const m = await waitFor(ws, x => x.event === 'cpu.getAllRegs' && x.ticket === ticket); const g = m.categories?.[0]?.uintValues; if (!g || g.length < 32) throw new Error('bad regs'); return g.map(x => x >>> 0); }
async function u32(ws, address, ticket) { send(ws, { event: 'memory.read_u32', address: address >>> 0, ticket }); const m = await waitFor(ws, x => (x.event === 'memory.read_u32' || x.event === 'error') && x.ticket === ticket); return m.event === 'error' ? null : (m.uintValue ?? m.value ?? null); }
async function words(ws, base, n, tag) { return Promise.all(Array.from({ length: n }, (_, i) => u32(ws, base + i * 4, `${tag}-${i}`))); }
async function main() {
  const ws = new WebSocket(`ws://127.0.0.1:${port}/debugger`, 'debugger.ppsspp.org');
  await new Promise((r, j) => { ws.addEventListener('open', r, { once: true }); ws.addEventListener('error', j, { once: true }); });
  send(ws, { event: 'version', name: 'aya-bone-ge-outputs', version: '0.1' }); const version = await waitFor(ws, x => x.event === 'version');
  send(ws, { event: 'cpu.breakpoint.add', address: target, enabled: true, log: false }); await waitFor(ws, x => x.event === 'cpu.breakpoint.add');
  send(ws, { event: 'input.buttons.send', buttons: { square: true } });
  const counts = new Map(), rows = []; let current = null, guard = 0;
  while (rows.length < framesWanted && guard++ < framesWanted * 200) {
    const stop = await waitFor(ws, x => x.event === 'cpu.stepping' && x.pc === target, 60000);
    const g = await regs(ws, `regs-${guard}`), obj = g[4] >>> 0, idx = g[7] >>> 0, scratch = g[8] >>> 0;
    let count = counts.get(obj); if (count === undefined) { const meta = await u32(ws, obj + 0x3e8, `meta-${guard}`); count = meta == null ? 0 : await u32(ws, meta + 6, `count-${guard}`); counts.set(obj, count); }
    if (count === 44) {
      if (idx === 0) { if (current && current.records.length === 44) rows.push(current); current = { frame: rows.length, ticks: stop.ticks, object: obj, scratch, records: [] }; }
      if (current && idx < 44) {
        const matrix = await words(ws, scratch, 16, `matrix-${guard}`);
        current.records.push({ index: idx, matrix });
      }
    }
    send(ws, { event: 'cpu.resume' });
  }
  if (current && current.records.length === 44 && rows.length < framesWanted) rows.push(current);
  send(ws, { event: 'input.buttons.send', buttons: {} }); send(ws, { event: 'cpu.breakpoint.remove', address: target }); await waitFor(ws, x => x.event === 'cpu.breakpoint.remove'); ws.close();
  fs.writeFileSync(out, JSON.stringify({ schema: 'aya-bone-ge-outputs/v1', target: `0x${target.toString(16)}`, count: rows.length, version, rows }, null, 2)); console.log(`rows=${rows.length} -> ${out}`);
}
main().catch(e => { console.error(e.stack || e); process.exitCode = 1; });
