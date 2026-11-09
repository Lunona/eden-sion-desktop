const test=require('node:test');
const assert=require('node:assert/strict');
const {ScreenConversation}=require('../src/live-companion.cjs');
const {CompanionBridge}=require('../src/companion-bridge.cjs');

const display={id:7,size:{width:1600,height:1000}};
function setup(getSources){
  const conversation=new ScreenConversation({getDisplays:()=>[display],getSources});
  const session=conversation.session={displayId:7,controller:new AbortController()};
  return {conversation,session};
}
function screenshot(toJPEG){
  return [{display_id:'7',thumbnail:{isEmpty:()=>false,toJPEG}}];
}

test('closing screen sharing immediately rejects a capture and discards its late frame',async()=>{
  const deferred=Promise.withResolvers();
  let calls=0;
  const {conversation,session}=setup(()=>{
    if(++calls===1)return deferred.promise;
    return Promise.resolve(screenshot(()=>Buffer.from('new')));
  });
  const waiting=conversation.capture(session);
  conversation.stop();
  await assert.rejects(waiting,/屏幕共享已关闭/);
  deferred.resolve(screenshot(()=>assert.fail('late image encoded')));
  await deferred.promise;
  const replacement={displayId:7,controller:new AbortController()};
  assert.equal(await conversation.capture(replacement),'data:image/jpeg;base64,bmV3');
});

test('a screenshot deadline fails promptly and keeps a stuck native request from accumulating',async t=>{
  const deadline=new AbortController(),deferred=Promise.withResolvers();
  t.mock.method(AbortSignal,'timeout',()=>deadline.signal);
  let calls=0;
  const {conversation,session}=setup(()=>{calls++;return deferred.promise;});
  const waiting=conversation.capture(session);
  deadline.abort(new DOMException('', 'TimeoutError'));
  await assert.rejects(waiting,/屏幕截图等待超时/);
  const secondDeadline=new AbortController();
  AbortSignal.timeout.mock.mockImplementation(()=>secondDeadline.signal);
  await assert.rejects(conversation.capture(session),/上一次截图仍在等待/);
  assert.equal(calls,1);
  deferred.resolve(screenshot(()=>assert.fail('expired image encoded')));
  await deferred.promise;
});

test('stopping a chat while its screenshot is pending never sends an image or a stale error',async()=>{
  const deferred=Promise.withResolvers();
  const {conversation,session}=setup(()=>deferred.promise);
  const bridge=Object.create(CompanionBridge.prototype);
  bridge.jobs=new Map();
  bridge.config=()=>({mode:'api',model:{timeoutSeconds:30},voice:{enabled:false}});
  bridge.screenTurn={turnId:'current',screen:{route:{id:'vision'},signal:session.controller.signal,
    capture:signal=>conversation.capture(session,signal)}};
  bridge.providers={chat:()=>assert.fail('cancelled image sent')};
  bridge.notify=()=>assert.fail('cancelled turn reported a failure');
  const pending=bridge.provide({id:'turn',request:{turn_id:'current',text:'看看画面'}});
  bridge.jobs.get('turn').abort();
  await pending;
  deferred.resolve(screenshot(()=>assert.fail('cancelled image encoded')));
  await deferred.promise;
});
