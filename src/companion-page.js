/* Companion workspace. Source data is always inserted using textContent/value. */
(()=>{
 const el=id=>document.getElementById(id),api=(a,d)=>window.sion.invoke(a,d),main=document.querySelector('main'),nav=document.querySelector('nav');
 function section(id,html){const p=document.createElement('section');p.id=id;p.className='page';p.innerHTML=html;main.append(p);return p;}
 const home=section('companion',`
  <div class="companion-heading journal-masthead">
   <div><span class="journal-kicker">诗音 · シオン</span><h2>陪伴空间</h2><p id="companion-date"></p></div>
   <div class="journal-tools"><span class="connection-pill" id="companion-connection">正在连接</span><button type="button" id="companion-reset">找回桌宠</button></div>
  </div>
  <div class="journal-tabs" role="group" aria-label="陪伴空间视图">
   <button type="button" data-companion-view="overview" aria-controls="companion-overview" aria-pressed="true">总览</button>
   <button type="button" data-companion-view="soul" aria-controls="companion-soul" aria-pressed="false">心绪与札记</button>
   <button type="button" data-companion-view="reminders" aria-controls="companion-reminders" aria-pressed="false">日程提醒</button>
  </div>
  <div id="companion-overview">
  <article class="journal-cover" id="companion-cover">
   <div class="journal-cover-copy">
    <span class="journal-kicker">相处札记</span>
    <h3>今天，和诗音聊一会儿。</h3>
    <p id="presence-label">平静地陪着你</p>
    <div class="journal-actions"><button type="button" class="primary" id="companion-talk">打开对话</button><button type="button" id="companion-voice">语音交谈</button></div>
   </div>
   <figure class="journal-portrait"><img src="sion-portrait.png" alt="诗音"></figure>
  </article>
  <div class="companion-grid journal-settings">
   <div class="companion-main">
    <article class="workspace-card relationship-card">
     <div class="card-head"><div><span class="card-eyebrow">BOND & STAGE</span><h3>关系与互动</h3></div><span class="soft-tag" id="relationship-stage-pill">长期相处</span></div>
     <div class="relationship-values"><div><small>长期阶段</small><strong id="relationship-label">初识</strong></div><div><small>当前互动</small><strong id="relationship-mood">平静</strong></div></div>
     <div class="relationship-track" aria-label="长期关系阶段"><span data-relation="acquaintance">初识</span><span data-relation="familiar">熟悉</span><span data-relation="close">亲近</span><span data-relation="intimate">亲密</span><span data-relation="deeply_bonded">羁绊</span><span data-relation="owner_exclusive">唯一专属</span></div>
     <p class="subtle" id="relationship-progress"></p>
     <details class="journal-disclosure" id="relationship-edit-box"><summary>调整关系阶段与专属羁绊背景</summary><form id="relationship-form"><label>关系阶段<select id="relationship-select"><option value="auto">按有效记忆和偏好自动调整</option><option value="acquaintance">初识</option><option value="familiar">熟悉</option><option value="close">亲近</option><option value="intimate">亲密</option><option value="deeply_bonded">羁绊</option><option value="owner_exclusive">唯一专属</option></select></label><label>专属联结背景（选填）<textarea id="relationship-bond" rows="2" maxlength="600" placeholder="自由填写你们之间独特的羁绊、过往或专属约定…"></textarea></label><button type="submit" class="primary">保存阶段与专属背景</button></form></details>
    </article>
   </div>
   <aside class="companion-side">
    <article class="workspace-card">
     <div class="card-head"><h3>陪伴表现</h3><span id="presence-emotion-tag" class="soft-tag">平静</span></div>
     <label class="meter-label">情绪强度<progress id="presence-intensity" max="1" value="0"></progress></label>
     <label class="switch-line"><span>随对话调整表情</span><input id="presence-auto-emotion" type="checkbox" checked></label>
     <label class="switch-line"><span>自然的小动作</span><input id="presence-auto-actions" type="checkbox" checked></label>
     <label class="switch-line"><span>自主待机动作</span><input id="presence-ambient-actions" type="checkbox" checked></label>
     <label class="switch-line"><span>保留短暂情绪余韵</span><input id="presence-afterglow" type="checkbox" checked></label>
    </article>
    <article class="workspace-card soul-shortcut-card">
     <div class="card-head"><h3>心绪与私密札记</h3><span id="soul-overview-tag" class="soft-tag">共鸣就绪</span></div>
     <p class="subtle" id="soul-overview-summary">四维灵魂共鸣、私密日记/梦境、未完挂念与专属画像已收进独立视图。</p>
     <button type="button" class="link-action" id="companion-open-soul">打开心绪与札记视图 →</button>
    </article>
    <article class="workspace-card">
     <h3>连接状态</h3>
     <div class="capability-line"><span>语音输入</span><b id="presence-asr">检查中</b></div>
     <button type="button" class="link-action" id="companion-open-models">查看模型与语音</button>
    </article>
   </aside>
  </div>
  </div>
  <section id="companion-soul" aria-label="心绪与札记" hidden>
   <article class="workspace-card soul-hero-card">
    <div class="card-head">
     <div><span class="card-eyebrow">SOUL RESONANCE · 灵魂共鸣</span><h3>四维心绪与睡眠巩固</h3></div>
     <div class="soul-head-actions"><span id="soul-summary-tag" class="soft-tag">共鸣就绪</span><button type="button" class="primary" id="sleep-consolidate-btn">✧ 立即睡眠巩固</button></div>
    </div>
    <div class="soul-meters-grid">
     <div class="soul-meter-item"><div><span>回忆深度</span><strong id="soul-val-recall">50%</strong></div><progress id="soul-bar-recall" max="100" value="50"></progress></div>
     <div class="soul-meter-item"><div><span>印象深度</span><strong id="soul-val-impression">50%</strong></div><progress id="soul-bar-impression" max="100" value="50"></progress></div>
     <div class="soul-meter-item"><div><span>表达欲望</span><strong id="soul-val-expression">50%</strong></div><progress id="soul-bar-expression" max="100" value="50"></progress></div>
     <div class="soul-meter-item"><div><span>思维发散</span><strong id="soul-val-creativity">50%</strong></div><progress id="soul-bar-creativity" max="100" value="50"></progress></div>
    </div>
    <p class="subtle" id="soul-meters-text">随对话温度、回忆命中与情绪余韵实时演化。点击「立即睡眠巩固」可整理今日画像、共同经历情景与私密日记/梦境。</p>
   </article>
   <div class="soul-grid">
    <article class="workspace-card" id="open-loops-box">
     <div class="card-head"><div><span class="card-eyebrow">OPEN LOOPS</span><h3>未完挂念的话题</h3></div><span class="soft-tag"><span id="open-loops-count">0</span> 项挂念</span></div>
     <div id="open-loops-list" class="soul-list"></div>
    </article>
    <article class="workspace-card" id="state-continuity-box">
     <div class="card-head"><div><span class="card-eyebrow">CONTINUITY</span><h3>跨天状态连续挂念</h3></div><span class="soft-tag"><span id="state-continuity-count">0</span> 项状态</span></div>
     <div id="state-continuity-list" class="soul-list"></div>
    </article>
    <article class="workspace-card" id="diaries-box">
     <div class="card-head"><div><span class="card-eyebrow">PRIVATE JOURNAL & DREAMS</span><h3>诗音的私密日记与梦境</h3></div><span class="soft-tag"><span id="diaries-count">0</span> 篇札记</span></div>
     <div id="diaries-list" class="soul-list soul-scroll"></div>
    </article>
    <article class="workspace-card" id="user-profile-box">
     <div class="card-head"><div><span class="card-eyebrow">PERSONA & EPISODES</span><h3>你的专属画像与相处情景</h3></div><span class="soft-tag"><span id="user-profile-count">0</span> 项记录</span></div>
     <div id="user-profile-list" class="soul-list soul-scroll"></div>
    </article>
    <article class="workspace-card soul-wide-card" id="self-timeline-box">
     <div class="card-head"><div><span class="card-eyebrow">SELF TIMELINE</span><h3>诗音的自我时间线</h3></div><span class="soft-tag"><span id="self-timeline-count">0</span> 条轨迹</span></div>
     <div id="self-timeline-list" class="soul-list soul-timeline-grid"></div>
    </article>
   </div>
  </section>
  <section id="companion-reminders" aria-label="日程提醒" hidden>
   <article class="workspace-card journal-reminders">
    <h3>提醒与约定</h3>
    <form id="companion-reminder-form">
     <label>这件事<input id="reminder-title" maxlength="120" placeholder="例如：晚上八点整理项目笔记" required></label>
     <div class="form-pair"><label>什么时候<input id="reminder-at" type="datetime-local" required></label><label>循环周期<select id="reminder-repeat"><option value="none">单次提醒</option><option value="daily">每天循环</option><option value="weekly">每周循环</option><option value="monthly">每月循环</option><option value="yearly">每年循环</option></select></label><button class="primary">记下提醒</button></div>
    </form>
    <div id="presence-reminders"></div>
   </article>
  </section>`);
 const models=section('providers',`<div class="companion-heading"><div><span class="eyebrow">THE RIGHT MODEL FOR EACH TASK</span><h2>让合适的模型，做合适的事。</h2><p>聊天、记忆整理、重排和语音识别，可分别连接不同服务。</p></div><button id="provider-save" class="primary">保存模型分配</button></div><div class="provider-layout"><div><article class="workspace-card"><div class="card-head"><div><span class="card-eyebrow">TASK ROUTING</span><h3>按任务分配</h3></div><span class="soft-tag">默认沿用原设置</span></div><div id="provider-routes"></div><p class="subtle">情绪判断随聊天一次返回，不额外调用情绪模型。语义索引继续在本机运行；记忆整理仍遵守每日额度。</p></article><article class="workspace-card"><div class="card-head"><div><span class="card-eyebrow">YOUR CONNECTIONS</span><h3>模型档案</h3></div><button id="provider-add">＋ 添加模型</button></div><div id="provider-profiles"></div></article><article class="workspace-card"><span class="card-eyebrow">RECENT REQUESTS</span><h3>最近的任务</h3><div id="provider-activity"></div></article></div><aside><article class="workspace-card"><span class="card-eyebrow">VOICE CONVERSATION</span><h3>听懂你说的话</h3><label>识别方式<select id="speech-mode"><option value="local">本机识别 · 无转写API费用</option><option value="api">使用上方分配的识别API</option></select></label><label>主要语言<select id="speech-language"><option value="zh">中文</option><option value="ja">日语</option><option value="en">英语</option><option value="auto">自动判断</option></select></label><p id="speech-ready" class="subtle"></p><details><summary>本机识别环境</summary><label>Python位置<input id="speech-python"></label><label>识别模型目录<input id="speech-model"></label></details><button id="speech-save" class="primary">保存语音输入设置</button><p class="subtle">在聊天框开启一次麦克风。收起聊天后可继续说话，也可在播报时插话。关闭麦克风、锁屏或退出会结束监听。</p></article><article class="workspace-card"><span class="card-eyebrow">KEEP IT SIMPLE</span><h3>先从简单的分配开始</h3><p class="subtle">日常聊天选你喜欢的模型；记忆提取和重排可以选更便宜的模型。没有独立设置时继续使用原聊天连接。</p><p class="subtle">主聊天可在连接失败、限流或服务故障时尝试一次备用模型。记忆失败退回本地，不追加付费请求。</p><button class="link-action" id="provider-old-settings">原聊天与朗读设置 →</button></article></aside></div>`);
 const dayOverview=window.mountCompanionDay(home);
 const importedNotice=document.createElement('p');importedNotice.className='note';importedNotice.hidden=true;
 models.querySelector('#provider-profiles').before(importedNotice);
 const names={companion:'陪伴空间',chat:'对话',character:'角色与动作',memory:'记忆',providers:'模型与语音',settings:'连接与朗读'};
 const journalScroll={overview:0,soul:0,reminders:0};
 home.dataset.view='overview';
 function showJournalView(view){
  const previous=home.dataset.view;
  if(previous===view)return;
  journalScroll[previous]=main.scrollTop;
  home.dataset.view=view;
  el('companion-overview').hidden=view!=='overview';
  if(el('companion-soul'))el('companion-soul').hidden=view!=='soul';
  el('companion-reminders').hidden=view!=='reminders';
  home.querySelectorAll('.journal-tabs button').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.companionView===view)));
  main.scrollTop=journalScroll[view]||0;
 }
 if(el('companion-open-soul'))el('companion-open-soul').onclick=()=>showJournalView('soul');
 home.querySelectorAll('[data-companion-view]').forEach(button=>button.onclick=()=>showJournalView(button.dataset.companionView));
 document.addEventListener('click',event=>{
  const button=event.target.closest?.('[data-page],[data-console-page]');
  const destination=button?.dataset.page||button?.dataset.consolePage;
  if(destination&&destination!=='companion'&&home.classList.contains('active'))journalScroll[home.dataset.view]=main.scrollTop;
 },true);
 for(const id of ['companion','providers']){const b=document.createElement('button');b.className='nav';b.dataset.page=id;b.textContent=names[id];nav.append(b);}
 ['companion','chat','character','memory','providers','settings'].forEach((id,i)=>{const b=document.querySelector('[data-page='+id+']');b.textContent=names[id];const number=document.createElement('span');number.textContent=String(i+1).padStart(2,'0');b.append(number);nav.append(b);b.onclick=()=>{if(id==='companion'&&home.classList.contains('active'))return;document.querySelectorAll('.page,.nav').forEach(e=>e.classList.remove('active'));b.classList.add('active');el(id).classList.add('active');el('page-title').textContent=names[id];main.scrollTop=id==='companion'?journalScroll[home.dataset.view]:0;if(id==='companion')refreshPresence();if(id==='providers')loadProviders();if(id==='memory')loadMemories(true);};});
 function go(id){document.querySelector('[data-page='+id+']').click();}
 el('companion-date').textContent=new Date().toLocaleDateString('zh-CN',{year:'numeric',month:'long',day:'numeric',weekday:'long'});
 el('companion-talk').onclick=()=>go('chat');el('companion-voice').onclick=()=>{go('chat');const toggle=document.querySelector('#chat .voice-start');if(toggle?.getAttribute('aria-pressed')!=='true')toggle?.click();};el('companion-open-models').onclick=()=>go('providers');el('provider-old-settings').onclick=()=>go('settings');
 el('companion-reset').onclick=()=>api('reset').catch(error=>toast(error.message));
 function empty(box,text){const p=document.createElement('p');p.className='empty-state';p.textContent=text;box.append(p);}
 let relationshipDraft=false;
 function paintRelationship(r){
  const relation=r.interaction_policy;
  if(!relation)return;
  el('relationship-label').textContent=relation.label;
  const band=r.expression_decision;
  el('relationship-mood').textContent=band?band.label+'（温暖度 '+band.warmth+'）':r.emotion.label;
  const focus=relation.focus_preference?.value;
  const focusLabel=focus==='quiet'?' · 专注时保持安静':focus==='normal'?' · 专注时允许主动搭话':'';
  el('relationship-progress').textContent=relation.known_sources+' 项偏好来源 · '+relation.shared_sources+
    ' 项共同经历来源'+focusLabel+(relation.manual?' · 阶段已手动设定':'')+
    ' · 历史积分 '+(r.relationship?.score??0);
  for(const node of home.querySelectorAll('[data-relation]')){
   const active=node.dataset.relation===relation.stage;
   node.classList.toggle('active',active);
   node.setAttribute('aria-current',active?'step':'false');
  }
  if(!relationshipDraft){el('relationship-select').value=relation.manual||'auto';if(el('relationship-bond'))el('relationship-bond').value=relation.exclusive_bond||r.relationship?.exclusive_bond||'';}
  if(r.soul_state){
   const s=r.soul_state,pct=v=>Math.round((v??0.5)*100);
   for(const [k,v] of [['recall',s.recall_depth],['impression',s.impression_depth],['expression',s.expression_desire],['creativity',s.creativity]]){
    const n=pct(v);
    if(el('soul-val-'+k))el('soul-val-'+k).textContent=n+'%';
    if(el('soul-bar-'+k))el('soul-bar-'+k).value=n;
   }
   const summary='回忆 '+pct(s.recall_depth)+'% · 印象 '+pct(s.impression_depth)+'% · 表达欲 '+pct(s.expression_desire)+'% · 思维发散 '+pct(s.creativity)+'%';
   if(el('soul-overview-summary')){
    const loops=(r.open_loops||[]).length,diaries=(r.diaries||[]).length,profs=(r.user_profile||[]).length;
    el('soul-overview-summary').textContent=summary+' · '+loops+' 项未完挂念 · '+diaries+' 篇日记/梦境 · '+profs+' 项专属画像';
   }
  }
  if(el('open-loops-list')){
   const loops=r.open_loops||[];el('open-loops-count').textContent=String(loops.length);
   const box=el('open-loops-list');box.replaceChildren();
   if(!loops.length)empty(box,'暂无未完话题。聊天中提到稍后要做的事会自动记在这里。');
   for(const item of loops){
    const row=document.createElement('div');row.className='capability-line';
    const span=document.createElement('span');span.textContent=item.topic;
    const btn=document.createElement('button');btn.type='button';btn.textContent='已完结';
    btn.onclick=()=>api('companion-open-loop',{action:'resolve',id:item.id}).then(paintPresence).catch(e=>toast(e.message));
    row.append(span,btn);box.append(row);
   }
  }
  if(el('diaries-list')){
   const diaries=r.diaries||[];el('diaries-count').textContent=String(diaries.length);
   const box=el('diaries-list');box.replaceChildren();
   if(!diaries.length)empty(box,'她还没有写下新的日记或梦境碎片。');
   for(const d of diaries){
    const row=document.createElement('article');row.className='reminder-row';
    const p=document.createElement('p'),sm=document.createElement('small');
    p.textContent=(d.kind==='dream'?'【梦境碎片】':'【私密日记】')+d.content;
    sm.textContent=[d.emotion,d.created_at?new Date(d.created_at).toLocaleString('zh-CN'):''].filter(Boolean).join(' · ');
    row.append(p,sm);box.append(row);
   }
  }
  if(el('state-continuity-list')){
   const states=r.state_continuity||[];el('state-continuity-count').textContent=String(states.length);
   const box=el('state-continuity-list');box.replaceChildren();
   if(!states.length)empty(box,'暂无持续状态记录（如熬夜、感冒、赶项目）。');
   for(const st of states){
    const row=document.createElement('div');row.className='capability-line';
    const span=document.createElement('span');span.textContent=st.state_text;
    const btn=document.createElement('button');btn.type='button';btn.textContent='已恢复';
    btn.onclick=()=>api('companion-open-loop',{action:'resolve_state',id:st.id}).then(paintPresence).catch(e=>toast(e.message));
    row.append(span,btn);box.append(row);
   }
  }
  if(el('user-profile-list')){
   const profs=r.user_profile||[],eps=r.dialogue_episodes||[];
   el('user-profile-count').textContent=String(profs.length+eps.length);
   const box=el('user-profile-list');box.replaceChildren();
   if(!profs.length&&!eps.length)empty(box,'多聊几句或点击下方「立即睡眠巩固」，会自动沉淀你的画像与共同经历情景。');
   for(const p of profs){
    const row=document.createElement('div');row.className='capability-line';
    const k=document.createElement('span'),v=document.createElement('b');
    k.textContent=p.attr_label;v.textContent=p.attr_value;row.append(k,v);box.append(row);
   }
   for(const ep of eps){
    const row=document.createElement('article');row.className='reminder-row';
    const p=document.createElement('p');p.textContent='【情景记忆】'+ep.summary;
    row.append(p);box.append(row);
   }
  }
  if(el('self-timeline-list')){
   const tl=r.self_timeline||[];el('self-timeline-count').textContent=String(tl.length);
   const box=el('self-timeline-list');box.replaceChildren();
   if(!tl.length)empty(box,'暂无近期活动时间线。');
   for(const item of tl){
    const row=document.createElement('div');row.className='capability-line';
    const span=document.createElement('span');span.textContent=item.summary;
    row.append(span);box.append(row);
   }
  }
 }
 el('relationship-select').options[0].textContent='按有效记忆和偏好自动调整';
 el('relationship-select').onchange=()=>{relationshipDraft=true;};
 if(el('relationship-bond'))el('relationship-bond').oninput=()=>{relationshipDraft=true;};
 el('relationship-form').onsubmit=async e=>{
  e.preventDefault();
  try{
   const result=await api('relationship-set',{stage:el('relationship-select').value,exclusive_bond:el('relationship-bond')?.value||''});
   relationshipDraft=false;paintRelationship(result);toast('关系阶段已保存');
  }catch(error){toast(error.message);}
 };
 function paintPresence(r){
  dayOverview.paint(r);
  el('presence-label').textContent='此刻的心情 · '+r.emotion.label;
  el('presence-emotion-tag').textContent=r.emotion.label;
  el('presence-intensity').value=r.emotion.intensity;
  paintRelationship(r);
  for(const [id,key] of [['presence-auto-emotion','automatic_emotion'],['presence-auto-actions','automatic_actions'],['presence-ambient-actions','ambient_actions'],['presence-afterglow','afterglow']])el(id).checked=r.config[key];
  const reminders=el('presence-reminders');
  reminders.replaceChildren();
  if(!r.reminders.length)empty(reminders,'暂时没有提醒。把你真正想记住的时间放在这里。');
  for(const m of r.reminders){
   const row=document.createElement('article'),text=document.createElement('p'),info=document.createElement('small');
   row.className='reminder-row';text.textContent=m.title;
   const phase={pending:'等到那时',dispatching:'已发出，等待展示回执',notified:'已显示提醒',
    uncertain:'展示未确认',cancelled:'已取消',done:'已完成',overdue:'已错过时间'}[m.status];
   const audio={requested:'语音合成中',generated:'语音已合成',playing:'正在播放',finished:'语音已播完',
    failed:'语音未播完',interrupted:'语音已中断',unconfirmed:'语音未确认',skipped:'本次使用文字提醒'}[m.audio_state];
   const repeatLabel={daily:'每天循环',weekly:'每周循环',monthly:'每月循环',yearly:'每年循环'}[m.repeat];
   info.textContent=[new Date(m.at*1000).toLocaleString('zh-CN'),repeatLabel,phase,audio].filter(Boolean).join(' · ');
   row.append(text,info);
   const actions=['done','cancelled','overdue'].includes(m.status)?[['移除','remove']]:[['完成','done'],['移除','remove']];
   for(const [label,action] of actions){const b=document.createElement('button');b.textContent=label;b.onclick=()=>api('companion-reminder',{id:m.id,action}).then(paintPresence).catch(e=>toast(e.message));row.append(b);}
   reminders.append(row);
  }
 }
 async function refreshPresence(){try{paintPresence(await api('companion-status'));const m=await api('memory-status'),count=m.enhancement.memory_counts.active||0;dayOverview.memory(count);}catch(e){toast(e.message);}}
 for(const [id,key] of [['presence-auto-emotion','automatic_emotion'],['presence-auto-actions','automatic_actions'],['presence-ambient-actions','ambient_actions'],['presence-afterglow','afterglow']])el(id).onchange=()=>api('companion-config',{[key]:el(id).checked}).then(paintPresence).catch(e=>toast(e.message));
 if(el('sleep-consolidate-btn'))el('sleep-consolidate-btn').onclick=()=>api('companion-open-loop',{action:'sleep_consolidate'}).then(r=>{paintPresence(r);toast('已完成睡眠巩固：整理了画像、情景与今日札记');}).catch(e=>toast(e.message));
 el('companion-reminder-form').onsubmit=async e=>{e.preventDefault();try{paintPresence(await api('companion-reminder',{title:el('reminder-title').value,at:new Date(el('reminder-at').value).getTime()/1000,repeat:el('reminder-repeat')?.value||'none'}));el('reminder-title').value='';toast('到时会在桌面提醒你');}catch(e){toast(e.message);}};
 let providerDraft=null,providerDirty=false;
 const taskNames={'vision':['屏幕理解','共享屏幕时，接收当前画面的图片模型。'],'computer':['电脑操作规划','根据当前窗口，规划一件待确认的操作。'],'dialogue':['日常交谈','回复你，也带回当下情绪与表情。'],'memory.extract':['记忆提取','从交流中整理值得留下的信息。'],'memory.embedding':['记忆向量','默认使用本地 MiniLM。选用 API 后，纳入索引的记忆、资料片段与召回查询会发给该服务。'],'memory.rerank':['回忆重排','本地结果难判断时，再核对相关性。'],'asr':['语音识别API','使用云端识别时，把说话转换成文字。']};
 function field(label,value,type='text'){const l=document.createElement('label'),input=document.createElement('input');l.textContent=label;input.type=type;input.value=value??'';l.append(input);return {l,input};}
 function routeSelect(value,purpose){const select=document.createElement('select'),defaultOption=document.createElement('option');defaultOption.value='';defaultOption.textContent=purpose==='memory.embedding'?'本地 MiniLM · 默认':purpose==='asr'?'未分配 · 默认用本机识别':purpose==='vision'?'自动 · 已支持图片的聊天模型':'沿用原聊天设置';select.append(defaultOption);for(const p of providerDraft.profiles.filter(p=>purpose==='memory.embedding'?p.protocol==='embedding':p.protocol!=='embedding'&&(p.protocol==='rerank'?purpose==='memory.rerank':(p.protocol==='asr')===(purpose==='asr')))){const o=document.createElement('option');o.value=p.id;o.textContent=p.label+' · '+(p.name||'尚未填写模型');select.append(o);}select.value=value||'';return select;}
 function paintRoutes(){const box=el('provider-routes');box.replaceChildren();for(const [purpose,[name,note]] of Object.entries(taskNames)){const row=document.createElement('article'),description=document.createElement('div'),title=document.createElement('h4'),sub=document.createElement('p'),pair=document.createElement('div');row.className='provider-route';title.textContent=name;sub.textContent=note;description.append(title,sub);row.append(description);const primary=routeSelect(providerDraft.routes[purpose],purpose),fallback=routeSelect(providerDraft.fallbacks[purpose],purpose);fallback.options[0].textContent=purpose==='memory.embedding'?'暂不可用时使用关键词与图谱':purpose==='dialogue'?'不使用备用模型':['asr','vision'].includes(purpose)?'失败时提示重试':'失败时使用本地结果';if(purpose!=='dialogue'){fallback.value='';fallback.disabled=true;providerDraft.fallbacks[purpose]='';}primary.setAttribute('aria-label',name+'首选模型');fallback.setAttribute('aria-label',name+'备用模型');primary.onchange=()=>{providerDraft.routes[purpose]=primary.value;providerDirty=true;};fallback.onchange=()=>{providerDraft.fallbacks[purpose]=fallback.value;providerDirty=true;};pair.className='route-selects';pair.append(primary,fallback);row.append(pair);box.append(row);}}
 function paintProfiles(){const box=el('provider-profiles');box.replaceChildren();if(!providerDraft.profiles.length)empty(box,'还没有独立档案。现在各任务继续沿用你的原聊天配置。');for(const p of providerDraft.profiles){const card=document.createElement('details'),summary=document.createElement('summary'),body=document.createElement('div');card.className='provider-profile';card.open=!p.name;summary.textContent=p.label+(p.name?' · '+p.name:' · 待填写');card.append(summary);body.className='profile-fields';const label=field('档案名称',p.label),base=field('服务地址',p.baseUrl),model=field('模型名称',p.name),key=field(p.keySaved?'密钥已保存 · 留空继续使用':'API密钥','','password'),limit=field('最多输出 tokens',p.maxTokens||1200,'number'),timeout=field('等待秒数',p.timeoutSeconds||45,'number');const protocolLabel=document.createElement('label'),protocol=document.createElement('select');protocolLabel.textContent='接口格式';for(const [value,text] of [['openai','OpenAI兼容（DeepSeek、Ollama等）'],['anthropic','Anthropic Messages'],['gemini','Google Gemini'],['asr','OpenAI兼容语音识别'],['embedding','向量嵌入 API'],['rerank','重排 API']]){const o=document.createElement('option');o.value=value;o.textContent=text;protocol.append(o);}protocol.value=p.protocol;protocolLabel.append(protocol);protocol.onchange=()=>{p.protocol=protocol.value;providerDirty=true;paintRoutes();};body.append(label.l,protocolLabel,base.l,model.l,key.l,limit.l,timeout.l);for(const [control,property] of [[label.input,'label'],[base.input,'baseUrl'],[model.input,'name'],[key.input,'apiKey'],[limit.input,'maxTokens'],[timeout.input,'timeoutSeconds']])control.oninput=()=>{p[property]=control.type==='number'?Number(control.value):control.value;providerDirty=true;};const clear=document.createElement('label'),checkbox=document.createElement('input');checkbox.type='checkbox';clear.className='switch-line';clear.append('清除这个档案的密钥',checkbox);checkbox.onchange=()=>{p.clearKey=checkbox.checked;providerDirty=true;};body.append(clear);const actions=document.createElement('div'),test=document.createElement('button'),remove=document.createElement('button');actions.className='profile-actions';test.textContent='保存后测试连接';test.type=remove.type='button';test.disabled=p.protocol==='asr';test.onclick=async()=>{try{await saveProviders();test.disabled=true;const r=await api('providers-test',{id:p.id});toast(r.label+'已连通 · '+(r.milliseconds/1000).toFixed(1)+'秒');}catch(e){toast(e.message);}finally{test.disabled=false;}};remove.textContent='移除档案';remove.onclick=()=>{providerDraft.profiles=providerDraft.profiles.filter(x=>x.id!==p.id);for(const t of Object.keys(taskNames))for(const k of ['routes','fallbacks'])if(providerDraft[k][t]===p.id)providerDraft[k][t]='';providerDirty=true;paintProfiles();paintRoutes();};actions.append(test,remove);body.append(actions);card.append(body);box.append(card);}}
 async function loadProviders(){if(!providerDirty){providerDraft=await api('providers');paintProfiles();paintRoutes();}const imported=providerDraft.profiles.filter(p=>p.id.startsWith('astrbot_'));importedNotice.hidden=!imported.length&&!providerDraft.keyError;importedNotice.textContent=providerDraft.keyError?providerDraft.configError:'从 AstrBot 导入 '+imported.length+' 个档案，'+imported.filter(p=>p.keySaved).length+' 个已保存密钥。可在上方为记忆向量、提取和重排分别选模型。';const s=await api('speech-status');el('speech-mode').value=s.config.mode;el('speech-language').value=s.config.language;el('speech-python').value=s.config.python;el('speech-model').value=s.config.modelPath;el('speech-ready').textContent=s.localAvailable?'已找到本机识别环境 · CPU运行 · 空闲90秒释放。':'本机识别环境未找到，可检查路径或选择识别API。';const box=el('provider-activity');box.replaceChildren();for(const a of providerDraft.activity||[]){const row=document.createElement('div');row.className='capability-line';row.textContent=(taskNames[a.purpose]?.[0]||a.purpose)+' · '+a.label+' · '+(a.ok?'完成':'未完成')+(a.fallback?' · 使用备用':'')+(a.inputTokens===undefined?'':' · 输入 '+a.inputTokens+' / 输出 '+a.outputTokens+(a.cachedTokens===undefined?'':' · 缓存命中 '+a.cachedTokens));box.append(row);}if(!box.childNodes.length)empty(box,'发起任务后，这里显示实际使用的模型。');}
 async function saveProviders(){const saved=await api('providers-save',providerDraft);providerDraft=saved;providerDirty=false;paintProfiles();paintRoutes();toast('模型分配已保存；新请求开始使用');return saved;}
 el('provider-add').onclick=()=>{providerDraft.profiles.push({id:'model_'+crypto.randomUUID().slice(0,8),label:'新模型',protocol:'openai',baseUrl:'https://api.deepseek.com/v1',name:'',maxTokens:1200,timeoutSeconds:45});providerDirty=true;paintProfiles();paintRoutes();};el('provider-save').onclick=()=>saveProviders().catch(e=>toast(e.message));
 el('speech-save').onclick=()=>api('speech-config',{mode:el('speech-mode').value,language:el('speech-language').value,python:el('speech-python').value,modelPath:el('speech-model').value}).then(()=>toast('语音输入设置已保存')).catch(e=>toast(e.message));
 window.sion.subscribe(e=>{if(e.type==='state'){const s=e.state;el('companion-connection').textContent=s.memoryReady?'● 已在身边':'正在连接';el('presence-asr').textContent=s.speechInput?.localAvailable?'本机可用':'可配置API';if(s.companion)paintPresence(s.companion);}if(e.type==='companion-notice')toast('诗音提醒你：'+e.notice.title);});
 setInterval(()=>{if(!document.hidden&&home.classList.contains('active'))refreshPresence();},15000);
 go('companion');
})();
