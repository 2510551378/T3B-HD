// Trace the runtime parameters of z_un_08bfff98 while the game is running.
// PPSSPP must be launched with --debugger=9900 and the battle state.
const fs = require('fs');

const port = Number(process.env.PPSSPP_DEBUGGER_PORT || 9900);
const durationMs = Number(process.env.MATRIX_TRACE_MS || 8000);
const out = process.env.MATRIX_TRACE_OUT || 'matrix_runtime_trace.json';
const targets = (process.env.MATRIX_TRACE_TARGETS || '0x08bfff98')
  .split(',').map(x => Number(x.trim())).filter(Number.isFinite);
let buttons = { square: true };
let analog = null;
try { if (process.env.MATRIX_TRACE_BUTTONS_JSON) buttons = JSON.parse(process.env.MATRIX_TRACE_BUTTONS_JSON); } catch (_) {}
try { if (process.env.MATRIX_TRACE_ANALOG_JSON) analog = JSON.parse(process.env.MATRIX_TRACE_ANALOG_JSON); } catch (_) {}

function send(ws, msg) { ws.send(JSON.stringify(msg)); }
function waitFor(ws, pred, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { cleanup(); reject(new Error('timeout')); }, timeoutMs);
    const onMessage = (e) => {
      let msg; try { msg = JSON.parse(e.data); } catch (_) { return; }
      if (!pred(msg)) return;
      cleanup(); resolve(msg);
    };
    const onClose = () => { cleanup(); reject(new Error('websocket closed')); };
    function cleanup() { clearTimeout(timer); ws.removeEventListener('message', onMessage); ws.removeEventListener('close', onClose); }
    ws.addEventListener('message', onMessage); ws.addEventListener('close', onClose);
  });
}

async function main() {
  const ws = new WebSocket(`ws://127.0.0.1:${port}/debugger`, 'debugger.ppsspp.org');
  await new Promise((resolve, reject) => { ws.addEventListener('open', resolve, { once: true }); ws.addEventListener('error', reject, { once: true }); });
  send(ws, { event: 'version', name: 'aya-matrix-runtime-trace', version: '0.1' });
  const version = await waitFor(ws, m => m.event === 'version');
  console.log(`connected ${version.version}`);
  const hits = [];
  const logs = [];
  const onMessage = (e) => {
    let m; try { m = JSON.parse(e.data); } catch (_) { return; }
    if (m.event === 'cpu.breakpoint.hit' && m.hit && targets.includes(m.hit.address)) hits.push(m.hit);
    if (m.event === 'log' && typeof m.message === 'string' && m.message.includes('matrix')) logs.push(m);
  };
  ws.addEventListener('message', onMessage);
  const addReplies = [];
  for (const target of targets) {
    const add = {
      event: 'cpu.breakpoint.add', address: target, enabled: false, log: true,
      logFormat: `matrix pc=${target.toString(16)} a0={a0} a1={a1} a2={a2} a3={a3} ra={ra}`,
    };
    send(ws, add);
    const addReply = await waitFor(ws, m => m.event === 'cpu.breakpoint.add');
    addReplies.push({ target, reply: addReply });
    console.log(`breakpoint add ${target.toString(16)}: ${JSON.stringify(addReply)}`);
  }
  send(ws, { event: 'input.buttons.send', buttons });
  if (analog) send(ws, { event: 'input.analog.send', ...analog });
  await new Promise(resolve => setTimeout(resolve, durationMs));
  send(ws, { event: 'input.buttons.send', buttons: {} });
  if (analog) send(ws, { event: 'input.analog.send', stick: analog.stick, x: 0, y: 0 });
  const removeReplies = [];
  for (const target of targets) {
    send(ws, { event: 'cpu.breakpoint.remove', address: target });
    const removeReply = await waitFor(ws, m => m.event === 'cpu.breakpoint.remove');
    removeReplies.push({ target, reply: removeReply });
  }
  console.log(`breakpoint remove: ${JSON.stringify(removeReplies)}`);
  ws.removeEventListener('message', onMessage); ws.close();
  const result = { schema: 'aya-matrix-runtime-trace/v1', targets: targets.map(x => `0x${x.toString(16)}`), durationMs, version, addReplies, removeReplies, hits, logs };
  fs.writeFileSync(out, JSON.stringify(result, null, 2));
  console.log(`hits=${hits.length} logs=${logs.length} -> ${out}`);
}

main().catch(err => { console.error(err.stack || err); process.exitCode = 1; });
