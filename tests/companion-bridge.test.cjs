const test=require('node:test'),assert=require('node:assert/strict');
const {CompanionBridge,replyText,speechText,requestJapaneseSpeech,messagesFor,renderSourceCitations}=require('../src/companion-bridge.cjs');
const {chat}=require('../src/services.cjs');
test('plain replies keep display text independent of malformed side data',()=>{
 assert.equal(replyText('我在这里。'),'我在这里。');
 assert.equal(replyText('{"text":"我在这里。","speechText":null,"visual":"invalid"}'),'我在这里。');
 assert.throws(()=>replyText('<think>分析</think>你好。'),/未返回可显示/);
 assert.equal(speechText('日语译文：ここにいるよ。'),'ここにいるよ。');
 assert.throws(()=>speechText('我在这里。'),/缺少可用的日文/);
});
test('the independent plain Japanese request retries invalid content once',async()=>{
 const original=global.fetch;
 const config={baseUrl:'https://api.deepseek.com',name:'deepseek-flash'};
 const sent=[];
 global.fetch=async(_url,request)=>{
  sent.push(JSON.parse(request.body));
  return Response.json({choices:[{finish_reason:'stop',message:{content:sent.length===1?'我在这里。':'ここにいるよ。'}}]});
 };
 try{
  const text=await chat(config,'unit-key',[{role:'user',content:'我在这里。'}],undefined,{parseReply:speechText,retryReply:true});
  assert.equal(text,'ここにいるよ。');
  assert.equal(sent.length,2);
  assert.equal(sent[0].response_format,undefined);
  assert.deepEqual(sent[0],sent[1]);
 }finally{global.fetch=original;}
});
for(const protocol of ['anthropic','gemini']){
 test(protocol+' retries one completed invalid translation and accounts for both requests',async()=>{
  const original=global.fetch;
  const config={baseUrl:'http://127.0.0.1:8200',name:'translation-fixture',protocol};
  const sent=[],usage=[];
  const response=(text,finished)=>{
   if(protocol==='anthropic')return {content:[{type:'text',text}],stop_reason:finished?'end_turn':'max_tokens',
    usage:{input_tokens:18,output_tokens:7}};
   return {candidates:[{content:{parts:[{text}]},finishReason:finished?'STOP':'MAX_TOKENS'}],
    usageMetadata:{promptTokenCount:18,candidatesTokenCount:7}};
  };
  global.fetch=async(_url,request)=>{
   sent.push(JSON.parse(request.body));
   return Response.json(response(sent.length===1?'我在这里。':'ここにいるよ。',true));
  };
  try{
   const options={parseReply:speechText,retryReply:true,onUsage:value=>usage.push(value)};
   const messages=[{role:'user',content:'我在这里。'}];
   assert.equal(await chat(config,'unit-key',messages,undefined,options),'ここにいるよ。');
   assert.equal(sent.length,2);
   assert.deepEqual(sent[0],sent[1]);
   assert.equal(usage.length,1);
   assert.equal(usage[0].prompt_tokens,36);
   assert.equal(usage[0].completion_tokens,14);
   let interrupted=0;
   global.fetch=async()=>{interrupted++;return Response.json(response('ここにいるよ。',false));};
   await assert.rejects(chat(config,'unit-key',messages,undefined,options),/未返回可显示/);
   assert.equal(interrupted,1);
  }finally{global.fetch=original;}
 });
}
test('bilingual playback retries a merged translation and accepts harmless wrapping on a single line',async()=>{
 const original=global.fetch;
 const config={baseUrl:'http://127.0.0.1:8200',name:'translation-fixture'};
 const merged='まだ決まっていないよ。七時前にもう一度調べるね。';
 const aligned='まだ決まっていないよ。\n七時前にもう一度調べるね。';
 const source='还没确定。\r\n\r\n七点之前我再查一次。';
 const outputs=[merged,aligned,merged,merged,aligned];
 let calls=0;
 global.fetch=async()=>Response.json({choices:[{finish_reason:'stop',message:{content:outputs[calls++]}}]});
 const ask=(messages,timeout,options)=>chat(config,'',messages,AbortSignal.timeout(timeout),options);
 try{
  assert.equal(await requestJapaneseSpeech(source,ask),aligned);
  assert.equal(calls,2);
  await assert.rejects(requestJapaneseSpeech(source,ask),{code:'provider_bad_response'});
  assert.equal(calls,4);
  assert.equal(await requestJapaneseSpeech('还没确定，七点之前我再查一次。',ask),aligned.replace('\n',' '));
  assert.equal(calls,5);
 }finally{global.fetch=original;}
});
test('body is published before translation, and bad visual data does not prevent Japanese speech',async()=>{
 const b=Object.create(CompanionBridge.prototype);
 const token={turn_id:'test',generation:1};
 const calls=[],events=[];
 let giveTranslation;
 b.current=token;b.jobs=new Map();b.observationRun='test-run';
 b.config=()=>({mode:'api',model:{timeoutSeconds:30},voice:{enabled:true,textLang:'ja'}});
 b.providers={chat:async(purpose,messages,signal,options)=>{
  calls.push({purpose,messages,options,signal});
  if(calls.length===1){options.onProvider({id:'vision-model'});return options.parseReply('这条正文已经完成。');}
  if(options.json)return options.parseReply('表情格式错误');
  return new Promise(resolve=>{giveTranslation=()=>resolve(options.parseReply('この返事はもうできているよ。'));});
 }};
 b.notify=(type,data)=>events.push({type,data});
 b.publish=()=>{};
 b.speak=(audio,token,caption,visual)=>events.push({type:'spoken',audio,caption,visual});
 b.screenTurn={turnId:'test',screen:{route:{id:'vision-model'},signal:new AbortController().signal,capture:async()=> 'data:image/png;base64,YQ=='}};
 const request={...token,text:'告诉我你的想法',profile:{},history:[],memory:{context:''}};
 await b.provide({id:'main',request});
 assert.deepEqual(events[0],{type:'companion-event',data:{kind:'screen.captured',source:'screen',
  turn_id:'test',generation:1,progress:undefined,id:'test-run:screen:main'}});
 assert.equal(events.find(event=>event.type==='provider.complete').data.result.plan.text,'这条正文已经完成。');
 assert.equal(b.speechPending,true);
 assert.equal(calls[0].options.image,'data:image/png;base64,YQ==');
 assert.ok(calls.slice(1).every(call=>!call.options.image&&call.options.selection.id==='vision-model'));
 assert.equal(calls.at(-1).messages.at(-1).content,'这条正文已经完成。');
 b.presentVisual(b.presentation);
 b.presentSpeech(token,'这条正文已经完成。',b.presentation);
 await b.presentation.visual;
 assert.ok(events.some(event=>event.type==='reply-visual'&&event.data.visual.face==='neutral'));
 giveTranslation();
 await b.presentation.speech;
 assert.equal(events.at(-1).audio,'この返事はもうできているよ。');
 assert.equal(events.at(-1).caption,'这条正文已经完成。');
 assert.equal(b.speechPending,false);
});
test('provider failures keep the sanitized cause for the saved turn',async()=>{
 const b=Object.create(CompanionBridge.prototype),events=[];
 b.jobs=new Map();
 b.config=()=>({mode:'api',model:{timeoutSeconds:30},voice:{enabled:false}});
 b.providers={chat:async()=>{throw Object.assign(new Error('服务返回 HTTP 429'),{httpStatus:429});}};
 b.notify=(type,data)=>events.push({type,data});
 await b.provide({id:'limited',request:{text:'你好',profile:{},history:[],memory:{context:''}}});
 assert.deepEqual(events,[{type:'provider.complete',data:{id:'limited',result:{
  error:'服务返回 HTTP 429',code:'provider_rate_limit'}}}]);
});
test('stopping a turn drops pending speech and facial updates',async()=>{
 const b=Object.create(CompanionBridge.prototype),token={turn_id:'old',generation:1};
 let finish;
 const waiting=new Promise(resolve=>{finish=resolve;});
 const p={token,controller:new AbortController(),speech:waiting,visual:waiting};
 b.current=token;b.presentation=p;
 b.speak=()=>assert.fail('old audio played');
 b.notify=()=>assert.fail('old visuals were sent');
 b.presentVisual(p);
 b.presentSpeech(token,'旧回复',p);
 b.cancelPresentation();
 finish('古い返事。');
 await waiting;
 assert.equal(p.controller.signal.aborted,true);
});
test('backend cancellation clears its own pending delivery without exposing a cancelled ready reply',async()=>{
 const b=Object.create(CompanionBridge.prototype);
 const old={turn_id:'old-source',generation:1},next={turn_id:'new-source',generation:2};
 const ready={type:'reply.ready',turn_id:old.turn_id,payload:{generation:1,plan:{text:'旧资料结果'}}};
 const cancelled={type:'turn.interrupted',turn_id:old.turn_id,payload:{generation:1,reason:'notes_imported'}};
 const controller=new AbortController(),replies=[];
 let stops=0;
 b.current=old;b.pending=true;b.pendingReply={...old,text:'等待旧资料'};
 b.presentation={token:old,controller,speechPending:true};
 b.stopAudio=()=>stops++;
 b.publish=()=>{};
 b.request=async()=>[];
 b.emit=(type,value)=>{if(type==='reply')replies.push(value);};
 await b.receive({event:'companion.events',events:[ready,cancelled]});
 assert.deepEqual(replies,[]);
 assert.equal(b.pendingReply,null);
 assert.equal(b.pending,false);
 assert.equal(controller.signal.aborted,true);
 assert.equal(stops,1);
 b.current=next;b.pending=true;
 await b.receive({event:'companion.events',events:[cancelled]});
 assert.deepEqual(b.current,next);
 assert.equal(b.pending,true);
 assert.equal(stops,1);
});
test('a slow expression uses the same fallback for speech and the displayed face',async()=>{
 const b=Object.create(CompanionBridge.prototype);
 const token={turn_id:'late-expression',generation:1};
 let resolveVisual, resolveSpeech;
 const started=new Promise(resolve=>{resolveSpeech=resolve;});
 const shown=[];
 b.current=token;
 b.providers={chat:async(_purpose,_messages,_signal,options)=>options.json
  ?new Promise(resolve=>{resolveVisual=()=>resolve(options.parseReply('{"visual":{"emotion":"joy","face":"happy","action":18}}'));})
  :options.parseReply('今はお約束できないけれど、三時ごろなら大丈夫かもしれません。')};
 b.speak=(_spoken,_token,_text,visual)=>resolveSpeech(visual);
 b.notify=(name,data)=>{if(name==='reply-visual')shown.push(data.visual);};
 b.preparePresentation(token,'现在还不能答应你。也许三点左右可以。',{text:'三点能确定吗？'},{voice:{enabled:true,textLang:'ja'}});
 const presentation=b.presentation;
 b.presentSpeech(token,'现在还不能答应你。也许三点左右可以。',presentation);
 const voiceVisual=await started;
 b.presentVisual(presentation);
 await new Promise(resolve=>setImmediate(resolve));
 const shownBeforeProvider=shown.slice();
 resolveVisual();
 assert.equal((await presentation.visual).emotion,'joy');
 assert.equal(voiceVisual?.emotion,'calm');
 assert.equal(shownBeforeProvider.length,1);
 assert.deepEqual(shown,[voiceVisual]);
});
test('speech-synced bubbles reveal only the spoken prefix and release all text on speech failure',()=>{
 const b=Object.create(CompanionBridge.prototype),token={turn_id:'test',generation:1};
 const events=[];
 b.current=token;b.pendingReply={...token,text:'第一句。\\n第二句。',audioSync:true,visibleChars:0};
 b.presentation={token,visual:Promise.resolve({})};
 b.publish=()=>{};b.notify=(name,data)=>events.push({name,data});
 assert.equal(b.visibleReply,null);
 b.revealSpeech(token,4);
 assert.equal(b.visibleReply.text,'第一句。');
 assert.equal(events[0].data.completed,false);
 b.revealSpeech(token,2);
 assert.equal(b.visibleReply.text,'第一句。');
 assert.equal(b.releaseSpeech(token,'本地合成失败'),true);
 assert.equal(b.visibleReply.text,'第一句。\\n第二句。');
 assert.equal(b.voiceNotice,'本地合成失败');
});
test('only acknowledged history and provenance-marked reference memory enter provider messages',()=>{
 const request={profile:{name:'诗音'},history:[{text:'上一句',reply:'只看到了前半句',status:'interrupted'},{text:'未显示',reply:null,status:'ready'}],memory:{context:'共同经历：喜欢茶'},state:{mood:'calm'},text:'现在的问题'};
 const messages=messagesFor(request,true);assert.match(messages[0].content,/直接输出给用户看的中文正文/);assert.doesNotMatch(messages[0].content,/speechText/);assert.deepEqual(messages.filter(m=>m.role==='assistant'),[{role:'assistant',content:'只看到了前半句'}]);assert.ok(messages.at(-1).content.includes('共同经历'));assert.equal(request.history[1].reply,null);
});
test('document citations are rendered from current source ranges, not generated line numbers',()=>{
 const source={title:'水尺手册',version_id:'current',line_start:5,line_end:6};
 const context=JSON.stringify({memories:[{document_source:source},{reading_interpretation:{
  title:source.title,version_id:source.version_id,anchors:[{line_start:5,line_end:6},{line_start:9,line_end:10}]
 }}]});
 const citations=new Map();
 const messages=messagesFor({profile:{},history:[],memory:{context},text:'手册在哪一行？'},false,false,citations);
 assert.match(messages.at(-1).content,/【原文1】/);
 assert.match(messages.at(-1).content,/【原文2】/);
 assert.equal(citations.size,2);
 assert.equal(renderSourceCitations('周期见【原文1】，处置见【原文2】。',citations),'周期见《水尺手册》第 5–6 行，处置见《水尺手册》第 9–10 行。');
 assert.equal(renderSourceCitations('依据第 500 行【原文99】。',citations),'依据原文相应位置。');
});
test('two visible windows acknowledging the same reply start speech exactly once',async()=>{
 const b=Object.create(CompanionBridge.prototype);let acks=0,speaks=0;b.current={turn_id:'t',generation:1};b.pendingReply={...b.current,text:'你好😀'};b.presentation={token:b.current};b.publish=()=>{};b.presentVisual=()=>speaks++;b.request=async(method,p)=>{await new Promise(r=>setTimeout(r,10));if(method==='ack'){acks++;assert.equal(p.visible_chars,3);return {status:'completed'};}return [];};
 await Promise.all([b.ack(b.current),b.ack(b.current)]);assert.equal(acks,1);assert.equal(speaks,1);assert.equal(b.pendingReply,null);
});
test('a reply superseded while acknowledgement waits cannot start old audio',async()=>{
 const b=Object.create(CompanionBridge.prototype);let speaks=0;b.current={turn_id:'old',generation:1};b.pendingReply={...b.current,text:'迟到'};b.presentation={token:b.current};b.publish=()=>{};b.presentVisual=()=>speaks++;b.request=async()=>{b.current={turn_id:'new',generation:2};return {status:'completed'};};
 await b.ack({turn_id:'old',generation:1});assert.equal(speaks,0);
});

test('ordinary follow-ups receive the last verified desktop receipt and respect the heart voice switch',()=>{
 const request={profile:{name:'诗音'},history:[
  {text:'帮我打开谷歌浏览器',reply:'谷歌浏览器已经打开了。',status:'completed',mode:'desktop:confirmed',created:123},
  {text:'谢谢',reply:'嗯。',status:'completed',mode:'configured_host_model'}],
  memory:{context:'{}'},text:'你做了什么？'};
 const msgs=messagesFor(request,false);
 assert.match(msgs[0].content,/不写心声/);
 const state=JSON.parse(msgs.at(-1).content.split('\n当前消息：')[0]);
 assert.deepEqual(state.recent_desktop_result,{request:'帮我打开谷歌浏览器',message:'谷歌浏览器已经打开了。',outcome:'confirmed',at:123});
 assert.match(messagesFor({...request,showHeartVoice:true},false)[0].content,/角色感受/);
 const {extractPersonaThoughts,withoutHeartVoice,spokenOnlyText}=require('../src/companion-bridge.cjs');
 const raw='（心声：松了口气。）正文保留。\n第二句。';
 assert.equal(extractPersonaThoughts(raw,true).visibleText,raw);
 assert.equal(extractPersonaThoughts(raw,false).visibleText,'正文保留。\n第二句。');
 assert.equal(spokenOnlyText(raw),'正文保留。\n第二句。');
 assert.equal(withoutHeartVoice('（心声：好）\n正文\n    indented code'),'正文\n    indented code');
});
test('a cancelled reply has no separate side effects and factual notes are not forwarded',async()=>{
 const b=Object.create(CompanionBridge.prototype),outgoing=[];
 b.jobs=new Map();
 b.config=()=>({mode:'api',model:{timeoutSeconds:10},voice:{enabled:false}});
 b.notify=(type,data)=>outgoing.push({type,data});
 const deferred=Promise.withResolvers();
 b.providers={chat:()=>deferred.promise};
 const request={purpose:'dialogue',turn_id:'turn',generation:1,profile:{},history:[],memory:{context:'{}'},text:'测试'};
 const pending=b.provide({id:'cancelled',request});
 b.jobs.get('cancelled').abort();
 deferred.resolve('迟到正文。<memory_note>用户住在岛上。</memory_note><secret_thought>迟到心声</secret_thought>');
 await pending;
 assert.deepEqual(outgoing,[]);
 b.providers.chat=async()=> '正常正文。<memory_note>用户住在岛上。</memory_note><secret_thought>今天很开心。</secret_thought>';
 await b.provide({id:'accepted',request});
 assert.deepEqual(outgoing.map(x=>x.type),['provider.complete']);
 assert.equal(outgoing[0].data.result.plan.text,'正常正文。');
 assert.equal(outgoing[0].data.result.notes.secret,'今天很开心。');
 assert.equal(outgoing[0].data.result.notes.memories,undefined);
});
