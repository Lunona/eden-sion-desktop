const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {DEFAULTS,validateSettings,endpoint,framePath,Store,loadPack,messagesFor}=require('../src/core.cjs');
test('service URL validation allows loopback HTTP and HTTPS, rejects unsafe credentials/schemes',()=>{
  assert.equal(endpoint('http://127.0.0.1:9880/tts'),'http://127.0.0.1:9880/tts');
  for(const url of ['file:///etc/passwd','http://example.com/v1','https://user:pass@example.com','https://example.com/?key=secret'])assert.throws(()=>endpoint(url));
  assert.throws(()=>validateSettings({scale:'NaN'}));assert.throws(()=>validateSettings({mode:'api'}));
  assert.equal(validateSettings({scale:.45}).scale,.45);
  assert.throws(()=>validateSettings({scale:.44}));
  assert.equal(DEFAULTS.voice.enabled,false);assert.equal(validateSettings({topmost:false}).topmost,false);
});
test('missing expression and simultaneous mouth/blink have deterministic fallbacks',()=>{
  const p={expressions:{neutral:{idle:'base'},happy:{idle:'smile',talk:'smile-open'}}};
  assert.equal(framePath(p,'sad',true,true),'base');assert.equal(framePath(p,'happy',true,true),'smile-open');assert.equal(framePath(p,'happy',true,false),'smile');
});
test('store persists 200 messages and clearing removes future model context',()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'sion-test-'));try{
    const s=new Store(dir);for(let i=0;i<205;i++)s.add(i%2?'assistant':'user','message-'+i,'demo');
    const loaded=new Store(dir);assert.equal(loaded.state.messages.length,200);assert.equal(messagesFor(loaded.state.messages).length,13);loaded.clear();assert.equal(new Store(dir).state.messages.length,0);
  }finally{fs.rmSync(dir,{recursive:true,force:true});}
});
test('asset pack paths cannot escape the pack, including traversal',()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'sion-pack-'));try{fs.mkdirSync(path.join(dir,'pack'));fs.writeFileSync(path.join(dir,'outside.png'),'x');fs.writeFileSync(path.join(dir,'pack','character.json'),JSON.stringify({version:1,expressions:{neutral:{idle:'../outside.png'}}}));assert.throws(()=>loadPack(path.join(dir,'pack')),/越出/);}finally{fs.rmSync(dir,{recursive:true,force:true});}
});
