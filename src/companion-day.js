window.mountCompanionDay=function(home){
 const section=document.createElement('section');
 section.className='day-overview';
 section.setAttribute('aria-label','今日相处');
 section.innerHTML=`
  <div class="day-board">
   <article class="workspace-card day-card">
    <h3>此刻</h3>
    <div class="day-current"><span data-current-time>此刻</span><strong data-current>正在读取</strong><p data-detail></p><progress data-current-progress aria-label="当前活动进度" max="100" value="0" hidden></progress></div>
    <dl class="day-ledger">
     <div><dt>今日回复</dt><dd data-replies>0 次</dd></div>
     <div><dt>今日互动</dt><dd data-touches>0 次</dd></div>
     <div><dt>有效记忆</dt><dd id="presence-memories" data-memories>—</dd></div>
    </dl>
    <p class="day-latest" data-dialogue-results hidden></p>
    <p class="day-latest" data-reminder>今天没有待办提醒。</p>
    <button type="button" class="link-action" data-memory-link>打开记忆网络</button>
   </article>
   <article class="workspace-card day-card journal-history">
    <div class="day-card-heading"><h3>相处记录</h3><time data-day></time></div>
    <p class="day-latest" data-no-events>今天还没有互动记录。</p>
    <ol id="presence-events" class="journal-events" data-events></ol>
    <details class="journal-disclosure" data-activity-details>
     <summary>阅读与休息</summary>
     <div class="day-activities" data-activities></div>
     <p role="status" class="day-latest" data-activity-error></p>
    </details>
    <details class="journal-disclosure" data-week-details>
     <summary>近七天相处</summary>
     <ol class="journal-week" data-week></ol>
    </details>
    <details class="journal-disclosure" data-plan>
     <summary>查看原有角色日程</summary>
     <p class="day-latest">这里显示角色计划。实际完成的阅读与休息见上方记录。</p>
     <ol data-timeline class="day-timeline"></ol>
    </details>
   </article>
  </div>`;
 home.querySelector('#companion-cover').after(section);
 const find=key=>section.querySelector('[data-'+key+']');
 const set=(key,text)=>{const node=find(key);if(node.textContent!==text)node.textContent=text;};
 const hm=minutes=>String(Math.floor(minutes/60)).padStart(2,'0')+':'+String(minutes%60).padStart(2,'0');
 const dayOf=new Intl.DateTimeFormat('sv-SE').format;
 const timeOf=new Intl.DateTimeFormat('zh-CN',{hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format;
 find('memory-link').onclick=()=>{
  document.querySelector('[data-page=memory]').click();
  document.querySelector('[data-memory-tab=network]').click();
 };
 let timelineKey='',activityKey='',eventKey='',weekKey='',positioned=false,reading=false;
 const phases={idle:'待机',listening:'正在听',speaking:'检测到讲话',recognizing:'识别语音',
  thinking:'组织回复',waiting_for_provider:'等待模型',ready:'等待显示',presenting:'呈现回复',
  synthesizing:'合成语音',playing:'播放语音',tool:'使用电脑助手',paused:'已暂停'};
 const activityNames={idle:'安静待机',chat:'正在交谈',rest:'虚拟休息',read:'阅读指定资料'};
 const states={queued:'等待开始',running:'进行中',paused:'已暂停，可继续',completed:'已完成',cancelled:'已取消',
  unavailable:'原文不可用',expired:'时段结束，未完成'};
 function activityRows(activity){
  const hasReading=activity.pending.some(item=>item.kind==='read');
  if(hasReading&&!reading)find('activity-details').open=true;
  reading=hasReading;
  const items=[...activity.pending,...activity.recent];
  const key=JSON.stringify(items);
  if(activityKey===key)return;
  activityKey=key;
  const root=find('activities');
  root.replaceChildren();
  if(!items.length){
   const empty=document.createElement('p');
   empty.className='day-latest';
   empty.textContent='暂无阅读或休息记录。';
   root.append(empty);
  }
  for(const item of items){
   const row=document.createElement('div'),title=document.createElement('strong'),detail=document.createElement('small');
   title.textContent=activityNames[item.kind];
   detail.textContent=states[item.state];
   if(item.kind==='rest'){
    detail.textContent+=' · '+Math.floor(item.progress/60)+' / '+Math.round(item.total/60)+' 分钟';
   }else if(item.state==='completed'){
    detail.textContent+=' · '+item.progress+' 字 · '+item.sections+' 段';
    if(item.headings)detail.textContent+=' · '+item.headings+' 个标题';
    const notes={queued:'摘记待整理',running:'正在整理摘记',ready:'可在原文中查看读后笔记',
     unavailable:'原文已失效',failed:'摘记暂未完成'}[item.notes];
    if(notes)detail.textContent+=' · '+notes;
   }else{
    detail.textContent+=' · '+item.progress+' / '+item.total+' 字';
   }
   row.append(title,detail);
   if(item.kind==='read'&&item.interruptible){
    const cancel=document.createElement('button');
    cancel.type='button';cancel.textContent='取消阅读';
    cancel.onclick=async()=>{
     cancel.disabled=true;
     try{await window.sion.invoke('companion-read',{action:'cancel',id:item.id});set('activity-error','');}
     catch(e){set('activity-error',e.message);cancel.disabled=false;}
    };
    row.append(cancel);
   }
   root.append(row);
  }
 }
 function journalEntries(events,day){
  const items=events.filter(event=>dayOf(new Date(event.at*1000))===day).slice(0,8);
  const key=JSON.stringify(items);
  if(key===eventKey)return;
  eventKey=key;
  find('no-events').hidden=!!items.length;
  const list=find('events');
  list.replaceChildren();
  const sourceNames={dialogue:'对话',touch:'触摸',touch_feedback:'触摸回应'};
  for(const item of items){
   const row=document.createElement('li'),time=document.createElement('time'),body=document.createElement('div');
   const title=document.createElement('strong'),source=document.createElement('small');
   const date=new Date(item.at*1000);
   time.dateTime=date.toISOString();time.textContent=timeOf(date);
   title.textContent=item.label;source.textContent=sourceNames[item.source]||'互动';
   body.append(title,source);row.append(time,body);list.append(row);
  }
 }
 function journalWeek(days,day){
  const key=JSON.stringify([day,days]);
  if(key===weekKey)return;
  weekKey=key;
  const list=find('week'),counts=new Map(days.map(row=>[row.day,row]));
  list.replaceChildren();
  for(let offset=0;offset<7;offset++){
   const date=new Date(day+'T12:00:00');
   date.setDate(date.getDate()-offset);
   const id=dayOf(date),record=counts.get(id);
   const row=document.createElement('li'),time=document.createElement('time'),value=document.createElement('span');
   time.dateTime=id;
   time.textContent=offset===0?'今天':date.toLocaleDateString('zh-CN',{month:'numeric',day:'numeric',weekday:'short'});
   value.textContent=(record?.replies||0)+' 次回复 · '+(record?.touches||0)+' 次互动';
   row.append(time,value);list.append(row);
  }
 }
 function positionTimeline(list){
  if(positioned||!list.clientHeight)return;
  const current=list.querySelector('[data-status=current]');
  if(!current)return;
  const start=current.previousElementSibling||current;
  list.scrollTop+=start.getBoundingClientRect().top-list.getBoundingClientRect().top;
  positioned=true;
 }
 find('plan').addEventListener('toggle',()=>{if(find('plan').open)positionTimeline(find('timeline'));});
 return {
  paint(presence){
   const plan=presence.day_plan;
   if(!plan)return;
   set('day',plan.day);
   const focus=presence.focus;
   const activity=presence.activity;
   const current=activity?.current;
   const meter=find('current-progress');
   meter.hidden=!focus&&!current?.total;
   if(focus){
    set('current','专注陪伴 · '+focus.activity);
    set('detail',focus.quiet?'这段时间安静陪伴。到点会提醒你休息。':'到点会提醒你休息。');
    set('current-time','休息提醒 · '+timeOf(new Date(focus.ends_at*1000)));
    meter.value=100*(Date.now()/1000-focus.started_at)/(focus.ends_at-focus.started_at);
   }else if(current){
    set('current',activityNames[current.kind]);
    set('detail',current.kind==='rest'?'休息时段至 '+timeOf(new Date(current.deadline*1000))+'，交谈时会暂停。':
     current.kind==='read'?'正在处理你指定的资料原文。':'');
    set('current-time',activity.program==='idle'?'当前状态':phases[activity.program]||'当前状态');
    meter.value=current.total?100*current.progress/current.total:0;
   }else{
    set('current','安静待机');set('detail','');
    set('current-time','此刻');
    find('current-progress').value=0;
   }
   if(activity)activityRows(activity);
   set('replies',(activity?.delivered??presence.today.replies)+' 次');
   const outcomes=[activity?.interrupted&&'中断 '+activity.interrupted+' 次',activity?.failed&&'未能回复 '+activity.failed+' 次'].filter(Boolean);
   find('dialogue-results').hidden=!outcomes.length;
   set('dialogue-results',outcomes.join(' · '));
   set('touches',presence.today.touches+' 次');
   journalEntries(presence.events,plan.day);
   journalWeek(presence.days,plan.day);
   const reminder=presence.reminders.filter(item=>item.status==='pending'&&dayOf(new Date(item.at*1000))===plan.day).sort((a,b)=>a.at-b.at)[0];
   set('reminder',reminder?'下次提醒 · '+timeOf(new Date(reminder.at*1000))+' '+reminder.title:'今天没有待办提醒。');
   const key=JSON.stringify(plan);
   const list=find('timeline');
   if(timelineKey===key){positionTimeline(list);return;}
   timelineKey=key;
   positioned=false;
   list.replaceChildren();
   for(const slot of plan.slots){
    const row=document.createElement('li'),time=document.createElement('time'),body=document.createElement('div');
    const name=document.createElement('strong'),description=document.createElement('p'),tag=document.createElement('span');
    row.dataset.status=slot.status;
    time.textContent=hm(slot.start)+'–'+hm(slot.end);
    name.textContent=slot.title;
    description.textContent=slot.detail;
    tag.textContent={elapsed:'时段已过',current:'当前时段',upcoming:'接下来'}[slot.status];
    body.append(name,description,tag);row.append(time,body);list.append(row);
   }
   positionTimeline(list);
  },
  memory(count){set('memories',count+' 条');}
 };
};
