(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.RigMath=api;})(typeof window==='object'?window:globalThis,function(){
  const clamp=(v,min,max)=>Math.max(min,Math.min(max,v));
  const defaults={headX:0,headY:0,headZ:0,gazeX:0,gazeY:0,eyeOpen:1,mouthOpen:0,body:0,hair:0};
  function normalized(input){const p={};for(const [key,value] of Object.entries(defaults)){const n=Number(input[key]??value);p[key]=Number.isFinite(n)?clamp(n,key==='eyeOpen'||key==='mouthOpen'?0:-1,1):value;}return p;}
  function headMatrix(input){const p=normalized(input),z=p.headZ*.105,scale=1-Math.abs(p.headX)*.035,c=Math.cos(z),s=Math.sin(z);return {a:c*scale,b:s*scale,c:-s+p.headX*.015,d:c,e:543+p.headX*16,f:580+p.headY*10};}
  function applyHead(point,input){const m=headMatrix(input),x=point[0]-543,y=point[1]-580;return [m.a*x+m.c*y+m.e,m.b*x+m.d*y+m.f];}
  function smooth(current,target,dt){const next={};const weight=1-Math.exp(-Math.min(.1,Math.max(0,dt))*7);for(const key of Object.keys(defaults))next[key]=current[key]+(target[key]-current[key])*weight;return next;}
  function spring(state,target,dt){dt=Math.min(.04,Math.max(0,dt));const acceleration=(target-state.value)*32-state.velocity*9;return {velocity:state.velocity+acceleration*dt,value:state.value+(state.velocity+acceleration*dt)*dt};}
  function gazeOffsets(input){const p=normalized(input);return [p.gazeX*5.5,p.gazeY*4.5];}
  return {defaults,normalized,headMatrix,applyHead,smooth,spring,gazeOffsets};
});
