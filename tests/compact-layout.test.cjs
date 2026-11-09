const {test}=require('node:test'),assert=require('node:assert/strict');const {placeCompact}=require('../src/compact-layout.cjs');
test('chat stays directly below pet and inside the working area at all four corners and desktop scales',()=>{
  for(const area of [{x:0,y:0,width:1706,height:1018},{x:-1920,y:0,width:1920,height:1040},{x:0,y:-720,width:1280,height:680}])
  for(const scale of [.45,.65,1,1.4])for(const x of [area.x-20,area.x+area.width-100])for(const y of [area.y-100,area.y+area.height-50]){
    const p={x,y,width:Math.round(330*scale),height:Math.round(650*scale)},out=placeCompact(p,area);
    for(const box of [out.pet,out.chat]){assert.ok(box.x>=area.x);assert.ok(box.y>=area.y);assert.ok(box.x+box.width<=area.x+area.width);assert.ok(box.y+box.height<=area.y+area.height);}
    assert.ok(out.chat.y>=out.pet.y+out.pet.height);assert.ok(Math.abs(out.pet.width/out.pet.height-p.width/p.height)<.005);
  }
});
test('opening chat keeps the figure size when there is enough room',()=>{
  const p={x:100,y:50,width:330,height:650},r=placeCompact(p,{x:0,y:0,width:1920,height:1080});assert.deepEqual(r.pet,p);assert.equal(r.chat.y,706);
});
