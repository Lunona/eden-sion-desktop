/* One continuous full-body source. Only registered eye and mouth patches change. */
(function(){
  class Rig{
    constructor(images,layout){
      this.images=images;this.layout=layout;this.width=images.master.naturalWidth;this.height=images.master.naturalHeight;
      if(this.width!==layout.width||this.height!==layout.height)throw new Error('立绘尺寸与眼口位置不一致');
      this.texture=document.createElement('canvas');this.texture.width=this.width;this.texture.height=this.height;
      this.ctx=this.texture.getContext('2d',{willReadFrequently:true});this.ctx.drawImage(images.master,0,0);
      // Canonicalize the decoded canvas once. Keep subsequent patch writes on
      // the same ImageData path so alpha-edge rounding does not accumulate.
      this.ctx.putImageData(this.ctx.getImageData(0,0,this.width,this.height),0,0);
      this.original=this.ctx.getImageData(0,0,this.width,this.height);this.closedEyes=false;this.draws=0;this.motionFailed=false;
      this.eyes=layout.eyes.map(e=>{
        if(images[e.id].naturalWidth!==e.w||images[e.id].naturalHeight!==e.h)throw new Error('闭眼素材尺寸不一致');
        const canvas=document.createElement('canvas');canvas.width=e.w;canvas.height=e.h;
        const ctx=canvas.getContext('2d',{willReadFrequently:true});ctx.drawImage(images[e.id],0,0);
        return {...e,raw:this.ctx.getImageData(e.x,e.y,e.w,e.h),closed:ctx.getImageData(0,0,e.w,e.h),canvas,ctx};
      });
      this.mouth=new SourceMouth.Renderer(this.ctx,images.mouth,layout.mouth);this.lastMouth=0;this.lastParts=['whole'];
    }
    draw(canvas,input,time=0){
      const p=RigMath.normalized(input),closed=p.eyeOpen<.5,patches=[];
      if(closed!==this.closedEyes){
        for(const eye of this.eyes){
          const image=closed?eye.closed:eye.raw;eye.ctx.putImageData(image,0,0);
          this.ctx.putImageData(image,eye.x,eye.y);patches.push(eye);
        }
        this.closedEyes=closed;
      }
      const amount=Math.round(p.mouthOpen*4)/4;
      if(amount!==this.lastMouth){const patch=this.mouth.draw(amount);this.ctx.putImageData(patch.image,patch.x,patch.y);patches.push(patch);this.lastMouth=amount;}
      let source=this.texture;
      if(SourceMotion.active(p)&&!this.motionFailed){
        try{if(!this.motion)this.motion=new SourceMotion.Renderer();source=this.motion.draw(source,'fullbody-v1',p,canvas.width,canvas.height,patches);}
        catch(e){this.motionFailed=true;console.warn(e.message);}
      }else if(this.motion&&patches.length){this.motion.uploadKey=null;}
      const ctx=canvas.getContext('2d');ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,canvas.width,canvas.height);ctx.drawImage(source,0,0,canvas.width,canvas.height);this.draws++;
      return {draws:this.draws,parameters:p,closedEyes:closed,mouthOpen:amount,motionActive:SourceMotion.active(p)&&!this.motionFailed};
    }
    audit(){
      const current=this.ctx.getImageData(0,0,this.width,this.height).data,original=this.original.data;
      let changed=0,maxDifference=0;for(let i=0;i<current.length;i++){const d=Math.abs(current[i]-original[i]);if(d)changed++;if(d>maxDifference)maxDifference=d;}
      return {width:this.width,height:this.height,changedChannels:changed,maxDifference,source:'master.png'};
    }
  }
  window.SionRig={Rig,W:2160,H:3840};
})();
