const net=require('node:net');
const os=require('node:os');
const fs=require('node:fs/promises');
const path=require('node:path');
const {randomBytes}=require('node:crypto');
const {spawn,execFile}=require('node:child_process');
const {setTimeout:delay}=require('node:timers/promises');

const GiB=1024**3;
const minimumStart=1.2*GiB,minimumIdle=0.5*GiB;
const startupMs=95000;

function listening(){
  return new Promise(resolve=>{
    const socket=net.createConnection({host:'127.0.0.1',port:9880});
    const finish=ok=>{socket.destroy();resolve(ok);};
    socket.setTimeout(750);
    socket.once('connect',()=>finish(true));
    socket.once('timeout',()=>finish(false));
    socket.once('error',()=>finish(false));
  });
}
function freeVram(){
  return new Promise(resolve=>{
    execFile('nvidia-smi',['-i','0','--query-gpu=memory.free','--format=csv,noheader,nounits'],
      {windowsHide:true,timeout:1500},(error,stdout)=>{
        const mib=Number.parseInt(stdout,10);
        resolve(!error&&Number.isFinite(mib)?mib:null);
      });
  });
}
function runScript(root,operation,id){
  const file=path.join(root,'tools',operation+'-Voice.ps1');
  const args=['-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',file,...(id?['-RunId',id]:[])];
  return new Promise((resolve,reject)=>{
    const child=spawn('powershell.exe',args,
      {windowsHide:true,stdio:'ignore'});
    const timeout=setTimeout(()=>{child.kill();reject(Error('本机配音管理命令等待超时。'));},15000);
    child.once('error',error=>{clearTimeout(timeout);reject(error);});
    child.once('exit',code=>{
      clearTimeout(timeout);
      if(code===0)resolve();
      else reject(Error(operation==='Start'?'本机配音启动失败，请检查本机语音服务。':'本机配音服务未能释放。'));
    });
  });
}
async function launchAlive(root,id){
  const record=path.join(root,'work','voice','managed',id,'process.json');
  let pid;
  try{({pid}=JSON.parse((await fs.readFile(record,'utf8')).replace(/^\uFEFF/,'')));}
  catch(error){return error.code==='ENOENT'||error instanceof SyntaxError?false:null;}
  if(!Number.isSafeInteger(pid)||pid<=0)return false;
  try{process.kill(pid,0);return true;}
  catch(error){return error.code==='ESRCH'?false:null;}
}
async function abortable(task,signal){
  signal.throwIfAborted();
  let abort;
  try{
    return await Promise.race([task,new Promise((_,reject)=>{
      abort=()=>reject(signal.reason);
      signal.addEventListener('abort',abort,{once:true});
    })]);
  }finally{signal.removeEventListener('abort',abort);}
}
function managedVoiceEndpoint(url){
  return url.protocol==='http:'&&['127.0.0.1','localhost'].includes(url.hostname)&&
    url.port==='9880'&&url.pathname==='/tts'&&!url.username&&!url.password;
}

class LocalVoiceService{
  constructor(root,{probe=listening,run=(operation,id)=>runScript(root,operation,id),freeMemory=os.freemem,
                    vram=freeVram,clock=()=>performance.now(),pause=delay,
                    alive=id=>launchAlive(root,id)}={}){
    Object.assign(this,{probe,run,freeMemory,vram,clock,pause,alive,inUse:0,closed:false});
  }
  async acquire(signal){
    signal.throwIfAborted();
    if(this.closed)throw Error('桌宠已退出。');
    this.inUse++;
    let released=false;
    const release=()=>{
      if(released)return;
      released=true;
      this.inUse--;
      if(!this.inUse&&this.freeMemory()<minimumIdle)void this.reclaim();
    };
    try{
      if(this.stopping)await abortable(this.stopping,signal);
      signal.throwIfAborted();
      if(this.starting||!await this.probe()){
        signal.throwIfAborted();
        await abortable(this.ensureStarted(),signal);
      }
      signal.throwIfAborted();
      return release;
    }catch(error){release();throw error;}
  }
  ensureStarted(){
    if(!this.starting){
      const controller=new AbortController();
      this.startController=controller;
      this.starting=this.start(controller.signal).finally(()=>{
        this.startController=null;
        this.starting=null;
      });
    }
    return this.starting;
  }
  async start(signal,id=randomBytes(16).toString('hex')){
    signal.throwIfAborted();
    if(this.closed)throw Error('桌宠已退出。');
    if(this.runId&&this.runId!==id)await this.retire();
    if(this.freeMemory()<minimumStart)throw Error('当前可用内存不足 1.2 GiB，本机配音暂缓启动。');
    const availableVram=await this.vram();
    if(availableVram!==null&&availableVram<1500)throw Error('当前可用显存不足约 1.5 GB，本机配音暂缓启动。');
    signal.throwIfAborted();
    if(await this.probe())return;
    signal.throwIfAborted();
    this.runId=id;
    try{
      try{await this.run('Start',id);}
      catch(error){
        // A separately started service may win the race to the port.
        if(signal.aborted||!await this.probe())throw error;
        await this.retire();
        return;
      }
      const deadline=this.clock()+startupMs;
      while(this.clock()<deadline){
        signal.throwIfAborted();
        if(this.freeMemory()<minimumIdle)throw Error('本机配音加载时内存不足，已暂停启动。');
        if(await this.probe()){
          signal.throwIfAborted();
          this.watch=setInterval(()=>{void this.reclaim();},15000);
          this.watch.unref();
          return;
        }
        if(await this.alive(id)===false)throw Error('本机配音进程在加载模型时退出，请查看语音服务日志。');
        await this.pause(700,undefined,{signal});
      }
      throw Error('本机配音服务启动超时，请查看语音服务日志。');
    }catch(error){
      await this.retire().catch(()=>{});
      throw error;
    }
  }
  status(){
    return {running:!!this.runId,starting:!!this.starting,stopping:!!this.stopping};
  }
  async startManual(){
    if(this.closed)throw Error('桌宠已退出。');
    if(this.stopping)await this.stopping;
    if(this.starting||!await this.probe())await this.ensureStarted();
    return true;
  }
  async stopManual(){
    if(this.starting){
      this.startController.abort(Error('本机配音启动已取消。'));
      await this.starting.catch(()=>{});
      if(this.runId)await this.retire();
      return true;
    }
    if(this.runId){await this.retire();return true;}
    await this.run('Stop','');
    return true;
  }
  async reclaim(){
    const id=this.runId;
    if(!id||this.starting||this.stopping||this.inUse||this.closed)return;
    const lowRam=this.freeMemory()<minimumIdle;
    const vram=lowRam?null:await this.vram();
    if(this.runId===id&&!this.inUse&&(lowRam||vram!==null&&vram<512)){
      await this.retire().catch(()=>{});
    }
  }
  retire(){
    if(this.stopping)return this.stopping;
    const id=this.runId;
    if(!id)return Promise.resolve();
    this.stopping=this.run('Stop',id).then(()=>{
      if(this.runId===id)this.runId=null;
      clearInterval(this.watch);
    }).finally(()=>{this.stopping=null;});
    return this.stopping;
  }
  close(){
    this.closed=true;
    this.startController?.abort(Error('桌宠已退出。'));
    clearInterval(this.watch);
    void this.retire().catch(()=>{});
  }
}
module.exports={LocalVoiceService,managedVoiceEndpoint};
