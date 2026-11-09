const test=require('node:test');
const assert=require('node:assert/strict');
const {LiveWatch}=require('../src/live-watch.cjs');
const {VoiceRunway}=require('../src/voice-runway.cjs');

test('early audio uses sustained fast delivery and keeps the original reserve for slow streams',()=>{
  const fast=new VoiceRunway(0);
  assert.equal(fast.reserve(300),4);
  assert.equal(fast.readyEarly(300,1.1),false);
  assert.equal(fast.readyEarly(310,2.8),false);
  assert.equal(fast.readyEarly(920,3.1),true);
  assert.equal(fast.readyEarly(950,3.2),false);

  const slow=new VoiceRunway(0);
  assert.equal(slow.reserve(5000),5.5);
  assert.equal(slow.readyEarly(5000,.75),false);
  assert.equal(slow.readyEarly(9300,1.5),false);
  assert.equal(slow.readyEarly(9800,3.9),false);
});

function fixture(){
  let time=0,pixels=0,available=true,delay=null;
  const counts={captures:0,drafts:0,delivered:0};
  const screen={session:null,enable(){this.session={route:{}};},stop(){this.session=null;},async capture(_session,_signal,{acceptFrame}){
    counts.captures++;
    return acceptFrame({resize:()=>({toBitmap:()=>Buffer.alloc(32*18*4,pixels)})})?'data:image/jpeg;base64,AAA=':null;
  }};
  const watch=new LiveWatch({screen,canObserve:()=>available,publish:()=>{},clock:()=>time,
    draft:async()=>{counts.drafts++;return delay?delay.promise:{text:'刚才那一下有意思。',scene:'测试画面'};},
    deliver:async()=>{counts.delivered++;}
  });
  return {watch,screen,counts,set(timeMs,brightness,canObserve=true){time=timeMs;pixels=brightness;available=canObserve;},
    delay(){delay=Promise.withResolvers();return delay.resolve;}};
}

test('live observation is opt-in, bounded, skips static screens and yields to conversation',async()=>{
  const f=fixture();
  await f.watch.tick();
  assert.equal(f.counts.captures,0);
  f.watch.start(1,false);
  await f.watch.tick();
  assert.equal(f.counts.delivered,1);
  f.set(31000,20);
  await f.watch.tick();
  assert.equal(f.counts.captures,1);
  f.set(56000,1);
  await f.watch.tick();
  assert.equal(f.counts.drafts,1);
  f.set(86000,30,false);
  await f.watch.tick();
  assert.equal(f.counts.captures,2);
  f.set(86000,30);
  await f.watch.tick();
  assert.equal(f.counts.drafts,2);
  assert.equal(f.counts.delivered,1);
});

test('closing the live session drops in-flight observations and their results',async()=>{
  const f=fixture();
  f.watch.start(1,true);
  const resolve=f.delay();
  const pending=f.watch.tick();
  await Promise.resolve();
  assert.equal(f.counts.drafts,1);
  f.watch.stop();
  resolve({text:'过时的评论',scene:'测试'});
  await pending;
  assert.equal(f.watch.status().enabled,false);
  assert.equal(f.screen.session,null);
  assert.equal(f.counts.delivered,0);
});
