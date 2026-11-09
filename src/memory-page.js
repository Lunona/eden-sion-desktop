/* Independent memory management page; all mutations pass through CompanionRuntime. */
let memoryOffset=0,memoryBusy=false,memoryQuerySerial=0;
const layerNames={canon:'原作资料',realworld:'现实资料',shared_experience:'共同经历',story_branch:'补充故事'};
const statusNames={active:'当前有效',candidate:'待确认',superseded:'已更新的旧版本',retracted:'已撤回',archived:'已归档',expired:'已失效'};
const categoryNames={canon:'原作设定',fact_preference:'事实与偏好',shared_episode:'共同经历',pending_task:'未完成事项',virtual_life:'角色虚拟生活',temporary:'临时状态',reading_excerpt:'原文摘记',reading_interpretation:'读后解读'};
function memoryDate(s){if(!s)return '';const d=new Date(s);return Number.isNaN(d.valueOf())?'':d.toLocaleString('zh-CN');}
function memoryButton(parent,label,fn){const b=document.createElement('button');b.type='button';b.textContent=label;b.onclick=async()=>{b.disabled=true;try{await fn();}catch{}finally{b.disabled=false;}};parent.append(b);return b;}
async function memorySummary(){
 const s=await call('memory-status'),m=s.memory,e=s.enhancement||{},counts=e.memory_counts||{},embedding=e.embedding||{};
 $('mem-count').textContent=counts.active||0;$('semantic-state').textContent=embedding.remote?'API 向量':embedding.ready?'本地语义':'未就绪';$('organize-state').textContent=(m.jobs.pending||0)+(m.jobs.running||0)?'整理中':'空闲';
 $('memory-summary').textContent='已保存在本机 · '+(embedding.ready?'关键词与语义联合回忆':'当前使用关键词回忆')+' · '+(e.api_enabled&&e.config?.automatic?'交流后自动整理':'当前使用本地保守整理');
 window.fillMemoryExtras?.(e);window.loadDeepMemoryPane?.();$('mem-auto').checked=e.config?.automatic!==false;$('mem-rerank').checked=e.config?.rerank!==false;
 $('memory-engine-info').textContent=embedding.remote
   ?embedding.model+(embedding.dimensions?' · '+embedding.dimensions+' 维':' · 等待首次调用')+'。接口暂不可用时继续使用关键词与图谱。'
   :embedding.ready?'语义模型在 CPU 上运行，使用 2 个线程，不占用语音与 Live2D 的显存。':'语义模型未就绪：'+(embedding.error||'请重启后检查');
 $('memory-jobs').textContent='待处理 '+(m.jobs.pending||0)+' · 正在整理 '+(m.jobs.running||0)+' · 已完成 '+(m.jobs.completed||0)+' · 未完成 '+(m.jobs.failed||0);
 const notes=await call('notes');$('note-count').textContent=notes.items.length;return notes;
}
async function loadMemories(reset=false){
 if(memoryBusy)return;if(reset)memoryOffset=0;const serial=++memoryQuerySerial;memoryBusy=true;$('memory-refresh').disabled=true;$('memory-status').textContent='正在读取…';
 try{
  const r=await call('memories',{offset:memoryOffset,query:$('memory-search').value.trim(),layer:$('memory-layer').value,status:$('memory-scope').value});if(serial!==memoryQuerySerial)return;
  $('memory-list').replaceChildren();$('memory-status').textContent=r.total?'找到 '+r.total+' 条记录':'没有符合条件的记忆。';
  for(const m of r.items){
   const row=document.createElement('article'),head=document.createElement('div'),text=document.createElement('textarea');head.className='memory-item-head';head.textContent=(categoryNames[m.category]||layerNames[m.knowledge_layer]||m.knowledge_layer)+' · '+(statusNames[m.status]||m.status)+' · 版本 '+m.revision+' · '+memoryDate(m.created_at);text.value=m.text;text.readOnly=m.status!=='active';text.setAttribute('aria-label','记忆内容');row.append(head,text);
   const readingNote=Boolean(m.qualifiers?.reading_note);
   if(readingNote)text.readOnly=true;
   if(m.status==='active'){
    if(!readingNote)memoryButton(row,'保存更正',async()=>{if(!text.value.trim())return;await call('correct',{id:m.memory_id,text:text.value.trim(),revision:m.revision});await loadMemories();});
    memoryButton(row,'删除这项',async()=>{if(confirm('删除这项记忆及其相关来源内容？后续对话将不再使用它。')){await call('forget',{id:m.memory_id,revision:m.revision});await loadMemories();}});
   }
   const detail=document.createElement('details'),summary=document.createElement('summary'),source=document.createElement('div');summary.textContent='查看来源依据';source.className='memory-evidence';source.textContent=readingNote?(m.qualifiers.anchors||[]).map(a=>'第 '+a.line_start+'–'+a.line_end+' 行\n'+a.text).join('\n\n'):m.evidence?.length?m.evidence.map(e=>e.quote).join('\n\n'):'没有可显示的来源原文。';detail.append(summary,source);row.append(detail);window.memoryPolicyControls?.(row,m);$('memory-list').append(row);
  }
  $('memory-prev').disabled=memoryOffset===0;$('memory-next').disabled=memoryOffset+r.limit>=r.total;$('memory-page-label').textContent='第 '+(Math.floor(memoryOffset/30)+1)+' 页';await memorySummary();
 }catch(e){$('memory-status').textContent='读取未完成，请重试。';}
 finally{memoryBusy=false;$('memory-refresh').disabled=false;}
}
$('memory-refresh').onclick=()=>loadMemories(true);
$('memory-prev').onclick=()=>{memoryOffset=Math.max(0,memoryOffset-30);loadMemories();};$('memory-next').onclick=()=>{memoryOffset+=30;loadMemories();};
for(const id of ['memory-layer','memory-scope'])$(id).onchange=()=>loadMemories(true);
$('memory-search').onkeydown=e=>{if(e.key==='Enter'&&!e.isComposing){e.preventDefault();loadMemories(true);}};
$('memory-form').onsubmit=async e=>{e.preventDefault();if(memoryBusy)return;const text=$('memory-text').value.trim();if(!text)return;const b=e.currentTarget.querySelector('button[type=submit]');b.disabled=true;try{await call('remember',{text,layer:$('memory-add-layer').value,pinned:document.getElementById('memory-add-pinned')?.checked||false,importance:Number(document.getElementById('memory-add-importance')?.value||.7)});$('memory-text').value='';await loadMemories(true);}catch{}finally{b.disabled=false;}};
$('recall-form').onsubmit=async e=>{
 e.preventDefault();const query=$('recall-query').value.trim();if(!query)return;const b=e.currentTarget.querySelector('button');b.disabled=true;const box=$('recall-results');box.replaceChildren();box.textContent='正在回忆…';
 try{const r=await call('recall',{query});box.replaceChildren();const note=document.createElement('p');note.textContent=r.hits.length?'找到 '+r.hits.length+' 条相关记忆。':'当前没有找到相关记忆。';box.append(note);for(const m of r.hits){const a=document.createElement('article'),label=document.createElement('small'),p=document.createElement('p');label.textContent=(layerNames[m.knowledge_layer]||m.knowledge_layer)+' · '+(m.match_reasons||[]).map(k=>({keyword:'关键词',entity_or_exact:'名称或原文',semantic:'语义相关',time:'时间相关',graph_association:'关联回忆'}[k]||k)).join('、')+(r.reranked?' · 已核对相关性':'');p.textContent=m.text;a.append(label,p);box.append(a);}}
 catch{box.textContent='本次回忆未完成，请重试。';}finally{b.disabled=false;}
};
document.querySelector('[data-page=memory]').addEventListener('click',()=>loadMemories(true));
window.sion.subscribe(e=>{if(e.type==='navigate'&&e.page==='memory')loadMemories(true);});

async function loadNotes(){
 const r=await call('notes'),list=$('notes-list');
 list.replaceChildren();
 for(const m of r.items){
  const card=document.createElement('article');
  card.className='settings-card';
  const title=document.createElement('h3'),info=document.createElement('p'),excerpt=document.createElement('p');
  title.textContent=m.text.split('\n')[0].replace(/^资料：/,'');
  info.textContent=(layerNames[m.knowledge_layer]||m.knowledge_layer)+' · '+m.chunks+' 个资料片段';
  excerpt.textContent=m.text.split('\n').slice(1).join('\n');
  excerpt.className='note';
  card.append(title,info,excerpt);
  memoryButton(card,'阅读原文',()=>window.readMemoryNote(m));
  memoryButton(card,'请诗音读这份资料',async()=>{
   await call('companion-read',{id:m.memory_id});
   $('notes-notice').textContent='已安排阅读，可在「今日」看进度。读后笔记会出现在原文窗口。';
  });
  memoryButton(card,'编辑原文',()=>window.editMemoryNote(m));
  memoryButton(card,'删除整份资料',async()=>{
   if(confirm('删除整份资料及其所有片段？')){
    await call('forget',{id:m.memory_id,revision:m.revision});await loadNotes();await memorySummary();
   }
  });
  list.append(card);
 }
 if(!r.items.length){const p=document.createElement('p');p.className='note';p.textContent='还没有导入资料。';list.append(p);}
}
document.querySelectorAll('[data-memory-tab]').forEach(button=>button.onclick=()=>{document.querySelectorAll('[data-memory-tab]').forEach(b=>{b.classList.toggle('selected',b===button);b.setAttribute('aria-selected',String(b===button));});document.querySelectorAll('.memory-pane').forEach(p=>p.id==='memory-pane-'+button.dataset.memoryTab?p.classList.add('active'):p.classList.remove('active'));if(button.dataset.memoryTab==='notes')loadNotes().catch(()=>{});if(button.dataset.memoryTab==='settings'){memorySummary().catch(()=>{});window.loadMemoryBackups?.().catch(()=>{});}});
$('notes-file').onclick=async()=>{try{const r=await call('notes-file');if(r){$('notes-title').value=r.title;$('notes-text').value=r.text;}}catch{}};
$('notes-form').onsubmit=async e=>{e.preventDefault();const title=$('notes-title').value.trim(),text=$('notes-text').value;if(!text.trim())return;const b=e.currentTarget.querySelector('button[type=submit]');b.disabled=true;$('notes-notice').textContent='正在导入…';try{const r=await call('notes-import',{title:title||'未命名资料',text,layer:$('notes-layer').value,...(window.memoryNotesEdit||{})});$('notes-text').value='';window.memoryNotesEdit=null;b.textContent='导入这份资料';$('notes-notice').textContent='已导入 '+r.chunks+' 个资料片段，正在后台建立索引。';await loadNotes();await memorySummary();}catch{$('notes-notice').textContent='导入未完成，请重试。';}finally{b.disabled=false;}};
$('mem-save').onclick=async()=>{try{await call('memory-config',{automatic:$('mem-auto').checked,rerank:$('mem-rerank').checked});await memorySummary();toast('整理设置已保存');}catch{}};
$('mem-retry').onclick=async()=>{try{await call('memory-retry');await memorySummary();toast('已安排重试');}catch{}};
$('mem-reindex').onclick=async()=>{try{await call('memory-reindex');await memorySummary();toast('已安排在后台重建索引');}catch{}};
window.sion.subscribe(e=>{if(e.type==='memory-changed'){$('recall-results').replaceChildren();}});
