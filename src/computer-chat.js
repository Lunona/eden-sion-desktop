(() => {
  const form=document.getElementById('chat-form');
  const card=document.createElement('section');
  card.className='desktop-request';
  card.hidden=true;
  card.setAttribute('aria-label','电脑操作');
  card.innerHTML='<div class="desktop-request-head"><strong></strong><button type="button" data-settings>电脑权限</button></div><div class="desktop-request-copy" role="status"><p data-prompt></p><ol hidden></ol><p data-result hidden></p></div><div class="desktop-request-actions" hidden><button type="button" data-confirm>确认执行</button><button type="button" data-cancel>取消</button></div>';
  const heart=document.createElement('p');
  heart.className='inner-thought-chip task-heart-voice';
  heart.hidden=true;
  form.before(card,heart);
  const node=selector=>card.querySelector(selector);
  const confirm=node('[data-confirm]'),cancel=node('[data-cancel]');
  let request=null,signature='',pendingClick=false;
  function render(state){
    const line=state.settings.showHeartVoice?state.computer?.taskHeartVoice:'';
    heart.hidden=!line;
    heart.textContent=line?'💭 心声：'+line:'';
    const incoming=state.computer?.chatRequest;
    const next=incoming?.phase==='done'?null:incoming;
    const key=JSON.stringify(next);
    if(key===signature)return;
    signature=key;
    request=next;
    card.hidden=!request;
    if(!request)return;
    const title={planning:'诗音 · 我先看一下',ready:'诗音 · 等你确认',running:'诗音 · 我在处理'};
    node('strong').textContent=title[request.phase];
    node('[data-prompt]').textContent=request.prompt.length>100?request.prompt.slice(0,100)+'…':request.prompt;
    const steps=request.steps||[];
    const list=node('ol');
    list.hidden=!request.step&&!steps.length;
    list.replaceChildren();
    for(const [index,step] of [...steps,...(request.step?[request.step]:[])].entries()){
      const item=document.createElement('li');
      item.textContent=index<steps.length?'已执行 · '+step:step;
      list.append(item);
    }
    const status=request.message||request.description;
    node('[data-result]').hidden=!status;
    node('[data-result]').textContent=status||'';
    node('.desktop-request-actions').hidden=request.phase!=='ready';
    const copy=node('.desktop-request-copy');
    copy.scrollTop=copy.scrollHeight;
  }
  async function act(approved){
    if(request?.phase!=='ready'||pendingClick)return;
    pendingClick=true;
    confirm.disabled=cancel.disabled=true;
    const {id}=request;
    try{
      await window.sion.invoke(approved?'computer-execute':'computer-discard',{id,confirmed:approved});
    }catch(e){
      if(request?.id===id){
        node('[data-result]').hidden=false;
        node('[data-result]').textContent=e.message.replace(/^Error invoking remote method '[^']+': Error: /,'');
      }
    }finally{
      pendingClick=false;
      confirm.disabled=cancel.disabled=false;
    }
  }
  confirm.onclick=()=>act(true);
  cancel.onclick=()=>act(false);
  node('[data-settings]').onclick=()=>window.sion.invoke('panel',{page:'computer'}).catch(()=>{});
  window.sion.subscribe(e=>{if(e.type==='state')render(e.state);});
  window.sion.invoke('state').then(render).catch(()=>{});
})();
