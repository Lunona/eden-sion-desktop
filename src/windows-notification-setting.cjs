const {execFile}=require('node:child_process');
const path=require('node:path');
const {promisify}=require('node:util');

const DESKTOP_APP_ID='local.eden.sion.fullbody.desktop';
const blocked=new Set(['DisabledForApplication','DisabledForUser','DisabledByGroupPolicy','DisabledByManifest']);
const run=promisify(execFile);
const script=`$ErrorActionPreference='Stop'
[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime]::CreateToastNotifier('${DESKTOP_APP_ID}').Setting.ToString()`;
const encoded=Buffer.from(script,'utf16le').toString('base64');

async function readWindowsNotificationSetting(){
  if(process.platform!=='win32'||!process.env.SystemRoot)return null;
  const shell=path.join(process.env.SystemRoot,'System32','WindowsPowerShell','v1.0','powershell.exe');
  try{
    const {stdout}=await run(shell,['-NoProfile','-NonInteractive','-EncodedCommand',encoded],
      {windowsHide:true,timeout:2000,maxBuffer:8192});
    const setting=stdout.trim();
    return setting==='Enabled'||blocked.has(setting)?setting:null;
  }catch{return null;}
}

module.exports={DESKTOP_APP_ID,readWindowsNotificationSetting,isWindowsNotificationBlocked:setting=>blocked.has(setting)};
