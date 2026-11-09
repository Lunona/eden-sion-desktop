(() => {
  const api = window.sion;
  const form = document.getElementById('chat-form');
  if (!form) return;

  const bar = document.createElement('div');
  bar.className = 'voice-input-bar';
  bar.innerHTML = '<button type="button" class="voice-start" aria-pressed="false">语音交谈</button>' +
    '<button type="button" class="screen-start" aria-pressed="false">屏幕共享</button>' +
    '<button type="button" class="live-watch" aria-pressed="false">实时陪伴</button>' +
    '<span class="voice-live" role="status"></span>' +
    '<div class="voice-options"><label title="关着麦克风也可以收到应用内文字"><input type="checkbox" class="voice-proactive"> 偶尔主动搭话</label></div>' +
    '<div class="screen-options" hidden><label>共享显示器 <select class="screen-display"></select></label>' +
    '<p class="screen-destination"></p><label class="live-speech-option" hidden><input type="checkbox" class="live-speech" checked> 也用声音接话</label>' +
    '<button type="button" class="screen-confirm">开始共享</button></div>';
  form.before(bar);
  const select = selector => bar.querySelector(selector);
  const start = select('.voice-start');
  const status = select('.voice-live');
  const proactive = select('.voice-proactive');
  const screenButton = select('.screen-start');
  const liveButton = select('.live-watch');
  const liveSpeech = select('.live-speech');
  const liveSpeechOption = select('.live-speech-option');
  const screenOptions = select('.screen-options');
  const displays = select('.screen-display');
  const destination = select('.screen-destination');
  const share = select('.screen-confirm');
  let state, selection='share';

  function render(next) {
    state = next;
    const voice = state.voiceSession;
    start.setAttribute('aria-pressed', String(voice.enabled));
    start.textContent = voice.enabled ? '关闭麦克风' : '开启语音交谈';
    bar.classList.toggle('listening', voice.enabled);
    proactive.checked = voice.proactive;
    const phrases = {off: '开启一次，收起聊天框也可以直接说话。', starting: '正在开启麦克风…',
      listening: state.voicePlaying ? '诗音在说话 · 可以插话' : '麦克风开启 · 随时可以说话',
      speaking: '正在听你说话…', recognizing: '正在识别…'};
    status.textContent = voice.inputSilent && voice.phase === 'listening'
      ? '未收到麦克风声音，请检查系统静音和输入设备。'
      : voice.detail || phrases[voice.phase] || '';
    if(state.liveWatch?.enabled&&!voice.inputSilent&&['off','listening'].includes(voice.phase)&&!state.voicePlaying){
      status.textContent=state.liveWatch.detail||'正在一起看 · 有话题才开口';
    }
    status.title = status.textContent;
    const screen = state.screenShare;
    if (!screen) return;
    screenButton.setAttribute('aria-pressed', String(screen.enabled));
    screenButton.textContent = screen.enabled ? '停止共享' : '屏幕共享';
    const watching=state.liveWatch?.enabled===true;
    liveButton.setAttribute('aria-pressed',String(watching));
    liveButton.textContent=watching?'结束实时陪伴':'实时陪伴';
    if(watching||screen.enabled&&selection==='share')screenOptions.hidden=true;
    const displayKey = JSON.stringify(screen.displays);
    if (displays.dataset.key !== displayKey) {
      displays.dataset.key = displayKey;
      displays.replaceChildren();
      for (const display of screen.displays) displays.add(new Option(display.label, String(display.id)));
    }
    destination.textContent = !screen.model
      ? '请先在「模型与语音」为屏幕理解选择支持图片的模型。'
      : selection==='watch'
        ? '陪伴开启后，变化的画面会间隔发送给 '+screen.model+'（'+screen.provider+'）。看视频或玩游戏时，诗音会视情况聊一句。'
        : '共享期间，发言时会把这块屏幕的当前画面发给 ' + screen.model + '（' + screen.provider + '）。';
    bar.classList.toggle('choosing-screen',!screenOptions.hidden);
    liveSpeechOption.hidden=selection!=='watch';
    share.textContent=selection==='watch'?'开始实时陪伴':'开始共享';
    share.disabled = !screen.model || !screen.displays.length;
  }

  async function invoke(action, value) {
    try { return await api.invoke(action, value); }
    catch (error) { status.textContent = error.message.replace(/^Error invoking remote method '[^']+': Error: /, ''); }
  }
  start.onclick = async () => {
    if (!state) return;
    start.disabled = true;
    await invoke('voice-session', {enabled: !state.voiceSession.enabled});
    start.disabled = false;
  };
  proactive.onchange = () => void invoke('voice-proactive', {enabled: proactive.checked});
  screenButton.onclick = () => {
    if (!state?.screenShare) return;
    if (state.screenShare.enabled) void invoke('screen-share', {enabled: false});
    else choose('share');
  };
  function choose(mode){
    const show=screenOptions.hidden||selection!==mode;
    selection=mode;
    screenOptions.hidden=!show;
    render(state);
  }
  liveButton.onclick=()=>{
    if(!state?.screenShare)return;
    if(state.liveWatch?.enabled)void invoke('live-watch',{enabled:false});
    else choose('watch');
  };
  share.onclick=async()=>{
    share.disabled=true;
    await invoke(selection==='watch'?'live-watch':'screen-share',
      {enabled:true,displayId:Number(displays.value),speak:liveSpeech.checked});
    share.disabled=!state?.screenShare?.model||!state?.screenShare?.displays.length;
  };
  api.subscribe(event => { if (event.type === 'state') render(event.state); });
  api.invoke('state').then(render).catch(() => {});
  window.sionVoiceInput = {
    stop: () => invoke('voice-session', {enabled: false}),
    status: () => ({armed: !!state?.voiceSession.enabled, phase: state?.voiceSession.phase})
  };
})();
