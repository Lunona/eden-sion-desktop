'use strict';
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto'),readline=require('node:readline'),{spawn}=require('node:child_process');
const {writeJSON}=require('./core.cjs');
const LOCAL_START_MIN_MEMORY=1.0*1024**3;
class SpeechInput{
 constructor({dataRoot,backend,providers}){Object.assign(this,{dataRoot,backend,providers});this.file=path.join(dataRoot,'speech-input.json');this.config={mode:'local',language:'zh',python:process.env.SION_ASR_PYTHON||'',modelPath:process.env.SION_ASR_MODEL||''};if(fs.existsSync(this.file))try{this.config=this.validate(JSON.parse(fs.readFileSync(this.file,'utf8')));}catch{this.configError='语音设置无法读取，原文件保留，暂用默认本机识别。';}this.serial=0;this.active=null;this.child=null;this.waiters=new Map();}
 validate(input){const c={...this.config,...input};if(!['local','api'].includes(c.mode)||!['zh','ja','en','auto'].includes(c.language))throw Error('语音识别设置无效');if(typeof c.python!=='string'||typeof c.modelPath!=='string'||c.python.length>1000||c.modelPath.length>1000)throw Error('本机识别路径无效');return {mode:c.mode,language:c.language,python:c.python,modelPath:c.modelPath};}
 save(input){if(this.active)throw Error('请等本次识别结束后再修改设置');this.config=this.validate(input);writeJSON(this.file,this.config);this.release();return this.status();}
 status(){return {config:this.config,busy:!!this.active,loaded:!!this.child,configError:this.configError||'',localAvailable:fs.existsSync(this.config.python)&&fs.existsSync(path.join(this.config.modelPath,'model.bin')),idleReleaseSeconds:90};}
 release(){clearTimeout(this.idle);const child=this.child;this.child=null;if(child){child.stdin.end();child.kill();}for(const p of this.waiters.values())p.reject(Error('语音识别已停止'));this.waiters.clear();}
 cancel(){this.active?.abort();this.release();}
 startLocalWorker(){
  if(os.freemem()<LOCAL_START_MIN_MEMORY)return null;
  const child=spawn(this.config.python,['-u',path.join(this.backend,'asr_worker.py'),this.config.modelPath],{
   windowsHide:true,stdio:['pipe','pipe','pipe'],env:{...process.env,PYTHONUTF8:'1',CUDA_VISIBLE_DEVICES:'-1',OMP_NUM_THREADS:'4',
    OPENBLAS_NUM_THREADS:process.env.OPENBLAS_NUM_THREADS||'1'}
  });
  this.child=child;
  const disconnected=()=>{if(this.child===child)this.release();};
  child.stderr.resume();
  child.on('error',disconnected);
  child.on('exit',disconnected);
  child.stdin.on('error',disconnected);
  readline.createInterface({input:child.stdout}).on('line',line=>{
   if(this.child!==child)return;
   let result;
   try{result=JSON.parse(line);}catch{return;}
   const waiter=this.waiters.get(result.id);
   if(!waiter)return;
   this.waiters.delete(result.id);
   if(result.error)waiter.reject(Error('本机识别失败：'+result.error));
   else waiter.resolve(result);
  });
  return child;
 }
 prepareLocal(){
  // Loading overlaps confirmed speech only when there is room for the CPU model.
  if(this.config.mode!=='local'||this.child||this.active||!this.status().localAvailable)return;
  const child=this.startLocalWorker();
  if(!child)return;
  this.idle=setTimeout(()=>this.release(),90000);
  child.stdin.write('{"warmup":true}\n');
 }
 async local(file,signal){
  if(!this.status().localAvailable)throw Error('未找到本机语音识别环境，可配置识别API或检查本机路径');
  clearTimeout(this.idle);
  const child=this.child||this.startLocalWorker();
  if(!child)throw Error('可用内存不足，暂时无法启动本机语音识别。稍后可以再试。');
  const id=++this.serial;return new Promise((resolve,reject)=>{const abort=()=>{this.waiters.delete(id);reject(Error('识别已取消'));this.release();},finish=fn=>r=>{signal.removeEventListener('abort',abort);if(this.child===child)this.idle=setTimeout(()=>this.release(),90000);fn(r);};this.waiters.set(id,{resolve:finish(resolve),reject:finish(reject)});signal.addEventListener('abort',abort,{once:true});if(signal.aborted)return abort();child.stdin.write(JSON.stringify({id,file,language:this.config.language==='auto'?null:this.config.language})+'\n');});
 }
 async transcribe(input){
  if(this.active)throw Error('另一处语音正在识别，请稍候');
  if(!input||typeof input.audio!=='string'||input.audio.length>12*1024*1024||!['audio/webm','audio/wav','audio/ogg'].includes(input.mime))throw Error('只接受32秒以内的语音');
  const bytes=Buffer.from(input.audio,'base64');if(!bytes.length||bytes.length>8*1024*1024)throw Error('语音片段过大');
  const signature=bytes.subarray(0,4).toString('hex');if(!['1a45dfa3','52494646','4f676753'].includes(signature))throw Error('语音文件格式无效');
  const controller=new AbortController();this.active=controller;const deadline=setTimeout(()=>controller.abort(),150000);let dir;
  try{
   let result;
   if(this.config.mode==='local'){dir=fs.mkdtempSync(path.join(os.tmpdir(),'sion-asr-'));const file=path.join(dir,'utterance.'+({'audio/webm':'webm','audio/wav':'wav','audio/ogg':'ogg'}[input.mime]));fs.writeFileSync(file,bytes);result=await this.local(file,controller.signal);}
   else{
    if(!this.providers.has('asr'))throw Error('请先为语音识别选择一个API档案');const r=this.providers.resolve('asr'),base=r.config.baseUrl,url=base.endsWith('/audio/transcriptions')?base:base+'/audio/transcriptions';const form=new FormData();form.append('file',new Blob([bytes],{type:input.mime}),'speech.'+input.mime.split('/')[1]);form.append('model',r.config.name);if(this.config.language!=='auto')form.append('language',this.config.language);const response=await fetch(url,{method:'POST',redirect:'error',headers:r.key?{Authorization:'Bearer '+r.key}:{},body:form,signal:AbortSignal.any([controller.signal,AbortSignal.timeout(r.config.timeoutSeconds*1000)])});if(!response.ok){response.body?.cancel();throw Error('语音服务返回 HTTP '+response.status);}if(Number(response.headers.get('content-length'))>65536)throw Error('识别结果过大');const reader=response.body.getReader();let size=0,parts=[];while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>65536){await reader.cancel();throw Error('识别结果过大');}parts.push(Buffer.from(value));}result=JSON.parse(Buffer.concat(parts).toString('utf8'));
   }
   if(controller.signal.aborted)throw Error('识别已取消');if(typeof result.text!=='string'||result.text.length>4000)throw Error('识别结果无效');return {text:result.text.trim(),language:result.language||this.config.language,milliseconds:result.milliseconds||null};
  }finally{clearTimeout(deadline);if(this.active===controller)this.active=null;if(dir){for(const p of fs.readdirSync(dir)){const file=path.join(dir,p);for(let i=0;i<12;i++){try{fs.unlinkSync(file);break;}catch(e){if(e.code==='ENOENT')break;if(i===11)throw e;await new Promise(r=>setTimeout(r,80));}}}fs.rmdirSync(dir);}}
 }
}
module.exports={SpeechInput};
