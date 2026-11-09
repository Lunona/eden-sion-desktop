const {test}=require('node:test'),assert=require('node:assert/strict');
const http=require('node:http');const {chat,chatReply,parseBilingual}=require('../src/services.cjs');
const {validateSettings,messagesFor}=require('../src/core.cjs');
const {replyText}=require('../src/companion-bridge.cjs');
test('bilingual replies separate display text from speech and skip missing translation safely',()=>{
  assert.deepEqual(parseBilingual('```json\n{"reply":"你好。","speech":"こんにちは。"}\n```'),{text:'你好。',speechText:'こんにちは。',speechError:''});
  assert.equal(parseBilingual('{"reply":"你好。"}').speechText,'');assert.ok(parseBilingual('{"reply":"你好。"}').speechError);
  assert.throws(()=>parseBilingual('plain text'));assert.throws(()=>parseBilingual('{"speech":"こんにちは"}'));
  assert.equal(validateSettings({voice:{japaneseSpeech:false}}).voice.japaneseSpeech,false);
  assert.deepEqual(messagesFor([{role:'assistant',content:'你好。',speechText:'こんにちは。'}])[1],{role:'assistant',content:'你好。'});
});
test('one model request produces Chinese display and Japanese speech without mutating history',async()=>{
  let requests=0;const server=http.createServer(async(req,res)=>{requests++;let raw='';for await(const c of req)raw+=c;const body=JSON.parse(raw);assert.ok(body.messages.some(m=>m.role==='system'&&m.content.includes('JSON')));assert.equal(body.messages.at(-1).content,'你好');res.setHeader('Content-Type','application/json');res.end(JSON.stringify({choices:[{message:{content:'{"reply":"我在这里。","speech":"ここにいるよ。"}'}}]}));});
  await new Promise(r=>server.listen(0,'127.0.0.1',r));const history=[{role:'user',content:'你好'}];
  try{const r=await chatReply({baseUrl:`http://127.0.0.1:${server.address().port}/v1`,name:'test'},'',history,undefined,true);assert.equal(r.text,'我在这里。');assert.equal(r.speechText,'ここにいるよ。');assert.equal(requests,1);assert.equal(history.length,1);}finally{server.closeAllConnections();await new Promise(r=>server.close(r));}
});
test('DeepSeek uses exact configured model, quick nonthinking JSON mode and requires key',async()=>{
  await assert.rejects(chat({baseUrl:'https://api.deepseek.com',name:'deepseek-flash'},'',[{role:'user',content:'test'}]),/密钥/);
  const original=global.fetch;global.fetch=async(url,options)=>{const body=JSON.parse(options.body);assert.equal(url,'https://api.deepseek.com/chat/completions');assert.equal(body.model,'deepseek-flash');assert.deepEqual(body.thinking,{type:'disabled'});assert.deepEqual(body.response_format,{type:'json_object'});return new Response(JSON.stringify({choices:[{message:{content:'{"reply":"你好","speech":"こんにちは"}'}}]}),{headers:{'content-type':'application/json'}});};
  try{const r=await chatReply({baseUrl:'https://api.deepseek.com',name:'deepseek-flash'},'fake-unit-key',[],undefined,true);assert.equal(r.speechText,'こんにちは');}finally{global.fetch=original;}
});
test('DeepSeek recovers a blank JSON reply once on the same model with the original image',async()=>{
  const original=global.fetch,bodies=[],usage=[];
  const config={baseUrl:'https://api.deepseek.com',name:'deepseek-flash'};
  const messages=[{role:'system',content:'JSON example: {"text":"hello"}'},{role:'user',content:'hello'}];
  global.fetch=async(url,options)=>{
    assert.equal(url,'https://api.deepseek.com/chat/completions');
    const body=JSON.parse(options.body);bodies.push(body);
    return Response.json({
      choices:[{finish_reason:'stop',message:{content:bodies.length===1?'   ':'{"text":"hello"}'}}],
      usage:{prompt_tokens:10,completion_tokens:3,prompt_cache_hit_tokens:bodies.length===1?0:8}
    });
  };
  try{
    const reply=await chat(config,'test-key',messages,undefined,{json:true,parseReply:replyText,image:'data:image/png;base64,YQ==',onUsage:value=>usage.push(value)});
    assert.equal(reply,'hello');
    assert.equal(bodies.length,2);
    assert.deepEqual(bodies[1],{...bodies[0],response_format:{type:'text'}});
    assert.deepEqual(usage,[{prompt_tokens:20,completion_tokens:6,prompt_cache_hit_tokens:8}]);
    assert.equal(messages[1].content,'hello');
  }finally{global.fetch=original;}
});
test('DeepSeek does not retry a filtered reply or continue recovery after cancellation',async()=>{
  const original=global.fetch,controller=new AbortController();
  let calls=0;
  const config={baseUrl:'https://api.deepseek.com',name:'deepseek-flash'},options={json:true,parseReply:replyText};
  global.fetch=async()=>{calls++;return Response.json({choices:[{finish_reason:'content_filter',message:{content:''}}]});};
  try{
    await assert.rejects(chat(config,'test-key',[],undefined,options),/拦截/);
    assert.equal(calls,1);
    global.fetch=async()=>{
      calls++;
      controller.abort();
      return Response.json({choices:[{finish_reason:'stop',message:{content:' '}}]});
    };
    await assert.rejects(chat(config,'test-key',[],controller.signal,options),{name:'AbortError'});
    assert.equal(calls,2);
  }finally{global.fetch=original;}
});
