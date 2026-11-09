/* All content is rendered as text. Network edges carry real source memory IDs. */
const memoryTabs=document.querySelector('.memory-tabs');let memoryViewSerial=0,graphPayload=null,graphFullScope=false;
function memoryPane(id,title,html){const b=document.createElement('button');b.type='button';b.dataset.memoryTab=id;b.setAttribute('role','tab');b.textContent=title;memoryTabs.append(b);const pane=document.createElement('div');pane.id='memory-pane-'+id;pane.className='memory-pane';pane.innerHTML=html;$('memory').append(pane);b.onclick=()=>{document.querySelectorAll('[data-memory-tab]').forEach(x=>{x.classList.toggle('selected',x===b);x.setAttribute('aria-selected',String(x===b));});document.querySelectorAll('.memory-pane').forEach(x=>x.classList.toggle('active',x===pane));if(window.Graph2D)window.Graph2D.setActive(id==='network');if(id==='network')loadMemoryGraph();if(id==='profile'){loadMemoryProfiles();loadDeepMemoryPane();}if(id==='maintenance')loadMemoryBackups();};}
memoryPane('network','记忆网络',`<div class="lm-graph-shell"><header class="lm-graph-header"><div class="lm-graph-title-wrap"><div class="lm-brand-badge"><span class="lm-mark">LM</span><span>LIVING MEMORY · LIVE GRAPH / XY</span></div><h3 class="lm-page-title"><span class="lm-page-index">01</span>知识图谱</h3><span class="lm-license-tag" title="知识图谱 2D 力导向引擎与视觉设计移植自开源项目 astrbot_plugin_livingmemory (GNU AGPL-3.0)">开源图谱引擎：astrbot_plugin_livingmemory · AGPL-3.0</span></div><div class="lm-header-actions"><button id="memory-graph-scope-btn" type="button" class="lm-btn lm-btn-secondary">⊞ 受限概览</button><button id="memory-graph-reset" type="button" class="lm-btn lm-btn-secondary">概览</button></div></header><div class="lm-graph-body"><div class="lm-stat-pills" id="graph-stats"><div class="lm-stat-pill" data-index="A1"><div class="lm-stat-value" id="gs-total">0</div><div class="lm-stat-label">总记忆</div></div><div class="lm-stat-pill" data-index="A2"><div class="lm-stat-value lm-c-moss" id="gs-nodes">0</div><div class="lm-stat-label">节点</div></div><div class="lm-stat-pill" data-index="A3"><div class="lm-stat-value lm-c-coral" id="gs-edges">0</div><div class="lm-stat-label">关系</div></div><div class="lm-stat-pill" data-index="A4"><div class="lm-stat-value lm-c-cyan" id="gs-sessions">0</div><div class="lm-stat-label">活跃会话</div></div></div><div class="lm-canvas-container" id="graph-canvas-container"><div id="memory-graph-info" class="lm-canvas-state" role="status"></div><canvas id="memory-graph-canvas" class="graph-canvas" width="960" height="540" aria-label="记忆关联网络，可缩放拖动"></canvas></div><div class="lm-graph-legend" id="graph-legend"></div><form id="memory-graph-form" class="lm-graph-toolbar"><input id="memory-graph-query" class="lm-input" placeholder="输入人物、主题、事实或整句，查看召回到的图谱子图"><button type="submit" class="lm-btn lm-btn-primary">🔍 检索图谱</button><input id="memory-graph-focus-id" class="lm-input lm-input-short" placeholder="输入记忆 ID 定位局部子图"><button type="button" id="memory-graph-focus-btn" class="lm-btn lm-btn-secondary">⌖ 定位记忆</button></form></div><div id="memory-graph-detail" class="lm-peek-card" role="status" hidden></div><details class="lm-memory-list-drawer"><summary>关联内容列表</summary><div id="memory-graph-list" class="lm-memory-chip-list"></div></details></div>`);
memoryPane('profile','偏好与习惯',`<div class="memory-profile-grid"><div class="settings-card"><div class="card-head"><h3>记得你的偏好</h3><button id="memory-profile-refresh" type="button">刷新</button></div><p class="note">这里只展示你明确说过的偏好、关系和计划；不把一时的心情写成性格。每项都能查看来源和更正。</p><div id="memory-profile-list"></div></div><div class="settings-card"><h3>说话习惯学习</h3><p class="note">从明确的相处偏好中积累依据。同一种习惯在三个不同日期出现后，你可确认用于后续对话。</p><div id="memory-learning-list"></div></div></div><div class="settings-card soul-hero-card memory-soul-spacing"><div class="card-head"><div><span class="card-eyebrow">DEEP MEMORY & SOUL</span><h3>灵魂共鸣与睡眠巩固</h3></div><div class="soul-head-actions"><span class="soft-tag">艾宾浩斯软衰减已启用</span><button type="button" class="primary" id="mem-deep-sleep-btn">✧ 立即睡眠巩固</button></div></div><p class="note" id="mem-deep-soul-text">回忆深度 50% · 印象深度 50% · 表达欲望 50% · 思维发散 50%</p></div><div class="memory-deep-grid"><div class="settings-card"><div class="card-head"><h3>你的专属画像与相处情景</h3><span class="soft-tag" id="mem-deep-profile-count">0 项</span></div><div id="mem-deep-profile-list" class="soul-list soul-scroll"></div></div><div class="settings-card"><div class="card-head"><h3>诗音的私密日记与梦境</h3><span class="soft-tag" id="mem-deep-diaries-count">0 篇</span></div><div id="mem-deep-diaries-list" class="soul-list soul-scroll"></div></div><div class="settings-card"><div class="card-head"><h3>未完挂念的话题</h3><span class="soft-tag" id="mem-deep-loops-count">0 项</span></div><div id="mem-deep-loops-list" class="soul-list"></div></div><div class="settings-card"><div class="card-head"><h3>跨天状态连续挂念</h3><span class="soft-tag" id="mem-deep-states-count">0 项</span></div><div id="mem-deep-states-list" class="soul-list"></div></div></div>`);
memoryPane('maintenance','整理与备份',`<div class="settings-card"><h3>长期留存与本机备份</h3><p class="note">重要记忆可以固定保护。稳定事实不会仅因时间久就被自动删除；归档的内容可以恢复。备份恢复时继续遵守后来发生的删除。</p><div class="memory-tools"><button id="memory-maintain" type="button">检查与整理</button><button id="memory-backup-create" class="primary" type="button">创建本机备份</button></div><p id="memory-maintain-result" role="status"></p><div id="memory-backup-list"></div></div><div class="settings-card"><h3>导入与导出 JSON</h3><p class="note">导出包含记忆及其来源依据，请保存在你信任的位置。导入先预览，不覆盖已有记录。</p><div class="memory-tools"><button id="memory-export" type="button">下载记忆 JSON</button><button id="memory-import-preview" type="button">预览导入</button><button id="memory-import-run" class="primary" type="button" hidden>按预览执行导入</button></div><label class="memory-import-label">选择以前导出的记忆<input type="file" id="memory-import-file" accept="application/json,.json"></label><p id="memory-import-result" role="status"></p></div>`);
memoryPane('prompts','整理偏好',`<div class="settings-card"><h3>哪些事情值得记住</h3><p class="note">默认优先保留明确偏好、重要约定、人物关系和可复用的经历。原文依据、身份范围和删除规则始终有效。</p><label>补充整理偏好<textarea id="mem-guidance" maxlength="1000" rows="5" placeholder="例如：优先记录长期项目、称呼和重要约定，少记普通闲聊。"></textarea></label><div class="memory-tools"><button id="memory-guidance-save" class="primary" type="button">保存偏好</button><button id="memory-guidance-reset" type="button">恢复默认</button></div></div>`);
const costBox=document.createElement('div');costBox.className='settings-card';costBox.innerHTML=`<h3>控制额外花费</h3><label>记忆整理方式<select id="memory-cost-mode"><option value="economy">省量：本地优先，难以判断时再核对</option><option value="quality">细致：更多使用模型整理与重排</option></select></label><label>每天最多调用记忆模型次数<input id="memory-daily-calls" type="number" min="0" max="200" value="12"></label><label>每日额外输入预算（估算 tokens）<input id="memory-daily-input" type="number" min="0" max="2000000" value="12000"></label><p class="note">只限制额外记忆整理与重排，不限制正常聊天。任一上限设为 0 后仍可本地检索。输入预算采用保守估算，最终费用以服务方账单为准；超出时使用本地结果。</p><p id="memory-usage" role="status"></p><p id="memory-deepseek-cache" class="note" hidden></p>`;$('memory-pane-settings').prepend(costBox);
const addPolicy=document.createElement('div');addPolicy.className='memory-tools';addPolicy.innerHTML='<label class="toggle"><input id="memory-add-pinned" type="checkbox">固定保护这件事</label><label>重要程度<input id="memory-add-importance" type="range" min="0" max="1" step=".05" value=".7"></label>';$('memory-form').insertBefore(addPolicy,$('memory-form').lastElementChild);
const archived=document.createElement('option');archived.value='archived';archived.textContent='已归档';$('memory-scope').append(archived);
window.memoryPolicyControls=function(row,m){
 if(!['active','archived','candidate'].includes(m.status))return;
 const info=document.createElement('small');info.className='note';info.textContent='重要程度 '+Math.round((m.importance??.5)*100)+' / 100'+(m.pinned?' · 已固定保护':'')+(m.useful_count?' · 有用反馈 '+m.useful_count+' 次':'');row.append(info);
 if(m.status==='active'){
  const controls=document.createElement('div');controls.className='memory-tools';const priority=document.createElement('input');priority.type='range';priority.min=0;priority.max=1;priority.step=.05;priority.value=m.importance??.5;priority.setAttribute('aria-label','重要程度');const label=document.createElement('label');label.textContent='固定保护';label.className='toggle';const pin=document.createElement('input');pin.type='checkbox';pin.checked=m.pinned;label.prepend(pin);controls.append(priority,label);row.append(controls);
  memoryButton(controls,'保存保护设置',async()=>{await call('memory-action',{id:m.memory_id,revision:m.revision,action:'policy',pinned:pin.checked,importance:Number(priority.value)});toast('保护设置已保存');await loadMemories();});
  memoryButton(controls,'这条有用',async()=>{await call('memory-action',{id:m.memory_id,revision:m.revision,action:'feedback',useful:true});toast('已记录有用反馈');});
  memoryButton(controls,'这条没帮助',async()=>{await call('memory-action',{id:m.memory_id,revision:m.revision,action:'feedback',useful:false});toast('已记录反馈，后续回忆会参考');});
  if(!m.pinned)memoryButton(controls,'归档',async()=>{await call('memory-action',{id:m.memory_id,revision:m.revision,action:'archive'});await loadMemories();});
 }else if(m.status==='archived')memoryButton(row,'恢复使用',async()=>{await call('memory-action',{id:m.memory_id,revision:m.revision,action:'restore'});await loadMemories();});
 if(m.status==='candidate'){
  memoryButton(row,'确认这条记忆',async()=>{await call('memory-action',{id:m.memory_id,revision:m.revision,action:'approve'});await loadMemories();});
  memoryButton(row,'拒绝候选',async()=>{await call('memory-action',{id:m.memory_id,revision:m.revision,action:'reject'});await loadMemories();});
 }
};
window.fillMemoryExtras=function(e){$('memory-cost-mode').value=e.config?.cost_mode||'economy';$('memory-daily-calls').value=e.config?.daily_calls??12;$('memory-daily-input').value=e.config?.daily_input_tokens??12000;if(document.activeElement!==$('mem-guidance'))$('mem-guidance').value=e.config?.guidance||'';const u=e.usage||{};$('memory-usage').textContent='今天已使用 '+(u.calls||0)+' / '+(u.limit??12)+' 次额外记忆调用 · 输入 '+(u.input_tokens||0)+'，输出 '+(u.output_tokens||0)+' tokens'+(u.all_measured?'（模型返回的用量）':'（未返回用量的请求按估算计入）');
 const cache=u.deepseek_cache||[];
 const output=$('memory-deepseek-cache');
 const totals=cache.reduce((a,b)=>({input:a.input+b.input_tokens,hits:a.hits+b.cached_tokens,calls:a.calls+b.measured}),{input:0,hits:0,calls:0});
 output.hidden=!totals.input;
 if(totals.input)output.textContent='DeepSeek 额外记忆请求 · '+totals.calls+' 次有回报 · 命中 '+totals.hits+' / '+totals.input+' tokens（'+Math.round(totals.hits*100/totals.input)+'%）';
};
$('mem-save').onclick=async()=>{try{await call('memory-config',{automatic:$('mem-auto').checked,rerank:$('mem-rerank').checked,cost_mode:$('memory-cost-mode').value,daily_calls:Number($('memory-daily-calls').value),daily_input_tokens:Number($('memory-daily-input').value)});await memorySummary();toast('省量设置已保存');}catch{}};
$('memory-guidance-save').onclick=()=>call('memory-config',{guidance:$('mem-guidance').value}).then(()=>toast('整理偏好已保存')).catch(()=>{});
$('memory-guidance-reset').onclick=()=>call('memory-config',{guidance:''}).then(()=>{$('mem-guidance').value='';toast('已恢复默认');}).catch(()=>{});
async function loadMemoryProfiles(){const serial=memoryViewSerial;const r=await call('memory-profiles');if(serial!==memoryViewSerial)return;paintLearning(r.learning||[]);const box=$('memory-profile-list');box.replaceChildren();for(const m of r.items){const a=document.createElement('article');a.className='memory-profile-item';const p=document.createElement('p');p.textContent=m.text;a.append(p);memoryButton(a,'查看与更正',()=>focusMemoryEntry(m.memory_id));box.append(a);}if(!r.items.length)box.textContent='还没有明确记录的偏好、关系或计划。';}
function paintLearning(items){
 const list=$('memory-learning-list');list.replaceChildren();
 if(!items.length){list.textContent='还没有明确的说话习惯依据。';return;}
 for(const item of items){
  const row=document.createElement('article');row.className='memory-profile-item';
  const title=document.createElement('strong'),status=document.createElement('p');
  title.textContent=item.title;
  status.textContent=item.active?'已应用':item.days>=3?'待确认':'观察中 · '+item.days+' / 3 天';
  const evidence=document.createElement('details'),summary=document.createElement('summary');
  summary.textContent='查看原话与日期';evidence.append(summary);
  for(const source of item.evidence){
   const p=document.createElement('p');p.textContent=source.day+' · '+source.quote;evidence.append(p);
  }
  row.append(title,status,evidence);
  if(item.active||item.days>=3)memoryButton(row,item.active?'停止应用':'确认这条习惯',async()=>{
   paintLearning(await call('learning-review',{key:item.key,enabled:!item.active}));
   toast(item.active?'已停用该习惯':'后续对话会采用这个习惯');
  });
  list.append(row);
 }
}
$('memory-profile-refresh').onclick=()=>loadMemoryProfiles().catch(()=>{});
async function focusMemoryEntry(id){
 const serial=memoryViewSerial;
 const result=await call('memory-detail',{id});
 if(serial!==memoryViewSerial)return;
 const box=$('memory-graph-detail');
 box.replaceChildren();
 box.hidden=false;
 const item=result.items[0];
 if(!item){box.textContent='这项记忆已更新或移除，请刷新。';return;}
 const head=document.createElement('div');head.className='lm-peek-head';
 const badge=document.createElement('span');badge.className='lm-node-badge lm-badge-fact';badge.textContent='记忆原文 · '+item.memory_id;
 const closeBtn=document.createElement('button');closeBtn.type='button';closeBtn.className='lm-peek-close';closeBtn.textContent='×';closeBtn.onclick=()=>{box.hidden=true;};
 head.append(badge,closeBtn);
 const p=document.createElement('p');p.className='lm-peek-text';p.textContent=item.text;
 const evidence=document.createElement('p');evidence.className='note';evidence.textContent='来源依据：'+item.evidence.map(e=>e.quote).join('；');
 const actions=document.createElement('div');actions.className='memory-tools';
 memoryButton(actions,'在记忆列表更正',async()=>{$('memory-search').value=item.text.slice(0,60);document.querySelector('[data-memory-tab=library]').click();await loadMemories(true);});
 memoryButton(actions,'定位该记忆子图',()=>{if($('memory-graph-focus-id'))$('memory-graph-focus-id').value=item.memory_id;loadMemoryGraph(true,{id:item.memory_id}).catch(()=>{});});
 box.append(head,p,evidence,actions);
 document.querySelector('[data-memory-tab=network]').click();
}
let graphLoadSerial=0,graphRefreshTimer,graph2dReady=false;
function ensureGraph2D(){
 if(graph2dReady||!window.Graph2D||!$('graph-canvas-container'))return;
 window.Graph2D.init($('graph-canvas-container'),{
  onNodeClick:nodeId=>showGraphNodeDetail(nodeId),
  onNodeDblClick:nodeId=>{
   const nd=(graphPayload?.snapshot?.nodes||[]).find(n=>Number(n.id)===Number(nodeId));
   if(nd?.label){$('memory-graph-query').value=nd.label;loadMemoryGraph(true).catch(()=>{});}
  },
  onBackgroundClick:()=>{if($('memory-graph-detail'))$('memory-graph-detail').hidden=true;},
 });
 graph2dReady=true;
}
function renderGraphLegend(summary){
 const el=$('graph-legend');if(!el)return;
 el.replaceChildren();
 const colors=window.GraphShared?.TYPE_COLORS||{person:'#2a9e96',topic:'#78a94b',fact:'#c58c2a',summary:'#df6d62'};
 const labels={fact:'事实',topic:'主题',person:'人物',summary:'摘要'};
 const relLabels={describes:'Describes',mentioned_in:'Mentioned In',co_occurs_with:'Co Occurs With'};
 const nBreakdown=summary?.node_type_breakdown||{};
 const rBreakdown=summary?.relation_breakdown||{};
 for(const [type,count] of Object.entries(nBreakdown)){
  if(!count)continue;
  const chip=document.createElement('span');chip.className='lm-legend-chip';
  const dot=document.createElement('span');dot.className='dot';dot.style.background=colors[type]||'#74868a';
  const txt=document.createElement('span');txt.textContent=`${labels[type]||type} · ${count}`;
  chip.append(dot,txt);el.append(chip);
 }
 for(const [rel,count] of Object.entries(rBreakdown)){
  if(!count)continue;
  const chip=document.createElement('span');chip.className='lm-legend-chip';
  chip.textContent=`${relLabels[rel]||rel} · ${count}`;
  el.append(chip);
 }
}
function showGraphNodeDetail(nodeId){
 const box=$('memory-graph-detail');if(!box||!graphPayload?.snapshot)return;
 const nodes=graphPayload.snapshot.nodes||[];
 const edges=graphPayload.snapshot.edges||[];
 const memories=graphPayload.snapshot.memories||[];
 const nd=nodes.find(n=>Number(n.id)===Number(nodeId));
 if(!nd)return;
 box.replaceChildren();
 box.hidden=false;
 const typeLabels={person:'人物节点',topic:'主题节点',fact:'事实节点',summary:'深层札记'};
 const head=document.createElement('div');head.className='lm-peek-head';
 const badge=document.createElement('span');badge.className=`lm-node-badge lm-badge-${nd.type||'topic'}`;
 badge.textContent=`${typeLabels[nd.type]||'图谱节点'} · 度 ${nd.degree||0} · 关联记忆 ${nd.memory_count||1}`;
 const closeBtn=document.createElement('button');closeBtn.type='button';closeBtn.className='lm-peek-close';closeBtn.textContent='×';closeBtn.onclick=()=>{box.hidden=true;window.Graph2D?.clearSelection?.();};
 head.append(badge,closeBtn);
 const title=document.createElement('h4');title.className='lm-peek-title';title.textContent=nd.label||nd.canonical_value||'节点';
 box.append(head,title);
 const connectedEdges=edges.filter(e=>Number(e.source)===Number(nodeId)||Number(e.target)===Number(nodeId));
 const memIds=new Set(connectedEdges.map(e=>e.raw_memory_id||e.memory_id).filter(Boolean));
 const relList=document.createElement('div');relList.className='lm-peek-relations';
 const nodeMap=new Map(nodes.map(n=>[Number(n.id),n]));
 for(const e of connectedEdges.slice(0,10)){
  const otherId=Number(e.source)===Number(nodeId)?Number(e.target):Number(e.source);
  const other=nodeMap.get(otherId);
  if(!other)continue;
  const chip=document.createElement('button');chip.type='button';chip.className='lm-rel-chip';
  chip.textContent=`${e.relation_type} → ${other.label.slice(0,26)}`;
  chip.onclick=()=>{window.Graph2D?.selectNode?.(other.id);showGraphNodeDetail(other.id);};
  relList.append(chip);
 }
 if(relList.childElementCount)box.append(relList);
 const matchedMemories=memories.filter(m=>memIds.has(m.memory_id)||memIds.has(m.id));
 if(matchedMemories.length){
  const memWrap=document.createElement('div');memWrap.className='lm-peek-memories';
  for(const m of matchedMemories.slice(0,4)){
   const p=document.createElement('p');p.className='lm-peek-mem-item';p.textContent=m.text;
   memoryButton(p,'查看来源与更正',()=>focusMemoryEntry(m.memory_id));
   memWrap.append(p);
  }
  box.append(memWrap);
 }
}
async function loadMemoryGraph(reset=true,extra={}){
 const serial=++graphLoadSerial,view=memoryViewSerial;
 const query=$('memory-graph-query')?.value.trim()||'';
 const focusVal=$('memory-graph-focus-id')?.value.trim()||'';
 ensureGraph2D();
 const params={query,full_graph:graphFullScope,...extra};
 if(focusVal&&!params.id)params.id=focusVal;
 const r=await call('memory-graph',params);
 if(serial!==graphLoadSerial||view!==memoryViewSerial)return;
 graphPayload=r;
 const sum=r.summary||{};
 if($('gs-total'))$('gs-total').textContent=String(sum.total_memories??r.total_memories??0);
 if($('gs-nodes'))$('gs-nodes').textContent=String(sum.nodes??r.nodes?.length??0);
 if($('gs-edges'))$('gs-edges').textContent=String(sum.edges??r.edges?.length??0);
 if($('gs-sessions'))$('gs-sessions').textContent=String(sum.sessions??1);
 renderGraphLegend(sum);
 const info=$('memory-graph-info');
 const hasGraphNodes=Boolean(r.shown_memories||(r.snapshot?.nodes?.length&&r.total_memories));
 info.replaceChildren();
 if(hasGraphNodes){
  info.textContent=`显示 ${r.shown_memories} 条有来源的记忆、${r.edges?.length||0} 条提及关联 · ${r.snapshot?.nodes?.length||r.nodes?.length||0} 个图谱节点`;
  info.classList.add('is-badge');
 }else{
  info.classList.remove('is-badge');
  info.textContent=query?'没有匹配的记忆。点击「概览」查看全部。':'有一条已保存的记忆就会出现节点。可以记下一件事、导入资料，或在聊天中明确说「请记住……」。';
  if(!query&&!r.shown_memories)memoryButton(info,'记下一件事',()=>{
   document.querySelector('[data-memory-tab=library]').click();
   $('memory-text').focus();
  });
 }
 const canvas=$('memory-graph-canvas');
 if(canvas)canvas.hidden=!hasGraphNodes;
 const box=$('memory-graph-list');box.replaceChildren();
 for(const n of r.nodes.filter(n=>n.kind==='memory'))memoryButton(box,n.label,()=>focusMemoryEntry(n.memory_id));
 if(window.Graph2D&&$('graph-canvas-container')){
  window.Graph2D.setActive(true);
  window.Graph2D.loadData(r,{
   onLayoutDone:()=>{if(canvas)canvas.hidden=!hasGraphNodes;},
  });
  if(canvas)canvas.hidden=!hasGraphNodes;
  setTimeout(()=>{if(window.Graph2D)window.Graph2D.resize();},30);
 }
}
function refreshOpenGraph(){
 clearTimeout(graphRefreshTimer);
 graphRefreshTimer=setTimeout(()=>{
  if(document.querySelector('#memory.active #memory-pane-network.active')&&!document.hidden)loadMemoryGraph(false).catch(()=>{});
 },80);
}
function drawMemoryGraph(){
 if(window.Graph2D&&graphPayload)window.Graph2D.resize();
}
$('memory-graph-form').onsubmit=e=>{e.preventDefault();loadMemoryGraph(true).catch(()=>{});};
$('memory-graph-reset').onclick=()=>{if($('memory-graph-query'))$('memory-graph-query').value='';if($('memory-graph-focus-id'))$('memory-graph-focus-id').value='';if($('memory-graph-detail'))$('memory-graph-detail').hidden=true;window.Graph2D?.clearSelection?.();loadMemoryGraph(true).catch(()=>{});};
if($('memory-graph-focus-btn'))$('memory-graph-focus-btn').onclick=()=>{const fid=$('memory-graph-focus-id')?.value.trim();loadMemoryGraph(true,{id:fid||undefined}).catch(()=>{});};
if($('memory-graph-scope-btn'))$('memory-graph-scope-btn').onclick=()=>{
 graphFullScope=!graphFullScope;
 $('memory-graph-scope-btn').textContent=graphFullScope?'⊞ 全量图谱':'⊞ 受限概览';
 $('memory-graph-scope-btn').classList.toggle('is-active',graphFullScope);
 loadMemoryGraph(true).catch(()=>{});
};

async function loadMemoryBackups(){const serial=memoryViewSerial,r=await call('memory-backups');if(serial!==memoryViewSerial)return;const box=$('memory-backup-list');box.replaceChildren();for(const item of r.items){const a=document.createElement('article'),p=document.createElement('p');p.textContent=new Date(item.modified*1000).toLocaleString('zh-CN')+' · '+Math.ceil(item.size/1024)+' KB';a.append(p);memoryButton(a,'恢复这份备份',async()=>{if(confirm('用这份备份恢复记忆？当前对话会中断，后来明确删除的内容仍保持删除。')){await call('memory-restore',{name:item.name});await loadMemories(true);toast('备份已恢复，删除记录已重新核对');}});box.append(a);}if(!r.items.length)box.textContent='还没有本机备份。';}
$('memory-backup-create').onclick=async()=>{try{await call('memory-backup');await loadMemoryBackups();toast('本机备份已创建');}catch{}};
$('memory-maintain').onclick=async()=>{try{const r=await call('memory-maintain');$('memory-maintain-result').textContent='已检查 '+r.checked+' 条当前记忆，'+r.protected+' 条固定保护；没有自动删除稳定事实。';}catch{}};
$('memory-export').onclick=async()=>{try{const data=await call('memory-export'),url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='诗音记忆-'+new Date().toISOString().slice(0,10)+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch{}};
let memoryImportData=null;$('memory-import-file').onchange=()=>{memoryImportData=null;$('memory-import-run').hidden=true;};
$('memory-import-preview').onclick=async()=>{try{const file=$('memory-import-file').files[0];if(!file)return;if(file.size>16*1024*1024)throw Error('导入文件请控制在16MB以内');memoryImportData=JSON.parse(await file.text());const r=await call('memory-import',{data:memoryImportData,dry_run:true});$('memory-import-result').textContent='可导入 '+r.count+' 条当前有效记忆，'+r.blocked+' 条因曾删除而继续拦截。已有记录和原始对话不会覆盖。';$('memory-import-run').hidden=false;}catch(e){toast(e.message);}};
$('memory-import-run').onclick=async()=>{try{if(!memoryImportData)return;const r=await call('memory-import',{data:memoryImportData,dry_run:false});$('memory-import-result').textContent='已导入 '+r.count+' 条记忆；'+r.blocked+' 条继续保持删除。';$('memory-import-run').hidden=true;memoryImportData=null;await loadMemories(true);}catch{}};
let noteReader=null,noteReadState=null;
window.readMemoryNote=async function(m,offset=0){
 const serial=memoryViewSerial,r=await call('notes-read',{id:m.memory_id,offset});
 if(serial!==memoryViewSerial)return;
 if(!noteReader){
  noteReader=document.createElement('dialog');noteReader.className='memory-note-dialog';
  noteReader.innerHTML='<h3></h3><p class="note"></p><pre></pre><details class="reading-notes"><summary></summary><div data-reading-notes></div></details><div class="memory-tools"><button data-note-prev>上一段</button><button data-note-next>下一段</button><button data-note-close>关闭</button></div>';
  document.body.append(noteReader);
  noteReader.querySelector('[data-note-close]').onclick=()=>noteReader.close();
 }
 noteReadState={m,r};
 noteReader.querySelector('h3').textContent=r.title;
 noteReader.querySelector('p').textContent='从第 '+r.line_start+' 行开始 · 共 '+r.total_lines+' 行 · 原文分段阅读';
 noteReader.querySelector('pre').textContent=r.text;
 const details=noteReader.querySelector('.reading-notes'),list=details.querySelector('[data-reading-notes]');
 const notes=r.reading_notes||[];
 details.hidden=!notes.length;
 details.querySelector('summary').textContent='读后笔记（'+notes.length+'）';
 list.replaceChildren();
 for(const item of notes){
  const card=document.createElement('article'),heading=document.createElement('strong');
  heading.textContent=item.kind==='interpretation'?'诗音的解读':'原文摘记';
  card.append(heading);
  if(item.kind==='interpretation'){
   const body=document.createElement('p');body.textContent=item.text;card.append(body);
  }
  for(const anchor of item.source.anchors){
   const location=document.createElement('small'),quote=document.createElement('blockquote');
   const lines=anchor.line_start===anchor.line_end?anchor.line_start:anchor.line_start+'–'+anchor.line_end;
   location.textContent='《'+item.source.title+'》第 '+lines+' 行'+(anchor.column_start?' · 从第 '+(anchor.column_start+1)+' 字起':'');
   quote.textContent=anchor.text;
   card.append(location,quote);
  }
  list.append(card);
 }
 const previous=noteReader.querySelector('[data-note-prev]'),next=noteReader.querySelector('[data-note-next]');
 previous.disabled=r.offset===0;next.disabled=!r.has_more;
 previous.onclick=()=>readMemoryNote(m,Math.max(0,r.offset-6000));next.onclick=()=>readMemoryNote(m,r.next_offset);
 if(!noteReader.open){details.open=false;noteReader.showModal();}
};
window.sion.subscribe(e=>{
 if(e.type==='memory-changed'){
  memoryViewSerial++;graphPayload=null;drawMemoryGraph();$('memory-graph-detail').replaceChildren();$('memory-graph-detail').hidden=true;$('memory-profile-list').replaceChildren();if(noteReader?.open)noteReader.close();noteReadState=null;
 }
 if(e.type==='memory-changed'||e.type==='memory-graph-changed')refreshOpenGraph();
});
window.memoryNotesEdit=null;
window.editMemoryNote=async function(m){const serial=memoryViewSerial;let text='',offset=0,title='';do{const r=await call('notes-read',{id:m.memory_id,offset});if(serial!==memoryViewSerial)return;text+=r.text;title=r.title;offset=r.next_offset;if(!r.has_more)break;}while(text.length<=32000);$('notes-title').value=title;$('notes-text').value=text;$('notes-layer').value=m.knowledge_layer;window.memoryNotesEdit={replace_id:m.memory_id,revision:m.revision};$('notes-form').querySelector('button[type=submit]').textContent='保存资料新版';$('notes-notice').textContent='正在编辑原文。保存后旧版归档，新版供后续回忆使用。';$('notes-text').focus();};
const cancelNoteEdit=document.createElement('button');cancelNoteEdit.type='button';cancelNoteEdit.textContent='另建一份资料';cancelNoteEdit.onclick=()=>{window.memoryNotesEdit=null;$('notes-form').querySelector('button[type=submit]').textContent='导入这份资料';$('notes-notice').textContent='将作为新资料导入。';};$('notes-form').append(cancelNoteEdit);
window.loadMemoryBackups=loadMemoryBackups;
async function loadDeepMemoryPane(){
 try{
  const r=await call('companion-status');
  const profs=r.user_profile||[],eps=r.dialogue_episodes||[],diaries=r.diaries||[],loops=r.open_loops||[],states=r.state_continuity||[];
  if($('mem-side-deep-summary'))$('mem-side-deep-summary').textContent=`已沉淀 ${profs.length} 项专属画像 · ${eps.length} 段相处情景 · ${diaries.length} 篇私密日记/梦境 · ${loops.length} 项未完挂念。`;
  if($('mem-deep-soul-text')&&r.soul_state){
   const s=r.soul_state,pct=v=>Math.round((v??0.5)*100)+'%';
   $('mem-deep-soul-text').textContent=`四维灵魂共鸣：回忆深度 ${pct(s.recall_depth)} · 印象深度 ${pct(s.impression_depth)} · 表达欲望 ${pct(s.expression_desire)} · 思维发散 ${pct(s.creativity)}`;
  }
  const empty=(box,txt)=>{const p=document.createElement('p');p.className='empty-state';p.textContent=txt;box.append(p);};
  if($('mem-deep-profile-list')){
   $('mem-deep-profile-count').textContent=(profs.length+eps.length)+' 项';
   const box=$('mem-deep-profile-list');box.replaceChildren();
   if(!profs.length&&!eps.length)empty(box,'暂无专属画像或情景片段。多聊几句或点击右上角「立即睡眠巩固」即可自动提炼。');
   for(const p of profs){const row=document.createElement('div');row.className='capability-line';const k=document.createElement('span'),v=document.createElement('b');k.textContent=p.attr_label;v.textContent=p.attr_value;row.append(k,v);box.append(row);}
   for(const ep of eps){const row=document.createElement('article');row.className='reminder-row';const p=document.createElement('p');p.textContent='【情景记忆】'+ep.summary;row.append(p);box.append(row);}
  }
  if($('mem-deep-diaries-list')){
   $('mem-deep-diaries-count').textContent=diaries.length+' 篇';
   const box=$('mem-deep-diaries-list');box.replaceChildren();
   if(!diaries.length)empty(box,'还没有写下私密日记或梦境碎片。');
   for(const d of diaries){const row=document.createElement('article');row.className='reminder-row';const p=document.createElement('p'),sm=document.createElement('small');p.textContent=(d.kind==='dream'?'【梦境碎片】':'【私密日记】')+d.content;sm.textContent=[d.emotion,d.created_at?new Date(d.created_at).toLocaleString('zh-CN'):''].filter(Boolean).join(' · ');row.append(p,sm);box.append(row);}
  }
  if($('mem-deep-loops-list')){
   $('mem-deep-loops-count').textContent=loops.length+' 项';
   const box=$('mem-deep-loops-list');box.replaceChildren();
   if(!loops.length)empty(box,'暂无未完挂念的话题。');
   for(const item of loops){const row=document.createElement('div');row.className='capability-line';const span=document.createElement('span');span.textContent=item.topic;const btn=document.createElement('button');btn.type='button';btn.textContent='已完结';btn.onclick=()=>call('companion-open-loop',{action:'resolve',id:item.id}).then(loadDeepMemoryPane);row.append(span,btn);box.append(row);}
  }
  if($('mem-deep-states-list')){
   $('mem-deep-states-count').textContent=states.length+' 项';
   const box=$('mem-deep-states-list');box.replaceChildren();
   if(!states.length)empty(box,'暂无跨天连续状态（如熬夜、感冒、赶项目）。');
   for(const st of states){const row=document.createElement('div');row.className='capability-line';const span=document.createElement('span');span.textContent=st.state_text;const btn=document.createElement('button');btn.type='button';btn.textContent='已恢复';btn.onclick=()=>call('companion-open-loop',{action:'resolve_state',id:st.id}).then(loadDeepMemoryPane);row.append(span,btn);box.append(row);}
  }
 }catch{}
}
window.loadDeepMemoryPane=loadDeepMemoryPane;
if($('mem-open-deep-tab'))$('mem-open-deep-tab').onclick=()=>document.querySelector('[data-memory-tab=deep]')?.click();
for(const id of ['mem-deep-sleep-btn','mem-side-sleep-btn']){
 if($(id))$(id).onclick=()=>call('companion-open-loop',{action:'sleep_consolidate'}).then(()=>{loadDeepMemoryPane();toast('已完成睡眠巩固：整理了画像、情景与今日札记');}).catch(()=>{});
}
