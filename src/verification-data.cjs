const fs=require('node:fs');
const path=require('node:path');

function directChildDirectory(parent,name){
  const directory=path.join(parent,name);
  fs.mkdirSync(directory,{recursive:true});
  if(path.relative(directory,fs.realpathSync(directory))!=='')
    throw Error('验收工作目录不能重定向到其他位置');
  return directory;
}

function verificationDataRoot(root,override,{requiresProfile=false,prefix='runtime-'}={}){
  if(requiresProfile&&!override)throw Error('请用 --data-dir 指定 work/verification-data 下已配置的独立验收目录');
  const work=directChildDirectory(fs.realpathSync(root),'work');
  const allowed=directChildDirectory(work,'verification-data');
  if(!override)return fs.mkdtempSync(path.join(allowed,prefix));

  const target=fs.realpathSync(path.resolve(override));
  const relative=path.relative(allowed,target);
  if(!relative||relative==='..'||relative.startsWith('..'+path.sep)||path.isAbsolute(relative)||!fs.statSync(target).isDirectory())
    throw Error('验收目录必须位于 work/verification-data 内');
  if(requiresProfile&&!['state.json','providers.json'].some(name=>fs.existsSync(path.join(target,name))))
    throw Error('独立验收目录尚未配置模型');
  return target;
}

module.exports={verificationDataRoot};
