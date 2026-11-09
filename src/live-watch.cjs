'use strict';

const OBSERVE_INTERVAL=30000;
const REMARK_INTERVAL=55000;

function changedFrame(previous, pixels) {
  if(!previous||previous.length!==pixels.length)return true;
  let difference=0;
  for(let i=0;i<pixels.length;i+=4){
    difference+=Math.abs(pixels[i]-previous[i])+Math.abs(pixels[i+1]-previous[i+1])+
      Math.abs(pixels[i+2]-previous[i+2]);
  }
  return difference/(pixels.length*.75)>9;
}

class LiveWatch {
  constructor({screen,canObserve,draft,deliver,publish,clock=Date.now}) {
    Object.assign(this,{screen,canObserve,draft,deliver,publish,clock});
    this.session=null;
  }
  status(){
    const s=this.session;
    return {enabled:!!s,speak:s?.speak===true,detail:s?.detail||''};
  }
  start(displayId,speak) {
    this.screen.enable(displayId);
    this.cancel();
    this.session={shared:this.screen.session,speak,scene:'',nextIdea:'',lastRemark:'',nextAt:0,lastAt:-Infinity};
  }
  cancel(){this.job?.abort();}
  stop(){
    this.cancel();
    if(this.session?.shared===this.screen.session)this.screen.stop();
    this.session=null;
  }
  async tick(){
    const s=this.session,now=this.clock();
    if(!s||this.job||now<s.nextAt||now-s.lastAt<REMARK_INTERVAL||!this.canObserve())return;
    if(s.shared!==this.screen.session){this.stop();this.publish();return;}
    s.nextAt=now+OBSERVE_INTERVAL;
    const job=this.job=new AbortController();
    const signal=AbortSignal.any([job.signal,AbortSignal.timeout(12000)]);
    const current=()=>this.session===s&&!signal.aborted&&s.shared===this.screen.session&&this.canObserve();
    try{
      const image=await this.screen.capture(s.shared,signal,{maxDimension:960,acceptFrame:frame=>{
        const pixels=frame.resize({width:32,height:18}).toBitmap();
        if(!changedFrame(s.frame,pixels))return false;
        s.frame=pixels;
        return true;
      }});
      if(!image||!current())return;
      const remark=await this.draft(s,image,signal);
      if(!current())return;
      s.detail='';
      s.scene=remark.scene;
      s.nextIdea=remark.nextIdea||'';
      const normalize=text=>text.replace(/[^\p{L}\p{N}]/gu,'');
      if(remark.text&&normalize(remark.text)&&normalize(remark.text)!==normalize(s.lastRemark)){
        s.lastRemark=remark.text;s.lastAt=this.clock();
        await this.deliver(remark,s,current);
      }
    }catch{
      if(this.session===s&&!job.signal.aborted){
        s.frame=null;
        s.detail='暂时没看清画面，稍后再试。';
      }
    }finally{
      if(this.job===job)this.job=null;
      this.publish();
    }
  }
}

module.exports={LiveWatch};
