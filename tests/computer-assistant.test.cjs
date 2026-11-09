const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {ComputerAssistant,validateAction,focused,desktopIntent}=require('../src/computer-assistant.cjs');
const tools=[{name:'Click',description:'click',inputSchema:{type:'object',properties:{loc:{type:'array'},label:{type:'integer'}}}},{name:'Type',description:'type',inputSchema:{properties:{loc:{type:'array'},text:{type:'string'}}}},{name:'App',description:'app',inputSchema:{properties:{mode:{type:'string'},name:{type:'string'}}}},{name:'Shortcut',description:'key',inputSchema:{properties:{shortcut:{type:'string'}}}}];
test('desktop actions exclude shell, stale labels, terminals and system shortcuts',()=>{assert.throws(()=>validateAction('PowerShell',{script:'dir'},tools));assert.throws(()=>validateAction('Click',{label:5},tools));assert.throws(()=>validateAction('App',{mode:'launch',name:'powershell'},tools));assert.throws(()=>validateAction('App',{mode:'launch',name:'notepad;bad'},tools));assert.throws(()=>validateAction('Shortcut',{shortcut:'Win+r'},tools));assert.deepEqual(validateAction('Click',{loc:[50,60]},tools).arguments.loc,[50,60]);assert.equal(focused('Focused Window:\nNotepad\n\nOpened Windows:\n...'),'Notepad');});
test('approval, budget, cancellation and one-use desktop plans without operating a desktop',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'sion-computer-test-'));let calls=0,inputs=0;const providers={revision:'v1',has:()=>true,legacy:()=>({mode:'api'}),chat:async()=>{calls++;await new Promise(r=>setTimeout(r,15));return '{"tool":"Click","arguments":{"loc":[50,60]},"description":"选择测试输入框"}';}};
 const c=new ComputerAssistant({dataRoot:dir,backend:dir,python:process.execPath,providers,withDesktop:fn=>fn()});c.config={enabled:true,daily_calls:2,daily_input_tokens:12000};c.ensure=async()=>{c.tools=tools;};c.request=async(tool)=>{if(tool==='Click')inputs++;return {content:[{type:'text',text:'Focused Window:\nFixture\n\nOpened Windows:\nFixture'}]};};
 try{
  await c.capture();const first=await c.plan('选择测试框');assert.equal(inputs,0);await assert.rejects(()=>c.execute({id:first.id,confirmed:false}));await c.execute({id:first.id,confirmed:true});assert.equal(inputs,1);await assert.rejects(()=>c.execute({id:first.id,confirmed:true}));
  const pending=c.plan('再选择一次');await new Promise(r=>setTimeout(r,1));c.stop();await assert.rejects(()=>pending);assert.equal(c.pending,null);assert.equal(c.snapshot,null);assert.equal(inputs,1);assert.equal(calls,2);
  await c.capture();await assert.rejects(()=>c.plan('额度用尽'),/额度/);assert.equal(calls,2);
  const onDisk=fs.readFileSync(c.file,'utf8');assert.ok(!onDisk.includes('Fixture'));assert.ok(!onDisk.includes('选择测试框'));
  let reads=0;c.snapshot=null;c.appWindow=async mode=>mode==='launch'?{status:'not-found'}:mode==='dispatch'?{status:'unverified'}:
   ++reads<3?[]:[{hwnd:7,pid:2,created:2,image:'C:\\Apps\\notepad.exe',title:'Fixture'}];
  const local=await c.plan('打开记事本');assert.equal(local.local,true);assert.equal(local.arguments.name,'Notepad');assert.equal(calls,2);
  assert.match((await c.execute({id:local.id,confirmed:true})).message,/已经打开/);assert.equal(reads,3);assert.equal(calls,2);
 }finally{c.stop();for(const name of fs.readdirSync(dir))fs.unlinkSync(path.join(dir,name));fs.rmdirSync(dir);}
});
test('spoken process commands stay separate from window commands and ordinary chat',()=>{
 assert.deepEqual(desktopIntent('帮我关闭下qq'),{kind:'quit-qq'});
 assert.deepEqual(desktopIntent('诗音，能不能帮我把 Ｑ Ｑ 关掉？'),{kind:'quit-qq'});
 assert.deepEqual(desktopIntent('帮我关闭 QQ 窗口'),{kind:'close-window',app:'QQ'});
 assert.deepEqual(desktopIntent('能帮我打开微软浏览器吗'),{kind:'launch',app:'微软浏览器'});
 assert.deepEqual(desktopIntent('打开Edge浏览器'),{kind:'launch',app:'Edge浏览器'});
 assert.deepEqual(desktopIntent('帮我关闭记事本然后打开计算器'),{kind:'plan'});
 assert.equal(desktopIntent('别关闭 QQ'),null);
 assert.equal(desktopIntent('你为什么要关闭 QQ'),null);
 assert.deepEqual(desktopIntent('你好，帮我找下电脑里有没有什么好看的图片'),{kind:'plan',localImages:true});
 assert.deepEqual(desktopIntent('你好，打开夸克'),{kind:'launch',app:'夸克'});
 assert.deepEqual(desktopIntent('打开 B 站'),{kind:'launch',app:'B 站'});
 assert.equal(desktopIntent('你好，别打开夸克'),null);
 assert.equal(desktopIntent('你好，帮我找下网上有没有好看的图片'),null);
});
test('app launch uses the same installed target in chat and model-planned steps',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'sion-app-launch-'));
 const reports=[],nativeCalls=[];
 const c=new ComputerAssistant({dataRoot:dir,backend:dir,python:process.execPath,withDesktop:fn=>fn(),
  providers:{revision:'fixture'},report:(_id,outcome)=>reports.push(outcome)});
 c.config.enabled=true;
 let status='confirmed',dispatchCalls=0;
 c.appWindow=async(mode,target)=>{
  nativeCalls.push([mode,target]);
  if(mode==='find-launch')return [{hwnd:1,pid:4,created:1,image:'C:\\Apps\\chrome.exe',title:'哔哩哔哩'}];
  if(mode==='dispatch'){dispatchCalls++;return {status:'submitted'};}
  return {status};
 };
 c.ensure=async()=>{};
 c.request=async(tool)=>{
  assert.equal(tool,'Snapshot');
  return {content:[{type:'text',text:'Focused Window:\nFixture\n\nOpened Windows:\nFixture'}]};
 };
 const confirm=()=>c.execute({id:c.pending.id,confirmed:true});
 const runChat=async()=>{
  const text='打开 B 站';
  await c.planChat(text,desktopIntent(text));
  assert.equal(c.chatRequest.phase,'ready');
  return confirm();
 };
 try{
  await runChat();
  assert.equal(c.recentResult().outcome,'confirmed');
  assert.match(c.recentResult().message,/已经打开/);
  c.snapshot={id:'snapshot',focused:'Fixture'};
  c.setPending({tool:'App',arguments:{mode:'launch',name:'Bilibili'},observationId:'snapshot',focus:'Fixture'});
  assert.match((await confirm()).result,/已经打开/);
  assert.deepEqual(nativeCalls,[['launch','哔哩哔哩'],['launch','哔哩哔哩']]);
  status='already-open';
  await runChat();
  assert.match(c.recentResult().message,/已经开着/);
  status='failed';
  await runChat();
  assert.equal(c.recentResult().outcome,'failed');
  assert.equal(dispatchCalls,0);
  status='not-found';
  await runChat();
  assert.equal(c.recentResult().outcome,'unconfirmed');
  assert.equal(dispatchCalls,1);
  assert.deepEqual(reports.filter(report=>report!=='approved'),['confirmed','confirmed','confirmed','failed','unconfirmed']);
 const text='打开 B 站';
 await c.planChat(text,desktopIntent(text));
 const execution=confirm();
 await new Promise(resolve=>setTimeout(resolve,40));
 c.stop();
 await assert.rejects(execution);
 assert.equal(c.recentResult().outcome,'cancelled');
 assert.equal(reports.at(-1),'cancelled');
 }finally{c.stop();if(fs.existsSync(c.file))fs.unlinkSync(c.file);fs.rmdirSync(dir);}
});
test('desktop chat continues from real tool results and retains persona without exposing it in progress',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'sion-computer-loop-'));
 const context=[],executed=[],rolePrompts=[],hearts=[];
 const c=new ComputerAssistant({dataRoot:dir,backend:dir,python:process.execPath,withDesktop:fn=>fn(),providers:{
  revision:'fixture',has:()=>true,chat:async(_purpose,messages)=>{
   const request=JSON.parse(messages.at(-1).content);
   context.push(request);rolePrompts.push(messages[0].content);
   const next=context.length;
   if(next===3)return JSON.stringify({tool:null,description:'两处我都点好了。'});
   return JSON.stringify({tool:'Click',arguments:{loc:[next,60]},description:'我会点击这里。'});
  }
 }});
 c.config.enabled=true;
 c.config.daily_input_tokens=100000;
 const role={profile:{name:'诗音',speaking_style:['简短、温柔']},history:[],memory:'同一个记忆库'};
 c.roleContext=async()=>role;
 c.heartVoiceEnabled=()=>true;
 c.generateHeartVoice=async(task,context)=>{hearts.push({task,context});return '我想把这点小事做稳妥。';};
 c.ensure=async()=>{c.tools=tools;};
 c.request=async(name,args)=>{
  if(name==='Click'){executed.push(args.loc);return {content:[{type:'text',text:'fixture clicked '+args.loc[0]}]};}
  return {content:[{type:'text',text:'Focused Window:\nFixture\n\nOpened Windows:\nFixture'}]};
 };
 try{
  const command='帮我点击两个测试按钮';
  await c.planChat(command,desktopIntent(command));
  assert.equal(c.chatRequest.phase,'ready');
  assert.equal(c.chatRequest.description,'我会点击这里。');
  assert.deepEqual(executed,[]);
  await c.execute({id:c.pending.id,confirmed:true});
  assert.equal(c.chatRequest.phase,'ready');
  assert.equal(c.chatRequest.steps.length,1);
  assert.match(context[1].history[0].result,/fixture clicked 1/);
  assert.match(rolePrompts[1],/简短、温柔/);
  assert.equal(context[1].reference_memory,'同一个记忆库');
  assert.deepEqual(hearts,[{task:{request:command,action:'Click',phase:'running'},context:role}]);
  await c.execute({id:c.pending.id,confirmed:true});
  assert.deepEqual(executed,[[1,60],[2,60]]);
  assert.equal(c.chatRequest.phase,'done');
  assert.deepEqual(c.recentResult(),{request:command,message:'两处我都点好了。',outcome:'unconfirmed'});
  assert.equal(c.chatRequest.steps.length,2);
  assert.equal(hearts.length,1);
  assert.match(c.status().taskHeartVoice,/稳妥/);
  c.clearTaskHeart();
  assert.equal(c.status().taskHeartVoice,'');
  assert.ok(!JSON.stringify(c.chatRequest).includes('fixture clicked'));
 }finally{c.stop();for(const name of fs.readdirSync(dir))fs.unlinkSync(path.join(dir,name));fs.rmdirSync(dir);}
});
test('worker exceptions and failed tool results stay out of chat receipts',async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'sion-worker-failure-'));
 const receipts=[],reports=[];
 const c=new ComputerAssistant({dataRoot:dir,backend:dir,python:process.execPath,withDesktop:fn=>fn(),
  providers:{revision:'fixture',has:()=>true,chat:async()=>JSON.stringify({tool:'Click',arguments:{loc:[50,60]},description:'选择测试按钮'})},
  report:(_id,outcome)=>reports.push(outcome),recordChatResult:receipt=>receipts.push(receipt)});
 c.config.enabled=true;
 const snapshot={content:[{type:'text',text:'Focused Window:\nFixture\n\nOpened Windows:\nFixture'}]};
 const internal="ToolError: Error calling tool 'App': (-2147220991, '事件无法调用任何订户', (None, None, None, 0, None))";
 let failure={error:internal};
 c.ensure=async()=>{
  c.tools=tools;
  c.child={exitCode:0,stdin:{writable:true,end(){},write(line){
   const {id,tool}=JSON.parse(line);
   c.waiters.get(id).resolve(tool==='Snapshot'?{result:snapshot}:failure);
  }}};
 };
 try{
  const command='帮我点击测试按钮';
  for(const envelope of [{error:internal},{result:{isError:true,content:[{type:'text',text:internal}]}},{}]){
   failure=envelope;
   await c.planChat(command,desktopIntent(command));
   assert.equal(c.chatRequest.phase,'ready');
   await c.execute({id:c.pending.id,confirmed:true});
   await c.receiptPending;
   assert.equal(c.chatRequest.outcome,'failed');
   assert.equal(c.chatTask,null);
   assert.equal(receipts.at(-1).outcome,'failed');
   assert.equal(receipts.at(-1).message,'Windows 没有确认这一步，请先查看目标窗口。');
   assert.doesNotMatch(JSON.stringify(c.chatRequest),/ToolError|2147220991/);
  }
  assert.deepEqual(reports.filter(outcome=>outcome!=='approved'),['failed','failed','failed']);
  assert.equal(c.waiters.size,0);
  assert.deepEqual(await c.request('Snapshot',{}),snapshot);
 }finally{c.stop();if(fs.existsSync(c.file))fs.unlinkSync(c.file);fs.rmdirSync(dir);}
});
