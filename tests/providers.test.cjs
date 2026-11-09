const {test}=require('node:test'),assert=require('node:assert/strict'),http=require('node:http'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {ProviderRouter}=require('../src/providers.cjs'),{visualPlan}=require('../src/visual-plan.cjs');
test('task routes, native protocols, usage, encrypted secrets and bounded fallback',async()=>{
 const requests=[],server=http.createServer(async(req,res)=>{let raw='';for await(const b of req)raw+=b;const body=JSON.parse(raw);requests.push({url:req.url,headers:req.headers,body});res.setHeader('Content-Type','application/json');if(req.url.startsWith('/failure')){res.statusCode=503;res.end('{}');}else if(req.url.endsWith('/messages'))res.end(JSON.stringify({content:[{type:'text',text:'{"events":[]}'}],usage:{input_tokens:9,output_tokens:3}}));else if(req.url.includes(':generateContent'))res.end(JSON.stringify({candidates:[{content:{parts:[{text:'{"ids":[]}'}]}}],usageMetadata:{promptTokenCount:7,candidatesTokenCount:2}}));else res.end(JSON.stringify({choices:[{message:{content:'OK'}}]}));});await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'sion-provider-test-')),base='http://127.0.0.1:'+server.address().port,keyMarker='known-synthetic-secret';const storage={isEncryptionAvailable:()=>true,encryptString:s=>Buffer.from(s.split('').reverse().join('')),decryptString:b=>b.toString().split('').reverse().join('')},legacy=()=>({mode:'api',model:{baseUrl:base+'/v1',name:'legacy',timeoutSeconds:5}});
 try{
  const router=new ProviderRouter({dataRoot:dir,safeStorage:storage,legacy,legacyKey:()=>''});const profiles=['openai','anthropic','gemini'].map(protocol=>({id:protocol,label:protocol,protocol,name:'test-model',baseUrl:base+'/'+protocol,timeoutSeconds:5,maxTokens:128,apiKey:keyMarker}));profiles.push({...profiles[0],id:'broken',baseUrl:base+'/failure'});
  router.save({profiles,routes:{dialogue:'broken','memory.extract':'anthropic','memory.rerank':'gemini'},fallbacks:{dialogue:'openai'}});
  assert.ok(!fs.readFileSync(router.file,'utf8').includes(keyMarker));assert.ok(!fs.readFileSync(router.keyFile,'utf8').includes(keyMarker));assert.ok(!JSON.stringify(router.public()).includes(keyMarker));
  assert.equal(await router.chat('dialogue',[{role:'user',content:'hello'}]),'OK');assert.equal(router.public().activity.at(-1).fallback,true);
  const extract=await router.memory({purpose:'memory.extract',events:[]});assert.equal(extract._usage.prompt_tokens,9);const rerank=await router.memory({purpose:'memory.rerank',query:'q',candidates:[]});assert.equal(rerank._usage.completion_tokens,2);
  const claude=requests.find(r=>r.url.endsWith('/messages'));assert.equal(claude.headers['x-api-key'],keyMarker);assert.equal(claude.body.max_tokens,128);assert.ok(claude.body.system.includes('记忆整理器'));
  const gemini=requests.find(r=>r.url.includes(':generateContent'));assert.equal(gemini.headers['x-goog-api-key'],keyMarker);assert.equal(gemini.body.generationConfig.responseMimeType,'application/json');
  const reopened=new ProviderRouter({dataRoot:dir,safeStorage:storage,legacy,legacyKey:()=>''});assert.equal(reopened.resolve('memory.extract').key,keyMarker);
  assert.throws(()=>router.save({profiles,routes:{asr:'openai'}}));assert.throws(()=>router.save({profiles:[{...profiles[0],baseUrl:'http://example.test'}],routes:{}}));
 }finally{server.closeAllConnections();server.close();for(const p of fs.readdirSync(dir))fs.unlinkSync(path.join(dir,p));fs.rmdirSync(dir);}
});
test('invalid visuals cannot select arbitrary parameters, actions or mismatched emotions',()=>{
 assert.equal(visualPlan({expression:'concerned',visual:{face:'angry',intensity:Infinity,action:1000}}).face,'worried');assert.equal(visualPlan({expression:'smile'}).emotion,'warm');assert.equal(visualPlan({visual:{emotion:'joy',face:'laugh',action:18,side:'right',intensity:9}}).intensity,.85);
});

test('DeepSeek memory sends the same text and rules with compact event labels, then restores provenance',async()=>{
 const services=require('../src/services.cjs');
 const config={baseUrl:'https://api.deepseek.com/v1',name:'deepseek-flash'};
 const request={purpose:'memory.extract',guidance:'完整保留用户原意',events:[
  {id:'u:b7582889-645d-4ebc-a8e4-6b0cdba8c34f',text:'我午后常去那间靠窗的咖啡店。',role:'user',knowledge_layer:'shared_experience'},
  {id:'u:c91547fd-c32e-4d72-a151-79b2feffcd6b',text:'我平时会带一本素描本。',role:'user',knowledge_layer:'shared_experience'}
 ]};
 const replies=[];
 const ask=async(_config,_key,messages,_signal,options)=>{
  const sent=JSON.parse(messages[1].content);
  assert.match(messages[0].content,/完整保留用户原意/);
  assert.equal(sent.guidance,request.guidance);
  assert.equal(sent.purpose,request.purpose);
  assert.deepEqual(sent.events.map((row,index)=>({...row,id:request.events[index].id})),request.events);
  assert.deepEqual(sent.events.map(row=>row.id),['e1','e2']);
  replies.push(messages[1].content);
  options.onUsage({prompt_tokens:312,prompt_cache_hit_tokens:160,completion_tokens:24});
  return JSON.stringify({events:sent.events.map(row=>({event_id:row.id,memories:[{quote:row.text,kind:'note'}]}))});
 };
 const result=await services.memory(config,'fixture',request,null,ask);
 assert.deepEqual(result.events.map(x=>x.event_id),request.events.map(x=>x.id));
 assert.deepEqual(result.events.map(x=>x.memories[0].quote),request.events.map(x=>x.text));
 assert.equal(result._usage.deepseek_memory,true);
 assert.equal(Buffer.byteLength(JSON.stringify(request))-Buffer.byteLength(replies[0]),72);
 await assert.rejects(services.memory(config,'fixture',request,null,async()=>JSON.stringify({events:[{event_id:'e9'}]})),/未知来源/);
});

test('non-DeepSeek memory keeps its original request and cannot supply fake cache counts in the generated JSON',async()=>{
 const services=require('../src/services.cjs');
 const request={purpose:'memory.extract',events:[{id:'original',text:'固定来源',role:'user',knowledge_layer:'shared_experience'}]};
 const result=await services.memory({baseUrl:'https://example.test/v1'},'fixture',request,null,async(_c,_k,messages)=>{
  assert.deepEqual(JSON.parse(messages[1].content),request);
  return '{"events":[],"_usage":{"deepseek_memory":true}}';
 });
 assert.deepEqual(result,{events:[]});
});
