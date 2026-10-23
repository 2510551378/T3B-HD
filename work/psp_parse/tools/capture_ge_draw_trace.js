// Capture GE dumps and 0x8b5e3a8 log-only events on one PPSSPP timeline.
const fs = require('fs');
const path = require('path');
const port = Number(process.env.PPSSPP_DEBUGGER_PORT || 9900);
const count = Number(process.env.GE_DRAW_TRACE_FRAMES || 12);
const outDir = process.env.GE_DRAW_TRACE_DIR || path.resolve(__dirname, '../raw/ge_draw_trace');
const buttons = process.env.GE_DRAW_TRACE_BUTTONS ? JSON.parse(process.env.GE_DRAW_TRACE_BUTTONS) : { square: true };
const analog = process.env.GE_DRAW_TRACE_ANALOG ? JSON.parse(process.env.GE_DRAW_TRACE_ANALOG) : null;
const target = 0x08b5e3a8;
fs.mkdirSync(outDir, { recursive: true });

function send(ws, msg) { ws.send(JSON.stringify(msg)); }
function waitFor(ws, pred, timeoutMs = 30000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { cleanup(); reject(new Error('timeout')); }, timeoutMs);
    const onMessage = (e) => { let m; try { m = JSON.parse(e.data); } catch (_) { return; } if (!pred(m)) return; cleanup(); resolve(m); };
    const onClose = () => { cleanup(); reject(new Error('websocket closed')); };
    function cleanup() { clearTimeout(timer); ws.removeEventListener('message', onMessage); ws.removeEventListener('close', onClose); }
    ws.addEventListener('message', onMessage); ws.addEventListener('close', onClose);
  });
}
function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

async function main() {
  const ws = new WebSocket(`ws://127.0.0.1:${port}/debugger`, 'debugger.ppsspp.org');
  await new Promise((resolve, reject) => { ws.addEventListener('open', resolve, { once: true }); ws.addEventListener('error', reject, { once: true }); });
  send(ws, { event: 'version', name: 'aya-ge-draw-trace', version: '0.1' });
  const version = await waitFor(ws, m => m.event === 'version');
  const logs = [];
  const onMessage = (e) => {
    let m; try { m = JSON.parse(e.data); } catch (_) { return; }
    if (m.event === 'log' && typeof m.message === 'string' && m.message.includes('draw-record')) logs.push({ wallMs: Date.now(), message: m.message, timestamp: m.timestamp });
  };
  ws.addEventListener('message', onMessage);
  send(ws, { event: 'cpu.breakpoint.add', address: target, enabled: false, log: true, logFormat: 'draw-record a0={a0} a1={a1} a2={a2} a3={a3} t0={t0} s3={s3}' });
  await waitFor(ws, m => m.event === 'cpu.breakpoint.add');
  send(ws, { event: 'input.buttons.send', buttons });
  if (analog) send(ws, { event: 'input.analog.send', ...analog });
  const frames = [];
  for (let i = 0; i < count; i++) {
    const before = logs.length;
    const wallStart = Date.now();
    const ticket = `ge-${i}`;
    send(ws, { event: 'gpu.record.dump', ticket });
    const dump = await waitFor(ws, m => m.event === 'gpu.record.dump' && m.ticket === ticket);
    const wallResponse = Date.now();
    let file = null;
    if (dump.uri && dump.uri.startsWith('data:')) {
      const comma = dump.uri.indexOf(',');
      file = `frame_${String(i).padStart(4, '0')}.ppdmp`;
      fs.writeFileSync(path.join(outDir, file), Buffer.from(dump.uri.slice(comma + 1), 'base64'));
    }
    await sleep(20);
    frames.push({ frame: i, file, wallStart, wallResponse, logStart: before, logEnd: logs.length });
    console.log(`frame ${i + 1}/${count}: logs ${before}..${logs.length}`);
  }
  send(ws, { event: 'input.buttons.send', buttons: {} });
  if (analog) send(ws, { event: 'input.analog.send', stick: analog.stick, x: 0, y: 0 });
  send(ws, { event: 'cpu.breakpoint.remove', address: target });
  await waitFor(ws, m => m.event === 'cpu.breakpoint.remove');
  ws.removeEventListener('message', onMessage); ws.close();
  fs.writeFileSync(path.join(outDir, 'manifest.json'), JSON.stringify({ schema: 'aya-ge-draw-trace/v1', version, target: `0x${target.toString(16)}`, buttons, analog, frames, logs }, null, 2));
}

main().catch(err => { console.error(err.stack || err); process.exitCode = 1; });
