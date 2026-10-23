// Pair each 44-bone matrix-output pass with a PPSSPP gpu.record.dump taken
// immediately after the pass resumes.  This gives a same-run mapping between
// source record indices and the draw-local GE palettes.
const fs = require('fs');
const port = Number(process.env.PPSSPP_DEBUGGER_PORT || 49261);
const target = Number(process.env.BONE_PAIR_TARGET || 0x08b5251c);
const framesWanted = Number(process.env.BONE_PAIR_FRAMES || 12);
const outDir = process.env.BONE_PAIR_DIR || 'bone_ge_pairs';
let buttons = {};
let analog = null;
try { if (process.env.BONE_PAIR_BUTTONS_JSON) buttons = JSON.parse(process.env.BONE_PAIR_BUTTONS_JSON); } catch (_) {}
try { if (process.env.BONE_PAIR_ANALOG_JSON) analog = JSON.parse(process.env.BONE_PAIR_ANALOG_JSON); } catch (_) {}
fs.mkdirSync(outDir, { recursive: true });
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
async function dump(ws, ticket, file) { send(ws, { event: 'gpu.record.dump', ticket }); const m = await waitFor(ws, x => x.event === 'gpu.record.dump' && x.ticket === ticket, 60000); if (!m.uri?.startsWith('data:')) return null; const comma = m.uri.indexOf(','); const bytes = Buffer.from(m.uri.slice(comma + 1), 'base64'); fs.writeFileSync(file, bytes); return { file, bytes: bytes.length }; }
async function main() {
  const ws = new WebSocket(`ws://127.0.0.1:${port}/debugger`, 'debugger.ppsspp.org');
  await new Promise((r, j) => { ws.addEventListener('open', r, { once: true }); ws.addEventListener('error', j, { once: true }); });
  send(ws, { event: 'version', name: 'aya-bone-ge-pairs', version: '0.1' }); const version = await waitFor(ws, x => x.event === 'version');
  send(ws, { event: 'cpu.breakpoint.add', address: target, enabled: true, log: false }); await waitFor(ws, x => x.event === 'cpu.breakpoint.add'); send(ws, { event: 'input.buttons.send', buttons }); if (analog) send(ws, { event: 'input.analog.send', ...analog });
  const counts = new Map(), bases = new Map(), rows = []; let current = null, guard = 0;
  while (rows.length < framesWanted && guard++ < framesWanted * 200) {
    const stop = await waitFor(ws, x => x.event === 'cpu.stepping' && x.pc === target, 60000);
    const g = await regs(ws, `regs-${guard}`), obj = g[4] >>> 0, idx = g[7] >>> 0;
    let count = counts.get(obj); if (count === undefined) { const meta = await u32(ws, obj + 0x3e8, `meta-${guard}`); count = meta == null ? 0 : await u32(ws, meta + 6, `count-${guard}`); counts.set(obj, count); }
    if (count === 44) {
      let sourceBase = bases.get(obj); if (sourceBase === undefined) { sourceBase = await u32(ws, obj + 0x3c4, `source-${guard}`); bases.set(obj, sourceBase); }
      if (idx === 0) { if (current && current.records.length === 44) rows.push(current); current = { frame: rows.length, ticks: stop.ticks, object: obj, sourceBase, records: [] }; }
      if (current && idx < 44) current.records.push({ index: idx, matrix: await words(ws, sourceBase + idx * 0x130 + 0xc0, 12, `matrix-${guard}`) });
      if (idx === 43 && current && current.records.length === 44) {
        // Remove the breakpoint while the display list finishes.  Otherwise
        // the next bone-0 hit pauses the CPU before gpu.record.dump can run.
        send(ws, { event: 'cpu.breakpoint.remove', address: target });
        await waitFor(ws, x => x.event === 'cpu.breakpoint.remove');
        send(ws, { event: 'cpu.resume' });
        const name = `frame_${String(rows.length).padStart(4, '0')}.ppdmp`;
        current.dump = await dump(ws, `dump-${rows.length}`, `${outDir}/${name}`);
        send(ws, { event: 'cpu.breakpoint.add', address: target, enabled: true, log: false });
        await waitFor(ws, x => x.event === 'cpu.breakpoint.add');
        continue;
      }
    }
    send(ws, { event: 'cpu.resume' });
  }
  if (current && current.records.length === 44 && rows.length < framesWanted) rows.push(current);
  send(ws, { event: 'input.buttons.send', buttons: {} }); if (analog) send(ws, { event: 'input.analog.send', stick: analog.stick, x: 0, y: 0 }); send(ws, { event: 'cpu.breakpoint.remove', address: target }); await waitFor(ws, x => x.event === 'cpu.breakpoint.remove'); ws.close();
  fs.writeFileSync(`${outDir}/manifest.json`, JSON.stringify({ schema: 'aya-bone-ge-pairs/v1', target: `0x${target.toString(16)}`, version, buttons, analog, frames: rows }, null, 2)); console.log(`rows=${rows.length} -> ${outDir}/manifest.json`);
}
main().catch(e => { console.error(e.stack || e); process.exitCode = 1; });
