const {test}=require('node:test');
const assert=require('node:assert/strict');
const os=require('node:os');
const {SpeechInput}=require('../src/speech-input.cjs');

test('low memory skips Whisper startup and still allows an existing worker',async t=>{
  t.mock.method(os,'freemem',()=>0.5*1024**3);
  const speech=Object.assign(Object.create(SpeechInput.prototype),{
    config:{mode:'local',language:'ja'},serial:0,child:null,waiters:new Map(),
    status:()=>({localAvailable:true})
  });
  const signal=new AbortController().signal;
  speech.prepareLocal();
  assert.equal(speech.child,null);
  await assert.rejects(speech.local('fixture.wav',signal),/可用内存不足/);
  assert.equal(speech.waiters.size,0);
  speech.child={stdin:{write(line){
    const request=JSON.parse(line);
    assert.equal(request.language,'ja');
    const waiter=speech.waiters.get(request.id);
    speech.waiters.delete(request.id);
    waiter.resolve({text:'テストです'});
  }}};
  try{
    assert.deepEqual(await speech.local('fixture.wav',signal),{text:'テストです'});
  }finally{clearTimeout(speech.idle);}
});
