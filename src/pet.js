let state,rig,loading=false,press=null,dragging=false,playSerial=0,audio=null,context=null,analyser=null,audioFrame,hostAudio=null,mouthAmount=0,controlAt=0,bubbleTimer,ackKey='';
let pcmPlayback=null,lastStream=null,pausedForInput=false,audioTimer=null;
const PCM_START_BUFFER_MS=500;
const PCM_READY_SECONDS=1.6;
const TOUCH_HOLD_MS=220;
let gestureId=0;
const caption=document.createElement('div');
caption.id='subtitle';caption.hidden=true;caption.setAttribute('aria-label','中文字幕');
document.body.append(caption);
const sessionChip=document.getElementById('session-chip');
const chatButton=document.getElementById('pet-chat');
const canvas=document.getElementById('sprite');
const call=(name,data={})=>window.sion.invoke(name,data).catch(e=>{bubble(e.message.replace(/^Error invoking remote method '[^']+': Error: /,''));return null;});
function control(data){return call('control',data);}
function toggleChat(){return call('click');}
async function loadRig(){
  if(rig||loading||!state?.assets.live2d)return;loading=true;
  try{rig=new SionLive2D(canvas);const params=await rig.load(state.assets.live2d);await call('model-init',{params});}
  catch(e){rig=null;bubble(e.message);}
  finally{loading=false;}
}
function bubble(text){if(state?.compactOpen)return;const b=document.getElementById('bubble');b.textContent=text;b.hidden=false;clearTimeout(bubbleTimer);bubbleTimer=setTimeout(()=>b.hidden=true,9000);}
function acknowledge(reply){
  if(!reply||reply.audioSync||state?.compactOpen||document.hidden)return;const key=reply.turn_id+':'+reply.generation;if(ackKey===key)return;
  bubble(reply.text);requestAnimationFrame(()=>requestAnimationFrame(()=>{if(!document.hidden&&!state?.compactOpen&&state?.pendingReply?.turn_id===reply.turn_id){ackKey=key;call('ack',{turn_id:reply.turn_id,generation:reply.generation});}}));
}
function render(s){
  if(state?.settings?.showHeartVoice&&s.settings?.showHeartVoice===false){
    const bubble=document.getElementById('bubble');
    if(/^\s*[（(]\s*(?:心声|内心(?:想法)?)\s*[:：]/.test(bubble.textContent))bubble.hidden=true;
  }
  state=s;
  chatButton.hidden=s.settings?.petControls?.chatButton===false;
  chatButton.setAttribute('aria-expanded',String(!!s.compactOpen));
  if(s.clickthrough||(s.settings?.petControls?.touch===false&&press&&!press.windowMove))release(true);
  if(s.compactOpen)document.getElementById('bubble').hidden=true;
  sessionChip.textContent=s.voiceSession?.enabled?'麦克风开启':'';
  sessionChip.hidden=!sessionChip.textContent;
  loadRig();acknowledge(s.pendingReply);
}
function stopAudio(){
  playSerial++;cancelAnimationFrame(audioFrame);clearTimeout(audioTimer);
  if(audio){audio.pause();audio.src='';audio=null;}
  clearTimeout(pcmPlayback?.startTimer);
  pcmPlayback=null;pausedForInput=false;
  context?.close().catch(()=>{});context=analyser=null;hostAudio=null;mouthAmount=0;
  caption.hidden=true;caption.textContent='';
}
function prepareAudio(event){
  stopAudio();
  hostAudio={token:event.token,serial:event.serial,noticeId:event.noticeId};
  try{
    context=new AudioContext();analyser=context.createAnalyser();analyser.fftSize=256;
    analyser.connect(context.destination);
  }catch{
    finishAudio('无法播放语音，请检查音频输出设备。');
    return null;
  }
  return playSerial;
}
function setCaption(text,visibleChars){
  document.getElementById('bubble').hidden=true;
  caption.textContent=text;caption.scrollTop=0;caption.hidden=!text;
  if((hostAudio?.token||hostAudio?.noticeId)&&visibleChars)void call('audio-caption',{...hostAudio,visibleChars});
}
function showSubtitle(text,duration,visibleChars){
  setCaption(text,visibleChars);
  void call('audio-start',{...hostAudio,duration});
}
function finishAudio(message){
  const host=hostAudio;
  if(pcmPlayback)lastStream={chunks:pcmPlayback.chunks,maximumGapMs:Math.round(pcmPlayback.maximumGap*1000),seconds:pcmPlayback.seconds};
  stopAudio();
  if(host)void call('audio-end',{...host,completed:!message});
  if(message)bubble(message);
}
async function pausePlayback(event,pause){
  if(!context||hostAudio?.serial!==event.serial)return;
  const current=context;
  const clip=audio;
  pausedForInput=pause;
  try{
    if(pause){
      clip?.pause();caption.hidden=true;mouthAmount=0;
      void call('audio-level',{...hostAudio,level:0});
      await current.suspend();
    }else{
      await current.resume();
      if(context!==current||pausedForInput)return;
      if(clip)await clip.play();
      if(context===current&&!pausedForInput)caption.hidden=!caption.textContent;
    }
  }catch{if(context===current)finishAudio('音频设备已断开。');}
}
function animateAudio(serial,step){
  const samples=new Uint8Array(256);let last=0;
  function next(){
    if(document.hidden)audioTimer=setTimeout(()=>frame(performance.now()),40);
    else audioFrame=requestAnimationFrame(frame);
  }
  function frame(now){
    if(serial!==playSerial||!analyser)return;
    if(pausedForInput){next();return;}
    if(step?.()===false)return;
    if(document.hidden){mouthAmount=0;next();return;}
    analyser.getByteTimeDomainData(samples);
    let sum=0;
    for(const value of samples)sum+=((value-128)/128)**2;
    mouthAmount=Math.max(0,Math.min(.85,(Math.sqrt(sum/samples.length)-.025)*7));
    if(now-last>=33){last=now;void call('audio-level',{...hostAudio,level:mouthAmount});}
    next();
  }
  next();
}
async function play(e){
  let local;
  try{
    local=prepareAudio(e);
    if(local===null)return;
    const clip=audio=new Audio(e.audio);
    context.createMediaElementSource(clip).connect(analyser);
    await context.resume();if(local!==playSerial)return;
    clip.onended=()=>{if(local===playSerial)finishAudio();};
    clip.onerror=()=>{if(local===playSerial)finishAudio('语音播放失败，请检查音频输出设备。');};
    await clip.play();if(local!==playSerial){clip.pause();return;}
    showSubtitle(e.subtitle,Math.max(.05,Math.min(120,clip.duration)),e.visibleChars);
    animateAudio(local);
  }catch{if(local===playSerial)finishAudio('无法播放语音，请检查音频输出设备。');}
}
function startPCM(e){
  const local=prepareAudio(e);
  if(local===null)return;
  const playback=pcmPlayback={rate:e.rate,reserveSeconds:e.reserveSeconds||0,cues:[],pending:[],pendingBytes:0,startTimer:null,firstAt:null,nextAt:0,
    done:false,started:false,chunks:0,maximumGap:0,seconds:0};
  void context.resume().catch(()=>{if(local===playSerial)finishAudio('无法播放语音，请检查音频输出设备。');});
  animateAudio(local,()=>{
    while(playback.cues.length&&context.currentTime>=playback.cues[0].start){
      const cue=playback.cues.shift();
      if(playback.started)setCaption(cue.caption,cue.visibleChars);
      else{playback.started=true;showSubtitle(cue.caption,120,cue.visibleChars);}
    }
    if(playback.done&&context.currentTime>=playback.nextAt){finishAudio();return false;}
    return true;
  });
}
function queuePCM(event){
  const playback=pcmPlayback;
  if(!playback||hostAudio.serial!==event.serial)return;
  if(playback.firstAt===null){
    if(!playback.pending.length&&!playback.reserveSeconds)playback.startTimer=setTimeout(()=>flushPCM(playback),PCM_START_BUFFER_MS);
    playback.pending.push(event);
    playback.pendingBytes+=event.pcm.byteLength;
    if(playback.pendingBytes>=playback.rate*2*(playback.reserveSeconds||PCM_READY_SECONDS))flushPCM(playback);
    return;
  }
  schedulePCM(playback,event);
}
function flushPCM(playback){
  if(pcmPlayback!==playback)return;
  clearTimeout(playback.startTimer);
  for(const chunk of playback.pending)schedulePCM(playback,chunk);
  playback.pending.length=0;
  playback.pendingBytes=0;
}
function schedulePCM(playback,event){
  const pcm=new DataView(event.pcm.buffer,event.pcm.byteOffset,event.pcm.byteLength);
  const buffer=context.createBuffer(1,pcm.byteLength/2,playback.rate);
  const channel=buffer.getChannelData(0);
  for(let i=0;i<channel.length;i++)channel[i]=pcm.getInt16(i*2,true)/32768;
  const source=context.createBufferSource();source.buffer=buffer;source.connect(analyser);
  const start=Math.max(playback.nextAt,context.currentTime+(playback.firstAt===null?.08:.015));
  if(playback.nextAt)playback.maximumGap=Math.max(playback.maximumGap,start-playback.nextAt);
  playback.chunks++;playback.seconds+=buffer.duration;
  if(event.caption)playback.cues.push({start,caption:event.caption,visibleChars:event.visibleChars});
  playback.firstAt??=start;playback.nextAt=start+buffer.duration;
  source.start(start);
}
function point(e){const b=canvas.getBoundingClientRect();return {x:(e.clientX-b.left)/b.width,y:(e.clientY-b.top)/b.height};}
function updatePointer(e,force=false){if(!rig?.ready)return;const p=point(e),now=performance.now();if(force||now-controlAt>32){controlAt=now;const [x,y]=rig.sourcePoint(p.x,p.y);control({name:'pointer',x:(x-1882)/1100,y:(y-1000)/1600,inside:true});}return p;}
function startContact(current){
  if(current.contact||current.windowMove)return;
  clearTimeout(current.timer);
  current.contact=true;
  control({name:'press',zone:current.zone});
}
function screenPoint(e){return {x:e.screenX,y:e.screenY};}
function startWindowMove(current,e){
  clearTimeout(current.timer);
  if(current.contact)control({name:'release',cancelled:true});
  current.windowMove=true;dragging=true;
  call('drag-start',{id:current.id,origin:{x:current.screenX,y:current.screenY},point:screenPoint(e)})
    .then(accepted=>{if(!accepted&&press===current)release(true);});
}
function queueWindowMove(current,e){
  current.nextPoint=screenPoint(e);
  if(current.frame!==undefined)return;
  current.frame=requestAnimationFrame(()=>{
    current.frame=undefined;
    if(press===current)call('drag-move',{id:current.id,point:current.nextPoint})
      .then(moved=>{if(!moved&&press===current)release(true);});
  });
}
canvas.addEventListener('pointerdown',e=>{
  if(e.button!==0||!e.isPrimary||!rig?.ready)return;
  release(true);
  const p=updatePointer(e,true),zone=rig.zone(p.x,p.y);if(!zone)return;
  const touch=state?.settings?.petControls?.touch!==false;
  try{canvas.setPointerCapture(e.pointerId);}catch{return;}
  const current=press={id:++gestureId,pointerId:e.pointerId,screenX:e.screenX,screenY:e.screenY,x:p.x,y:p.y,zone,
    touch,interactionDrag:touch&&e.shiftKey,moved:false,windowMove:false,contact:false};
  if(e.altKey)startWindowMove(current,e);
  else if(touch)current.timer=setTimeout(()=>{if(press===current)startContact(current);},TOUCH_HOLD_MS);
});
canvas.addEventListener('pointermove',e=>{
  const current=press;
  if(current&&e.pointerId===current.pointerId){
    if(!(e.buttons&1)){release(true,e.pointerId);return;}
    if(current.windowMove){queueWindowMove(current,e);return;}
  }
  const p=updatePointer(e);if(!p||!current||e.pointerId!==current.pointerId)return;
  const dx=e.screenX-current.screenX,dy=e.screenY-current.screenY;
  if(Math.hypot(dx,dy)>5){
    current.moved=true;
    if(!current.interactionDrag){
      startWindowMove(current,e);return;
    }
    startContact(current);
  }
  if(current.contact)control({name:'move',x:(p.x-current.x)/.24,y:(p.y-current.y)/.18});
});
function release(cancel=false,pointerId=press?.pointerId,position){
  const current=press;if(!current||current.pointerId!==pointerId)return;
  press=null;clearTimeout(current.timer);
  if(canvas.hasPointerCapture(current.pointerId))canvas.releasePointerCapture(current.pointerId);
  if(current.windowMove){
    if(current.frame!==undefined)cancelAnimationFrame(current.frame);
    dragging=false;call('drag-end',{id:current.id,point:cancel?undefined:position});
  }
  else if(current.contact)control({name:'release',cancelled:cancel});
  else if(!cancel&&!current.moved&&current.touch&&state?.settings?.petControls?.touch!==false){
    startContact(current);control({name:'release',cancelled:false});
  }
}
canvas.addEventListener('pointerup',e=>release(false,e.pointerId,screenPoint(e)));
canvas.addEventListener('pointercancel',e=>release(true,e.pointerId));
canvas.addEventListener('lostpointercapture',e=>release(true,e.pointerId));
window.addEventListener('blur',()=>release(true));
document.addEventListener('visibilitychange',()=>{if(document.hidden)release(true);});
canvas.addEventListener('pointerleave',()=>{if(!press)control({name:'pointer',x:0,y:0,inside:false});});
canvas.addEventListener('dblclick',e=>{e.preventDefault();if(state?.settings?.petControls?.touch!==false)control({name:'double'});});
document.body.addEventListener('contextmenu',e=>{e.preventDefault();call('menu');});sessionChip.onclick=toggleChat;chatButton.onclick=toggleChat;
window.sion.subscribe(e=>{
  if(e.type==='state')render(e.state);
  if(e.type==='drag-cancelled'&&press?.id===e.id)release(true);
  if(e.type==='live2d-frame')rig?.apply(e.values);
  if(e.type==='cursor'&&!press)control({name:'pointer',x:e.pose.x,y:e.pose.y,inside:!dragging});
  if(e.type==='reply-ready')acknowledge(e.reply);
  if(e.type==='bubble')bubble(e.text);
  if(e.type==='audio')play(e);
  if(e.type==='pcm-start')startPCM(e);
  if(e.type==='pcm-chunk')queuePCM(e);
  if(e.type==='pcm-ready'&&pcmPlayback&&hostAudio.serial===e.serial&&pcmPlayback.firstAt===null)flushPCM(pcmPlayback);
  if(e.type==='pcm-end'&&pcmPlayback&&hostAudio.serial===e.serial){
    pcmPlayback.done=true;
    flushPCM(pcmPlayback);
  }
  if(e.type==='pause-for-input')void pausePlayback(e,true);
  if(e.type==='resume-after-input')void pausePlayback(e,false);
  if(e.type==='stop-audio')stopAudio();
  if(e.type==='mouth-test'){stopAudio();bubble('口型节奏演示 · 无语音');const start=performance.now(),serial=playSerial;let last=0;function demo(now){if(serial!==playSerial)return;if(now-start>1800){control({name:'mouth-demo',value:0});return;}if(now-last>33){last=now;control({name:'mouth-demo',value:.65*Math.max(0,Math.sin((now-start)/100))});}requestAnimationFrame(demo);}requestAnimationFrame(demo);}
});
window.sionVisual={stats:()=>({mode:'cubism-core-v105',ready:!!rig?.ready,source:rig?{width:rig.c?.CanvasWidth,height:rig.c?.CanvasHeight}:null,frames:rig?.frames||0,lost:!!rig?.gl?.isContextLost(),mouthOpen:mouthAmount,audioPlaying:!!audio||!!pcmPlayback?.started,pausedForInput:pausedForInput&&context?.state==='suspended',streaming:!!pcmPlayback,lastStream,drawables:rig?.d?.count,coreVersion:Live2DCubismCore.Version.csmGetVersion()}),pixels:()=>rig?.pixels(),parameters:()=>rig?Object.fromEntries(rig.model.parameters.ids.map((id,i)=>[id,rig.model.parameters.values[i]])):null};
window.sion.invoke('state').then(render);
