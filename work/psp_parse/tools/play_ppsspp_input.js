// Drive a loaded PPSSPP state with debugger input events for runtime probing.
const port = Number(process.env.PPSSPP_DEBUGGER_PORT || 9900);
const sleep = ms => new Promise(r => setTimeout(r, ms));
function send(ws, msg) { ws.send(JSON.stringify(msg)); }
async function main() {
  const ws = new WebSocket(`ws://127.0.0.1:${port}/debugger`, 'debugger.ppsspp.org');
  await new Promise((resolve, reject) => { ws.addEventListener('open', resolve, { once: true }); ws.addEventListener('error', reject, { once: true }); });
  send(ws, { event: 'version', name: 'aya-play-input', version: '0.1' });
  await sleep(500);
  const step = async (x, y, buttons, ms) => { send(ws, { event: 'input.analog.send', stick: 'left', x, y }); send(ws, { event: 'input.buttons.send', buttons: buttons || {} }); await sleep(ms); };
  for (let i = 0; i < 3; i++) await step(0, 0, { circle: true }, 700);
  for (let i = 0; i < 3; i++) await step(0, 0, { circle: true }, 700);
  for (let i = 0; i < 12; i++) await step(1, 0, {}, 700);
  for (let i = 0; i < 12; i++) await step(0, -1, {}, 700);
  for (let i = 0; i < 20; i++) await step(0, 0, { rtrigger: true, square: true }, 500);
  send(ws, { event: 'input.buttons.send', buttons: {} }); send(ws, { event: 'input.analog.send', stick: 'left', x: 0, y: 0 }); ws.close();
}
main().catch(e => { console.error(e.stack || e); process.exitCode = 1; });
