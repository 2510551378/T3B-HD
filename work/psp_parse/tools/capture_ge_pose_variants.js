// Capture GE dumps under several PPSSPP input poses without touching the saved state.
// Start PPSSPP with --debugger=9900 --state=<battle.ppst> <iso>.
const fs = require('fs');
const path = require('path');

const port = Number(process.env.PPSSPP_DEBUGGER_PORT || 9900);
const framesPerPose = Number(process.env.GE_VARIANT_FRAMES || 12);
const outDir = process.env.GE_VARIANT_DIR || path.resolve(__dirname, '../raw/ge_pose_variants');
const poses = [
  ['square', { square: true }],
  ['ltrigger_square', { square: true, ltrigger: true }],
  ['rtrigger_square', { square: true, rtrigger: true }],
  ['both_triggers_square', { square: true, ltrigger: true, rtrigger: true }],
];
fs.mkdirSync(outDir, { recursive: true });

function waitFor(ws, pred, timeoutMs = 30000) {
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
  send(ws, { event: 'version', name: 'aya-ge-pose-variants', version: '0.1' });
  const version = await waitFor(ws, m => m.event === 'version');
  console.log(`connected ${version.version} pid=${version.pid ?? 'unknown'}`);
  const manifest = [];
  for (const [pose, buttons] of poses) {
    const dir = path.join(outDir, pose);
    fs.mkdirSync(dir, { recursive: true });
    send(ws, { event: 'input.buttons.send', buttons });
    for (let i = 0; i < framesPerPose; i++) {
      const ticket = `${pose}-${i}`;
      send(ws, { event: 'gpu.record.dump', ticket });
      const msg = await waitFor(ws, m => m.event === 'gpu.record.dump' && m.ticket === ticket);
      if (!msg.uri || !msg.uri.startsWith('data:')) throw new Error(`${ticket} has no data URI`);
      const comma = msg.uri.indexOf(',');
      const bytes = Buffer.from(msg.uri.slice(comma + 1), 'base64');
      const name = `frame_${String(i).padStart(4, '0')}.ppdmp`;
      fs.writeFileSync(path.join(dir, name), bytes);
      manifest.push({ pose, frame: i, file: path.join(pose, name), bytes: bytes.length, ticket });
      console.log(`${pose} frame ${i + 1}/${framesPerPose}: ${bytes.length} bytes`);
    }
    send(ws, { event: 'input.buttons.send', buttons: {} });
  }
  fs.writeFileSync(path.join(outDir, 'manifest.json'), JSON.stringify({
    schema: 'aya-ge-pose-variants/v1', capturedAt: new Date().toISOString(), port, framesPerPose, poses: poses.map(x => x[0]), frames: manifest,
  }, null, 2));
  ws.close();
}

main().catch(err => { console.error(err.stack || err); process.exitCode = 1; });
