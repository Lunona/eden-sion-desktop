const test=require('node:test');
const assert=require('node:assert/strict');
const {matchWindowsPower}=require('../tools/power-evidence.cjs');

test('modern standby callbacks require evidence that Windows actually slept',()=>{
  const entry={id:506,at:100000,recordId:1,bootId:'188',scenarioId:'96'};
  const exit={id:507,at:200000,recordId:2,bootId:'188',scenarioId:'96'};
  const match=event=>matchWindowsPower([entry,event],entry.at,exit.at).result;
  assert.equal(match({...exit,sleepEntered:false,sleepDurationUs:0}),'screen_off_only');
  assert.equal(match({...exit,sleepEntered:true,sleepDurationUs:40000000}),'modern_standby_sleep');
  assert.equal(match(exit),'sleep_not_confirmed');
  assert.equal(match({...exit,scenarioId:'99',sleepEntered:true,sleepDurationUs:40000000}),'no_matching_windows_events');
  assert.equal(match({...exit,bootId:'189',sleepEntered:true,sleepDurationUs:40000000}),'no_matching_windows_events');
});

test('classic Windows sleep must match the application timestamps',()=>{
  const entry={id:42,at:100000,recordId:1};
  const exit={id:107,at:200000,recordId:2};
  assert.deepEqual(matchWindowsPower([entry,exit],101000,201000),
    {result:'system_sleep',enteredRecord:1,exitedRecord:2});
  assert.equal(matchWindowsPower([entry,exit],101000,230000).result,'no_matching_windows_events');
});
