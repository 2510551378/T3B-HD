// Read-only guest-memory snapshot at the original bone writer. No save writes.
const fs = require('fs');
const path = require('path');
const port = Number(process.env.PPSSPP_DEBUGGER_PORT || 9900);
const out = process.env.BONE_PAIR_DIR;
const target = 0x08b5251c;
const captureBone = Number(process.env.BONE_METADATA_INDEX ?? 43);
if (!out) throw new Error('BONE_PAIR_DIR is required');

async function main() {
  const ws = new WebSocket(`ws://127.0.0.1:${port}/debugger`, 'debugger.ppsspp.org');
  const pending = new Map(), events = [], waiters = [];
  let serial = 0, breakpoint = false;
  ws.addEventListener('message', e => {
    let m; try { m = JSON.parse(e.data); } catch { return; }
    const request = pending.get(m.ticket);
    if (request) { pending.delete(m.ticket); clearTimeout(request.timer); m.event === 'error' ? request.reject(new Error(JSON.stringify(m))) : request.resolve(m); return; }
    if (m.event !== 'cpu.stepping') return;
    const waiter = waiters.shift();
    if (waiter) { clearTimeout(waiter.timer); waiter.resolve(m); } else events.push(m);
  });
  const rpc = (event, fields = {}) => new Promise((resolve, reject) => {
    const ticket = `metadata-${++serial}`;
    const timer = setTimeout(() => { pending.delete(ticket); reject(new Error(`timeout: ${event}`)); }, 30000);
    pending.set(ticket, { resolve, reject, timer });
    ws.send(JSON.stringify({ event, ...fields, ticket }));
  });
  const stop = () => events.length ? Promise.resolve(events.shift()) : new Promise((resolve, reject) => {
    const entry = { resolve, timer: setTimeout(() => { const i = waiters.indexOf(entry); if (i >= 0) waiters.splice(i, 1); reject(new Error('no bone-writer stop')); }, 30000) }; waiters.push(entry);
  });
  const read = async address => { const m = await rpc('memory.read_u32', { address }); const value = m.uintValue ?? m.value; if (!Number.isInteger(value)) throw new Error(`invalid u32 at ${address.toString(16)}`); return value >>> 0; };
  const words = (address, count) => Promise.all(Array.from({ length: count }, (_, i) => read(address + i * 4)));
  try {
    await new Promise((resolve, reject) => { ws.addEventListener('open', resolve, { once: true }); ws.addEventListener('error', reject, { once: true }); });
    const version = await rpc('version', { name: 'aya-metadata-snapshot', version: '1' });
    await rpc('cpu.breakpoint.add', { address: target, enabled: true, log: false }); breakpoint = true;
    // Fresh runner startup is already running. cpu.resume is a notification,
    // not an RPC with an acknowledgement; never await a ticket for it.
    for (let attempt = 0; attempt < 1000; attempt++) {
      const stepping = await stop();
      if (stepping.pc !== target) { ws.send(JSON.stringify({ event: 'cpu.resume' })); continue; }
      const regs = await rpc('cpu.getAllRegs');
      const g = regs.categories?.[0]?.uintValues;
      if (!g || g.length < 32) throw new Error('missing registers');
      const object = g[4] >>> 0, boneIndex = g[7] >>> 0;
      const metadata = await read(object + 0x3e8);
      const countWord = await read(metadata + 4), boneCount = countWord >>> 16;
      if (boneCount !== 44 || boneIndex !== captureBone) { ws.send(JSON.stringify({ event: 'cpu.resume' })); continue; }
      const sourceBase = await read(object + 0x3c4);
      const header = await words(metadata, 16);
      const descriptors = header[0x18 / 4], drawTable = header[0x34 / 4];
      const descriptorWords = await words(descriptors, boneCount * 4);
      const records = [];
      for (let i = 0; i < boneCount; i++) records.push({ index: i, words: await words(sourceBase + i * 0x130, 0x130 / 4) });
      // Preserve the whole table including vertices; request bounded batches.
      const count = (await read(drawTable)) & 0xffff;
      if (count > 2000) throw new Error(`unexpected draw count ${count}`);
      let p = drawTable + 4;
      for (let i = 0; i < count; i++) {
        const h = await words(p, 3), n = h[0] & 0xffff, updates = (h[1] >>> 8) & 255, halfwords = (h[1] >>> 16) & 255;
        if (updates > 8 || !halfwords) throw new Error(`invalid packet ${i}`);
        p = (p + 12 + updates * 4 + n * halfwords * 2 + 3) & ~3;
      }
      if (p - drawTable > 4 * 1024 * 1024) throw new Error('draw table too large');
      const drawWords = [];
      for (let address = drawTable; address < p; address += 256) drawWords.push(...await words(address, Math.min(64, (p - address) / 4)));
      fs.mkdirSync(out, { recursive: true });
      fs.writeFileSync(path.join(out, 'metadata_snapshot.json'), JSON.stringify({ schema: 'aya-metadata-snapshot/v1', version, target, boneIndex, ticks: stepping.ticks, object, sourceBase, metadata, boneCount, header, descriptors, descriptorWords, drawTable, drawWords, records }, null, 2));
      console.log(`Captured ${boneCount} bones, ${count} draw packets, ${drawWords.length * 4} draw-table bytes`);
      return;
    }
    throw new Error('44-bone object not found');
  } finally {
    if (ws.readyState === WebSocket.OPEN) {
      if (breakpoint) await rpc('cpu.breakpoint.remove', { address: target }).catch(() => {});
      ws.send(JSON.stringify({ event: 'cpu.resume' }));
      ws.close();
    }
    for (const p of pending.values()) clearTimeout(p.timer);
    for (const w of waiters) clearTimeout(w.timer);
  }
}
main().catch(e => { console.error(e.stack || e); process.exitCode = 1; });
