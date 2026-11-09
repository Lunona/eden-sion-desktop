const fs=require('node:fs');
const path=require('node:path');

function productionDataRoot(root,override,legacyData){
  if(override)return path.resolve(override);
  const manifest=path.join(root,'安装存档.json');
  if(fs.existsSync(manifest)){
    const {dataRoot}=JSON.parse(fs.readFileSync(manifest,'utf8'));
    if(typeof dataRoot!=='string'||!path.isAbsolute(dataRoot)||
       !fs.statSync(path.join(dataRoot,'state.json'),{throwIfNoEntry:false})?.isFile()){
      throw Error('找不到正式存档，请检查安装目录里的「安装存档.json」。');
    }
    return path.resolve(dataRoot);
  }
  return fs.existsSync(path.join(legacyData,'state.json'))?legacyData:path.join(root,'data');
}
module.exports={productionDataRoot};
