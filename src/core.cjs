const fs = require('node:fs');
const path = require('node:path');
const { randomUUID } = require('node:crypto');
const EXPRESSIONS = ['neutral', 'happy', 'sad', 'thinking'];
const FRAMES = ['idle', 'blink', 'talk', 'talkBlink'];
const DEFAULTS = {
  mode: 'demo', topmost: true, motion: true, scale: 1, showHeartVoice: false,
  model: {baseUrl: '', name: '', timeoutSeconds: 60},
  voice: {enabled: false, japaneseSpeech:true, emotionalReferences:true, endpoint: 'http://127.0.0.1:9880/tts', textLang: 'ja', promptLang: 'ja', refAudio: '', promptText: ''},
  petControls: {chatButton: true, touch: true},
  position: null
};
const SYSTEM = '你扮演《eden*》的诗音（Sion），作为用户的桌面伙伴。用中文简短、平静地回应，带一点好奇和温柔。不声称你是原作官方角色或能读取用户屏幕。不要编造原作剧情与长期记忆；不知道的事情坦诚说明。';
function endpoint(value) {
  const u = new URL(value);
  if (u.username || u.password || u.hash || u.search) throw new Error('服务地址不能包含密码、查询参数或片段');
  const local = ['127.0.0.1', 'localhost', '[::1]'].includes(u.hostname);
  if (u.protocol !== 'https:' && !(u.protocol === 'http:' && local)) throw new Error('服务地址须使用 HTTPS；本机服务可用 HTTP');
  return u.toString().replace(/\/$/, '');
}
function validateSettings(input, previous = DEFAULTS) {
  const c = structuredClone(previous);
  if (input.mode !== undefined) { if (!['demo','api'].includes(input.mode)) throw new Error('未知聊天模式'); c.mode = input.mode; }
  for (const k of ['topmost','motion']) if (input[k] !== undefined) c[k] = !!input[k];
  if (input.showHeartVoice !== undefined) {
    if (typeof input.showHeartVoice !== 'boolean') throw new Error('心声开关格式无效');
    c.showHeartVoice = input.showHeartVoice;
  }
  if (input.scale !== undefined) { const n = Number(input.scale); if (!Number.isFinite(n) || n < .45 || n > 1.4) throw new Error('尺寸范围为45%–140%'); c.scale = n; }
  if (input.model) {
    const m = input.model;
    if (m.baseUrl !== undefined) c.model.baseUrl = m.baseUrl.trim() ? endpoint(m.baseUrl.trim()) : '';
    if (m.name !== undefined) c.model.name = String(m.name).trim().slice(0,200);
    if (m.timeoutSeconds !== undefined) { const n=Number(m.timeoutSeconds); if(!Number.isFinite(n)||n<5||n>180) throw new Error('超时范围5–180秒'); c.model.timeoutSeconds=n; }
  }
  if (input.voice) {
    const v=input.voice;
    if(v.endpoint !== undefined) c.voice.endpoint=endpoint(v.endpoint.trim());
    if(v.enabled !== undefined) c.voice.enabled=!!v.enabled;
    if(v.japaneseSpeech !== undefined) c.voice.japaneseSpeech=!!v.japaneseSpeech;
    if(v.emotionalReferences !== undefined) c.voice.emotionalReferences=!!v.emotionalReferences;
    for(const k of ['refAudio','promptText']) if(v[k] !== undefined) c.voice[k]=String(v[k]).trim().slice(0,4000);
    for(const k of ['textLang','promptLang']) if(v[k] !== undefined) {if(!['ja','zh','en','auto'].includes(v[k])) throw new Error('未知语音语言'); c.voice[k]=v[k];}
  }
  if(input.petControls!==undefined){
    const {chatButton,touch}=input.petControls||{};
    if(typeof chatButton!=='boolean'||typeof touch!=='boolean')throw Error('角色互动设置无效');
    c.petControls={chatButton,touch};
  }
  if(c.mode==='api' && (!c.model.baseUrl || !c.model.name)) throw new Error('请填写模型服务地址和模型名称');
  if(c.voice.enabled && !c.voice.refAudio) throw new Error('请填写服务端可读的参考音频路径');
  return c;
}
function writeJSON(file, data) {
  fs.mkdirSync(path.dirname(file), {recursive:true});
  const temp = file + '.tmp'; fs.writeFileSync(temp, JSON.stringify(data,null,2)); fs.renameSync(temp,file);
}
class Store {
  constructor(root) {
    this.root=root; this.file=path.join(root,'state.json');
    this.state={settings:structuredClone(DEFAULTS),messages:[],overrides:{}};
    if(fs.existsSync(this.file)) {
      // Preserve malformed data for recovery; do not silently overwrite it.
      const s=JSON.parse(fs.readFileSync(this.file,'utf8'));
      this.state.settings=validateSettings(s.settings||{});
      this.state.settings.position=s.settings?.position||null;
      this.state.messages=Array.isArray(s.messages)?s.messages.filter(m=>['user','assistant'].includes(m.role)&&typeof m.content==='string').slice(-200):[];
      this.state.overrides=s.overrides||{};
    }
  }
  save(){writeJSON(this.file,this.state);}
  add(role,content,source,speechText=''){this.state.messages.push({id:randomUUID(),role,content,source,...(speechText?{speechText}:{}),time:new Date().toISOString()}); this.state.messages=this.state.messages.slice(-200);this.save();}
  clear(){this.state.messages=[];this.save();}
}
// Future long-term memory adapter. No automatic extraction or disk retrieval yet.
class NullMemory { async retrieve(_text){return [];} async observe(_turn){} }
function messagesFor(history, memories=[]) {
  return [{role:'system',content:SYSTEM+(memories.length?'\n用户确认的记忆：\n'+memories.join('\n'):'')},...history.slice(-12).map(({role,content})=>({role,content}))];
}
function framePath(pack, expression, blink, talk) {
  const e=pack.expressions[expression]||pack.expressions.neutral;
  const key=talk?(blink?'talkBlink':'talk'):(blink?'blink':'idle');
  return e[key]||e[talk?'talk':'idle']||e.idle||pack.expressions.neutral.idle;
}
function inside(root, file) {const rel=path.relative(root,file); return !!rel && !rel.startsWith('..'+path.sep) && rel!=='..' && !path.isAbsolute(rel);}
function loadPack(root, inspect) {
  root=fs.realpathSync(root);
  const manifest=JSON.parse(fs.readFileSync(path.join(root,'character.json'),'utf8'));
  if(manifest.version!==1||!manifest.expressions?.neutral?.idle) throw new Error('资源包须含version:1和neutral.idle');
  const out={version:1,name:String(manifest.name||'诗音').slice(0,100),placeholder:manifest.placeholder===true,expressions:{}};
  for(const e of EXPRESSIONS) {
    if(!manifest.expressions[e]) continue;
    out.expressions[e]={};
    for(const f of FRAMES) {
      const rel=manifest.expressions[e][f]; if(!rel) continue;
      if(typeof rel!=='string'||path.extname(rel).toLowerCase()!=='.png') throw new Error('资源只支持PNG');
      const target=fs.realpathSync(path.resolve(root,rel));
      if(!inside(root,target)) throw new Error('资源路径不能越出资源包目录');
      const stat=fs.statSync(target); if(!stat.isFile()||stat.size>32*1024*1024) throw new Error('单张PNG须小于32MB');
      if(inspect) inspect(target);
      out.expressions[e][f]=target;
    }
  }
  return out;
}
module.exports={DEFAULTS,EXPRESSIONS,FRAMES,Store,NullMemory,validateSettings,endpoint,messagesFor,framePath,loadPack,writeJSON};
