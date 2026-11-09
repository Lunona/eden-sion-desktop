const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
test('the real preload permits model-test and rejects unrecognized commands',async()=>{
  let bridge;const calls=[];const electron={contextBridge:{exposeInMainWorld(name,value){assert.equal(name,'sion');bridge=value;}},ipcRenderer:{invoke:async(...args)=>{calls.push(args);return {reply:'连接成功'};},on(){},removeListener(){}}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../src/preload.cjs'),'utf8'),{require:name=>{assert.equal(name,'electron');return electron;}});
  assert.equal((await bridge.invoke('model-test')).reply,'连接成功');assert.equal(calls[0][0],'sion');assert.equal(calls[0][1],'model-test');
  await bridge.invoke('compact-close');assert.equal(calls[1][1],'compact-close');
  await assert.rejects(bridge.invoke('run-shell'),/未知操作/);assert.equal(calls.length,2);
});
