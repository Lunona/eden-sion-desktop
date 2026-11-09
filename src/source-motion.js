/* Gentle motion of one continuous source texture. No new facial artwork.
   This is not an independently layered eye/mouth rig or a Cubism model. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.SourceMotion=api;})(typeof window==='object'?window:globalThis,function(){
  const clamp=n=>Math.max(0,Math.min(1,n));
  const smooth=(a,b,n)=>{const t=clamp((n-a)/(b-a));return t*t*(3-2*t);};
  function deform(u,v,p){
    const z=Math.max(-1,Math.min(1,p.headZ||0))*.025;
    const head=(1-smooth(.185,.275,v))*(1-smooth(.24,.40,Math.abs(u-.51)));
    const aspect=.5625,dx=(u-.51)*aspect,dy=v-.23,c=Math.cos(z),s=Math.sin(z);
    const breath=(p.body||0)*.0010*(1-smooth(.50,.80,v));
    const edge=smooth(0,.035,u)*(1-smooth(.965,1,u));
    const hair=smooth(.13,.30,Math.abs(u-.51))*smooth(.16,.34,v)*(1-smooth(.55,.65,v))*edge;
    return [u+head*((dx*c-dy*s-dx)/aspect+(p.headX||0)*.0014)+hair*(p.hair||0)*.0032,
      v+head*(dx*s+dy*c-dy+(p.headY||0)*.001)-breath];
  }
  function active(p){return ['headX','headY','headZ','body','hair'].some(k=>Math.abs(p[k]||0)>1e-7);}
  class Renderer{
    constructor(){
      this.canvas=document.createElement('canvas');this.canvas.width=720;this.canvas.height=1280;
      const gl=this.gl=this.canvas.getContext('webgl',{alpha:true,premultipliedAlpha:true,antialias:false,preserveDrawingBuffer:true});
      if(!gl)throw new Error('显卡未提供 WebGL，微动已停用；可继续查看静止还原。');
      const compile=(kind,code)=>{const shader=gl.createShader(kind);gl.shaderSource(shader,code);gl.compileShader(shader);if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(shader));return shader;};
      const program=gl.createProgram();gl.attachShader(program,compile(gl.VERTEX_SHADER,'attribute vec2 position;attribute vec2 uv;varying vec2 tex;void main(){tex=uv;gl_Position=vec4(position,0.,1.);}'));
      gl.attachShader(program,compile(gl.FRAGMENT_SHADER,'precision highp float;varying vec2 tex;uniform sampler2D image;void main(){gl_FragColor=texture2D(image,tex);}'));gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(program));gl.useProgram(program);
      this.cols=48;this.rows=64;this.uv=new Float32Array((this.cols+1)*(this.rows+1)*2);this.positions=new Float32Array(this.uv.length);
      for(let y=0;y<=this.rows;y++)for(let x=0;x<=this.cols;x++){const i=(y*(this.cols+1)+x)*2;this.uv[i]=x/this.cols;this.uv[i+1]=y/this.rows;}
      const indices=[];for(let y=0;y<this.rows;y++)for(let x=0;x<this.cols;x++){const a=y*(this.cols+1)+x,b=a+1,c=a+this.cols+1,d=c+1;indices.push(a,b,c,b,d,c);}this.count=indices.length;
      this.positionBuffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,this.positionBuffer);gl.bufferData(gl.ARRAY_BUFFER,this.positions,gl.DYNAMIC_DRAW);const pos=gl.getAttribLocation(program,'position');gl.enableVertexAttribArray(pos);gl.vertexAttribPointer(pos,2,gl.FLOAT,false,0,0);
      const uvBuffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,uvBuffer);gl.bufferData(gl.ARRAY_BUFFER,this.uv,gl.STATIC_DRAW);const uv=gl.getAttribLocation(program,'uv');gl.enableVertexAttribArray(uv);gl.vertexAttribPointer(uv,2,gl.FLOAT,false,0,0);
      const indexBuffer=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,indexBuffer);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,new Uint16Array(indices),gl.STATIC_DRAW);
      this.texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,this.texture);gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL,true);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
      gl.enable(gl.BLEND);gl.blendFunc(gl.ONE,gl.ONE_MINUS_SRC_ALPHA);gl.clearColor(0,0,0,0);this.uploadKey=null;this.lost=false;
      this.canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();this.lost=true;});
    }
    draw(source,key,p,width,height,patches=[]){
      if(this.lost)throw new Error('显卡上下文丢失，微动已停用。');
      const gl=this.gl;if(this.canvas.width!==width||this.canvas.height!==height){this.canvas.width=width;this.canvas.height=height;}
      gl.bindTexture(gl.TEXTURE_2D,this.texture);if(this.uploadKey!==key){gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,source);this.uploadKey=key;}
      else for(const patch of patches)gl.texSubImage2D(gl.TEXTURE_2D,0,patch.x,patch.y,gl.RGBA,gl.UNSIGNED_BYTE,patch.canvas);
      for(let i=0;i<this.uv.length;i+=2){const point=deform(this.uv[i],this.uv[i+1],p);this.positions[i]=point[0]*2-1;this.positions[i+1]=1-point[1]*2;}
      gl.viewport(0,0,width,height);gl.clear(gl.COLOR_BUFFER_BIT);gl.bindBuffer(gl.ARRAY_BUFFER,this.positionBuffer);gl.bufferSubData(gl.ARRAY_BUFFER,0,this.positions);gl.drawElements(gl.TRIANGLES,this.count,gl.UNSIGNED_SHORT,0);
      return this.canvas;
    }
  }
  return {deform,active,Renderer};
});
