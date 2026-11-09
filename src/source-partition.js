/* Exclusive source-pixel ownership. This is a neutral reconstruction study,
   not hidden-surface inpainting or a finished deformation model. */
(function(root){
  const ids=['rearHair','body','headBase','leftEye','rightEye','mouth','leftLock','rightLock'];
  const labels=['外围头发（原图）','躯干（原图）','头部（原图）','左眼区域（原图）','右眼区域（原图）','嘴部区域（原图）','左前发区域（原图）','右前发区域（原图）'];
  function owner(x,y){
    if(x>=385&&x<507&&y>=345&&y<465)return 3;
    if(x>=573&&x<685&&y>=345&&y<465)return 4;
    if(x>=520&&x<560&&y>=488&&y<526)return 5;
    if(((x-543)/325)**2+((y-285)/326)**2<=1)return 2;
    if(y>=440&&y<982&&x>=300&&x<420)return 6;
    if(y>=440&&y<982&&x>=618&&x<740)return 7;
    if(y>=550&&x>=350&&x<740)return 1;
    return 0;
  }
  function partition(width,height){
    const map=new Uint8Array(width*height);
    for(let y=0;y<height;y++)for(let x=0;x<width;x++)map[y*width+x]=owner((x+.5)*1086/width,(y+.5)*1448/height);
    return map;
  }
  function assemble(source,map,visible){
    const result=new Uint8ClampedArray(source.length);
    const src=new Uint32Array(source.buffer,source.byteOffset,source.byteLength/4);
    const dst=new Uint32Array(result.buffer);
    for(let i=0;i<map.length;i++)if(visible[map[i]])dst[i]=src[i];
    return result;
  }
  const api={ids,labels,owner,partition,assemble};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.SourcePartition=api;
})(typeof window!=='undefined'?window:globalThis);
