const {contextBridge,ipcRenderer}=require('electron');
const actions=new Set(['state','chat','stop','settings','clear','expression','panel','reset','drag-start','drag-end','click','menu','clickthrough','compact-close','import-image','reset-images','voice-test','mouth-test','model-test','quit','model-init','control','ack','audio-caption','audio-start','audio-level','audio-end','memories','recall','memory-status','memory-config','memory-retry','memory-reindex','notes','notes-import','notes-file','memory-action','memory-graph','memory-detail','memory-profiles','memory-maintain','memory-backups','memory-backup','memory-restore','memory-export','memory-import','notes-read','remember','correct','forget','providers','providers-save','providers-test','speech-status','speech-config','voice-session','voice-phase','voice-proactive','screen-share','live-watch','weather-search','weather-config','speech-transcribe','companion-status','relationship-set','learning-review','companion-config','companion-reminder','special-day','persona','persona-save','computer-status','computer-config','computer-connect','computer-capture','computer-plan','computer-execute','computer-stop']);
actions.add('computer-discard');
actions.add('companion-read');
actions.add('special-card-open');
actions.add('pet-controls');
actions.add('show-heart-voice');
actions.add('drag-move');
actions.add('companion-open-loop');
contextBridge.exposeInMainWorld('sion',{
  invoke:(action,data={})=>{if(!actions.has(action))return Promise.reject(new Error('未知操作'));return ipcRenderer.invoke('sion',action,data);},
  subscribe:callback=>{const fn=(_event,value)=>callback(value);ipcRenderer.on('sion-event',fn);return()=>ipcRenderer.removeListener('sion-event',fn);}
});
