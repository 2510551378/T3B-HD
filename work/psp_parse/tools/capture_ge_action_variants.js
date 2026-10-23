// Capture additional GE pose/action variants with button and analog injection.
const fs = require('fs');
const path = require('path');
const port = Number(process.env.PPSSPP_DEBUGGER_PORT || 9900);
const framesPerPose = Number(process.env.GE_ACTION_FRAMES || 8);
const outDir = process.env.GE_ACTION_DIR || path.resolve(__dirname, '../raw/ge_action_variants');
const actions = [
  ['square', { square: true }, null],
  ['ltrigger_square', { square: true, ltrigger: true }, null],
  ['rtrigger_square', { square: true, rtrigger: true }, null],
  ['ltrigger_square_forward', { square: true, ltrigger: true }, { stick: 'left', x: 0, y: -1 }],
  ['rtrigger_square_left', { square: true, rtrigger: true }, { stick: 'left', x: -1, y: 0 }],
  ['square_right', { square: true }, { stick: 'left', x: 1, y: 0 }],
];
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

async function main() {
  const ws = new WebSocket(`ws://127.0.0.1:${port}/debugger`, 'debugger.ppsspp.org');
  await new Promise((resolve, reject) => { ws.addEventListener('open', resolve, { once: true }); ws.addEventListener('error', reject, { once: true }); });
  send(ws, { event: 'version', name: 'aya-ge-action-variants', version: '0.1' });
  const version = await waitFor(ws, m => m.event === 'version');
  console.log(`connected ${version.version}`);
  const manifest = [];
  for (const [name, buttons, analog] of actions) {
    const dir = path.join(outDir, name); fs.mkdirSync(dir, { recursive: true });
    send(ws, { event: 'input.buttons.send', buttons });
    if (analog) send(ws, { event: 'input.analog.send', ...analog });
    for (let i = 0; i < framesPerPose; i++) {
      const ticket = `${name}-${i}`;
      send(ws, { event: 'gpu.record.dump', ticket });
      const msg = await waitFor(ws, m => m.event === 'gpu.record.dump' && m.ticket === ticket);
      if (!msg.uri || !msg.uri.startsWith('data:')) throw new Error(`${ticket} missing data URI`);
      const comma = msg.uri.indexOf(',');
      const bytes = Buffer.from(msg.uri.slice(comma + 1), 'base64');
      const file = `frame_${String(i).padStart(4, '0')}.ppdmp`;
      fs.writeFileSync(path.join(dir, file), bytes);
      manifest.push({ pose: name, frame: i, file: path.join(name, file), bytes: bytes.length, buttons, analog });
      console.log(`${name} ${i + 1}/${framesPerPose}: ${bytes.length}`);
    }
    send(ws, { event: 'input.buttons.send', buttons: {} });
    if (analog) send(ws, { event: 'input.analog.send', stick: analog.stick, x: 0, y: 0 });
  }
  fs.writeFileSync(path.join(outDir, 'manifest.json'), JSON.stringify({ schema: 'aya-ge-action-variants/v1', version, framesPerPose, actions: actions.map(x => x[0]), frames: manifest }, null, 2));
  ws.close();
}

main().catch(err => { console.error(err.stack || err); process.exitCode = 1; });
