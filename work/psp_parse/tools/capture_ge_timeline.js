// Capture consecutive PPSSPP GE frame dumps through the official WebSocket debugger.
// The caller starts PPSSPP with --debugger=9900 --state=<battle.ppst> <iso>.
const fs = require('fs');
const path = require('path');

const port = Number(process.env.PPSSPP_DEBUGGER_PORT || 9900);
const count = Number(process.env.GE_CAPTURE_FRAMES || 24);
const outDir = process.env.GE_CAPTURE_DIR || path.resolve(__dirname, '../raw/ge_timeline');
const holdSquare = process.env.GE_HOLD_SQUARE !== '0';
fs.mkdirSync(outDir, { recursive: true });

function waitFor(ws, pred, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { cleanup(); reject(new Error('timeout waiting for debugger event')); }, timeoutMs);
    const onMessage = (e) => {
      let msg;
      try { msg = JSON.parse(e.data); } catch (_) { return; }
      if (!pred(msg)) return;
      cleanup(); resolve(msg);
    };
    const onClose = () => { cleanup(); reject(new Error('debugger websocket closed')); };
    function cleanup() { clearTimeout(timer); ws.removeEventListener('message', onMessage); ws.removeEventListener('close', onClose); }
    ws.addEventListener('message', onMessage);
    ws.addEventListener('close', onClose);
  });
}

function send(ws, msg) { ws.send(JSON.stringify(msg)); }

async function main() {
  const ws = new WebSocket(`ws://127.0.0.1:${port}/debugger`, 'debugger.ppsspp.org');
  await new Promise((resolve, reject) => {
    ws.addEventListener('open', resolve, { once: true });
    ws.addEventListener('error', reject, { once: true });
  });
  send(ws, { event: 'version', name: 'aya-ge-timeline', version: '0.1' });
  const version = await waitFor(ws, m => m.event === 'version');
  console.log(`connected ${version.version} pid=${version.pid ?? 'unknown'}`);
  if (holdSquare) send(ws, { event: 'input.buttons.send', buttons: { square: true } });

  const manifest = [];
  for (let i = 0; i < count; i++) {
    const ticket = `ge-${i}`;
    send(ws, { event: 'gpu.record.dump', ticket });
    const msg = await waitFor(ws, m => m.event === 'gpu.record.dump' && m.ticket === ticket, 30000);
    if (!msg.uri || !msg.uri.startsWith('data:')) throw new Error(`frame ${i} has no data URI`);
    const comma = msg.uri.indexOf(',');
    const bytes = Buffer.from(msg.uri.slice(comma + 1), 'base64');
    const name = `frame_${String(i).padStart(4, '0')}.ppdmp`;
    fs.writeFileSync(path.join(outDir, name), bytes);
    manifest.push({ frame: i, file: name, bytes: bytes.length, ticket });
    console.log(`frame ${i + 1}/${count}: ${bytes.length} bytes`);
  }
  if (holdSquare) send(ws, { event: 'input.buttons.send', buttons: { square: false } });
  fs.writeFileSync(path.join(outDir, 'manifest.json'), JSON.stringify({
    schema: 'aya-ge-timeline/v1',
    capturedAt: new Date().toISOString(),
    port,
    holdSquare,
    frames: manifest,
  }, null, 2));
  ws.close();
}

main().catch(err => { console.error(err.stack || err); process.exitCode = 1; });
