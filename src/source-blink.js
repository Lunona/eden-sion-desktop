/* A short closed-eye key avoids squeezing the original iris or bangs. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.SourceBlink=api;})(typeof window==='object'?window:globalThis,function(){
  function phase(elapsed){return elapsed>=45&&elapsed<145?0:1;}
  return {phase};
});
