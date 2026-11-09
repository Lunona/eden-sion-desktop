const {app,BrowserWindow,ipcMain,screen,Menu,Tray,nativeImage,dialog,safeStorage,globalShortcut,Notification,desktopCapturer,powerMonitor}=require('electron');
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const {EventEmitter}=require('node:events');
const {pathToFileURL}=require('node:url');
const {Store,NullMemory,EXPRESSIONS,FRAMES,validateSettings,loadPack}=require('./core.cjs');
const services=require('./services.cjs');
const {CompanionBridge,spokenOnlyText,withoutHeartVoice}=require('./companion-bridge.cjs');
const {ProviderRouter}=require('./providers.cjs'),{SpeechInput}=require('./speech-input.cjs');
const {LocalVoiceService,managedVoiceEndpoint}=require('./local-voice-service.cjs');
const {productionDataRoot}=require('./production-data.cjs');
let instanceGuard;const {acquireInstance}=require('./single-instance.cjs');
const {ComputerAssistant,desktopIntent}=require('./computer-assistant.cjs');
const {japaneseLine,isEcho,ScreenConversation}=require('./live-companion.cjs');
const {VoiceRunway}=require('./voice-runway.cjs');
const {LiveWatch}=require('./live-watch.cjs');
const {loadVoiceReferences,selectVoiceReference}=require('./voice-references.cjs');
const {LocalWeather,windFor}=require('./local-weather.cjs');
const {DESKTOP_APP_ID,readWindowsNotificationSetting,isWindowsNotificationBlocked}=require('./windows-notification-setting.cjs');
const voiceReferences=loadVoiceReferences();
let computerAssistant;let providers,speechInput,speechRequest=null;const micAllowed=new Set();
let screenConversation,liveWatch,weather,proactiveTimer,voiceStartingTimer,audioQueued=false,activeLine=null,voicePaused=false,manualVoiceStart=null;
let previousCpu=null,lastPrepIdle=false;
const voiceSession={enabled:false,generation:0,inputEpoch:0,phase:'off',detail:'',inputSilent:false};
const {placeCompact}=require('./compact-layout.cjs');
const voiceIntegration=process.argv.includes('--voice-integration');
const dragCheck=process.argv.includes('--verify-drag');
const smoke=process.argv.includes('--smoke')||voiceIntegration||dragCheck;
const nativeComputerCheck=process.argv.includes('--verify-computer');
const desktopChatCheck=process.argv.includes('--verify-desktop-chat');
const visionCheck=process.argv.includes('--verify-vision');
const runtimeCheck=process.argv.includes('--verify-runtime');
const resourceCheck=process.argv.includes('--verify-resources');
const liveMemoryCheck=process.argv.includes('--verify-memory');
const providerCheck=process.argv.includes('--verify-provider');
const bilingualCheck=process.argv.includes('--verify-bilingual');
const bilingualKeyPipe=bilingualCheck&&process.argv.find(arg=>arg.startsWith('--bilingual-key-pipe='));
const modelCheck=visionCheck||liveMemoryCheck||providerCheck||bilingualCheck;
const diagnostic=smoke||nativeComputerCheck||desktopChatCheck||runtimeCheck||resourceCheck||modelCheck;
class VerificationNotification extends EventEmitter {
  static isSupported(){return true;}
  show(){this.emit('show');}
}
const reminderNotification=diagnostic?VerificationNotification:Notification;
const root=path.resolve(__dirname,'..');
const writableRoot=app.isPackaged?path.dirname(app.getPath('exe')):root;
const localVoice=!diagnostic&&process.platform==='win32'?new LocalVoiceService(writableRoot):null;
const assetRoot=app.isPackaged?path.join(process.resourcesPath,'assets'):path.join(root,'assets');
const dataOverride=process.argv.find(x=>x.startsWith('--data-dir='))?.slice(11);
const coreShadow=process.argv.includes('--core-shadow');
if(coreShadow&&(!(smoke||desktopChatCheck)||dataOverride))throw Error('核心观察只允许使用自动隔离的验收目录');
const legacyData=app.isPackaged?path.resolve(writableRoot,'../../release-0.4.1/win-unpacked/data'):path.join(root,'release-0.4.1/win-unpacked/data');
const computerCheckData=desktopChatCheck||nativeComputerCheck;
let dataRoot;
try{
  if(resourceCheck)dataRoot=fs.mkdtempSync(path.join(os.tmpdir(),'sion-resource-check-'));
  else if(computerCheckData)dataRoot=fs.mkdtempSync(path.join(os.tmpdir(),'sion-desktop-check-'));
  else if(diagnostic)dataRoot=require('./verification-data.cjs').verificationDataRoot(writableRoot,dataOverride,{
    requiresProfile:modelCheck,prefix:smoke?'live2d-smoke-':'runtime-'
  });
  else dataRoot=productionDataRoot(writableRoot,dataOverride,legacyData);
}catch(error){
  console.error(error.message);
  if(!diagnostic)dialog.showErrorBox('无法打开诗音存档',error.message);
  app.exit(2);
  return;
}
const backendRoot=app.isPackaged?path.join(process.resourcesPath,'backend'):path.join(root,'backend');
const runtimeRoot=path.join(assetRoot,'live2d/sion');
const catalog=JSON.parse(fs.readFileSync(path.join(backendRoot,'catalog.json'),'utf8'));
let bridge,activePlayback=false;
const memoryCheckRoot=modelCheck&&!bilingualCheck?fs.mkdtempSync(path.join(dataRoot,'live-memory-')):undefined;
app.setName('诗音全身桌宠');
app.setAppUserModelId(diagnostic?'local.eden.sion.fullbody.verification':DESKTOP_APP_ID);
fs.mkdirSync(dataRoot,{recursive:true});app.setPath('userData',dataRoot);app.setPath('sessionData',path.join(dataRoot,'session'));
app.commandLine.appendSwitch('autoplay-policy','no-user-gesture-required');
let panel,pet,compact,tray,store,pack,pending,voiceJob,drag,dragTimer,cursorTimer,quitting=false,expression='neutral',clickthrough=false,error='',audioSerial=0;
let compactRestore=null,compactMoved=false,placingCompact=false;
let secretInMemory='',connectionJob=null;
let systemSuspended=false,desktopLocked=false,proactiveJob=null;
const renderErrors=[];
async function verifyProviderConnection(){
  const report={date:new Date().toISOString(),actualRemoteChat:false,actualLocalVoice:false,model:store.state.settings.model.name};
  const pause=ms=>new Promise(r=>setTimeout(r,ms));
  try{
    pet.showInactive();
    for(let i=0;i<300;i++){await pause(100);if(!pet.webContents.isLoading()&&await pet.webContents.executeJavaScript('Boolean(window.sionVisual?.stats().frames>15)'))break;if(i===299)throw new Error('Live2D 未完成初始化');}
    const baseline=new Set(bridge.messages().map(m=>m.id));const started=Date.now();await chat('你好，用一句简短的话和我打个招呼。');
    let heard=false,peak=0,finished=false,message;
    for(let i=0;i<1800;i++){
      await pause(100);if(bridge.error||error)throw new Error(bridge.error||error);
      message=bridge.messages().find(m=>m.role==='assistant'&&!baseline.has(m.id));
      if(message&&!report.actualRemoteChat)Object.assign(report,{actualRemoteChat:true,chineseReply:message.content,chatSeconds:(Date.now()-started)/1000});
      const visual=await pet.webContents.executeJavaScript('window.sionVisual.stats()');
      if(visual.audioPlaying){heard=true;peak=Math.max(peak,visual.mouthOpen);}
      if(heard&&!visual.audioPlaying&&!voiceJob){finished=true;break;}
    }
    if(!report.actualRemoteChat)throw new Error('没有收到真实模型回复');
    if(!heard||!finished||peak<.05)throw new Error('文字已回复，本次语音与口型未完整通过');
    Object.assign(report,{actualLocalVoice:true,audioPlayed:true,maximumMouthOpen:peak,endedWithMouthClosed:true,passed:true});
    await pause(400);fs.mkdirSync(path.join(writableRoot,'docs'),{recursive:true});fs.writeFileSync(path.join(writableRoot,'docs','provider-live2d.png'),(await pet.webContents.capturePage()).toPNG());
  }catch(e){report.passed=false;report.error=e.message;}
  const dir=path.join(writableRoot,'docs');fs.mkdirSync(dir,{recursive:true});fs.writeFileSync(path.join(dir,'provider-live2d.json'),JSON.stringify(report,null,2));
  if(process.argv.includes('--verify-provider'))app.exit(report.passed?0:1);
}

const secretPath=path.join(dataRoot,'model-key.bin');
function key(){if(secretInMemory)return secretInMemory;if(!fs.existsSync(secretPath))return '';try{return safeStorage.decryptString(fs.readFileSync(secretPath));}catch{return '';}}
function saveKey(value){if(typeof value!=='string'||value.length>4096)throw new Error('密钥格式无效');if(!value){secretInMemory='';if(fs.existsSync(secretPath))fs.unlinkSync(secretPath);return;}if(safeStorage.isEncryptionAvailable()){fs.writeFileSync(secretPath,safeStorage.encryptString(value));secretInMemory='';}else secretInMemory=value;}
function inspectPNG(file){const img=nativeImage.createFromPath(file);const s=img.getSize();if(img.isEmpty()||s.width>8192||s.height>8192)throw new Error('图片无法读取或尺寸超过8192像素');return s;}
function displayedReply(reply){
  return reply&&!store.state.settings.showHeartVoice?{...reply,text:withoutHeartVoice(reply.text)}:reply;
}
function state(){
  const current=bridge?.messages()||[];
  const allMessages=[...store.state.messages,...current].slice(-200);
  const messages=store.state.settings.showHeartVoice?allMessages:allMessages.map(message=>
    message.role==='assistant'?{...message,content:withoutHeartVoice(message.content)}:message);
  const computer=computerAssistant?.status();
  if(computer&&!store.state.settings.showHeartVoice)computer.taskHeartVoice='';
  if(computer?.chatRequest?.phase==='done'&&bridge?.history.some(row=>row.id===computer.chatRequest.trace))computer.chatRequest=null;
  return {settings:store.state.settings,messages,assets:{name:'诗音 · Live2D v105',placeholder:false,live2d:pathToFileURL(path.join(runtimeRoot,'Sion_H20R12.model3.json')).href,faces:catalog.faces,actions:catalog.actions},expression,pending:!!bridge?.pending,voicePending:!!bridge?.speechPending||!!voiceJob||activePlayback||audioQueued,voiceNotice:bridge?.voiceNotice||"",voicePlaying:activePlayback,voiceStartingLocal:!!(manualVoiceStart||voiceJob&&activeLine?.startingLocal),voiceReference:activeLine?.reference||null,weather:weather?.status(),voiceSession:{...voiceSession,proactive:bridge?.presence?.proactive_enabled!==false},screenShare:screenConversation?.status(),liveWatch:liveWatch?.status(),error:bridge?.error||error,clickthrough,compactOpen:!!compact&&!compact.isDestroyed()&&compact.isVisible(),keySaved:!!key(),keyEncrypted:safeStorage.isEncryptionAvailable(),dataRoot,pendingReply:displayedReply(bridge?.visibleReply)||null,memoryReady:!!bridge?.status,providers:providers?.public(),speechInput:speechInput?.status(),companion:bridge?.presence,computer};
}
function emit(value){
  const event=value.type==='reply-ready'?{...value,reply:displayedReply(value.reply)}:value;
  for(const w of [panel,pet,compact])if(w&&!w.isDestroyed())w.webContents.send('sion-event',event);
}
let reportedProgram;
function publish(){
  if(quitting||![panel,pet,compact].some(w=>w&&!w.isDestroyed()))return;
  if(bridge?.status){
    const phase=computerAssistant?.busy?'tool':['speaking','recognizing'].includes(voiceSession.phase)?voiceSession.phase:
      activePlayback?'playing':voiceJob||audioQueued?'synthesizing':voiceSession.phase==='listening'?'listening':'idle';
    if(phase!==reportedProgram){reportedProgram=phase;bridge.notify('companion-program',{phase});}
  }
  const snapshot=state();
  for(const window of [panel,compact]){
    if(window&&!window.isDestroyed()&&window.isVisible())window.webContents.send('sion-event',{type:'state',state:snapshot});
  }
  if(pet&&!pet.isDestroyed()){
    const {assets,compactOpen,pendingReply,voicePlaying,voiceSession,screenShare}=snapshot;
    pet.webContents.send('sion-event',{type:'state',state:{assets,compactOpen,pendingReply,voicePlaying,voiceSession,screenShare,settings:{petControls:snapshot.settings.petControls,showHeartVoice:snapshot.settings.showHeartVoice}}});
  }
}
function reminderReceipt(id,channel,state){
  bridge?.notify('companion-notice-receipt',{id,channel,state});
}
function voiceBusy(){
  return !!(bridge?.pending||bridge?.pendingReply||bridge?.speechPending||voiceJob||activePlayback||
    audioQueued||speechRequest!==null||['speaking','recognizing'].includes(voiceSession.phase));
}
function focusQuiet(){
  return !!bridge?.presence?.focus?.quiet;
}
function showTouchFeedback(feedback){
  if(quitting||!pet?.isVisible()||focusQuiet()||voiceBusy())return;
  if(compact?.isVisible())compact.webContents.send('sion-event',{type:'companion-notice',notice:{kind:'touch',title:feedback.text}});
  else pet.webContents.send('sion-event',{type:'bubble',text:feedback.text});
  const cfg=voiceConfig();
  if(voiceSession.phase==='listening'&&bridge?.presence?.proactive_enabled!==false&&
    cfg.enabled&&cfg.refAudio&&['ja','zh'].includes(cfg.textLang)){
    void speak(cfg.textLang==='ja'?feedback.japanese:feedback.text,null,feedback.text,feedback);
  }
}
const reminderNotificationSetting=diagnostic?()=>null:readWindowsNotificationSetting;
function canShowProactive(){
  return !liveWatch?.session&&!quitting&&!systemSuspended&&!desktopLocked&&pet?.isVisible()&&!focusQuiet()&&
    bridge?.presence?.proactive_enabled!==false&&!voiceBusy()&&!drag&&!computerAssistant?.busy&&
    !['planning','ready','running'].includes(computerAssistant?.chatRequest?.phase);
}
function cancelProactive(){
  proactiveJob?.abort();
}
async function showProactiveMessage(notice){
  const expires=()=>Date.now()/1000>=notice.expires_at;
  if(proactiveJob||!canShowProactive()||expires()){
    reminderReceipt(notice.id,'display','unavailable');
    reminderReceipt(notice.id,'audio','skipped');
    return;
  }
  const job=proactiveJob=new AbortController();
  const current=()=>!job.signal.aborted&&canShowProactive()&&!expires();
  let recorded=false,playing=false;
  try{
    const draftSignal=AbortSignal.any([job.signal,AbortSignal.timeout(6500)]);
    const text=await bridge.draftProactive(notice,draftSignal).catch(()=>notice.title);
    if(!current())return;
    recorded=await bridge.recordProactiveMessage(notice,text);
    if(!recorded||!current())return;
    if(!compact?.isVisible())pet.webContents.send('sion-event',{type:'bubble',text});
    const cfg=voiceConfig();
    const canSpeak=()=>current()&&voiceSession.phase==='listening'&&voiceConfig().enabled;
    if(canSpeak()&&cfg.refAudio&&['ja','zh'].includes(cfg.textLang)){
      const speechSignal=AbortSignal.any([job.signal,AbortSignal.timeout(6500)]);
      const spoken=cfg.textLang==='zh'?text:text===notice.title?notice.japanese:
        await bridge.proactiveJapanese(text,speechSignal).catch(()=>null);
      if(spoken&&canSpeak()&&voiceConfig().textLang===cfg.textLang){
        playing=true;
        void speak(spoken,null,text,{emotion:'warm',intensity:.45},notice.id);
      }
    }
  }catch{}finally{
    if(proactiveJob===job)proactiveJob=null;
    if(!recorded)reminderReceipt(notice.id,'display','unavailable');
    if(!playing)reminderReceipt(notice.id,'audio','skipped');
  }
}
async function showCompanionNotice(notice,DesktopNotification=reminderNotification,readSetting=reminderNotificationSetting){
  if(['proactive','weather'].includes(notice.kind))return showProactiveMessage(notice);
  const recordDisplay=state=>bridge.request('companion-notice-receipt',{id:notice.id,channel:'display',state}).catch(()=>false);
  let displayResult;
  const settleDisplay=state=>{
    displayResult??=recordDisplay(state).then(accepted=>{
      if(!accepted||quitting)return null;
      if(state==='shown'){
        if(notice.observation_id)bridge.observe('notice.shown','host',{id:'notice-shown:'+notice.observation_id});
      }else{
        const visible=w=>w&&!w.isDestroyed()&&w.isVisible()&&!w.isMinimized();
        const target=[compact,panel].find(visible);
        if(target)target.webContents.send('sion-event',{type:'companion-notice',notice});
        else if(visible(pet))pet.webContents.send('sion-event',{type:'bubble',text:notice.title});
      }
      return state;
    });
    return displayResult;
  };
  if(DesktopNotification.isSupported()&&!isWindowsNotificationBlocked(await readSetting())){
    try{
      const notification=new DesktopNotification({title:'诗音的提醒',body:notice.title,silent:true});
      notification.once('failed',()=>void settleDisplay('unavailable'));
      // Windows emits show after the toast API returns, including when no banner appears.
      if(process.platform!=='win32')notification.once('show',()=>void settleDisplay('shown'));
      notification.once('click',async()=>{
        if(await settleDisplay('shown')==='shown'&&notice.kind==='special'&&!quitting)showPanel('companion');
      });
      if(!await recordDisplay('requested')||quitting)return;
      notification.show();
      if(notice.observation_id)bridge?.observe('notice.submitted','host',{id:'notice-submitted:'+notice.observation_id});
    }catch{if(!await settleDisplay('unavailable'))return;}
  }else if(!await settleDisplay('unavailable'))return;
  if(notice.kind==='reminder'||notice.kind==='special')reminderReceipt(notice.id,'audio','skipped');
  if(notice.kind==='focus'){
    const cfg=voiceConfig();
    if(!pet?.isVisible()||!cfg.enabled||!cfg.refAudio||!['ja','zh'].includes(cfg.textLang)||voiceBusy()){
      reminderReceipt(notice.id,'audio','skipped');
    }else{
      void speak(cfg.textLang==='ja'?notice.japanese:notice.title,null,notice.title,{emotion:'warm',intensity:.4},notice.id);
    }
  }
}
function stopAudio(){
  if(activeLine?.noticeId)reminderReceipt(activeLine.noticeId,'audio','interrupted');
  if(activeLine?.token&&(activePlayback||audioQueued||voiceJob))bridge?.observe('audio.interrupted','host',{...activeLine.token,id:'audio-interrupted:'+audioSerial});
  activePlayback=false;audioQueued=false;activeLine=null;voicePaused=false;bridge?.notify('voice-mouth',{level:0});audioSerial++;voiceJob?.abort();voiceJob=null;emit({type:'stop-audio'});
}

function pauseForVoiceInput(pause){
  if(voicePaused===pause||pause&&!activePlayback)return;
  voicePaused=pause;
  if(pet&&!pet.isDestroyed())pet.webContents.send('sion-event',{type:pause?'pause-for-input':'resume-after-input',serial:audioSerial});
}

function voiceConfig(){
  const cfg=store.state.settings.voice;
  return {...cfg,enabled:!systemSuspended&&(cfg.enabled||voiceSession.enabled&&!!cfg.refAudio)};
}

function setVoiceSession(enabled, detail=''){
  if(enabled&&(!pet||pet.isDestroyed()))throw Error('桌宠还在启动');
  if(enabled&&speechInput.config.mode==='local'&&!speechInput.status().localAvailable)throw Error('本机语音识别环境未找到');
  if(enabled&&speechInput.config.mode==='api'&&!providers.has('asr'))throw Error('请先选择语音识别API');
  voiceSession.generation++;
  voiceSession.inputEpoch=0;
  voiceSession.enabled=enabled;
  voiceSession.phase=enabled?'starting':'off';
  voiceSession.detail=detail;
  voiceSession.inputSilent=false;
  clearTimeout(voiceStartingTimer);
  micAllowed.clear();
  if(!enabled||speechInput?.active)speechInput?.cancel();
  pauseForVoiceInput(false);
  if(enabled){
    micAllowed.add(pet.webContents.id);bridge?.notify('companion-activity');
    voiceStartingTimer=setTimeout(()=>setVoiceSession(false,'麦克风开启超时，请检查输入设备。'),15000);
  }
  if(pet&&!pet.isDestroyed())pet.webContents.send('sion-event',{type:'voice-session',enabled,generation:voiceSession.generation});
  if(store)publish();
}

function deliverLiveText(remark){
  if(!compact?.isVisible()&&pet?.isVisible())pet.webContents.send('sion-event',{type:'bubble',text:remark.text});
  void bridge.rememberLiveRemark(remark).catch(()=>{});
}

function stopLiveWatch(){
  liveWatch?.stop();
  if(activeLine?.liveRemark&&(voiceJob||audioQueued||activePlayback))stopAudio();
}

function stopLiveSharing(){
  cancelProactive();
  stopLiveWatch();
  preparationAllowed(false);
  computerAssistant?.stop();
  screenConversation?.stop();
  setVoiceSession(false);
}

function suspendDesktop(){
  const spokenReply=bridge?.speechPending||bridge?.pendingReply?.audioSync||activeLine?.token||
    bridge?.pending&&voiceConfig().enabled;
  systemSuspended=true;
  if(spokenReply)void bridge.interrupt().catch(()=>{});
  else if(voiceJob||audioQueued||activePlayback)stopAudio();
  stopLiveSharing();
}

async function transcribeUtterance(data){
  const generation=voiceSession.generation;
  if(!voiceSession.enabled||data.generation!==generation||data.inputEpoch!==voiceSession.inputEpoch||speechRequest)return false;
  const line=activeLine;
  const request=speechRequest={cancelled:false};
  voiceSession.phase='recognizing';
  voiceSession.detail='';
  publish();
  try{
    const result=await speechInput.transcribe(data);
    if(request.cancelled||!voiceSession.enabled||generation!==voiceSession.generation)return false;
    if(result.text&&!(data.duringPlayback&&isEcho(result.text,line))){
      voiceSession.detail='听到 '+result.text.slice(0,100);
      await chat(result.text,'voice');
    }else if(!result.text)voiceSession.detail='这句没听清，可以接着说。';
    return !request.cancelled;
  }catch(e){
    if(!request.cancelled&&generation===voiceSession.generation)voiceSession.detail=e.message;
    return false;
  }finally{
    speechRequest=null;
    if(generation===voiceSession.generation){voiceSession.phase='listening';pauseForVoiceInput(false);publish();}
  }
}

function cancelVoiceInput(){
  if(speechRequest&&!speechRequest.cancelled){
    speechRequest.cancelled=true;
    if(speechInput.active)speechInput.cancel();
  }
  if(!voiceSession.enabled||voiceSession.phase==='starting')return;
  if(voiceSession.phase==='speaking'){
    voiceSession.phase='listening';voiceSession.detail='';pauseForVoiceInput(false);
  }
  const inputEpoch=++voiceSession.inputEpoch;
  if(pet&&!pet.isDestroyed())pet.webContents.send('sion-event',{type:'voice-discard',generation:voiceSession.generation,inputEpoch});
}

function maybeSpeakFirst(userIdleSeconds=powerMonitor.getSystemIdleTime()){
  if(!bridge||proactiveJob||!canShowProactive())return;
  const cfg=voiceConfig();
  bridge.notify('companion-proactive-tick',{
    text_allowed:true,listening:voiceSession.phase==='listening',busy:false,idle_seconds:userIdleSeconds,
    speech_allowed:cfg.enabled&&!!cfg.refAudio&&['ja','zh'].includes(cfg.textLang),
    weather:weather?.status().current?.label
  });
}

function idlePreparation(){
  if(focusQuiet()||!bridge.presence?.special_days?.length||bridge.presence?.interaction_policy?.stage==='acquaintance'){
    previousCpu=null;preparationAllowed(false);return;
  }
  let total=0,idle=0;
  for(const cpu of os.cpus()){
    idle+=cpu.times.idle;
    total+=Object.values(cpu.times).reduce((a,b)=>a+b,0);
  }
  const quiet=previousCpu&&total>previousCpu.total&&(idle-previousCpu.idle)/(total-previousCpu.total)>.68;
  previousCpu={total,idle};
  const allowed=!!quiet&&powerMonitor.getSystemIdleTime()>=180&&os.freemem()>=1024**3&&!voiceBusy()&&!computerAssistant?.busy;
  preparationAllowed(allowed);
}

function preparationAllowed(allowed){
  if(allowed!==lastPrepIdle){lastPrepIdle=allowed;bridge?.notify('preparation-idle',{allowed});}
}
function cancel(){liveWatch?.cancel();cancelProactive();cancelVoiceInput();computerAssistant?.stop();bridge?.notify('controls',{name:'cancel'});connectionJob?.abort();error='';expression='neutral';if(bridge)void bridge.interrupt().catch(e=>{error=e.message;publish();});else stopAudio();publish();}
function makeWindow(file,options,initiallyHidden=false){
  const w=new BrowserWindow({icon:path.join(assetRoot,'tray.png'),...options,show:false,webPreferences:{preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,sandbox:true,nodeIntegration:false,webSecurity:true,backgroundThrottling:file!=='pet.html'}});
  if(diagnostic){w.setOpacity(0);w.setFocusable(false);w.setSkipTaskbar(true);w.setIgnoreMouseEvents(true,{forward:true});w.webContents.setAudioMuted(true);}
  w.webContents.setWindowOpenHandler(()=>({action:'deny'}));w.webContents.on('will-navigate',e=>e.preventDefault());
  w.webContents.session.setPermissionRequestHandler((wc,permission,cb,details)=>cb(permission==='media'&&micAllowed.has(wc.id)&&![...(details.mediaTypes||[])].includes('video')));
  w.webContents.session.setPermissionCheckHandler((wc,permission,_origin,details)=>permission==='media'&&!!wc&&micAllowed.has(wc.id)&&details.mediaType!=='video');
  w.webContents.on('console-message',(_e,_level,message)=>{if(_level>=3)renderErrors.push(String(message));});
  w.webContents.on('render-process-gone',()=>{error='窗口渲染意外结束，请退出后重新启动';if(w===pet)stopLiveSharing();});
  let loaded=false;
  w.ensureLoaded=()=>{
    if(!loaded){
      loaded=true;
      void w.loadFile(path.join(__dirname,file)).catch(()=>{loaded=false;});
    }
  };
  w.once('ready-to-show',()=>{if(!diagnostic&&!initiallyHidden){if(file==='pet.html')w.showInactive();else w.show();}});
  w.webContents.on('did-finish-load',publish);
  if(!initiallyHidden||diagnostic&&!runtimeCheck&&!resourceCheck)w.ensureLoaded();
  return w;
}
function applyPetBounds(b){const old=pet.getContentBounds();if(old.width!==b.width||old.height!==b.height||old.x!==b.x||old.y!==b.y)pet.setContentBounds(b,false);}
function applyChatBounds(b){const old=compact.getContentBounds();if(old.width!==b.width||old.height!==b.height||old.x!==b.x||old.y!==b.y)compact.setContentBounds(b,false);}
function movePetTogether(b){
 if(placingCompact||!pet||pet.isDestroyed())return;
 const area=screen.getDisplayMatching(b).workArea;placingCompact=true;
 try{if(compact?.isVisible()){const next=placeCompact(b,area);applyPetBounds(next.pet);applyChatBounds(next.chat);}else applyPetBounds({...b,x:Math.round(Math.max(area.x,Math.min(area.x+area.width-b.width,b.x))),y:Math.round(Math.max(area.y,Math.min(area.y+area.height-b.height,b.y)))});}finally{placingCompact=false;}
}
function positionCompact(){
  if(placingCompact||!compact?.isVisible()||!pet||pet.isDestroyed())return;
  movePetTogether(pet.getContentBounds());
}
function showCompact(){
  if(!compact||compact.isDestroyed())return;
  compact.ensureLoaded();
  if(!compact.isVisible()){
    compactRestore=pet.getContentBounds();compactMoved=false;
    const area=screen.getDisplayMatching(compactRestore).workArea,next=placeCompact(compactRestore,area);
    placingCompact=true;try{applyPetBounds(next.pet);applyChatBounds(next.chat);}finally{placingCompact=false;}
    compact.setAlwaysOnTop(store.state.settings.topmost,'screen-saver');compact.show();
  }
  compact.focus();compact.webContents.send('sion-event',{type:'compact-focus'});publish();
}
function hideCompact(){
  if(!compact?.isVisible())return;compact.hide();
  if(compactRestore){const current=pet.getContentBounds(),back={...compactRestore};if(compactMoved){back.x=current.x;back.y=current.y;}applyPetBounds(back);compactRestore=null;clamp();store.state.settings.position=pet.getPosition();store.save();}
  publish();
}
function clamp(){if(!pet||pet.isDestroyed())return;movePetTogether(pet.getContentBounds());}
function reset(){computerAssistant?.stop();endDrag();hideCompact();clickthrough=false;pet.setIgnoreMouseEvents(false);const a=screen.getPrimaryDisplay().workArea,b=pet.getContentBounds();movePetTogether({...b,x:a.x+a.width-b.width-20,y:a.y+a.height-b.height});pet.show();clamp();publish();}
function showPanel(page='settings'){panel.ensureLoaded();panel.show();panel.focus();const send=()=>{panel.webContents.send('sion-event',{type:'navigate',page:['chat','settings','character','memory','companion','providers','persona','computer'].includes(page)?page:'settings'});publish();};if(panel.webContents.isLoading())panel.webContents.once('did-finish-load',send);else send();}
function resizePet(){const open=compact?.isVisible();if(open)hideCompact();const area=screen.getDisplayMatching(pet.getContentBounds()).workArea;const scale=Math.min(store.state.settings.scale,(area.width-12)/330,(area.height-12)/650),width=Math.round(330*scale),height=Math.round(650*scale);applyPetBounds({...pet.getContentBounds(),width,height});clamp();if(open)showCompact();}
function validDragPoint(point){
  return !!point&&Number.isFinite(point.x)&&Number.isFinite(point.y)&&Math.abs(point.x)<1000000&&Math.abs(point.y)<1000000;
}
function moveDrag({id,point}){
  if(!drag||id!==drag.id||!validDragPoint(point))return false;
  const {bounds,origin}=drag;
  const [x,y]=pet.getPosition();
  movePetTogether({...bounds,x:Math.round(bounds.x+point.x-origin.x),y:Math.round(bounds.y+point.y-origin.y)});
  const [nextX,nextY]=pet.getPosition();
  if(nextX!==x||nextY!==y){
    drag.moved=true;
    if(compact?.isVisible())compactMoved=true;
  }
  clearTimeout(dragTimer);
  dragTimer=setTimeout(endDrag,15000);
  return true;
}
function endDrag({id,point}={}){
  if(!drag||id!==undefined&&id!==drag.id)return false;
  if(validDragPoint(point))moveDrag({id:drag.id,point});
  clearTimeout(dragTimer);dragTimer=null;
  const finished=drag;drag=null;
  bridge?.notify('controls',{name:'window-drag',active:false});
  if(!pet.isDestroyed()){
    if(id===undefined)pet.webContents.send('sion-event',{type:'drag-cancelled',id:finished.id});
    if(finished.moved){store.state.settings.position=pet.getPosition();store.save();}
  }
  return true;
}
function beginDrag({id,origin,point}){
  if(clickthrough||!pet.isVisible()||!Number.isSafeInteger(id)||!validDragPoint(origin)||!validDragPoint(point))return false;
  endDrag();
  drag={id,origin,bounds:pet.getContentBounds(),moved:false};
  bridge?.notify('controls',{name:'window-drag',active:true});
  return moveDrag({id,point});
}
function toggleClickthrough(){
  endDrag();
  clickthrough=!clickthrough;
  pet.setIgnoreMouseEvents(clickthrough,{forward:true});publish();
  return true;
}
async function startLocalVoiceManual(){
  if(!localVoice)return;
  error='';
  if(manualVoiceStart)return;
  const start=localVoice.startManual();
  manualVoiceStart=start;publish();
  try{
    await start;
  }catch(e){
    if(manualVoiceStart===start)error=e.message||'本机配音启动失败';
  }finally{
    if(manualVoiceStart===start)manualVoiceStart=null;
    publish();
  }
}
async function stopLocalVoiceManual(){
  manualVoiceStart=null;
  stopAudio();
  if(!localVoice)return;
  try{await localVoice.stopManual();}
  catch(e){error=e.message||'本机配音停止失败';}
  publish();
}
function menu(){Menu.buildFromTemplate([
  {label:'和诗音聊天',click:showCompact},{label:'查看记忆',click:()=>showPanel('memory')},{label:'连接与设置',click:()=>showPanel('settings')},{type:'separator'},{label:'启动本机配音服务 (后台)',click:()=>void startLocalVoiceManual()},{label:'停止本机配音服务',click:()=>void stopLocalVoiceManual()},

  {type:'separator'},{label:'鼠标穿透',type:'checkbox',checked:clickthrough,click:toggleClickthrough},
  {label:'找回桌宠 · Ctrl+Shift+H',click:()=>{reset();showPanel();}},
  {label:'退出诗音',click:()=>{quitting=true;app.quit();}}
]).popup({window:pet});}
async function speak(text,token=null,subtitle=text,visual=null,noticeId=null,liveRemark=null){
  preparationAllowed(false);
  const saved=voiceConfig();stopAudio();
  const reference=saved.refAudio?selectVoiceReference(voiceReferences,saved,visual):null;
  const cfg=reference?{...saved,refAudio:reference.audio,promptText:reference.text,promptLang:'ja'}:saved;
  if(!cfg.enabled||cfg.textLang==='ja'&&!japaneseLine(text)){
    if(noticeId)reminderReceipt(noticeId,'audio','skipped');
    if(token&&!bridge.releaseSpeech(token))bridge.notify('audio-end',token);
    return;
  }
  const job=new AbortController(),serial=audioSerial;voiceJob=job;publish();
  let timer,liveSpeechDeadline,releaseLocalVoice;
  if(liveRemark)liveSpeechDeadline=setTimeout(()=>{if(!activePlayback)job.abort();},9000);
  const current=()=>serial===audioSerial&&!job.signal.aborted&&(!token||bridge.matches(token.turn_id,token.generation));
  const sendAudio=value=>pet.webContents.send('sion-event',{...value,token,serial,noticeId});
  let streamed=false,localSynthesis=false;
  if(token)bridge.observe('audio.requested','host',{...token,id:'audio-request:'+serial});
  if(noticeId)reminderReceipt(noticeId,'audio','requested');
  const line=activeLine={text,subtitle,noticeId,token,liveRemark,reference:reference?{name:reference.name,category:reference.category}:null};
  try{
    const local=new URL(cfg.endpoint);
    localSynthesis=['localhost','127.0.0.1','[::1]'].includes(local.hostname)&&local.port==='9880'&&local.pathname==='/tts';
    if(localVoice&&managedVoiceEndpoint(local)){
      line.startingLocal=true;publish();
      try{releaseLocalVoice=await localVoice.acquire(job.signal);}
      finally{line.startingLocal=false;}
      if(!current())return;
      publish();
    }
    timer=setTimeout(()=>job.abort(),120000);
    if(localSynthesis){
      try{
        const spokenLines=text.split(/\r?\n/).map(s=>s.trim()).filter(Boolean);
        const subtitles=subtitle.split(/\r?\n/).map(s=>s.trim()).filter(s=>Boolean(s)&&!/^[（(]\s*(?:心声|内心(?:想法)?)\s*[:：]/.test(s));
        const aligned=spokenLines.length===subtitles.length&&spokenLines.length<=4&&
          (cfg.textLang!=='ja'||spokenLines.every(japaneseLine));
        const lines=aligned?spokenLines.map((line,i)=>({line,caption:subtitles[i]})):[{line:text,caption:subtitle}];
        const runway=new VoiceRunway(performance.now());
        let seconds=0,streamRate,captionEnd=0;
        for(const {line,caption} of lines){
          captionEnd=subtitle.indexOf(caption,captionEnd)+caption.length;
          const visibleChars=Array.from(subtitle.slice(0,captionEnd)).length;
          if(!current())return;
          let firstChunk=true;
          await services.streamVoice(cfg,line,job.signal,({rate,pcm})=>{
            if(!current())return;
            seconds+=pcm.byteLength/(rate*2);
            if(seconds>120||streamRate&&rate!==streamRate)throw Error('流式语音长度或采样率异常');
            if(!streamed){
              streamed=true;streamRate=rate;audioQueued=true;
              sendAudio({type:'pcm-start',rate,reserveSeconds:runway.reserve(performance.now())});
            }
            sendAudio({type:'pcm-chunk',pcm,caption:firstChunk?spokenOnlyText(caption):undefined,visibleChars:firstChunk?visibleChars:undefined});
            if(runway.readyEarly(performance.now(),seconds))sendAudio({type:'pcm-ready'});
            firstChunk=false;
          });
        }
        if(streamed&&current()){
          if(token)bridge.observe('audio.generated','host',{...token,id:'audio-generated:'+serial});
          if(noticeId)reminderReceipt(noticeId,'audio','generated');
          sendAudio({type:'pcm-end'});return;
        }
      }catch(e){if(streamed||job.signal.aborted)throw e;}
    }
    if(!current())return;
    let audio;
    try{
      audio=await services.voice(cfg,text,job.signal);
    }catch(e){
      const sameReference=cfg.refAudio===saved.refAudio&&cfg.promptText===saved.promptText&&cfg.promptLang===saved.promptLang;
      if(sameReference||!current())throw e;
      activeLine.reference=null;
      audio=await services.voice(saved,text,job.signal);
    }
    if(current()){
      if(token)bridge.observe('audio.generated','host',{...token,id:'audio-generated:'+serial});
      if(noticeId)reminderReceipt(noticeId,'audio','generated');
      audioQueued=true;sendAudio({type:'audio',audio,subtitle:spokenOnlyText(subtitle),visibleChars:Array.from(subtitle).length});
    }
  }catch(e){
    if(serial===audioSerial){
      if(noticeId)reminderReceipt(noticeId,'audio','failed');
      if(activeLine){activeLine.noticeId=null;activeLine.token=null;}
      const timedOut=job.signal.aborted;
      stopAudio();
      if(!liveRemark)error=services.voiceFailureMessage(e,{local:localSynthesis,timedOut});
      if(liveRemark&&!line.liveDelivered&&liveWatch?.session)deliverLiveText(liveRemark);
      if(token&&bridge.matches(token.turn_id,token.generation)){
        bridge.observe('audio.failed','host',{...token,id:'audio-failed:'+serial});
        if(bridge.releaseSpeech(token,error))error='';
        else bridge.notify('audio-end',token);
      }
    }
  }
  finally{clearTimeout(timer);clearTimeout(liveSpeechDeadline);releaseLocalVoice?.();if(voiceJob===job)voiceJob=null;publish();}
}
async function chat(text,source){
  liveWatch?.cancel();
  cancelProactive();
  if(source!=='voice')cancelVoiceInput();
  if(source==='voice'){
    if(!voiceSession.enabled)return false;
    if(!pet.isVisible())pet.showInactive();
  }
  preparationAllowed(false);
  bridge?.notify('companion-activity');
  const intent=desktopIntent(text);
  if(intent){
    if(source==='voice'&&!compact.isVisible())showCompact();
    if(bridge.pending||bridge.pendingReply||bridge.speechPending||activePlayback||voiceJob)void bridge.interrupt().catch(()=>{});
    const trace=require('node:crypto').randomUUID();
    bridge.observe('input.accepted',source==='voice'?'voice':'text',{id:'computer-input:'+trace,turn_id:trace,generation:0});
    return computerAssistant.planChat(text.trim(),intent,trace);
  }
  computerAssistant.clearTaskHeart();
  const receiptPending=computerAssistant.receiptPending;
  if(computerAssistant.chatRequest?.phase==='done')computerAssistant.chatRequest=null;
  const session=screenConversation?.session;
  const current=weather?.status();
  const conditions=current?.current&&typeof text==='string'&&/天气|温度|刮风|风大|下雨|下雪|外面|出门|weather|forecast/i.test(text)
    ?{place:current.place,condition:current.current.label,temperature_c:current.current.temperature,wind_kmh:current.current.wind,time:current.current.at}:null;
  const desktop=(await receiptPending)?null:computerAssistant.recentResult();
  const shared=session?{route:session.route,signal:session.controller.signal,capture:signal=>screenConversation.capture(session,signal)}:null;
  const result=await bridge.send(text,shared,conditions,desktop,source==='voice'?'voice':'text');
  const voice=voiceConfig();
  if(localVoice&&voice.enabled&&voice.refAudio&&providers?.enabled()&&URL.canParse(voice.endpoint)&&managedVoiceEndpoint(new URL(voice.endpoint))){
    // Model startup can overlap an accepted dialogue turn.
    void localVoice.acquire(AbortSignal.timeout(115000)).then(release=>release(),()=>{});
  }
  return result;
}

async function action(event,name,data={}){
  const owner=event.sender===panel?.webContents?'panel':event.sender===pet?.webContents?'pet':event.sender===compact?.webContents?'compact':null;
  if(!owner||event.senderFrame!==event.sender.mainFrame)throw new Error('无效窗口');
  if(owner==='pet'&&!['state','drag-start','drag-move','drag-end','click','panel','menu','model-init','control','ack','audio-caption','audio-start','audio-level','audio-end','voice-phase','speech-transcribe'].includes(name))throw new Error('请在聊天面板操作');
  if(owner==='compact'&&!['state','chat','stop','panel','compact-close','ack','voice-session','voice-proactive','screen-share','live-watch','speech-status','computer-execute','computer-discard'].includes(name))throw new Error('请在设置面板操作');
  if(['computer-config','computer-execute','computer-discard'].includes(name)&&!BrowserWindow.fromWebContents(event.sender)?.isVisible())throw new Error('请在可见的聊天或设置窗口中操作');
  switch(name){
    case 'show-heart-voice':{
      if(typeof data.enabled!=='boolean')throw Error('心声开关格式无效');
      store.state.settings.showHeartVoice=data.enabled;if(!data.enabled)computerAssistant.clearTaskHeart();store.save();publish();return data.enabled;
    }
    case 'pet-controls':{
      const settings=validateSettings({petControls:data},store.state.settings);
      store.state.settings.petControls=settings.petControls;
      store.save();publish();return settings.petControls;
    }
    case 'computer-status':return computerAssistant.status();
    case 'weather-search':return weather.search(data.query);
    case 'weather-config':return weather.save(data);
    case 'computer-config':return computerAssistant.save(data);
    case 'computer-connect':await computerAssistant.ensure();return computerAssistant.status();
    case 'computer-capture':return computerAssistant.capture();
    case 'computer-plan':return computerAssistant.plan(data.prompt);
    case 'computer-execute':return computerAssistant.execute(data);
    case 'computer-discard':return computerAssistant.discard(data.id);
    case 'computer-stop':computerAssistant.stop();return computerAssistant.status();
    case 'providers':return providers.public();
    case 'providers-save':{
      stopLiveWatch();screenConversation.stop();
      await bridge.interrupt();
      const previousEmbedding=providers.embeddingRoute()?.model_id;
      const result=providers.save(data);
      if(previousEmbedding!==providers.embeddingRoute()?.model_id)bridge.cancelEmbeddings();
      computerAssistant?.stop();
      await bridge.request('configure',bridge.backendConfig());publish();return result;
    }
    case 'providers-test':return providers.test(data.id);
    case 'speech-status':return speechInput.status();
    case 'speech-config':return speechInput.save(data);
    case 'voice-session':setVoiceSession(data.enabled===true);return true;
    case 'voice-proactive':{
      const enabled=data.enabled===true;
      bridge.presence=await bridge.request('companion-proactive-setting',{enabled});
      if(!enabled){
        cancelProactive();
        if(activeLine?.noticeId?.startsWith('auto:'))stopAudio();
      }
      publish();return true;
    }
    case 'voice-phase':{
      if(owner!=='pet'||!voiceSession.enabled||data.generation!==voiceSession.generation)return false;
      if(data.phase==='failed'){setVoiceSession(false,'麦克风无法开启或已断开，请检查输入设备。');return false;}
      if(data.phase==='device-changed'){
        try{setVoiceSession(true,'正在切换到系统默认麦克风…');}
        catch{setVoiceSession(false,'无法切换麦克风，请检查系统输入和语音设置。');return false;}
        return true;
      }
      if(data.phase==='signal'&&typeof data.available==='boolean'){
        voiceSession.inputSilent=!data.available;
        publish();
        return true;
      }
      if(!['speaking','listening'].includes(data.phase))return false;
      if(data.phase==='speaking'&&data.inputEpoch!==voiceSession.inputEpoch)return false;
      clearTimeout(voiceStartingTimer);
      voiceSession.phase=data.phase;voiceSession.detail='';
      if(data.phase==='speaking'){
        liveWatch?.cancel();
        bridge?.notify('companion-activity');preparationAllowed(false);pauseForVoiceInput(true);
        speechInput.prepareLocal();
      }
      publish();return true;
    }
    case 'speech-transcribe':if(owner!=='pet')throw Error('无效语音来源');return transcribeUtterance(data);
    case 'live-watch':
      if(data.enabled===true){
        if(!BrowserWindow.fromWebContents(event.sender)?.isVisible()||systemSuspended||desktopLocked)
          throw Error('请在可见的聊天窗口开启实时陪伴。');
        liveWatch.start(data.displayId,data.speak===true);
        cancelProactive();
        void liveWatch.tick();
      }else stopLiveWatch();
      publish();return liveWatch.status();
    case 'screen-share':
      stopLiveWatch();
      if(data.enabled===true)screenConversation.enable(data.displayId);
      else screenConversation.stop();
      publish();return screenConversation.status();
    case 'persona':return bridge.request('persona');
    case 'persona-save':{liveWatch?.cancel();computerAssistant.clearTaskHeart();await bridge.interrupt();return bridge.request('persona-save',data);}
    case 'companion-status':return bridge.request('companion-status');
    case 'special-card-open':return owner==='panel'&&panel.isVisible()&&!panel.isMinimized()?bridge.request(name,data):false;
    case 'relationship-set':await bridge.interrupt();
    case 'companion-config':case 'companion-reminder':case 'special-day':case 'companion-read':case 'companion-open-loop':{
      const result=await bridge.request(name,data);
      if(name==='companion-reminder'&&activeLine?.noticeId===data.id&&['done','remove'].includes(data.action))stopAudio();
      bridge.presence=result;publish();return result;
    }
    case 'learning-review':await bridge.interrupt();return bridge.request(name,data);
    case 'state':return state();
    case 'chat':return chat(data.text,owner);
    case 'stop':cancel();return true;
    case 'settings':{
      if(bridge?.pending)throw new Error('请先停止当前请求，再修改连接');
      const next=validateSettings(data,store.state.settings);
      if(data.model||data.mode!==undefined||data.apiKey!==undefined){stopLiveWatch();screenConversation.stop();}
      if(data.apiKey!==undefined)saveKey(data.apiKey);
      if(bridge.pendingReply||bridge.speechPending)await bridge.interrupt();else stopAudio();store.state.settings=next;store.save();bridge.notify('configure',bridge.backendConfig());bridge.notify('controls',{name:'motion',value:next.motion});resizePet();pet.setAlwaysOnTop(next.topmost,'screen-saver');publish();return true;
    }
    case 'clear':liveWatch?.cancel();cancelProactive();cancelVoiceInput();computerAssistant.stop();computerAssistant.chatRequest=null;computerAssistant.lastChatResult=null;await computerAssistant.receiptPending;await bridge.interrupt();store.clear();const session=require('node:crypto').randomUUID();await bridge.request('session',{id:session});fs.writeFileSync(path.join(dataRoot,'companion','host-session.json'),JSON.stringify({session}));bridge.history=[];error='';publish();return true;
    case 'expression':if(!catalog.faces[data.value])throw new Error('未知表情');expression=data.value;bridge.notify('controls',{name:'face',value:data.value});publish();return true;
    case 'panel':showPanel(data.page);return true;
    case 'compact-close':hideCompact();return true;
    case 'reset':reset();return true;
    case 'drag-start':return owner==='pet'&&beginDrag(data);
    case 'drag-move':return owner==='pet'&&moveDrag(data);
    case 'drag-end':return owner==='pet'&&Number.isSafeInteger(data.id)&&endDrag(data);
    case 'click':if(compact.isVisible())hideCompact();else showCompact();return true;
    case 'menu':menu();return true;
    case 'clickthrough':return toggleClickthrough();
    case 'import-image':case 'reset-images':throw new Error('当前使用 Live2D，旧图片槽位已停用');
    case 'voice-test':if(!voiceConfig().enabled)throw new Error('请先启用并保存语音设置');void speak(voiceConfig().textLang==='ja'?'こんにちは。\nここにいるよ。':voiceConfig().textLang==='en'?'Hello.\nI am here.':'你好。\n我在这里。',null,'你好。\n我在这里。');return true;
    case 'model-test':{
      if(bridge?.pending||connectionJob)throw new Error('请先等待当前请求完成');
      const cfg=structuredClone(store.state.settings.model);if(!cfg.baseUrl||!cfg.name)throw new Error('请先填写模型地址和名称并保存');
      const job=new AbortController();connectionJob=job;const started=Date.now(),timer=setTimeout(()=>job.abort(),30000);
      try{const reply=await services.chat(cfg,key(),[{role:'user',content:'请只用一句简短中文确认模型连接成功。'}],job.signal);return {reply,seconds:(Date.now()-started)/1000};}
      finally{clearTimeout(timer);connectionJob=null;}
    }
    case 'mouth-test':stopAudio();emit({type:'mouth-test'});return true;
    case 'model-init':if(owner!=='pet')throw new Error('无效窗口');await bridge.ready;const result=await bridge.request('init',{params:data.params});bridge.notify('controls',{name:'motion',value:store.state.settings.motion});return result;
    case 'control':if(data.name==='press')preparationAllowed(false);bridge.notify('controls',data);return true;
    case 'ack':if(!event.sender.getOwnerBrowserWindow()?.isVisible())return {status:'not_visible'};return bridge.ack(data);
    case 'memory-config':case 'memory-retry':case 'memory-reindex':await bridge.interrupt();return bridge.request(name,data);
    case 'memory-graph':case 'memory-detail':case 'memory-profiles':case 'memory-backups':case 'memory-export':case 'notes-read':case 'notes':case 'memories':case 'recall':case 'memory-status':await bridge.ready;return bridge.request(name,data);
    case 'remember':case 'correct':case 'forget':{if(name!=='remember')computerAssistant?.stop();const r=await bridge.memory(name,data);emit({type:'memory-changed'});return r;}
    case 'memory-action':case 'memory-maintain':case 'memory-backup':case 'memory-restore':case 'memory-import':case 'notes-import':{if(['memory-action','memory-restore','memory-import','notes-import'].includes(name))computerAssistant?.stop();const r=await bridge.memory(name,data);emit({type:'memory-changed'});return r;}
    case 'notes-file':{
      const pick=await dialog.showOpenDialog(panel,{title:'导入资料笔记',properties:['openFile'],filters:[{name:'文字资料',extensions:['txt','md','markdown']}]});if(pick.canceled)return null;
      const file=pick.filePaths[0];if(fs.statSync(file).size>128*1024)throw new Error('单份资料请控制在128KB以内');
      const text=new TextDecoder('utf-8',{fatal:true}).decode(fs.readFileSync(file));if(text.length>32000)throw new Error('资料超过32000字，请分批导入');
      return {title:path.basename(file),text};
    }
    case 'audio-caption':{
      if(owner!=='pet'||data.serial!==audioSerial)return false;
      if(activeLine?.noticeId){
        if(pet.isVisible()&&Number.isInteger(data.visibleChars)&&data.visibleChars>0)reminderReceipt(activeLine.noticeId,'subtitle','shown');
        return true;
      }
      if(!data.token||!bridge.matches(data.token.turn_id,data.token.generation))return false;
      if(pet.isVisible())bridge.observe('caption.displayed','renderer',{...data.token,id:'caption:'+data.serial+':'+data.visibleChars,progress:data.visibleChars});
      bridge.revealSpeech(data.token,data.visibleChars);return true;
    }
    case 'audio-start':case 'audio-level':case 'audio-end':{
      if(owner!=='pet'||data.serial!==audioSerial)return false;
      const token=data.token;if(token&&!bridge.matches(token.turn_id,token.generation))return false;
      if(name==='audio-start'){
        activePlayback=true;audioQueued=false;
        if(activeLine?.liveRemark&&!activeLine.liveDelivered){
          activeLine.liveDelivered=true;
          void bridge.rememberLiveRemark(activeLine.liveRemark).catch(()=>{});
        }
        if(activeLine?.noticeId)reminderReceipt(activeLine.noticeId,'audio','playing');
        if(['speaking','recognizing'].includes(voiceSession.phase))pauseForVoiceInput(true);
      }else if(name==='audio-end'){
        activePlayback=false;audioQueued=false;voicePaused=false;
        if(activeLine)activeLine.token=null;
        if(activeLine?.noticeId){
          reminderReceipt(activeLine.noticeId,'audio',data.completed===true?'finished':'failed');
          activeLine.noticeId=null;
        }
      }
      if(name!=='audio-level')publish();
      if(token){
        if(name==='audio-start')bridge.observe('audio.started','renderer',{...token,id:'audio-start:'+data.serial});
        if(name==='audio-end')bridge.observe(data.completed===true?'audio.finished':'audio.failed','renderer',{...token,id:'audio-end:'+data.serial});
        if(name!=='audio-end'||!bridge.releaseSpeech(token))bridge.notify(name,{...token,duration:data.duration,level:data.level});
      }
      else if(name==='audio-level'||name==='audio-end')bridge.notify('voice-mouth',{level:name==='audio-end'?0:data.level});
      return true;
    }
    case 'quit':quitting=true;app.quit();return true;
    default:throw new Error('未知操作');
  }
}
async function guardedLaunch(){
if(!diagnostic){instanceGuard=await acquireInstance(app.getPath('home'),()=>{computerAssistant?.stop();if(panel){pet.showInactive();showCompact();}});if(!instanceGuard.primary){app.quit();return;}}
if(!app.requestSingleInstanceLock()){app.quit();}else{
  app.on('second-instance',()=>{computerAssistant?.stop();if(panel){pet.showInactive();showCompact();}});
  app.whenReady().then(async()=>{
    try{
      if(bilingualKeyPipe){
        const verifyBilingual=require('../tools/bilingual-check.cjs');
        const localFixture=process.argv.includes('--bilingual-local-fixture');
        const keyPipe=bilingualKeyPipe.slice('--bilingual-key-pipe='.length);
        app.exit(await verifyBilingual({dataRoot,keyPipe,localFixture})?0:1);
        return;
      }
      const fresh=!fs.existsSync(path.join(dataRoot,'state.json'));
      store=new Store(dataRoot);
      providers=new ProviderRouter({dataRoot,safeStorage,legacy:()=>store.state.settings,legacyKey:key});
      if(bilingualCheck){app.exit(await require('../tools/bilingual-check.cjs')({providers,dataRoot})?0:1);return;}
      speechInput=new SpeechInput({dataRoot,backend:backendRoot,providers});
      screenConversation=new ScreenConversation({providers,settings:()=>store.state.settings,getDisplays:()=>screen.getAllDisplays(),getSources:options=>desktopCapturer.getSources(options)});
      weather=new LocalWeather(dataRoot,()=>{bridge?.notify('weather-wind',windFor(weather.status().current));publish();});
      computerAssistant=new ComputerAssistant({dataRoot,backend:backendRoot,python:app.isPackaged?path.join(process.resourcesPath,'desktop-runtime/Scripts/python.exe'):path.join(root,'optional/desktop-runtime/Scripts/python.exe'),providers,changed:publish,recordChatResult:async receipt=>{
        await bridge.recordDesktopReceipt(receipt);
        if(!quitting&&bridge.presence?.proactive_enabled!==false&&!focusQuiet()&&pet?.isVisible()&&
           !compact?.isVisible()&&!panel?.isVisible()){
          pet.webContents.send('sion-event',{type:'bubble',text:receipt.message});
        }
      },
      roleContext:text=>bridge.desktopRoleContext(text),
      generateHeartVoice:(task,role,signal)=>bridge.desktopHeartVoice(task,role,signal),
      heartVoiceEnabled:()=>store.state.settings.showHeartVoice,report:(id,outcome,trace)=>bridge?.observe('tool.'+outcome,'tool',{id:'tool:'+id+':'+outcome,turn_id:trace}),withDesktop:async operation=>{
        if(nativeComputerCheck){const shown=[panel,compact,pet].filter(w=>w&&!w.isDestroyed()&&w.isVisible());for(const w of shown)w.hide();await new Promise(r=>setTimeout(r,250));try{return await operation();}finally{for(const w of shown)if(!w.isDestroyed())w.showInactive();}}
        endDrag();
        const overlays=[pet,compact].filter(w=>w&&!w.isDestroyed()&&w.isVisible());for(const w of overlays)w.setIgnoreMouseEvents(true,{forward:true});try{return await operation();}finally{if(pet&&!pet.isDestroyed())pet.setIgnoreMouseEvents(clickthrough,{forward:true});if(compact&&!compact.isDestroyed())compact.setIgnoreMouseEvents(false);}
      }});
      const effectiveSettings=()=>({...store.state.settings,voice:voiceConfig()});
      bridge=new CompanionBridge({backend:backendRoot,runtime:runtimeRoot,dataRoot,memoryRoot:memoryCheckRoot,config:effectiveSettings,key,stopAudio,speak,publish,providers,shadow:coreShadow});
      liveWatch=new LiveWatch({
        screen:screenConversation,
        canObserve:()=>!quitting&&!systemSuspended&&!desktopLocked&&pet?.isVisible()&&!focusQuiet()&&
          !voiceBusy()&&!drag&&!computerAssistant?.busy&&
          !['planning','ready','running'].includes(computerAssistant?.chatRequest?.phase),
        draft:(session,image,signal)=>bridge.draftLiveRemark(session,image,signal),
        deliver:(remark,session,current)=>{
          if(!current())return;
          const cfg=voiceConfig();
          const spoken=cfg.textLang==='zh'?remark.text:cfg.textLang==='ja'?remark.japanese:'';
          if(session.speak&&cfg.enabled&&cfg.refAudio&&spoken){
            void speak(spoken,null,remark.text,remark.visual,null,remark);
          }else deliverLiveText(remark);
        },
        publish
      });
      bridge.on('graph-changed',()=>{if(panel&&!panel.isDestroyed())panel.webContents.send('sion-event',{type:'memory-graph-changed'});});
      bridge.on('frame',values=>{if(pet&&!pet.isDestroyed()&&pet.isVisible())pet.webContents.send('sion-event',{type:'live2d-frame',values});});
      bridge.on('reply',reply=>emit({type:'reply-ready',reply}));bridge.on('notice',showCompanionNotice);
      bridge.on('touch-feedback',showTouchFeedback);
      await bridge.ready;
      const sessionFile=path.join(dataRoot,'companion','host-session.json');if(fs.existsSync(sessionFile)){const meta=JSON.parse(fs.readFileSync(sessionFile,'utf8'));await bridge.request('session',{id:meta.session});bridge.history=await bridge.request('history');}
      panel=makeWindow('panel.html',{width:1240,height:840,minWidth:880,minHeight:650,title:'诗音 · 桌面伙伴',backgroundColor:'#f6f4ee',autoHideMenuBar:true},true);
      pet=makeWindow('pet.html',{width:330,height:650,frame:false,transparent:true,backgroundColor:'#00000000',alwaysOnTop:store.state.settings.topmost,skipTaskbar:true,focusable:false,resizable:false,hasShadow:false,title:'诗音 · 全身桌宠'});
      compact=makeWindow('compact.html',{width:360,height:260,frame:false,transparent:true,backgroundColor:'#00000000',alwaysOnTop:store.state.settings.topmost,skipTaskbar:true,resizable:false,hasShadow:false,title:'和诗音聊天'},true);
      compact.on('close',e=>{if(!quitting&&!smoke){e.preventDefault();hideCompact();}});compact.webContents.on('did-finish-load',()=>{if(compact.isVisible())compact.webContents.send('sion-event',{type:'compact-focus'});});
      pet.on('move',positionCompact);pet.on('resize',positionCompact);
      resizePet();const position=store.state.settings.position;if(Array.isArray(position)&&position.length===2&&position.every(Number.isFinite))movePetTogether({...pet.getContentBounds(),x:Math.round(position[0]),y:Math.round(position[1])});else{const a=screen.getPrimaryDisplay().workArea;movePetTogether({...pet.getContentBounds(),x:a.x+a.width-pet.getContentBounds().width-20,y:a.y+a.height-pet.getContentBounds().height});}clamp();
      pet.on('show',()=>pet.setAlwaysOnTop(store.state.settings.topmost,'screen-saver'));
      pet.on('show',()=>bridge.notify('render-visible',{visible:true}));
      pet.on('hide',()=>{stopLiveWatch();endDrag();bridge.notify('render-visible',{visible:false});});
      panel.on('close',e=>{if(!quitting&&!smoke){e.preventDefault();panel.hide();}});pet.on('close',e=>{if(!quitting&&!smoke){e.preventDefault();hideCompact();pet.hide();}});pet.on('blur',()=>endDrag());
      ipcMain.handle('sion',action);
      if(!diagnostic){
        const icon=nativeImage.createFromPath(path.join(assetRoot,'tray.png'));tray=new Tray(icon);tray.setToolTip('诗音 · 桌面伙伴');tray.on('double-click',()=>{reset();showCompact();});
        tray.setContextMenu(Menu.buildFromTemplate([{label:'打开聊天',click:showCompact},{label:'查看记忆',click:()=>showPanel('memory')},{label:'连接与设置',click:()=>showPanel('settings')},{type:'separator'},{label:'启动本机配音服务 (后台)',click:()=>void startLocalVoiceManual()},{label:'停止本机配音服务',click:()=>void stopLocalVoiceManual()},{label:'停止麦克风和屏幕共享',click:stopLiveSharing},{label:'找回桌宠 / 取消穿透',click:reset},{type:'separator'},{label:'退出诗音',click:()=>{quitting=true;app.quit();}}]));
        if(!globalShortcut.register('CommandOrControl+Shift+H',()=>{reset();showCompact();})){error='找回快捷键被其他应用占用，请使用托盘菜单';}
        try{
          const bridgeHttp=require('node:http').createServer((req,res)=>{
            if(req.method==='GET'&&req.url==='/v1/status'){res.writeHead(200,{'Content-Type':'application/json; charset=utf-8'});res.end(JSON.stringify({ok:true,petVisible:Boolean(pet&&!pet.isDestroyed()&&pet.isVisible())}));return;}
            if(req.method==='POST'&&req.url==='/v1/say'){
              let raw='';req.on('data',c=>{if(raw.length<32768)raw+=c;});
              req.on('end',()=>{
                try{
                  const payload=JSON.parse(raw||'{}'),text=String(payload.text||'').trim().slice(0,1200);
                  if(!text){res.writeHead(400);res.end('{"ok":false}');return;}
                  if(!quitting&&!focusQuiet()){
                    if(compact&&!compact.isDestroyed()&&compact.isVisible())compact.webContents.send('sion-event',{type:'companion-notice',notice:{kind:payload.kind||'proactive',title:text}});
                    else if(pet&&!pet.isDestroyed()&&pet.isVisible())pet.webContents.send('sion-event',{type:'bubble',text});
                    const cfg=voiceConfig();
                    if(cfg.enabled&&cfg.refAudio&&!voiceBusy())void speak(text,null,text,{emotion:'warm',intensity:.45});
                  }
                  res.writeHead(200,{'Content-Type':'application/json; charset=utf-8'});
                  res.end(JSON.stringify({ok:true,messageId:payload.messageId||''}));
                }catch{res.writeHead(400);res.end('{"ok":false}');}
              });
              return;
            }
            res.writeHead(404);res.end('{}');
          });
          bridgeHttp.on('error',()=>{});
          bridgeHttp.listen(18120,'127.0.0.1');
          app.once('before-quit',()=>{try{bridgeHttp.close();}catch{}});
        }catch{}
      }
      screen.on('display-removed',clamp);screen.on('display-metrics-changed',clamp);
      screen.on('display-removed',(_event,display)=>{if(screenConversation.session?.displayId===display.id){stopLiveWatch();screenConversation.stop();}publish();});
      powerMonitor.on('lock-screen',()=>{desktopLocked=true;stopLiveSharing();});
      powerMonitor.on('unlock-screen',()=>{desktopLocked=false;});
      powerMonitor.on('suspend',suspendDesktop);
      powerMonitor.on('resume',()=>{systemSuspended=false;});
      proactiveTimer=setInterval(()=>{maybeSpeakFirst();void liveWatch.tick();idlePreparation();void weather.tick();},5000);
      if(!diagnostic)void weather.tick();
      if(!(runtimeCheck&&process.argv.includes('--verify-ambient-motion'))){
        cursorTimer=setInterval(()=>{if(!pet||pet.isDestroyed()||!pet.isVisible()||!store.state.settings.motion)return;const point=screen.getCursorScreenPoint(),b=pet.getContentBounds();const limit=n=>Math.max(-1,Math.min(1,n));pet.webContents.send('sion-event',{type:'cursor',pose:drag?{x:0,y:0}:{x:limit((point.x-b.x-b.width*.38)/550),y:limit((point.y-b.y-b.height*.3)/480)}});},66);
      }
      if(smoke)await require(dragCheck?'../tools/drag-only-check.cjs':voiceIntegration?'../tools/voice-integration.cjs':'../tools/live2d-smoke.cjs')({app,panel,pet,compact,store,root:writableRoot,dataRoot,state,action,renderErrors,clamp,movePetTogether,bridge,maybeSpeakFirst,speak,voiceReferences,providers,screenConversation,nativeImage});
      else if(desktopChatCheck)void require('../tools/desktop-chat-smoke.cjs')({app,panel,pet,compact,root:writableRoot,action,computerAssistant,speechInput,voiceSession,bridge});
      else if(nativeComputerCheck)void require('../tools/native-computer-check.cjs')({app,panel,root:writableRoot,action,computerAssistant});
      else if(visionCheck)void require('../tools/vision-check.cjs')({app,pet,providers,screenConversation,root:writableRoot});
      else if(runtimeCheck)void require('../tools/runtime-check.cjs')({app,pet,panel,compact,root:writableRoot,runtimeRoot,action,bridge,backendPid:bridge.child.pid});
      else if(resourceCheck)void require('../tools/resource-profile.cjs')({app,pet,panel,compact,root:writableRoot,action,state,bridge,speechInput});
      else if(liveMemoryCheck)void require('../tools/live-memory-check.cjs')({app,pet,panel,getBridge:()=>bridge,chat,stopAudio,output:path.join(writableRoot,'docs/verification-memory'),restartBridge:async()=>{
        const old=bridge;old.close();if(old.child.exitCode===null)await new Promise((resolve,reject)=>{const t=setTimeout(()=>reject(new Error('原记忆进程未退出')),7000);old.child.once('exit',()=>{clearTimeout(t);resolve();});});
        bridge=new CompanionBridge({backend:backendRoot,runtime:runtimeRoot,dataRoot,memoryRoot:memoryCheckRoot,config:()=>store.state.settings,key,stopAudio,speak,publish,providers});
        bridge.on('frame',values=>{if(pet&&!pet.isDestroyed())pet.webContents.send('sion-event',{type:'live2d-frame',values});});bridge.on('reply',reply=>emit({type:'reply-ready',reply}));bridge.on('notice',showCompanionNotice);bridge.on('touch-feedback',showTouchFeedback);await bridge.ready;
        const params=await pet.webContents.executeJavaScript('(()=>{const p=rig.model.parameters;return p.ids.map((id,i)=>({id,minimum:p.minimumValues[i],maximum:p.maximumValues[i],default:p.defaultValues[i]}));})()');await bridge.request('init',{params});
      }});
      else if(process.argv.includes('--verify-provider'))void verifyProviderConnection();
      else if(process.argv.includes('--panel')){if(panel.webContents.isLoading())panel.webContents.once('did-finish-load',()=>showPanel('companion'));else showPanel('companion');}
      else if(process.argv.includes('--compact')){if(compact.webContents.isLoading())compact.webContents.once('did-finish-load',showCompact);else showCompact();}
    }catch(e){if(smoke){console.error(e);app.exit(1);}else{dialog.showErrorBox('诗音启动失败',e.message+'\n数据保留于：'+dataRoot);app.exit(1);}}
  });
}
}
void guardedLaunch().catch(e=>{dialog.showErrorBox('诗音启动失败',e.message);app.quit();});
app.on('before-quit',()=>{instanceGuard?.close();computerAssistant?.stop();liveWatch?.stop();screenConversation?.stop();weather?.stop();quitting=true;cancelProactive();micAllowed.clear();speechInput?.cancel();clearTimeout(voiceStartingTimer);clearInterval(cursorTimer);clearInterval(proactiveTimer);endDrag();pending?.abort();stopAudio();localVoice?.close();connectionJob?.abort();bridge?.close();});
app.on('will-quit',()=>globalShortcut.unregisterAll());
