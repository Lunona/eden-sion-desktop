let state,toastTimer,historyKey='';const $=id=>document.getElementById(id);
async function call(action,data){try{return await window.sion.invoke(action,data);}catch(e){toast(e.message.replace(/^Error invoking remote method '[^']+': Error: /,''));throw e;}}
function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,5000);}
const petCard=document.createElement('section');
petCard.className='settings-card';
petCard.innerHTML=`
  <h3>角色上的操作</h3>
  <label class="toggle"><input type="checkbox" id="pet-chat-button">显示侧边聊天按钮</label>
  <label class="toggle"><input type="checkbox" id="pet-touch-enabled">轻点和长按有互动反馈</label>
  <p class="note">拖动角色移动位置。按住 Shift 再拖可拉袖口、拨头发等。隐藏聊天按钮后，仍可从托盘打开聊天。</p>
`;
$('character').append(petCard);
for(const [id,key] of [['pet-chat-button','chatButton'],['pet-touch-enabled','touch']])$(id).onchange=async()=>{
  try{await call('pet-controls',{...state.settings.petControls,[key]:$(id).checked});}
  catch{paintControls(state.settings);}
};
function paintControls(settings){
  $('pet-chat-button').checked=settings.petControls.chatButton;
  $('pet-touch-enabled').checked=settings.petControls.touch;
}
function fillAssistantContent(div,rawText){
  let bodyText=String(rawText||'');
  const th=bodyText.match(/^\s*[（(]\s*(?:心声|内心(?:想法)?)\s*[:：]([\s\S]*?)[）)]\s*/);
  if(th&&th[1].trim()){
    const chip=document.createElement('div');chip.className='inner-thought-chip';chip.textContent='💭 心声：'+th[1].trim();div.append(chip);
    bodyText=bodyText.slice(th[0].length).trim()||th[1].trim();
  }
  const p=document.createElement('p');p.textContent=bodyText;div.append(p);
}
function render(s){
  const first=!state;state=s;
  $('mode-label').textContent=s.settings.mode==='demo'?'离线演示':'模型 API';$('send').disabled=false;$('stop').disabled=false;
  $('error').hidden=!s.error;$('error').textContent=s.error;
  const cr=s.computer?.chatRequest;
  const signature=JSON.stringify(s.messages)+s.pending+JSON.stringify(s.pendingReply)+JSON.stringify(cr);
  if(signature!==historyKey){historyKey=signature;const box=$('messages');if(s.messages.length||cr){box.replaceChildren();for(const m of s.messages){const div=document.createElement('div');div.className='message '+m.role;const label=document.createElement('small');label.textContent=m.role==='user'?'你':m.source==='demo'?'诗音 · 演示台词':'诗音';div.append(label);if(m.role==='user'){const p=document.createElement('p');p.textContent=String(m.content||'');div.append(p);}else{fillAssistantContent(div,m.content);}if(m.speechText){const detail=document.createElement("details"),summary=document.createElement("summary"),spoken=document.createElement("p");summary.textContent="日语朗读文本";spoken.textContent=m.speechText;detail.append(summary,spoken);div.append(detail);}box.append(div);}if(cr){const uDiv=document.createElement('div');uDiv.className='message user';const uLabel=document.createElement('small');uLabel.textContent='你';const uP=document.createElement('p');uP.textContent=cr.prompt;uDiv.append(uLabel,uP);box.append(uDiv);const aDiv=document.createElement('div');aDiv.className='message assistant';const aLabel=document.createElement('small');aLabel.textContent='诗音 · 电脑助手';aDiv.append(aLabel);const steps=(cr.steps||[]).map(x=>'已执行：'+x);const statusText=cr.phase==='planning'?'我先看一下怎么做。':cr.phase==='ready'?[cr.description,'待确认：'+(cr.step||'桌面操作')].filter(Boolean).join('\n'):cr.phase==='running'?[cr.description,'正在执行：'+(cr.step||'桌面操作')].filter(Boolean).join('\n'):[...steps,cr.message||'已完成操作。'].filter(Boolean).join('\n');fillAssistantContent(aDiv,statusText);box.append(aDiv);}if(s.pending){const p=document.createElement('div');p.className='note';p.textContent='诗音正在想…';box.append(p);}box.scrollTop=box.scrollHeight;}else box.innerHTML='<div class="welcome"><span>✧</span><h2>我在这里。</h2><p>从一句问候开始吧。<br>这段小小的日常，慢慢来就好。</p></div>';}
  if(!document.querySelector('#face-buttons button'))buildControls(s.assets);
  $('asset-status').textContent=s.assets.placeholder?'占位资源 · 仅用于验证动作，可替换为诗音立绘':s.assets.name;
  $('toggle-click').textContent=s.clickthrough?'关闭穿透':'鼠标穿透';
  $('coverage').textContent='24 种原素材表情；脸红单独控制。支持对话情绪自动联动；手动表情优先保留30秒。';
  document.querySelectorAll('[data-expression]').forEach(b=>b.classList.toggle('selected',b.dataset.expression===s.expression));
  paintReady(s);
  paintControls(s.settings);
  for(const name of ['motion','topmost'])$(name).checked=s.settings[name];$('scale').value=String(s.settings.scale);
  $('key-status').textContent=s.keySaved?(s.keyEncrypted?'密钥已保存（Windows 系统加密）':'密钥只在本次运行内保存，系统加密不可用'):'尚未保存密钥；本地无鉴权服务可以留空。';
  $('voice-reference-now').textContent=s.voiceReference?'最近使用 '+s.voiceReference.category+' · '+s.voiceReference.name:'参考库会使用与这轮情绪对应的日语音频和原文。';
  if(first){fillSettings(s.settings);if(s.settings.mode==='api'&&!s.keySaved&&s.settings.model.baseUrl.includes('api.deepseek.com')){document.querySelector('[data-page=settings]').click();toast('已填好模型地址和名称，请填写 API 密钥并保存。');}}
}
function fillSettings(c){$('mode').value=c.mode;$('base-url').value=c.model.baseUrl;$('model-name').value=c.model.name;$('voice-enabled').checked=c.voice.enabled;$('voice-emotion-reference').checked=c.voice.emotionalReferences!==false;$('voice-url').value=c.voice.endpoint;$('ref-audio').value=c.voice.refAudio;$('prompt-text').value=c.voice.promptText;$('text-lang').value=c.voice.textLang;$('prompt-lang').value=c.voice.promptLang;}
document.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>{document.querySelectorAll('.page,.nav').forEach(e=>e.classList.remove('active'));b.classList.add('active');$(b.dataset.page).classList.add('active');$('page-title').textContent={chat:'今天，想聊些什么？',character:'让陪伴，多一点生动。',settings:'连接你的诗音。',memory:'一起记住的事。'}[b.dataset.page];});
$('chat-form').onsubmit=async e=>{e.preventDefault();const text=$('input').value.trim();if(!text)return;await call('chat',{text});$('input').value='';};
$('input').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();$('chat-form').requestSubmit();}};
for(const [id,action] of [['stop','stop'],['reset','reset'],['quit','quit'],['mouth-test','mouth-test'],['toggle-click','clickthrough'],['voice-test','voice-test']])$(id).onclick=()=>call(action).catch(()=>{});
$('clear').onclick=()=>{if(confirm('开始新对话？长期记忆仍保留，可在下方单独更正或删除。'))call('clear').catch(()=>{});};
document.querySelectorAll('[data-expression]').forEach(b=>b.onclick=()=>call('expression',{value:b.dataset.expression}).catch(()=>{}));
for(const name of ['motion','topmost','scale'])$(name).onchange=()=>call('settings',{[name]:name==='scale'?Number($(name).value):$(name).checked}).catch(()=>{});
$('import-image').onclick=async()=>{try{const r=await call('import-image',{expression:$('slot-expression').value,frame:$('slot-frame').value});if(r)toast(`已保留 ${r.size.width}×${r.size.height} 原图。${r.note}`);}catch{}};
$('reset-images').onclick=()=>call('reset-images').catch(()=>{});
$('settings-form').onsubmit=async e=>{e.preventDefault();try{const payload={mode:$('mode').value,model:{baseUrl:$('base-url').value,name:$('model-name').value},voice:{enabled:$('voice-enabled').checked,emotionalReferences:$('voice-emotion-reference').checked,endpoint:$('voice-url').value,refAudio:$('ref-audio').value,promptText:$('prompt-text').value,textLang:$('text-lang').value,promptLang:$('prompt-lang').value}};if($('delete-key').checked)payload.apiKey='';else if($('api-key').value)payload.apiKey=$('api-key').value;await call('settings',payload);$('api-key').value='';$('delete-key').checked=false;$('save-status').textContent='已保存在本机';toast('设置已保存');}catch{}};
window.sion.subscribe(e=>{if(e.type==='state')render(e.state);if(e.type==='navigate')document.querySelector(`[data-page="${['chat','settings','character','memory','companion','providers','persona','computer'].includes(e.page)?e.page:'settings'}"]`).click();});window.sion.invoke('state').then(render).catch(e=>toast(e.message));

$('model-test').onclick=async()=>{const button=$('model-test');button.disabled=true;try{const result=await call('model-test');toast(`模型已连接（${result.seconds.toFixed(1)}秒）：${result.reply}`);}catch{}finally{button.disabled=false;}};

let readyPainted='';
function paintReady(s){
 const p=s.pendingReply;if(!p||document.hidden||!$('chat').classList.contains('active'))return;
 let row=document.getElementById('ready-reply');
 if(!row){row=document.createElement('div');row.id='ready-reply';row.className='message assistant';$('messages').append(row);}
 row.replaceChildren();
 const label=document.createElement('small');label.textContent='诗音';row.append(label);
 fillAssistantContent(row,p.text);
 $('messages').scrollTop=$('messages').scrollHeight;
 if(p.audioSync)return;
 const k=p.turn_id+':'+p.generation;if(k===readyPainted)return;
 requestAnimationFrame(()=>requestAnimationFrame(()=>{if(!document.hidden&&state.pendingReply?.turn_id===p.turn_id){readyPainted=k;call('ack',{turn_id:p.turn_id,generation:p.generation}).catch(()=>{});}}));
}
function button(parent,label,fn){const b=document.createElement('button');b.type='button';b.textContent=label;b.onclick=()=>Promise.resolve(fn()).catch(()=>{});parent.append(b);return b;}
function buildControls(assets){
 for(const [id,label] of Object.entries(assets.faces))button($('face-buttons'),label,()=>call('expression',{value:id})).dataset.expression=id;
 for(const index of [1,2,3,4,5,6,7,8,9,10,15,16])button($('action-buttons'),assets.actions[index-1][1],()=>call('control',{name:'action',index}));
 button($('action-buttons'),'停止动作',()=>call('control',{name:'cancel'}));
 for(const [label,index,leftMirror] of [['碰手',11,false],['拉袖',12,true],['拨发',13,false],['抬脚',17,false],['摆手',18,false]])for(const [side,mirror] of [['左',leftMirror],['右',!leftMirror]])button($('action-buttons'),side+label,()=>call('control',{name:'action',index,mirror}));
 for(const [id,label] of [['pet','连续摸头'],['cheeks','点脸回应'],['hold','长按回应'],['hair','拖发余摆'],['sleeve','拉袖回弹'],['hand','碰手收指'],['wind','阵风'],['sleep','困倦哈欠'],['double','双击回应'],['proximity','靠近离开']])button($('extra-buttons'),label,()=>call('control',{name:'demo',value:id}));
}
$('blush').oninput=()=>call('control',{name:'blush',value:Number($('blush').value)}).catch(()=>{});
