/* Rendering of the exported MOC3 with official Cubism Core. No replacement art. */
class SionLive2D {
  constructor(canvas){this.canvas=canvas;this.frames=0;this.camera=[1882,3344,6688*1.04*canvas.width/canvas.height,6688*1.04];}
  async load(manifest){
    const data=await (await fetch(manifest)).json(),base=new URL('.',manifest);this.base=base;
    const bytes=await (await fetch(new URL(data.FileReferences.Moc,base))).arrayBuffer();
    this.moc=Live2DCubismCore.Moc.fromArrayBuffer(bytes);if(!this.moc)throw new Error('模型格式无法载入');
    this.model=Live2DCubismCore.Model.fromMoc(this.moc);if(!this.model)throw new Error('模型初始化失败');
    this.model.update();this.d=this.model.drawables;this.c=this.model.canvasinfo;
    if(this.model.offscreens.count)throw new Error('此模型含当前显示器不支持的离屏效果');
    this.roles=await (await fetch(new URL('网格触碰分类.json',base))).json();
    for(const id of this.d.ids){if(/^ArtMesh_Sion_0(?:39|40)/.test(id))this.roles[id]='footL';if(/^ArtMesh_Sion_0(?:35|36)/.test(id))this.roles[id]='footR';}
    const gl=this.gl=this.canvas.getContext('webgl',{alpha:true,premultipliedAlpha:true,antialias:true,preserveDrawingBuffer:true});if(!gl)throw new Error('无法启用角色显示');
    const vs=`attribute vec2 position;attribute vec2 texcoord;varying vec2 uv;varying vec2 screenpos;uniform vec2 origin;uniform float ppu;uniform vec4 camera;void main(){vec2 pixel=vec2(position.x*ppu+origin.x,origin.y-position.y*ppu);vec2 p=(pixel-camera.xy)*2.0/camera.zw;gl_Position=vec4(p.x,-p.y,0.,1.);uv=vec2(texcoord.x,1.-texcoord.y);screenpos=gl_Position.xy*.5+.5;}`;
    const fs=`precision mediump float;uniform sampler2D source;uniform sampler2D masktex;uniform bool masked;uniform bool maskpass;uniform bool inverted;uniform float opacity;uniform vec4 multiplyColor;uniform vec4 screenColor;varying vec2 uv;varying vec2 screenpos;void main(){vec4 c=texture2D(source,uv);if(maskpass){gl_FragColor=vec4(c.a);return;}c.rgb*=multiplyColor.rgb;c.rgb=c.rgb+screenColor.rgb-c.rgb*screenColor.rgb;c.a*=opacity;if(masked){float a=texture2D(masktex,screenpos).a;c.a*=inverted?1.-a:a;}c.rgb*=c.a;gl_FragColor=c;}`;
    const shader=(type,code)=>{const s=gl.createShader(type);gl.shaderSource(s,code);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(s));return s;};
    this.program=gl.createProgram();gl.attachShader(this.program,shader(gl.VERTEX_SHADER,vs));gl.attachShader(this.program,shader(gl.FRAGMENT_SHADER,fs));gl.linkProgram(this.program);if(!gl.getProgramParameter(this.program,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(this.program));gl.useProgram(this.program);
    this.u=Object.fromEntries(['origin','ppu','camera','source','masktex','masked','maskpass','inverted','opacity','multiplyColor','screenColor'].map(n=>[n,gl.getUniformLocation(this.program,n)]));this.a=['position','texcoord'].map(n=>gl.getAttribLocation(this.program,n));
    gl.uniform2f(this.u.origin,this.c.CanvasOriginX,this.c.CanvasOriginY);gl.uniform1f(this.u.ppu,this.c.PixelsPerUnit);gl.uniform4fv(this.u.camera,this.camera);gl.uniform1i(this.u.source,0);gl.uniform1i(this.u.masktex,1);
    this.alpha=[];this.textures=[];
    for(const rel of data.FileReferences.Textures){
      const im=new Image();im.src=new URL(rel,base).href;await im.decode();const tex=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,tex);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR_MIPMAP_LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,im);gl.generateMipmap(gl.TEXTURE_2D);this.textures.push(tex);
      const c=document.createElement('canvas');c.width=c.height=512;const x=c.getContext('2d',{willReadFrequently:true});x.drawImage(im,0,0,512,512);const rgba=x.getImageData(0,0,512,512).data,a=new Uint8Array(512*512);for(let i=0;i<a.length;i++)a[i]=rgba[i*4+3];this.alpha.push(a);im.src='';
    }
    this.buffers=this.d.ids.map((_,i)=>{const p=gl.createBuffer(),uv=gl.createBuffer(),indices=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,uv);gl.bufferData(gl.ARRAY_BUFFER,this.d.vertexUvs[i],gl.STATIC_DRAW);gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,indices);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,this.d.indices[i],gl.STATIC_DRAW);return {p,uv,indices};});
    this.masks=new Map();for(const group of this.d.masks){const key=Array.from(group).join(',');if(!key||this.masks.has(key))continue;const tex=gl.createTexture(),fb=gl.createFramebuffer();gl.bindTexture(gl.TEXTURE_2D,tex);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,this.canvas.width,this.canvas.height,0,gl.RGBA,gl.UNSIGNED_BYTE,null);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);gl.bindFramebuffer(gl.FRAMEBUFFER,fb);gl.framebufferTexture2D(gl.FRAMEBUFFER,gl.COLOR_ATTACHMENT0,gl.TEXTURE_2D,tex,0);if(gl.checkFramebufferStatus(gl.FRAMEBUFFER)!==gl.FRAMEBUFFER_COMPLETE)throw new Error('遮罩初始化失败');this.masks.set(key,{tex,fb,group});}
    gl.disable(gl.DEPTH_TEST);gl.disable(gl.CULL_FACE);gl.enable(gl.BLEND);this.ready=true;this.apply({});
    const p=this.model.parameters;return p.ids.map((id,i)=>({id,minimum:p.minimumValues[i],maximum:p.maximumValues[i],default:p.defaultValues[i]}));
  }
  apply(values){
    if(!this.ready)return;const p=this.model.parameters;for(let i=0;i<p.count;i++)if(Number.isFinite(values[p.ids[i]]))p.values[i]=Math.max(p.minimumValues[i],Math.min(p.maximumValues[i],values[p.ids[i]]));this.model.update();this.draw();
  }
  drawOne(i,mask=false){const gl=this.gl,d=this.d,b=this.buffers[i];gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,this.textures[d.textureIndices[i]]);gl.uniform1i(this.u.maskpass,mask);gl.uniform1i(this.u.masked,!mask&&d.maskCounts[i]>0);gl.uniform1i(this.u.inverted,Live2DCubismCore.Utils.hasIsInvertedMaskBit(d.constantFlags[i]));gl.uniform1f(this.u.opacity,mask?1:d.opacities[i]);gl.uniform4fv(this.u.multiplyColor,d.multiplyColors.subarray(i*4,i*4+4));gl.uniform4fv(this.u.screenColor,d.screenColors.subarray(i*4,i*4+4));
    if(!mask&&d.maskCounts[i]){gl.activeTexture(gl.TEXTURE1);gl.bindTexture(gl.TEXTURE_2D,this.masks.get(Array.from(d.masks[i]).join(',')).tex);}
    for(const [j,buffer] of [b.p,b.uv].entries()){gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.enableVertexAttribArray(this.a[j]);gl.vertexAttribPointer(this.a[j],2,gl.FLOAT,false,0,0);}gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,b.indices);gl.drawElements(gl.TRIANGLES,d.indexCounts[i],gl.UNSIGNED_SHORT,0);
  }
  syncRenderOrder(){
    const orders=this.model.getRenderOrders();
    if(this.renderOrders?.every((value,index)=>value===orders[index]))return;
    this.renderOrders=orders.slice(0,this.d.count);
    this.order=Array.from({length:this.d.count},(_,index)=>index).sort((a,b)=>orders[a]-orders[b]);
  }
  draw(){const gl=this.gl;gl.useProgram(this.program);gl.viewport(0,0,this.canvas.width,this.canvas.height);gl.blendFunc(gl.ONE,gl.ONE_MINUS_SRC_ALPHA);
    for(let i=0;i<this.d.count;i++){
      gl.bindBuffer(gl.ARRAY_BUFFER,this.buffers[i].p);
      gl.bufferData(gl.ARRAY_BUFFER,this.d.vertexPositions[i],gl.DYNAMIC_DRAW);
    }
    // A previous color pass can leave a mask texture bound while it becomes a render target.
    gl.activeTexture(gl.TEXTURE1);gl.bindTexture(gl.TEXTURE_2D,null);
    for(const {fb,group} of this.masks.values()){gl.bindFramebuffer(gl.FRAMEBUFFER,fb);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);for(const i of group)this.drawOne(i,true);}
    gl.bindFramebuffer(gl.FRAMEBUFFER,null);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);this.syncRenderOrder();
    for(const i of this.order){if(this.d.opacities[i]<.0001)continue;const f=this.d.constantFlags[i];gl.blendFunc(Live2DCubismCore.Utils.hasBlendMultiplicativeBit(f)?gl.DST_COLOR:gl.ONE,Live2DCubismCore.Utils.hasBlendAdditiveBit(f)?gl.ONE:gl.ONE_MINUS_SRC_ALPHA);this.drawOne(i);}
    this.frames++;this.d.resetDynamicFlags();
  }
  sourcePoint(x,y){return [this.camera[0]+(x-.5)*this.camera[2],this.camera[1]+(y-.5)*this.camera[3]];}
  alphaHit(i,x,y){const d=this.d,p=d.vertexPositions[i],uv=d.vertexUvs[i],idx=d.indices[i];for(let n=0;n<idx.length;n+=3){const a=idx[n]*2,b=idx[n+1]*2,c=idx[n+2]*2,ax=p[b]-p[a],ay=p[b+1]-p[a+1],bx=p[c]-p[a],by=p[c+1]-p[a+1],den=ax*by-ay*bx;if(Math.abs(den)<1e-10)continue;const u=((x-p[a])*by-(y-p[a+1])*bx)/den,v=(ax*(y-p[a+1])-ay*(x-p[a]))/den;if(u<0||v<0||u+v>1)continue;const tx=uv[a]*(1-u-v)+uv[b]*u+uv[c]*v,ty=uv[a+1]*(1-u-v)+uv[b+1]*u+uv[c+1]*v;if(this.alpha[d.textureIndices[i]][Math.max(0,Math.min(511,Math.floor((1-ty)*512)))*512+Math.max(0,Math.min(511,Math.floor(tx*512)))]>70)return true;}return false;}
  zone(nx,ny){if(!this.ready)return null;const [sx,sy]=this.sourcePoint(nx,ny),x=(sx-this.c.CanvasOriginX)/this.c.PixelsPerUnit,y=(this.c.CanvasOriginY-sy)/this.c.PixelsPerUnit;
    for(const i of [...this.order].reverse()){if(this.d.opacities[i]<.2||!this.alphaHit(i,x,y))continue;const masks=this.d.masks[i];if(masks.length&&!Array.from(masks).some(j=>this.alphaHit(j,x,y)))continue;let role=this.roles[this.d.ids[i]];if(!role)continue;if(role==='hair'&&sy<1250)return 'head';if(role==='hair')return sx<1882?'hairL':'hairR';if(role==='face')return sx<1882?'faceL':'faceR';if(role==='cloth'&&sy<1900&&sy>1350&&Math.abs(sx-1882)>232)return sx<1882?'shoulderL':'shoulderR';return role;}
    return null;
  }
  pixels(){const data=new Uint8Array(this.canvas.width*this.canvas.height*4);this.gl.readPixels(0,0,this.canvas.width,this.canvas.height,this.gl.RGBA,this.gl.UNSIGNED_BYTE,data);return data;}
}
window.SionLive2D=SionLive2D;
