const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

function pet(zone,touch=true){
  const handlers=new Map(),timers=new Map(),calls=[];
  let timerId=0,subscription;
  const node={append(){},setAttribute(){},addEventListener(){}};
  const canvas={...node,addEventListener(name,callback){handlers.set(name,callback);},
    setPointerCapture(){},hasPointerCapture(){return false;},getBoundingClientRect(){return {left:0,top:0,width:100,height:100};}};
  const window={addEventListener(){},sion:{subscribe(callback){subscription=callback;},invoke(name,details){
    if(name==='control'&&details.name!=='pointer')calls.push(details.name);
    if(['click','drag-start','drag-end'].includes(name))calls.push(name);
    return Promise.resolve(name==='state'?{assets:{}}:true);
  }}};
  const context=vm.createContext({window,document:{addEventListener(){},createElement:()=>({...node}),body:node,
    getElementById:id=>id==='sprite'?canvas:{...node}},performance:{now:()=>100},zone,touch,
    setTimeout(callback){timers.set(++timerId,callback);return timerId;},clearTimeout:id=>timers.delete(id)});
  const source=fs.readFileSync(path.join(__dirname,'../src/pet.js'),'utf8');
  vm.runInContext(source,context);
  vm.runInContext('rig={ready:true,zone:()=>zone,sourcePoint:()=>[1882,1000]};state={settings:{petControls:{touch}}}',context);
  const fire=(name,extra={})=>handlers.get(name)({button:0,buttons:1,isPrimary:true,pointerId:1,screenX:100,screenY:100,
    clientX:50,clientY:50,...extra});
  const expire=()=>{for(const [id,callback] of [...timers]){timers.delete(id);callback();}};
  return {fire,expire,calls,hostEvent:event=>subscription(event),chat:()=>vm.runInContext('chatButton.onclick()',context)};
}

test('tapping touches the character and only the side button opens chat',()=>{
  const p=pet('head');
  p.fire('pointerdown');p.fire('pointerup');p.expire();
  assert.deepEqual(p.calls,['press','release']);
  p.chat();
  assert.deepEqual(p.calls,['press','release','click']);
});

test('holding and Shift dragging interact while ordinary dragging moves the window',()=>{
  const hold=pet('head');
  hold.fire('pointerdown');hold.expire();hold.fire('pointerup');
  assert.deepEqual(hold.calls,['press','release']);
  const drag=pet('hairL');
  drag.fire('pointerdown',{shiftKey:true});drag.fire('pointermove',{screenX:112});drag.fire('pointerup');drag.expire();
  assert.deepEqual(drag.calls,['press','move','release']);
  const move=pet('hairL');
  move.fire('pointerdown');move.fire('pointermove',{screenX:112});move.fire('pointerup');
  assert.deepEqual(move.calls,['drag-start','drag-end']);
});

test('body and Alt dragging stay separate from chat and canceled taps do nothing',()=>{
  const body=pet('cloth');
  body.fire('pointerdown');body.fire('pointermove',{screenX:112});body.fire('pointerup');body.expire();
  assert.deepEqual(body.calls,['drag-start','drag-end']);
  const alt=pet('head');
  alt.fire('pointerdown',{altKey:true});alt.fire('lostpointercapture');alt.expire();
  assert.deepEqual(alt.calls,['drag-start','drag-end']);
  const canceled=pet('head');
  canceled.fire('pointerdown');canceled.fire('pointercancel');canceled.expire();
  assert.deepEqual(canceled.calls,[]);
});

test('touch preference disables taps and holds independently of chat and moving',()=>{
  const p=pet('head',false);
  p.fire('pointerdown');p.expire();p.fire('pointerup');
  p.fire('pointerdown',{shiftKey:true});p.fire('pointermove',{screenX:112});p.fire('pointerup');
  p.chat();
  assert.deepEqual(p.calls,['drag-start','drag-end','click']);
});

test('host cancellation and a lost mouse release allow the next drag',()=>{
  const p=pet('head');
  p.fire('pointerdown');p.fire('pointermove',{screenX:112});
  p.hostEvent({type:'drag-cancelled',id:1});
  p.fire('pointerdown');p.fire('pointermove',{screenX:112});
  p.fire('pointermove',{buttons:0});
  p.fire('pointerdown');p.fire('pointermove',{screenX:112});p.fire('pointerup');
  assert.deepEqual(p.calls,['drag-start','drag-end','drag-start','drag-end','drag-start','drag-end']);
});
