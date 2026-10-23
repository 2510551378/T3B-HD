// Capture the full 44-bone source table at the actual 0x2B matrix read loop.
// The breakpoint is deliberately 0x08b52330, where the code loads
// object+0x3c4 + boneIndex*0x130 + {0x40,0x80}.  0x08b52554 is a later
// flag/clear branch and is not the matrix payload source.
const fs = require('fs');
const port = Number(process.env.PPSSPP_DEBUGGER_PORT || 50500);
const target = Number(process.env.BONE_RECORD_TARGET || 0x08b52330);
const framesWanted = Number(process.env.BONE_RECORD_FRAMES || 24);
const out = process.env.BONE_RECORD_OUT || 'bone_records_44.json';

function send(ws, msg) { ws.send(JSON.stringify(msg)); }
function waitFor(ws, pred, timeoutMs = 30000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { cleanup(); reject(new Error('timeout')); }, timeoutMs);
    const onMessage = e => { let m; try { m = JSON.parse(e.data); } catch (_) { return; } if (!pred(m)) return; cleanup(); resolve(m); };
    const onClose = () => { cleanup(); reject(new Error('websocket closed')); };
    function cleanup() { clearTimeout(timer); ws.removeEventListener('message', onMessage); ws.removeEventListener('close', onClose); }
    ws.addEventListener('message', onMessage); ws.addEventListener('close', onClose);
  });
}
async function getRegs(ws, ticket) {
  send(ws, { event: 'cpu.getAllRegs', ticket });
  const m = await waitFor(ws, x => x.event === 'cpu.getAllRegs' && x.ticket === ticket);
  const g = m.categories && m.categories[0] && m.categories[0].uintValues;
  if (!g || g.length < 32) throw new Error('bad register response');
  return g.map(x => x >>> 0);
}
async function readU32(ws, address, ticket) {
  send(ws, { event: 'memory.read_u32', address: address >>> 0, ticket });
  const m = await waitFor(ws, x => (x.event === 'memory.read_u32' || x.event === 'error') && x.ticket === ticket);
  return m.event === 'error' ? null : (m.uintValue ?? m.value ?? null);
}
async function readU16(ws, address, ticket) {
  send(ws, { event: 'memory.read_u16', address: address >>> 0, ticket });
  const m = await waitFor(ws, x => (x.event === 'memory.read_u16' || x.event === 'error') && x.ticket === ticket);
  return m.event === 'error' ? null : (m.uintValue ?? m.value ?? null);
}
async function readWords(ws, base, count, tag) {
  const ps = [];
  for (let i = 0; i < count; i++) ps.push(readU32(ws, (base + i * 4) >>> 0, `${tag}-${i}`));
  return Promise.all(ps);
}
async function main() {
  const ws = new WebSocket(`ws://127.0.0.1:${port}/debugger`, 'debugger.ppsspp.org');
  await new Promise((resolve, reject) => { ws.addEventListener('open', resolve, { once: true }); ws.addEventListener('error', reject, { once: true }); });
  send(ws, { event: 'version', name: 'aya-bone-records-44', version: '0.1' });
  const version = await waitFor(ws, x => x.event === 'version');
  send(ws, { event: 'cpu.breakpoint.add', address: target, enabled: true, log: false });
  await waitFor(ws, x => x.event === 'cpu.breakpoint.add');
  send(ws, { event: 'input.buttons.send', buttons: { square: true } });
  const rows = [];
  let guard = 0;
  while (rows.length < framesWanted && guard++ < framesWanted * 300) {
    const stop = await waitFor(ws, x => x.event === 'cpu.stepping' && x.pc === target, 60000);
    const g = await getRegs(ws, `regs-${guard}`);
    const obj = g[4] >>> 0;
    const boneIndex = g[7] >>> 0;
    const meta = await readU32(ws, (obj + 0x3e8) >>> 0, `meta-${guard}`);
    const boneCount = meta == null ? null : await readU16(ws, (meta + 6) >>> 0, `count-${guard}`);
    // Only sample the first iteration of the 44-bone object.  The breakpoint
    // still fires for all other records; those hits are immediately resumed.
    if (boneIndex === 0 && boneCount === 44) {
      const sourceBase = await readU32(ws, (obj + 0x3c4) >>> 0, `source-${guard}`);
      const records = [];
      for (let i = 0; i < 44; i++) {
        const rb = (sourceBase + i * 0x130) >>> 0;
        const [m40, m80, head, tail, flags120, flags128] = await Promise.all([
          readWords(ws, rb + 0x40, 16, `m40-${guard}-${i}`),
          readWords(ws, rb + 0x80, 16, `m80-${guard}-${i}`),
          readWords(ws, rb, 16, `head-${guard}-${i}`),
          readWords(ws, rb + 0xc0, 16, `tail-${guard}-${i}`),
          readU32(ws, rb + 0x120, `f120-${guard}-${i}`),
          readU32(ws, rb + 0x128, `f128-${guard}-${i}`),
        ]);
        records.push({ index: i, address: rb, matrix40: m40, matrix80: m80, head, tail, flags120, flags128 });
      }
      const metaTablePtr = meta == null ? null : await readU32(ws, (meta + 0x34) >>> 0, `meta-table-ptr-${guard}`);
      const metaTable = metaTablePtr == null ? null : await readWords(ws, metaTablePtr, 512, `meta-table-${guard}`);
      rows.push({ frame: rows.length, ticks: stop.ticks, object: obj, sourceBase, meta, metaTablePtr, boneCount, a1: g[5] >>> 0, a2: g[6] >>> 0, records, metaTable });
      console.log(`frame ${rows.length}/${framesWanted}: object=${obj.toString(16)} source=${sourceBase.toString(16)}`);
    }
    send(ws, { event: 'cpu.resume' });
  }
  send(ws, { event: 'input.buttons.send', buttons: {} });
  send(ws, { event: 'cpu.breakpoint.remove', address: target });
  await waitFor(ws, x => x.event === 'cpu.breakpoint.remove');
  ws.close();
  fs.writeFileSync(out, JSON.stringify({ schema: 'aya-bone-records-44/v1', target: `0x${target.toString(16)}`, count: rows.length, version, rows }, null, 2));
  console.log(`rows=${rows.length} -> ${out}`);
}
main().catch(e => { console.error(e.stack || e); process.exitCode = 1; });
