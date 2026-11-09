'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {endpoint,writeJSON}=require('./core.cjs'),services=require('./services.cjs');
const PURPOSES=['dialogue','memory.extract','memory.embedding','memory.rerank','asr','computer','vision'];
function supports(purpose,protocol){
 if(purpose==='memory.embedding'||protocol==='embedding')return purpose==='memory.embedding'&&protocol==='embedding';
 if(protocol==='rerank')return purpose==='memory.rerank';
 return (purpose==='asr')===(protocol==='asr');
}
class ProviderRouter{
 constructor({dataRoot,safeStorage,legacy,legacyKey,publicConfigOnly=false}){
  Object.assign(this,{dataRoot,safeStorage,legacy,legacyKey});this.file=path.join(dataRoot,'providers.json');this.keyFile=path.join(dataRoot,'provider-keys.bin');this.config={version:1,profiles:[],routes:{},fallbacks:{}};this.keys={};this.revision=crypto.randomUUID();this.activity=[];
  try{
   if(!publicConfigOnly&&fs.existsSync(this.keyFile)){
    const vault=JSON.parse(safeStorage.decryptString(fs.readFileSync(this.keyFile)));
    if(vault.config&&vault.keys){this.config=this.validate(vault.config);this.keys=vault.keys;}
    else{this.keys=vault;if(fs.existsSync(this.file))this.config=this.validate(JSON.parse(fs.readFileSync(this.file,'utf8')));}
   }else if(fs.existsSync(this.file))this.config=this.validate(JSON.parse(fs.readFileSync(this.file,'utf8')));
  }catch{this.keys={};this.config={version:1,profiles:[],routes:{},fallbacks:{}};this.keyError=true;this.configError='模型档案暂时无法读取，原文件保留，当前沿用原聊天设置。';}
 }
 validate(input){
  if(!input||!Array.isArray(input.profiles)||input.profiles.length>16)throw Error('模型档案最多16个');
  const seen=new Set(),profiles=input.profiles.map(p=>{
   if(!/^[a-zA-Z0-9_-]{1,48}$/.test(p.id)||seen.has(p.id))throw Error('模型编号无效或重复');seen.add(p.id);
   if(!['openai','anthropic','gemini','asr','embedding','rerank'].includes(p.protocol))throw Error('接口类型无效');
   const baseUrl=endpoint(p.baseUrl),name=String(p.name||'').trim(),label=String(p.label||name).slice(0,60),timeoutSeconds=Number(p.timeoutSeconds??45),maxTokens=Number(p.maxTokens??1200);
   if(!name||name.length>200||!Number.isInteger(maxTokens)||maxTokens<32||maxTokens>8192||!Number.isFinite(timeoutSeconds)||timeoutSeconds<5||timeoutSeconds>180)throw Error('请检查模型名、输出上限和超时');
   return {id:p.id,label,protocol:p.protocol,baseUrl,name,timeoutSeconds,maxTokens};
  });
  const routes={},fallbacks={};for(const purpose of PURPOSES){for(const [source,dest] of [[input.routes||{},routes],[input.fallbacks||{},fallbacks]]){const id=source[purpose]||'';if(id&&!seen.has(id))throw Error('任务引用了不存在的模型');const p=profiles.find(p=>p.id===id);if(p&&!supports(purpose,p.protocol))throw Error('所选模型类型不支持这项任务');dest[purpose]=id;}if(routes[purpose]&&routes[purpose]===fallbacks[purpose])throw Error('备用模型不能与首选相同');}
  if(fallbacks['memory.embedding'])throw Error('不同向量模型的索引需分别建立');
  return {version:1,profiles,routes,fallbacks};
 }
 public(){return {...structuredClone(this.config),profiles:this.config.profiles.map(p=>({...p,keySaved:!!this.keys[p.id]})),keyError:!!this.keyError,configError:this.configError||'',revision:this.revision,activity:this.activity.slice(-12)};}
 has(purpose){return !!this.config.routes[purpose];}
 enabled(){return this.legacy().mode==='api'||['dialogue','memory.extract','memory.rerank'].some(p=>this.has(p));}
 save(input){
  const config=this.validate(input),keys={...this.keys};
  for(const item of input.profiles){if(item.clearKey)delete keys[item.id];else if(item.apiKey!==undefined&&item.apiKey!==''){if(typeof item.apiKey!=='string'||item.apiKey.length>4096)throw Error('密钥格式无效');keys[item.id]=item.apiKey;}}
  for(const id of Object.keys(keys))if(!config.profiles.some(p=>p.id===id))delete keys[id];
  if(this.safeStorage.isEncryptionAvailable()){
   // Configuration and credentials commit together so a crash cannot pair a
   // new vendor's key with an old vendor's address. JSON is only a safe mirror.
   const tmp=this.keyFile+'.tmp';fs.writeFileSync(tmp,this.safeStorage.encryptString(JSON.stringify({config,keys})));fs.renameSync(tmp,this.keyFile);
   try{writeJSON(this.file,config);}catch{this.mirrorError=true;}
  }else{if(Object.keys(keys).length||fs.existsSync(this.keyFile))throw Error('系统加密当前不可用，尚未保存新档案');writeJSON(this.file,config);}
  this.config=config;this.keys=keys;this.keyError=false;this.configError='';this.revision=crypto.randomUUID();return this.public();
 }
 resolve(purpose,id){const selected=id||this.config.routes[purpose];if(!selected)return {config:this.legacy().model,key:this.legacyKey(),label:'原聊天设置',id:'legacy'};const p=this.config.profiles.find(p=>p.id===selected);if(!p)throw Error('所选模型已移除');return {config:p,key:this.keys[p.id]||'',label:p.label,id:p.id};}
 embeddingRoute(){
  if(!this.has('memory.embedding'))return null;
  const {config}=this.resolve('memory.embedding');
  const signature=JSON.stringify([config.id,config.baseUrl,config.name]);
  return {model_id:'api:'+crypto.createHash('sha256').update(signature).digest('hex'),label:config.label,name:config.name};
 }
 async embed(request,signal){
  if(this.embeddingRoute()?.model_id!==request.model_id||!this.has('memory.embedding'))throw Error('向量模型已切换');
  if(typeof request.text!=='string'||!request.text.trim()||request.text.length>32000)throw Error('向量输入超出范围');
  const selected=this.resolve('memory.embedding'),start=Date.now();
  try{
   let usage;
   const vector=await services.embedding(selected.config,selected.key,request.text,signal,value=>{usage=value;});
   this.record('memory.embedding',selected.label,true,Date.now()-start,false,usage);
   return vector;
  }catch(e){this.record('memory.embedding',selected.label,false,Date.now()-start,false);throw e;}
 }
 async chat(purpose,messages,signal,options={}){
  const primary=options.selection||this.resolve(purpose),fallback=options.noFallback?'':this.config.fallbacks[purpose];let used=primary;
  let usage;
  const attempt=async selected=>{
    used=selected;const timer=AbortSignal.timeout(selected.config.timeoutSeconds*1000);
    return services.chat(selected.config,selected.key,messages,signal?AbortSignal.any([signal,timer]):timer,{
      ...options,onUsage:value=>{usage=value;options.onUsage?.(value);}
    });
  };
  const start=Date.now();try{let text;try{text=await attempt(primary);}catch(e){if(!fallback||signal?.aborted||!e.retryable&&e.name!=='TimeoutError')throw e;text=await attempt(this.resolve(purpose,fallback));}if(!options.privateUsage)this.record(purpose,used.label,true,Date.now()-start,used.id!==primary.id,usage);options.onProvider?.(used);return text;}catch(e){if(!options.privateUsage)this.record(purpose,used.label,false,Date.now()-start,false);throw e;}
 }
 record(purpose,label,ok,ms,fallback,usage){
  const entry={purpose,label,ok,ms,fallback,at:new Date().toISOString()};
  if(Number.isInteger(usage?.prompt_tokens)&&Number.isInteger(usage?.completion_tokens)){
    entry.inputTokens=usage.prompt_tokens;entry.outputTokens=usage.completion_tokens;
    const cached=usage.prompt_cache_hit_tokens??usage.prompt_tokens_details?.cached_tokens;
    if(Number.isInteger(cached))entry.cachedTokens=cached;
  }
  this.activity.push(entry);if(this.activity.length>24)this.activity.shift();
 }
 async memory(request,signal){
  if(request.purpose==='memory.rerank'){
   const selected=this.resolve(request.purpose);
   if(selected.config.protocol==='rerank'){
    const timer=AbortSignal.timeout(selected.config.timeoutSeconds*1000);
    const start=Date.now();
    try{
     const result=await services.rerank(selected.config,selected.key,request.query,request.candidates,signal?AbortSignal.any([signal,timer]):timer);
     this.record(request.purpose,selected.label,true,Date.now()-start,false,result._usage);
     return result;
    }catch(e){this.record(request.purpose,selected.label,false,Date.now()-start,false);throw e;}
   }
  }
  const purpose=request.purpose==='memory.reading'?'memory.extract':request.purpose;
  const selection=this.resolve(purpose);
  return services.memory(selection.config,null,request,signal,(_c,_k,m,s,o)=>this.chat(purpose,m,s,{...o,selection,noFallback:true}));
 }
 async test(id){
  const p=this.config.profiles.find(p=>p.id===id);if(!p||p.protocol==='asr')throw Error('请先保存可测试的模型档案');
  const t=Date.now(),r=this.resolve('dialogue',id),signal=AbortSignal.timeout(r.config.timeoutSeconds*1000);
  if(p.protocol==='embedding')await services.embedding(r.config,r.key,'连接测试',signal);
  else if(p.protocol==='rerank')await services.rerank(r.config,r.key,'苹果',[{id:'a',text:'苹果'},{id:'b',text:'火车'}],signal);
  else await services.chat(r.config,r.key,[{role:'user',content:'Reply with OK.'}],signal,{maxTokens:32});
  return {ok:true,label:r.label,milliseconds:Date.now()-t};
 }
}
module.exports={ProviderRouter,PURPOSES};
