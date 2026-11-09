let state,sending=false,signature='',ackKey='',noticeTimer;const $=id=>document.getElementById(id);
function fail(e){$('error').hidden=false;$('error').textContent=e.message.replace(/^Error invoking remote method '[^']+': Error: /,'');}
async function call(name,data){try{return await window.sion.invoke(name,data);}catch(e){fail(e);throw e;}}
function appendMessage(log,role,raw,pending=false){
 const row=document.createElement('div');row.className='message '+role+(pending?' pending':'');
 let text=String(raw||'');
 if(role==='assistant'&&!pending){
  const m=text.match(/^\s*[（(]\s*(?:心声|内心(?:想法)?)\s*[:：]([\s\S]*?)[）)]\s*/);
  if(m&&m[1].trim()){
   const chip=document.createElement('small');chip.className='inner-thought-chip';
   chip.textContent='💭 心声：'+m[1].trim();row.append(chip);
   text=text.slice(m[0].length).trim()||m[1].trim();
  }
 }
 const p=document.createElement('p');p.textContent=text;row.append(p);log.append(row);
}
function render(s){
 state=s;$('send').disabled=sending;$('stop').disabled=!(s.pending||s.voicePending||s.pendingReply||['speaking','recognizing'].includes(s.voiceSession?.phase)||['planning','ready','running'].includes(s.computer?.chatRequest?.phase));$('error').hidden=!s.error;$('error').textContent=s.error;$('status').textContent=s.pending?'正在回复…':s.voiceStartingLocal?'正在启动本机配音…':s.voicePending?'正在合成语音…':s.voiceNotice|| (s.settings.mode==='demo'?'离线演示':'我在这里。');
 const cr=s.computer?.chatRequest;
 const key=JSON.stringify(s.messages)+s.pending+JSON.stringify(s.pendingReply)+JSON.stringify(cr);if(key!==signature){signature=key;const log=$('messages');log.replaceChildren();for(const m of s.messages.slice(-8))appendMessage(log,m.role,m.content);if(cr&&cr.phase==='done'){appendMessage(log,'user',cr.prompt);appendMessage(log,'assistant',[...(cr.steps||[]).map(x=>'已执行：'+x),cr.message||'已完成操作。'].filter(Boolean).join('\n'));}if(s.pendingReply)appendMessage(log,'assistant',s.pendingReply.text);if(s.pending&&!s.pendingReply)appendMessage(log,'assistant','诗音正在想…',true);if(!log.childNodes.length){const p=document.createElement('p');p.className='empty';p.textContent='想说什么，直接告诉我吧。';log.append(p);}log.scrollTop=log.scrollHeight;}
 const p=s.pendingReply;if(p&&!p.audioSync&&!document.hidden){const k=p.turn_id+':'+p.generation;if(k!==ackKey)requestAnimationFrame(()=>requestAnimationFrame(()=>{if(!document.hidden&&state.pendingReply?.turn_id===p.turn_id){ackKey=k;call('ack',{turn_id:p.turn_id,generation:p.generation}).catch(()=>{});}}));}
}
$('error').onclick=()=>{$('error').hidden=true;};
$('chat-form').onsubmit=async e=>{e.preventDefault();const text=$('input').value.trim();if(!text||sending)return;sending=true;$('send').disabled=true;try{await call('chat',{text});$('input').value='';}catch{}finally{sending=false;$('send').disabled=false;$('input').focus();}};
$('input').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing&&e.keyCode!==229){e.preventDefault();$('chat-form').requestSubmit();}};
for(const [id,name,data] of [['close','compact-close'],['settings','panel',{page:'settings'}],['stop','stop']])$(id).onclick=()=>call(name,data).catch(()=>{});
window.addEventListener('keydown',e=>{if(e.key==='Escape')call('compact-close').catch(()=>{});});
document.addEventListener('visibilitychange',()=>{if(state)render(state);});
window.sion.subscribe(e=>{
 if(e.type==='state')render(e.state);
 if(e.type==='compact-focus'){$('input').focus();if(state)render(state);}
 if(e.type==='companion-notice'){
  const notice=$('compact-notice');
  notice.textContent=(e.notice.kind==='touch'?'诗音 · ':'诗音提醒你 · ')+e.notice.title;
  notice.hidden=false;
  clearTimeout(noticeTimer);
  noticeTimer=setTimeout(()=>notice.hidden=true,8000);
 }
});window.sion.invoke('state').then(render).catch(fail);
