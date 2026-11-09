/* Mouth ink from a small aligned key; surrounding facial skin remains the master. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.SourceMouth=api;})(typeof window==='object'?window:globalThis,function(){
  const clamp=n=>Math.max(0,Math.min(1,n)),smooth=(a,b,n)=>{const t=clamp((n-a)/(b-a));return t*t*(3-2*t);};
  function textPose(elapsed,duration){if(elapsed<0||elapsed>=duration)return 0;const edge=Math.min(1,elapsed/100,(duration-elapsed)/100);return clamp((.23+.37*Math.sin(elapsed/78)**2+.27*Math.sin(elapsed/119)**2)*edge);}
  class Renderer{
    constructor(master,keyImage,layout){
      Object.assign(this,layout);this.raw=master.getImageData(this.x,this.y,this.w,this.h);
      this.canvas=document.createElement('canvas');this.canvas.width=this.w;this.canvas.height=this.h;this.ctx=this.canvas.getContext('2d',{willReadFrequently:true});this.ctx.drawImage(keyImage,0,0,this.w,this.h);this.key=this.ctx.getImageData(0,0,this.w,this.h);this.cache=new Map();
    }
    draw(amount){
      amount=clamp(amount);if(this.cache.has(amount))return this.cache.get(amount);
      const {x,y,w,h,cx,cy,raw,key}=this,out=new Uint8ClampedArray(raw.data),strength=smooth(0,.2,amount),ys=.15+.85*amount,xs=.75+.25*amount;
      const sample=(data,xx,yy,c)=>{const a=Math.max(0,Math.min(w-1,xx)),b=Math.max(0,Math.min(h-1,yy)),ix=Math.floor(a),iy=Math.floor(b),fx=a-ix,fy=b-iy,jx=Math.min(w-1,ix+1),jy=Math.min(h-1,iy+1);return data[(iy*w+ix)*4+c]*(1-fx)*(1-fy)+data[(iy*w+jx)*4+c]*fx*(1-fy)+data[(jy*w+ix)*4+c]*(1-fx)*fy+data[(jy*w+jx)*4+c]*fx*fy;};
      if(amount>0)for(let j=0;j<h;j++)for(let i=0;i<w;i++){
        const n=(j*w+i)*4,xx=x+i,yy=y+j;
        const skin=[0,1,2].map(c=>raw.data[(j*w+4)*4+c]*(1-i/(w-1))+raw.data[(j*w+w-5)*4+c]*i/(w-1));
        const erase=(((xx-cx)/9)**2+((yy-cy)/5)**2<1)?smooth(7,24,Math.max(...skin.map((v,c)=>v-raw.data[n+c])))*strength:0;
        const sx=cx-x+(xx-cx)/xs,sy=cy-y+(yy-cy)/ys;
        const ink=[0,1,2].map(c=>sample(key.data,sx,sy,c));
        const keySkin=[0,1,2].map(c=>sample(key.data,3,sy,c)*(1-i/(w-1))+sample(key.data,w-4,sy,c)*i/(w-1));
        const local=((xx-cx)/13)**2+((yy-cy)/13)**2<1;
        const alpha=local?smooth(12,32,Math.max(...keySkin.map((v,c)=>v-ink[c])))*strength:0;
        for(let c=0;c<3;c++){const bg=raw.data[n+c]*(1-erase)+skin[c]*erase;out[n+c]=bg*(1-alpha)+ink[c]*alpha;}
      }
      const image=new ImageData(out,w,h),canvas=document.createElement('canvas');canvas.width=w;canvas.height=h;canvas.getContext('2d').putImageData(image,0,0);
      const patch={x,y,w,h,image,canvas};this.cache.set(amount,patch);return patch;
    }
  }
  return {Renderer,textPose};
});
