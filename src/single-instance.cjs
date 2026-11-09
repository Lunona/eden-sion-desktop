const net=require('node:net'),crypto=require('node:crypto');
async function acquireInstance(identity,onActivate){
 const name='sion-fullbody-'+crypto.createHash('sha256').update(identity.toLowerCase()).digest('hex').slice(0,24),address=process.platform==='win32'?'\\\\.\\pipe\\'+name:require('node:path').join(require('node:os').tmpdir(),name+'.sock');
 const server=net.createServer(socket=>{socket.setTimeout(1000,()=>socket.destroy());socket.once('data',data=>{if(data.length<=32&&data.toString()==='activate')onActivate();socket.end('ok');});});
 const primary=await new Promise((resolve,reject)=>{const fail=e=>{if(e.code==='EADDRINUSE')resolve(false);else reject(e);};server.once('error',fail);server.listen(address,()=>{server.removeListener('error',fail);resolve(true);});});
 if(primary)return {primary,address,close:()=>{if(server.listening)server.close();}};
 await new Promise(resolve=>{const client=net.connect(address);client.setTimeout(1200);client.once('connect',()=>client.write('activate'));client.once('data',()=>{client.end();resolve();});client.once('timeout',()=>{client.destroy();resolve();});client.once('error',()=>resolve());});return {primary:false,address,close:()=>{}};
}
module.exports={acquireInstance};
