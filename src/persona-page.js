(()=>{
 const el=id=>document.getElementById(id),invoke=(a,p)=>window.sion.invoke(a,p);
 const main=document.querySelector('main');
 let current,loading=false,savedScroll=0,editVersion=0;
 const page=document.createElement('section');page.id='persona';page.className='page';page.innerHTML=`<div class="admin-section-title"><h2>人格设定</h2><p>同一位诗音，按你的习惯调整说话与相处方式。</p></div><div class="persona-workspace"><aside class="persona-directory"><h3>角色档案 <span>01</span></h3><article class="persona-selected"><img src="sion-portrait.png" alt="诗音"><div><strong>诗音</strong><p>《eden*》 · 当前角色</p><span id="persona-revision" class="soft-tag">正在读取</span></div></article><p>情绪改变表现，不切换角色身份。原作资料、现实与共同经历继续分别保留来源。</p><label class="toggle"><input id="persona-heart-voice" type="checkbox" disabled>显示心声</label><p class="note">聊天和电脑任务共用此开关。默认关闭，朗读只读正文。</p><button type="button" id="persona-export">导出当前设定</button><label class="persona-import">导入设定文件<input id="persona-file" type="file" accept=".json,application/json"></label></aside><article class="workspace-card persona-editor"><div class="card-head"><div><h3>设定内容</h3><p class="subtle">保存后从下一条对话生效；不会清空已有记忆。</p></div><button type="button" id="persona-save" class="primary">保存并生效</button></div><div class="profile-fields"><label>原作角色卡<textarea id="persona-canon" rows="10" maxlength="4000" required></textarea></label><label>现实认知<textarea id="persona-description" rows="10" maxlength="1500" required></textarea></label></div><div class="profile-fields"><label>说话风格 · 每行一条<textarea id="persona-style" rows="5"></textarea></label><label>性格特点 · 每行一条<textarea id="persona-traits" rows="5"></textarea></label></div><div class="persona-badges"><span>知道自己的作品来源</span><span>理解现实生活</span><span>同一个连续身份</span></div><div class="profile-actions"><button type="button" id="persona-default">填回默认设定</button><span id="persona-result" role="status"></span></div><details><summary>查看实际生效的设定</summary><pre id="persona-preview"></pre></details></article></div>`;document.querySelector('main').append(page);
 const nav=document.createElement('button');nav.className='nav';nav.dataset.page='persona';nav.innerHTML='人格设定<span>07</span>';document.querySelector('nav').append(nav);
 document.addEventListener('click',event=>{
   const target=event.target.closest('[data-page],[data-console-page]');
   const destination=target?.dataset.page||target?.dataset.consolePage;
   if(destination&&destination!=='persona'&&page.classList.contains('active'))savedScroll=main.scrollTop;
 },true);
 function show(){
   if(!page.classList.contains('active')){
     document.querySelectorAll('.page,.nav').forEach(x=>x.classList.remove('active'));
     page.classList.add('active');nav.classList.add('active');
     el('page-title').textContent='人格设定';
     main.scrollTop=savedScroll;
   }
   if(!current&&!loading)void load();
 }
 nav.onclick=show;
 const heartVoice=el('persona-heart-voice');
 function paintHeartVoice(settings){
   heartVoice.checked=settings.showHeartVoice===true;
   heartVoice.disabled=false;
 }
 invoke('state').then(s=>paintHeartVoice(s.settings)).catch(()=>{});
 window.sion.subscribe(e=>{if(e.type==='state')paintHeartVoice(e.state.settings);});
 heartVoice.onchange=async()=>{
   const enabled=heartVoice.checked;
   heartVoice.disabled=true;
   try{heartVoice.checked=await invoke('show-heart-voice',{enabled});}
   catch(e){heartVoice.checked=!enabled;toast(e.message);}
   finally{heartVoice.disabled=false;}
 };
 function draft(){return {...current.profile,canon_profile:el('persona-canon').value.trim(),self_description:el('persona-description').value.trim(),speaking_style:el('persona-style').value.split('\n').map(s=>s.trim()).filter(Boolean),traits:el('persona-traits').value.split('\n').map(s=>s.trim()).filter(Boolean)};}
 function fill(p){el('persona-canon').value=p.canon_profile||current?.profile?.canon_profile||'';el('persona-description').value=p.self_description;el('persona-style').value=p.speaking_style.join('\n');el('persona-traits').value=p.traits.join('\n');preview();}
 function preview(){if(!current)return;const p=draft();el('persona-preview').textContent=p.name+' · '+p.origin+'\n\n原作角色卡\n'+p.canon_profile+'\n\n现实认知\n'+p.self_description+'\n\n说话风格\n'+p.speaking_style.map(s=>'• '+s).join('\n')+'\n\n性格\n'+p.traits.join('、');}
 function paintRevision(){el('persona-revision').textContent='已生效 · 第 '+current.revision+' 版';}
 async function load(){
   loading=true;
   try{current=await invoke('persona');fill(current.profile);paintRevision();}
   catch(e){toast(e.message);}
   finally{loading=false;}
 }
 ['persona-canon','persona-description','persona-style','persona-traits'].forEach(id=>el(id).oninput=()=>{editVersion++;preview();});
 el('persona-save').onclick=async()=>{
   const button=el('persona-save');
   if(!current||button.disabled)return;
   const version=editVersion,profile=draft();
   button.disabled=true;
   try{
     const result=await invoke('persona-save',{profile,revision:current.revision});
     current={...current,profile,revision:result.revision};
     current=await invoke('persona').catch(()=>current);
     if(editVersion===version)fill(current.profile);
     paintRevision();
     el('persona-result').textContent='已保存 · 第 '+result.revision+' 版'+(editVersion===version?'':' · 还有未保存修改');
     toast('人格设定已生效');
   }catch(e){toast(e.message);}
   finally{button.disabled=false;}
 };
 el('persona-default').onclick=()=>{if(!current)return;editVersion++;fill(current.default);el('persona-result').textContent='已填回默认内容，保存后生效。';};
 el('persona-export').onclick=()=>{if(!current)return;const data=JSON.stringify({format:'sion-persona.v1',profile:current.profile},null,2),url=URL.createObjectURL(new Blob([data],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='诗音人格设定.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
 el('persona-file').onchange=async()=>{const input=el('persona-file');try{const file=input.files[0];if(!current||!file)return;if(file.size>32000)throw Error('设定文件请控制在32KB以内');const data=JSON.parse(await file.text());if(data.format!=='sion-persona.v1'||data.profile?.canon_entity_id!==current.profile.canon_entity_id||typeof data.profile?.self_description!=='string'||!Array.isArray(data.profile.speaking_style)||!Array.isArray(data.profile.traits))throw Error('设定文件格式无效');editVersion++;fill(data.profile);el('persona-result').textContent='已导入到编辑区，保存后生效。';}catch(e){toast(e.message);}finally{input.value='';}};
})();
