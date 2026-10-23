// Trace static GE BONE writer candidates (0x2A slot / 0x2B payload emitters).
const fs = require('fs');
const port = Number(process.env.PPSSPP_DEBUGGER_PORT || 9900);
const durationMs = Number(process.env.BONE_TRACE_MS || 1500);
const out = process.env.BONE_TRACE_OUT || 'bone_writer_trace.json';
const targets = (process.env.BONE_TRACE_TARGETS || '0x08b4f77c,0x08b52330,0x08b52554').split(',').map(x => Number(x.trim()));
const stateLoad = process.env.BONE_TRACE_STATE_LOAD || '';
let buttons = { square: true }; let analog = null;
try { if (process.env.BONE_TRACE_BUTTONS_JSON) buttons = JSON.parse(process.env.BONE_TRACE_BUTTONS_JSON); } catch (_) {}
try { if (process.env.BONE_TRACE_ANALOG_JSON) analog = JSON.parse(process.env.BONE_TRACE_ANALOG_JSON); } catch (_) {}
function send(ws, msg) { ws.send(JSON.stringify(msg)); }
function waitFor(ws, pred, timeoutMs = 15000) { return new Promise((resolve, reject) => { const timer=setTimeout(()=>{cleanup();reject(new Error('timeout'));},timeoutMs); const onMessage=e=>{let m;try{m=JSON.parse(e.data);}catch(_){return;}if(!pred(m))return;cleanup();resolve(m);}; const onClose=()=>{cleanup();reject(new Error('websocket closed'));}; function cleanup(){clearTimeout(timer);ws.removeEventListener('message',onMessage);ws.removeEventListener('close',onClose);} ws.addEventListener('message',onMessage);ws.addEventListener('close',onClose); }); }
async function main() {
  const ws = new WebSocket(`ws://127.0.0.1:${port}/debugger`, 'debugger.ppsspp.org');
  await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
  send(ws,{event:'version',name:'aya-bone-writer-trace',version:'0.1'}); const version=await waitFor(ws,m=>m.event==='version');
  const logs=[]; const onMessage=e=>{let m;try{m=JSON.parse(e.data);}catch(_){return;}if(m.event==='log'&&typeof m.message==='string'&&m.message.includes('bone-writer'))logs.push({wallMs:Date.now(),message:m.message,timestamp:m.timestamp});}; ws.addEventListener('message',onMessage);
  const addReplies=[];
  for(const target of targets){send(ws,{event:'cpu.breakpoint.add',address:target,enabled:false,log:true,logFormat:`bone-writer pc=${target.toString(16)} a0={a0} a1={a1} a2={a2} a3={a3} t0={t0} t1={t1} t2={t2} t3={t3} s0={s0} s1={s1} s2={s2} s3={s3}`});addReplies.push(await waitFor(ws,m=>m.event==='cpu.breakpoint.add'));}
  if (stateLoad) { send(ws, { event: 'game.state.load', path: stateLoad, ticket: 'state-load' }); await waitFor(ws, m => (m.event === 'game.state.load' || m.event === 'error') && m.ticket === 'state-load', 30000); }
  send(ws,{event:'input.buttons.send',buttons}); if(analog)send(ws,{event:'input.analog.send',...analog});
  await new Promise(resolve=>setTimeout(resolve,durationMs));
  send(ws,{event:'input.buttons.send',buttons:{}}); if(analog)send(ws,{event:'input.analog.send',stick:analog.stick,x:0,y:0});
  const removeReplies=[]; for(const target of targets){send(ws,{event:'cpu.breakpoint.remove',address:target});removeReplies.push(await waitFor(ws,m=>m.event==='cpu.breakpoint.remove'));}
  ws.removeEventListener('message',onMessage);ws.close();fs.writeFileSync(out,JSON.stringify({schema:'aya-bone-writer-trace/v1',targets:targets.map(x=>`0x${x.toString(16)}`),durationMs,buttons,analog,version,addReplies,removeReplies,logs},null,2));console.log(`logs=${logs.length} -> ${out}`);
}
main().catch(err=>{console.error(err.stack||err);process.exitCode=1;});
