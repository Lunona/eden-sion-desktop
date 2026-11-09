const {execFile}=require('node:child_process');
const path=require('node:path');
const {promisify}=require('node:util');

const run=promisify(execFile);
const eventToleranceMs=15000;

function matchWindowsPower(events,suspendedAt,resumedAt){
  const near=(event,time)=>Math.abs(event.at-time)<=eventToleranceMs;
  const exits=events.filter(event=>[107,507].includes(event.id)&&near(event,resumedAt))
    .sort((a,b)=>Math.abs(a.at-resumedAt)-Math.abs(b.at-resumedAt));
  for(const exit of exits){
    const entry=events.find(event=>event.at<exit.at&&near(event,suspendedAt)&&
      (exit.id===107?event.id===42:
        event.id===506&&exit.bootId&&event.bootId===exit.bootId&&
        exit.scenarioId&&event.scenarioId===exit.scenarioId));
    if(!entry)continue;
    const records={enteredRecord:entry.recordId,exitedRecord:exit.recordId};
    if(exit.id===107)return {...records,result:'system_sleep'};
    if(exit.sleepEntered===false||exit.sleepDurationUs===0)return {...records,result:'screen_off_only'};
    if(exit.sleepEntered===true&&exit.sleepDurationUs>0)return {...records,result:'modern_standby_sleep'};
    return {...records,result:'sleep_not_confirmed'};
  }
  return {result:'no_matching_windows_events'};
}

async function readWindowsPower(suspendedAt,resumedAt){
  const from=new Date(suspendedAt-eventToleranceMs).toISOString();
  const to=new Date(resumedAt+eventToleranceMs).toISOString();
  const script=`
$ProgressPreference='SilentlyContinue'
$start=[DateTimeOffset]::Parse('${from}').LocalDateTime
$end=[DateTimeOffset]::Parse('${to}').LocalDateTime
$events=Get-WinEvent -FilterHashtable @{LogName='System';ProviderName='Microsoft-Windows-Kernel-Power';Id=42,107,506,507;StartTime=$start;EndTime=$end} -MaxEvents 24 -ErrorAction SilentlyContinue
$result=@(foreach($event in $events){
  $fields=@{}
  foreach($entry in ([xml]$event.ToXml()).Event.EventData.Data){if($entry.Name){$fields[$entry.Name]=$entry.'#text'}}
  $sleepEntered=$null
  $sleepDurationUs=$null
  if($fields.ContainsKey('SleepEntered')){$sleepEntered=$fields.SleepEntered -eq 'true'}
  if($fields.ContainsKey('SleepDurationInUs')){$sleepDurationUs=[long]$fields.SleepDurationInUs}
  [pscustomobject]@{
    id=$event.Id;recordId=$event.RecordId;at=([DateTimeOffset]$event.TimeCreated).ToUnixTimeMilliseconds()
    bootId=$fields.BootId;scenarioId=$fields.ScenarioInstanceIdV2
    sleepEntered=$sleepEntered;sleepDurationUs=$sleepDurationUs
  }
})
ConvertTo-Json -InputObject $result -Compress
`;
  const shell=path.join(process.env.SystemRoot,'System32','WindowsPowerShell','v1.0','powershell.exe');
  const command=Buffer.from(script,'utf16le').toString('base64');
  const {stdout}=await run(shell,['-NoProfile','-NonInteractive','-EncodedCommand',command],
    {windowsHide:true,timeout:5500,maxBuffer:64*1024});
  return matchWindowsPower(JSON.parse(stdout),suspendedAt,resumedAt);
}

module.exports={matchWindowsPower,readWindowsPower};
