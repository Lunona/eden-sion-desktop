const {test}=require('node:test');
const assert=require('node:assert/strict');
const {LocalVoiceService,managedVoiceEndpoint}=require('../src/local-voice-service.cjs');

const gib=1024**3;
const signal=()=>new AbortController().signal;

test('an existing local service is reused even under memory pressure and stays external',async()=>{
  const voice=new LocalVoiceService('',{
    probe:async()=>true,freeMemory:()=>2*gib,vram:async()=>200,
    run:async()=>assert.fail('an external service must never be managed')
  });
  (await voice.acquire(signal()))();
  await voice.reclaim();
  voice.close();
  assert.equal(voice.runId,undefined);
});

test('one startup serves concurrent turns and only idle pressure releases the owned service',async()=>{
  let listening=false,ram=8*gib,vram=4000,allowStart;
  const started=new Promise(resolve=>{allowStart=resolve;});
  const calls=[];
  const voice=new LocalVoiceService('',{
    probe:async()=>listening,freeMemory:()=>ram,vram:async()=>vram,
    run:async(operation,id)=>{
      calls.push([operation,id]);
      if(operation==='Start')await started;
      listening=operation==='Start';
    }
  });
  try{
    const first=voice.acquire(signal()),second=voice.acquire(signal());
    allowStart();
    const [releaseFirst,releaseSecond]=await Promise.all([first,second]);
    assert.equal(calls.length,1);
    vram=500;
    await voice.reclaim();
    assert.equal(calls.length,1);
    releaseFirst();releaseSecond();
    vram=4000;
    await voice.reclaim();
    assert.equal(calls.length,1,'normal idle keeps the model loaded');
    vram=500;
    await voice.reclaim();
    assert.deepEqual(calls,[['Start',calls[0][1]],['Stop',calls[0][1]]]);
    assert.equal(voice.runId,null);
    ram=0.8*gib;
    await assert.rejects(voice.acquire(signal()),/内存不足/);
    assert.equal(calls.length,2);
  }finally{voice.close();}
});

test('cancelling a waiting turn leaves one startup for the next turn',async()=>{
  let listening=false,allowStart;
  const started=new Promise(resolve=>{allowStart=resolve;});
  const operations=[];
  const voice=new LocalVoiceService('',{
    probe:async()=>listening,freeMemory:()=>8*gib,vram:async()=>4000,
    run:async operation=>{
      operations.push(operation);
      if(operation==='Start')await started;
      listening=operation==='Start';
    }
  });
  const controller=new AbortController();
  try{
    const old=voice.acquire(controller.signal);
    const next=voice.acquire(signal());
    await new Promise(resolve=>setImmediate(resolve));
    controller.abort();
    await assert.rejects(old,{name:'AbortError'});
    allowStart();
    (await next)();
    assert.deepEqual(operations,['Start']);
    await voice.retire();
    assert.deepEqual(operations,['Start','Stop']);
  }finally{voice.close();}
});

test('automatic service management applies only to the known local endpoint',()=>{
  assert.equal(managedVoiceEndpoint(new URL('http://127.0.0.1:9880/tts')),true);
  assert.equal(managedVoiceEndpoint(new URL('http://localhost:9880/tts')),true);
  assert.equal(managedVoiceEndpoint(new URL('https://example.org:9880/tts')),false);
  assert.equal(managedVoiceEndpoint(new URL('http://127.0.0.1:9890/tts')),false);
});

test('slow cold startup keeps one model loader and an exited loader fails promptly',async()=>{
  let elapsed=0,exited=false;
  const operations=[];
  const voice=new LocalVoiceService('',{
    probe:async()=>!exited&&elapsed>=16800,alive:async()=>!exited,
    clock:()=>elapsed,pause:async ms=>{elapsed+=ms;},
    freeMemory:()=>8*gib,vram:async()=>4000,run:async operation=>{operations.push(operation);}
  });
  try{
    (await voice.acquire(signal()))();
    assert.deepEqual(operations,['Start']);
    await voice.retire();
    elapsed=0;exited=true;
    await assert.rejects(voice.startManual(),/进程.*退出/);
    assert.equal(elapsed,0);
    assert.equal(voice.status().starting,false);
    assert.deepEqual(operations,['Start','Stop','Start','Stop']);
  }finally{voice.close();}
});

test('stopping during model load settles startup and permits a clean restart',async()=>{
  const operations=[];
  let entered;
  const loading=new Promise(resolve=>{entered=resolve;});
  let listening=false;
  const voice=new LocalVoiceService('',{
    probe:async()=>listening,alive:async()=>true,
    freeMemory:()=>8*gib,vram:async()=>4000,
    run:async operation=>{operations.push(operation);if(operation==='Start')entered();},
  });
  try{
    const start=voice.startManual();
    const cancelled=assert.rejects(start,/取消/);
    await loading;
    await voice.stopManual();
    await cancelled;
    assert.deepEqual(operations,['Start','Stop']);
    assert.equal(voice.status().starting,false);
    listening=true;
    assert.equal(await voice.startManual(),true);
  }finally{voice.close();}
});
