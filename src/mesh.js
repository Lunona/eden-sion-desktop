/* A small original 2D mesh renderer. No Cubism runtime or model file required. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.SionMesh=api;})(typeof window==='object'?window:globalThis,function(){
  const clamp=(n,a,b)=>Math.max(a,Math.min(b,n));
  function deform(u,v,pose,time=0,enabled=true){
    if(!enabled)return [u,v];
    const x=clamp(pose.x||0,-1,1),y=clamp(pose.y||0,-1,1),aspect=.5625;
    // Soft continuous weights avoid tearing a flattened picture into rigid pieces.
    const head=Math.exp(-(((u-.37)/.24)**2+((v-.145)/.14)**2)*1.6);
    const torso=Math.exp(-(((u-.45)/.34)**2+((v-.38)/.22)**2));
    const hair=clamp((u-.48)/.32,0,1)*Math.exp(-(((v-.29)/.24)**2));
    const anchor=1-clamp((v-.78)/.16,0,1);
    const angle=x*.060+Math.sin(time*.85)*.004;
    const dx=(u-.37)*aspect,dy=v-.19,c=Math.cos(angle),s=Math.sin(angle);
    const turnX=(dx*c-dy*s-dx)/aspect,turnY=dx*s+dy*c-dy;
    const breath=Math.sin(time*1.45)*.0018;
    return [u+anchor*(head*(turnX+x*.005)+torso*x*.004+hair*Math.sin(time*1.6+v*9)*.0025),
      v+anchor*(head*(turnY+y*.004)-torso*breath+hair*Math.sin(time*1.35+v*7)*.001)];
  }
  class Renderer{
    constructor(canvas){
      this.canvas=canvas;this.frames=0;this.textureCount=0;this.textures=new Map();this.columns=24;this.rows=40;
      const gl=this.gl=canvas.getContext('webgl',{alpha:true,premultipliedAlpha:true,antialias:true,preserveDrawingBuffer:true});
      if(!gl){this.ctx=canvas.getContext('2d');this.mode='canvas-fallback';return;}
      this.mode='webgl-mesh';
      const compile=(type,source)=>{const shader=gl.createShader(type);gl.shaderSource(shader,source);gl.compileShader(shader);if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(shader));return shader;};
      const vertex=compile(gl.VERTEX_SHADER,'attribute vec2 aPosition;attribute vec2 aUV;varying vec2 vUV;void main(){gl_Position=vec4(aPosition,0.,1.);vUV=aUV;}');
      const fragment=compile(gl.FRAGMENT_SHADER,'precision mediump float;varying vec2 vUV;uniform sampler2D uImage;void main(){gl_FragColor=texture2D(uImage,vUV);}');
      const program=this.program=gl.createProgram();gl.attachShader(program,vertex);gl.attachShader(program,fragment);gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(program));gl.useProgram(program);
      const count=(this.columns+1)*(this.rows+1);this.positions=new Float32Array(count*2);this.uv=new Float32Array(count*2);
      for(let row=0;row<=this.rows;row++)for(let col=0;col<=this.columns;col++){const i=(row*(this.columns+1)+col)*2;this.uv[i]=col/this.columns;this.uv[i+1]=row/this.rows;}
      const indices=[];for(let row=0;row<this.rows;row++)for(let col=0;col<this.columns;col++){const a=row*(this.columns+1)+col,b=a+1,c=a+this.columns+1,d=c+1;indices.push(a,b,c,b,d,c);}this.indexCount=indices.length;
      this.positionBuffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,this.positionBuffer);gl.bufferData(gl.ARRAY_BUFFER,this.positions,gl.DYNAMIC_DRAW);const p=gl.getAttribLocation(program,'aPosition');gl.enableVertexAttribArray(p);gl.vertexAttribPointer(p,2,gl.FLOAT,false,0,0);
      const uvBuffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,uvBuffer);gl.bufferData(gl.ARRAY_BUFFER,this.uv,gl.STATIC_DRAW);const a=gl.getAttribLocation(program,'aUV');gl.enableVertexAttribArray(a);gl.vertexAttribPointer(a,2,gl.FLOAT,false,0,0);
      const indexBuffer=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,indexBuffer);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,new Uint16Array(indices),gl.STATIC_DRAW);
      gl.enable(gl.BLEND);gl.blendFunc(gl.ONE,gl.ONE_MINUS_SRC_ALPHA);gl.clearColor(0,0,0,0);
      canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();this.lost=true;});canvas.addEventListener('webglcontextrestored',()=>location.reload());
    }
    draw(image,pose,time,enabled){
      if(this.lost)return;const w=this.canvas.width,h=this.canvas.height,pad=14;
      const scale=Math.min((w-pad*2)/image.naturalWidth,(h-pad*2)/image.naturalHeight),iw=image.naturalWidth*scale,ih=image.naturalHeight*scale,left=(w-iw)/2,top=h-ih-pad;
      if(!this.gl){this.ctx.clearRect(0,0,w,h);this.ctx.drawImage(image,left,top,iw,ih);this.frames++;return;}
      const gl=this.gl;let texture=this.textures.get(image);
      if(!texture){texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,texture);gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL,true);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,image);this.textures.set(image,texture);
        // Bound memory if the user repeatedly imports replacement artwork.
        if(this.textures.size>8){const oldest=this.textures.keys().next().value;gl.deleteTexture(this.textures.get(oldest));this.textures.delete(oldest);}}
      gl.bindTexture(gl.TEXTURE_2D,texture);
      for(let i=0;i<this.uv.length;i+=2){const point=deform(this.uv[i],this.uv[i+1],pose,time,enabled);this.positions[i]=(left+point[0]*iw)/w*2-1;this.positions[i+1]=1-(top+point[1]*ih)/h*2;}
      gl.viewport(0,0,w,h);gl.clear(gl.COLOR_BUFFER_BIT);gl.bindBuffer(gl.ARRAY_BUFFER,this.positionBuffer);gl.bufferSubData(gl.ARRAY_BUFFER,0,this.positions);gl.drawElements(gl.TRIANGLES,this.indexCount,gl.UNSIGNED_SHORT,0);this.frames++;
    }
    pixels(){if(this.gl){const pixels=new Uint8Array(this.canvas.width*this.canvas.height*4);this.gl.readPixels(0,0,this.canvas.width,this.canvas.height,this.gl.RGBA,this.gl.UNSIGNED_BYTE,pixels);return pixels;}return this.ctx.getImageData(0,0,this.canvas.width,this.canvas.height).data;}
    stats(){return {mode:this.mode,frames:this.frames,vertices:(this.columns+1)*(this.rows+1),triangles:this.indexCount/3,textures:this.textures.size,lost:!!this.lost};}
  }
  return {deform,Renderer};
});
