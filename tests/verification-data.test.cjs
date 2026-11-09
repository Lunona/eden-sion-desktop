const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {verificationDataRoot}=require('../src/verification-data.cjs');
const {productionDataRoot}=require('../src/production-data.cjs');

function fixture(t){
  const folder=fs.mkdtempSync(path.join(os.tmpdir(),'sion-verification-data-'));
  t.after(()=>fs.rmSync(folder,{recursive:true,force:true}));
  const formal=path.join(folder,'data');
  fs.mkdirSync(formal);
  fs.writeFileSync(path.join(formal,'state.json'),'formal state');
  return {folder,formal};
}

test('direct launch uses the installed profile, while verification and explicit overrides stay separate',t=>{
  const {folder,formal}=fixture(t);
  const legacy=path.join(folder,'legacy');
  const installed=path.join(folder,'original');
  fs.mkdirSync(installed);
  fs.writeFileSync(path.join(installed,'state.json'),'original profile');
  const manifest=path.join(folder,'安装存档.json');
  fs.writeFileSync(manifest,JSON.stringify({dataRoot:installed}));
  assert.equal(productionDataRoot(folder,undefined,legacy),installed);
  assert.equal(productionDataRoot(folder,formal,legacy),formal);
  assert.notEqual(verificationDataRoot(folder),installed);
  fs.writeFileSync(manifest,JSON.stringify({dataRoot:legacy}));
  assert.throws(()=>productionDataRoot(folder,undefined,legacy),/找不到正式存档/);
});

test('verification uses fresh local folders and never defaults to the formal state',t=>{
  const {folder,formal}=fixture(t);
  assert.throws(()=>verificationDataRoot(folder,undefined,{requiresProfile:true}),/独立验收目录/);
  const first=verificationDataRoot(folder);
  const second=verificationDataRoot(folder);
  assert.notEqual(first,second);
  assert.equal(path.dirname(first),path.join(fs.realpathSync(folder),'work','verification-data'));
  assert.equal(fs.existsSync(path.join(first,'state.json')),false);
  assert.throws(()=>verificationDataRoot(folder,first,{requiresProfile:true}),/尚未配置模型/);
  fs.writeFileSync(path.join(first,'state.json'),'fixture configuration');
  assert.equal(verificationDataRoot(folder,first,{requiresProfile:true}),first);
  assert.throws(()=>verificationDataRoot(folder,formal,{requiresProfile:true}),/必须位于/);
  assert.equal(fs.readFileSync(path.join(formal,'state.json'),'utf8'),'formal state');
});

test('a junction inside the verification folder cannot redirect an explicit profile',t=>{
  const {folder,formal}=fixture(t);
  const allowed=path.dirname(verificationDataRoot(folder));
  const alias=path.join(allowed,'redirect');
  fs.symlinkSync(formal,alias,process.platform==='win32'?'junction':'dir');
  assert.throws(()=>verificationDataRoot(folder,alias,{requiresProfile:true}),/必须位于/);
});

test('a redirected work folder is rejected before an external fixture is created',t=>{
  const {folder,formal}=fixture(t);
  fs.symlinkSync(formal,path.join(folder,'work'),process.platform==='win32'?'junction':'dir');
  assert.throws(()=>verificationDataRoot(folder),/不能重定向/);
  assert.equal(fs.existsSync(path.join(formal,'verification-data')),false);
});
