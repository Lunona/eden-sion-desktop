const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {ProviderRouter}=require('../src/providers.cjs');
const profileId=id=>'astrbot_'+crypto.createHash('sha256').update(id).digest('hex').slice(0,16);

function modelProfiles(config){
 const sources=new Map((config.provider_sources||[]).map(item=>[item.id,item]));
 return (config.provider||[]).filter(model=>model.enable!==false).map(model=>{
  const source=sources.get(model.provider_source_id);
  let protocol,name,baseUrl,apiKey,timeoutSeconds;
  if(model.provider_type==='embedding'){
   protocol='embedding';name=model.embedding_model;baseUrl=model.embedding_api_base;apiKey=model.embedding_api_key;timeoutSeconds=model.timeout;
  }else if(model.provider_type==='rerank'){
   protocol='rerank';name=model.rerank_model;baseUrl=new URL(model.rerank_api_suffix||'/v1/rerank',model.rerank_api_base).href;apiKey=model.rerank_api_key;timeoutSeconds=model.timeout;
  }else if(source?.type==='openai_chat_completion'){
   protocol=/(?:^|[\/])[^\/]*embedding/i.test(model.model)?'embedding':'openai';
   name=model.model;baseUrl=source.api_base;apiKey=source.key;timeoutSeconds=source.timeout;
  }else throw Error('存在暂不支持的 AstrBot 模型类型，未写入档案');
  return {id:profileId(model.id),
   label:'AstrBot · '+(source?.id||model.id),protocol,baseUrl,name,
   apiKey:Array.isArray(apiKey)?apiKey.find(key=>typeof key==='string'&&key.trim())||'':apiKey||'',
   timeoutSeconds:timeoutSeconds??45,maxTokens:1200};
 });
}

if(process.versions.electron){
 const {app}=require('electron');
 const arg=name=>process.argv.find(value=>value.startsWith('--'+name+'='))?.slice(name.length+3);
 const source=arg('source'),target=arg('target'),report=arg('report');
 if(!source||!target||!report||!path.isAbsolute(source)||!path.isAbsolute(target)||!path.isAbsolute(report)){
  console.error('请指定源配置、桌宠数据目录和报告路径');app.exit(1);
 }else{
 app.setName('诗音全身桌宠');
 // Safe Storage uses Chromium's per-session-data key on this Windows build.
 // Set the same paths as the desktop runtime before Electron initializes it.
 const sessionData=path.join(target,'session');
 fs.mkdirSync(sessionData,{recursive:true});
 app.setPath('userData',target);
 app.setPath('sessionData',sessionData);
 app.whenReady().then(()=>{
  try{
   const {safeStorage}=require('electron');
   const local=new ProviderRouter({dataRoot:target,safeStorage});
   const readJson=file=>JSON.parse(fs.readFileSync(file,'utf8').replace(/^\uFEFF/,''));
   const config=readJson(source);
   const incoming=modelProfiles(config);
   if(!incoming.length)throw Error('AstrBot 没有启用的模型档案');
   let previous=local.config;
   const repaired=local.keyError===true;
   if(repaired){
    if(!process.argv.includes('--repair-imported-vault'))throw Error('桌宠原有密钥档案无法读取，未导入');
    previous=local.validate(readJson(local.file));
    const imported=new Map(local.validate({profiles:incoming}).profiles.map(profile=>[profile.id,profile]));
    if(previous.profiles.length!==imported.size||previous.profiles.some(profile=>{
     const match=imported.get(profile.id);
     return !match||match.protocol!==profile.protocol||match.name!==profile.name||match.baseUrl!==profile.baseUrl;
    }))throw Error('旧档案含其他模型或地址，无法从 AstrBot 安全重建');
    const backups=path.join(target,'backups');
    fs.mkdirSync(backups,{recursive:true});
    const backup=fs.mkdtempSync(path.join(backups,'astrbot-vault-'));
    fs.copyFileSync(local.keyFile,path.join(backup,path.basename(local.keyFile)));
    fs.copyFileSync(local.file,path.join(backup,path.basename(local.file)));
   }
   const profiles=new Map(previous.profiles.map(profile=>[profile.id,profile]));
   for(const profile of incoming)profiles.set(profile.id,profile);
   const routes={...previous.routes};
   if(process.argv.includes('--match-defaults')){
    const plugin=name=>{
     const file=path.join(path.dirname(source),'config','astrbot_plugin_'+name+'_config.json');
     return fs.existsSync(file)?readJson(file):{};
    };
    const living=plugin('livingmemory'),angel=plugin('angel_memory'),companion=plugin('private_companion');
    const settings=config.provider_settings||{};
    const assignment=companion.model_assignment_config||companion;
    for(const [task,sourceId] of Object.entries({
     dialogue:settings.default_provider_id,
     vision:settings.default_image_caption_provider_id,
     'memory.extract':living.provider_settings?.llm_provider_id||angel.provider_id,
     'memory.rerank':living.recall_engine?.rerank_provider_id||angel.retrieval?.rerank_provider_id,
     computer:assignment.COMPLEX_REASONING_PROVIDER_ID
    })){
     if(routes[task]||typeof sourceId!=='string'||!sourceId)continue;
     const profile=profiles.get(profileId(sourceId));
     if(profile&&(['openai','anthropic','gemini'].includes(profile.protocol)||task==='memory.rerank'&&profile.protocol==='rerank'))routes[task]=profile.id;
    }
    const fast=typeof assignment.FAST_RESPONSE_PROVIDER_ID==='string'&&profiles.get(profileId(assignment.FAST_RESPONSE_PROVIDER_ID));
    if(fast)fast.label+=' · 插件快速响应';
   }
   local.save({...previous,routes,profiles:[...profiles.values()]});
   const verified=new ProviderRouter({dataRoot:target,safeStorage});
   if(verified.keyError)throw Error('桌宠密钥档案导入后读取失败');
   const imported=verified.public().profiles.filter(profile=>incoming.some(item=>item.id===profile.id));
   if(imported.length!==incoming.length)throw Error('档案数量校验失败');
   fs.writeFileSync(report,JSON.stringify({repaired,count:imported.length,profiles:imported.map(({name,protocol,keySaved})=>({name,protocol,keySaved})),routes:verified.config.routes},null,2));
   app.exit(0);
  }catch(error){console.error(error.message);app.exit(1);}
 });
 }
}

module.exports={modelProfiles};
