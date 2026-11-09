const {test}=require('node:test');const assert=require('node:assert/strict');const http=require('node:http');const {chat,voice}=require('../src/services.cjs');
async function server(fn,run){const s=http.createServer(fn);await new Promise(r=>s.listen(0,'127.0.0.1',r));try{await run(`http://127.0.0.1:${s.address().port}`);}finally{s.closeAllConnections();await new Promise(r=>s.close(r));}}
test('chat adapter sends expected context/auth and returns Unicode text',async()=>{
  await server(async(req,res)=>{let raw='';for await(const chunk of req)raw+=chunk;const b=JSON.parse(raw);assert.equal(req.url,'/v1/chat/completions');assert.equal(req.headers.authorization,'Bearer test-key');assert.equal(b.stream,false);assert.equal(b.messages[0].content,'你好');res.setHeader('Content-Type','application/json');res.end(JSON.stringify({choices:[{message:{content:'我在这里。'}}]}));},async base=>{assert.equal(await chat({baseUrl:base+'/v1',name:'test'},'test-key',[{role:'user',content:'你好'}]),'我在这里。');});
});
test('GPT-SoVITS adapter posts api_v2 fields and accepts only audio WAV',async()=>{
  await server(async(req,res)=>{let raw='';for await(const c of req)raw+=c;const b=JSON.parse(raw);assert.equal(b.text_lang,'ja');assert.equal(b.streaming_mode,false);assert.equal(b.ref_audio_path,'test.wav');const wav=Buffer.alloc(44);wav.write('RIFF');wav.write('WAVE',8);res.setHeader('Content-Type','audio/wav');res.end(wav);},async base=>{const r=await voice({endpoint:base+'/tts',refAudio:'test.wav',textLang:'ja',promptLang:'ja',promptText:'テスト'},'こんにちは');assert.ok(r.startsWith('data:audio/wav;base64,'));});
  await server((_q,res)=>{res.setHeader('Content-Type','application/json');res.end('{}');},async base=>{await assert.rejects(voice({endpoint:base+'/tts',refAudio:'test.wav'},'test'),/WAV/);});
});
test('request failure never exposes service body/secrets; abort cancels waiting',async()=>{
  await server((_q,res)=>{res.writeHead(401);res.end('sensitive debug token');},async base=>{await assert.rejects(chat({baseUrl:base,name:'x'},'',[]),e=>e.message.includes('401')&&!e.message.includes('sensitive'));});
  await server(()=>{},async base=>{const controller=new AbortController();const p=chat({baseUrl:base,name:'x'},'',[],controller.signal);controller.abort();await assert.rejects(p,{name:'AbortError'});});
});

test('synthesis failure separates a stopped local service from a timeout',()=>{
  const {voiceFailureMessage}=require('../src/services.cjs');
  const refused=Object.assign(new Error('refused'),{code:'ECONNREFUSED'});
  const error=new TypeError('fetch failed',{cause:new AggregateError([refused])});
  assert.match(voiceFailureMessage(error,{local:true,timedOut:false}),/启动诗音语音/);
  assert.match(voiceFailureMessage(error,{local:true,timedOut:true}),/120 秒/);
  assert.match(voiceFailureMessage(error,{local:false,timedOut:false}),/fetch failed/);
});
