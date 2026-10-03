import * as THREE from 'three';
import {buildPaintBoundaries} from './paint-boundaries.js';

// Paint is a temporary color layer; only Apply sends pixels to the saved design.
export function createSurfacePaint({canvas,controls,camera,root,surface,selected,group,notify,changed}) {
 const bar=document.createElement('div');
 bar.className='paint-palette';
 const style=document.createElement('style');style.textContent=`
 .paint-palette{position:fixed;bottom:38px;left:12px;z-index:30;width:248px;max-height:calc(100vh - 100px);overflow:auto;background:#0d222df5;padding:14px;border:1px solid #3a6170;border-radius:12px;color:#e9f1f2;font:12px 'Segoe UI',sans-serif;box-shadow:0 8px 28px #0006}
 .paint-palette [data-tools]:not([hidden]){display:flex;flex-direction:column;gap:10px;margin-top:12px}
 .paint-palette label{margin:0;display:flex;align-items:center;justify-content:space-between;gap:8px}
 .paint-palette input[type=range]{width:115px;accent-color:#5dc6d1}
 .paint-palette input[type=color]{width:42px;height:30px;border:0;background:none}
 .paint-palette button{padding:8px 10px;font-size:12px}.paint-palette [data-action=start]{width:100%;text-align:left;font-weight:600}
 .paint-palette [data-action=apply]{background:#217646;border-color:#349d61}.paint-palette [data-status]{display:block;color:#9db7c1;font-size:11px;line-height:1.4;margin-top:10px}
 .paint-palette details{border-top:1px solid #35515e;padding-top:10px;margin-top:10px}.paint-palette details p{line-height:1.65;color:#b6cbd2}.paint-palette [data-tools]>span{display:grid;gap:10px}
 `;document.head.append(style);
 bar.innerHTML='<button data-action="start">Paint selected texture</button><span data-tools hidden><input aria-label="Brush color" type="color" value="#151515"> <label>Size <input aria-label="Brush size" type="range" min="2" max="160" value="24"></label> <button data-action="undo">Undo · Ctrl+Z</button><button data-action="redo">Redo · Ctrl+Shift+Z</button> <button data-action="apply">Apply paint</button> <button data-action="cancel">Cancel</button></span><span data-status></span><details><summary>Keyboard &amp; mouse</summary><p>B: Brush<br>[ / ]: Size<br>Shift+[ / ]: Hardness<br>1–9 / 0: Opacity<br>Alt-click: Sample color<br>Alt+right drag: Size / hardness<br>Space-drag: Pan<br>Ctrl+Space-drag: Orbit<br>Wheel: Zoom<br>Ctrl+Z: Undo<br>Ctrl+Shift+Z or Ctrl+Y: Redo</p></details>';
 document.body.append(bar);
 const status=bar.querySelector('[data-status]'),tool=bar.querySelector('[data-tools]');
 let active=null,drawing=false,last=null,history=[],redo=[],brushImage=null;
 let navigating=false,hover=null,space=false,hud=null,hardness=1,opacity=1,lastDigitTime=0,digits="";
 const cursor=document.createElementNS('http://www.w3.org/2000/svg','svg');
 cursor.setAttribute('aria-hidden','true');cursor.dataset.paintCursor='true';
 cursor.style.cssText='position:fixed;inset:0;width:100vw;height:100vh;pointer-events:none;z-index:25;display:none';
 cursor.innerHTML='<path fill="none" stroke="black" stroke-width="3"/><path fill="none" stroke="white" stroke-width="1"/>';
 document.body.append(cursor);
 const radius=()=>+bar.querySelector('[type=range]').value;
 const settings=document.createElement('span');settings.innerHTML='<label>Hardness <input data-hardness type="range" min="0" max="100" value="100"></label><label>Opacity <input data-opacity type="range" min="1" max="100" value="100"></label>';tool.append(settings);
 settings.querySelector('[data-hardness]').oninput=e=>hardness=+e.target.value/100;
 settings.querySelector('[data-opacity]').oninput=e=>opacity=+e.target.value/100;
 function syncBrush(){settings.querySelector('[data-hardness]').value=Math.round(hardness*100);settings.querySelector('[data-opacity]').value=Math.round(opacity*100);if(hover)showCursor(hover)}
 function sample(e){const picked=pick(e);if(!picked)return;const uv=picked.hit.uv.clone();picked.target.texture.transformUv(uv);const p=active.ctx.getImageData(Math.min(active.work.width-1,Math.floor(uv.x*active.work.width)),Math.min(active.work.height-1,Math.floor(uv.y*active.work.height)),1,1).data;bar.querySelector('[type=color]').value='#'+[...p.slice(0,3)].map(x=>x.toString(16).padStart(2,'0')).join('')}

 function hideCursor(){cursor.style.display='none';canvas.style.cursor=''}
 function pick(e){
  const rect=canvas.getBoundingClientRect();point.set((e.clientX-rect.left)/rect.width*2-1,1-(e.clientY-rect.top)/rect.height*2);ray.setFromCamera(point,camera);
  const hit=root()&&ray.intersectObject(root(),true)[0],s=hit&&surface(hit.object),target=active?.targets.find(x=>x.s===s);
  return target&&hit.uv?{hit,target,rect}:null;
 }
 function showCursor(e){
  hover=e;if(!active||navigating||e.altKey){hideCursor();return}
  const picked=pick(e);if(!picked){hideCursor();canvas.style.cursor='not-allowed';return}
  const {hit,target,rect}=picked,g=hit.object.geometry,ids=[hit.face.a,hit.face.b,hit.face.c];
  const vertices=ids.map(i=>new THREE.Vector3().fromBufferAttribute(g.attributes.position,i).applyMatrix4(hit.object.matrixWorld));
  target.texture.updateMatrix();
  const uvs=ids.map(i=>{const uv=new THREE.Vector2().fromBufferAttribute(g.attributes.uv,i);target.texture.transformUv(uv);return uv.multiply(new THREE.Vector2(active.work.width,active.work.height))});
  const a=uvs[1].clone().sub(uvs[0]),b=uvs[2].clone().sub(uvs[0]),det=a.x*b.y-a.y*b.x;
  if(Math.abs(det)<1e-8){hideCursor();return}
  const edgeA=vertices[1].clone().sub(vertices[0]),edgeB=vertices[2].clone().sub(vertices[0]);
  const du=edgeA.clone().multiplyScalar(b.y/det).addScaledVector(edgeB,-a.y/det),dv=edgeA.clone().multiplyScalar(-b.x/det).addScaledVector(edgeB,a.x/det);
  const points=[];for(let i=0;i<48;i++){const angle=i*Math.PI/24,p=hit.point.clone().addScaledVector(du,Math.cos(angle)*radius()).addScaledVector(dv,Math.sin(angle)*radius()).project(camera);points.push(`${rect.left+(p.x+1)*rect.width/2},${rect.top+(1-p.y)*rect.height/2}`)}
  const path='M'+points.join(' L')+' Z';for(const p of cursor.children)p.setAttribute('d',path);cursor.style.display='block';canvas.style.cursor='none';
 }
 controls.addEventListener('change',()=>{if(hover&&active&&!navigating)showCursor(hover)});
 bar.querySelector('[type=range]').addEventListener('input',()=>{if(hover)showCursor(hover)});
 const brushFile=document.createElement('input');brushFile.type='file';brushFile.accept='image/png';brushFile.setAttribute('aria-label','Brush PNG');brushFile.style.maxWidth='160px';tool.prepend(brushFile);
 brushFile.addEventListener('change',async()=>{const file=brushFile.files[0];if(!file){brushImage=null;return}try{const next=await createImageBitmap(file);brushImage?.close?.();brushImage=next;status.textContent='PNG brush ready.'}catch{status.textContent='Could not load brush PNG.'}});
 const solid=document.createElement('button');solid.textContent='Use color brush';solid.onclick=()=>{brushImage?.close?.();brushImage=null;brushFile.value=''};tool.prepend(solid);
 const ray=new THREE.Raycaster(),point=new THREE.Vector2();
 function finish(){if(!active)return;for(const x of active.targets){x.s.current.map=x.map;x.s.current.color.copy(x.color);x.texture.dispose()}active=null;drawing=false;navigating=false;hideCursor();controls.enabled=true;tool.hidden=true;history=[];changed()}
 function start(){
  finish();const s=selected();if(!s?.current.map?.image){status.textContent='Select a textured surface first.';return}
  const targets=group(s).filter(x=>x.materialId===s.materialId),image=s.current.map.image;
  const work=document.createElement('canvas');work.width=image.width;work.height=image.height;
  const ctx=work.getContext('2d',{willReadFrequently:true});ctx.drawImage(image,0,0);
  // Bake the existing material color once; the saved paint uses a neutral tint.
  const pixels=ctx.getImageData(0,0,work.width,work.height),rgb=s.current.color;
  const linear=x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4;
  const srgb=x=>x<=.0031308?12.92*x:1.055*x**(1/2.4)-.055;
  for(let i=0;i<pixels.data.length;i+=4)for(let c=0;c<3;c++)pixels.data[i+c]=Math.round(255*srgb(linear(pixels.data[i+c]/255)*[rgb.r,rgb.g,rgb.b][c]));
  ctx.putImageData(pixels,0,0);
  active={s,work,ctx,targets:targets.map(s=>{const map=s.current.map,color=s.current.color.clone(),texture=map.clone();texture.image=work;texture.needsUpdate=true;s.current.map=texture;s.current.color.set(0xffffff);return {s,map,color,texture}})};
  active.boundaries=buildPaintBoundaries(active.targets,work.width,work.height);
  redo=[];tool.hidden=false;status.textContent='Selected surface only';controls.enabled=true;changed();
 }
 function stamp(e){
  const rect=canvas.getBoundingClientRect();point.set((e.clientX-rect.left)/rect.width*2-1,1-(e.clientY-rect.top)/rect.height*2);ray.setFromCamera(point,camera);
  const hit=ray.intersectObject(root(),true)[0],s=hit&&surface(hit.object);
  const target=active.targets.find(x=>x.s===s);if(!target||!hit.uv){last=null;return}
  const uv=hit.uv.clone();target.texture.updateMatrix();target.texture.transformUv(uv);
  const x=uv.x*active.work.width,y=uv.y*active.work.height,r=+bar.querySelector('[type=range]').value;
  const ctx=active.ctx,color=bar.querySelector('[type=color]').value;ctx.fillStyle=color;
  const g=hit.object.geometry,ids=[hit.face.a,hit.face.b,hit.face.c],vs=ids.map(i=>new THREE.Vector3().fromBufferAttribute(g.attributes.position,i).applyMatrix4(hit.object.matrixWorld));
  const ts=ids.map(i=>{const p=new THREE.Vector2().fromBufferAttribute(g.attributes.uv,i);target.texture.transformUv(p);return p.multiply(new THREE.Vector2(active.work.width,active.work.height))});
  const a=ts[1].clone().sub(ts[0]),b=ts[2].clone().sub(ts[0]),det=a.x*b.y-a.y*b.x;if(Math.abs(det)<1e-7)return;
  const va=vs[1].clone().sub(vs[0]),vb=vs[2].clone().sub(vs[0]),du=va.clone().multiplyScalar(b.y/det).addScaledVector(vb,-a.y/det),dv=va.clone().multiplyScalar(-b.x/det).addScaledVector(vb,a.x/det);
  const worldRadius=r*(du.length()+dv.length())*1.05;

  const distance=last?Math.hypot(x-last.x,y-last.y):0;
  const steps=last&&distance<r*12?Math.ceil(distance/Math.max(1,r/3)):0;
  for(let i=0;i<=steps;i++){const t=steps?i/steps:1,px=last&&steps?last.x+(x-last.x)*t:x,py=last&&steps?last.y+(y-last.y)*t:y;ctx.save();const allowed=active.boundaries.clip(ctx,px,py,r,hit.point,worldRadius);if(!allowed){ctx.restore();status.textContent='Protected UV overlap or outside selected surface.';continue}ctx.globalAlpha=opacity;ctx.beginPath();ctx.arc(px,py,r,0,Math.PI*2);if(brushImage){ctx.clip();ctx.drawImage(brushImage,px-r,py-r,r*2,r*2)}else {if(hardness<1){const fade=ctx.createRadialGradient(px,py,r*hardness,px,py,r);fade.addColorStop(0,color);fade.addColorStop(1,color+'00');ctx.fillStyle=fade}else ctx.fillStyle=color;ctx.fill()}ctx.restore()}
  last={x,y};for(const x of active.targets)x.texture.needsUpdate=true;changed();
 }
 canvas.addEventListener('pointerdown',e=>{if(!active)return;if(e.altKey&&e.button===2){e.stopImmediatePropagation();e.preventDefault();hud={x:e.clientX,y:e.clientY,size:radius(),hardness};if(e.isTrusted)canvas.setPointerCapture(e.pointerId);return}if(e.altKey&&e.button===0&&!space){e.stopImmediatePropagation();e.preventDefault();sample(e);return}if(e.button!==0||space){controls.mouseButtons.LEFT=e.ctrlKey?THREE.MOUSE.ROTATE:THREE.MOUSE.PAN;navigating=true;hideCursor();return}e.stopImmediatePropagation();e.preventDefault();if(!pick(e))return;if(e.isTrusted)canvas.setPointerCapture(e.pointerId);controls.enabled=false;redo=[];history.push(active.ctx.getImageData(0,0,active.work.width,active.work.height));if(history.length>Math.max(1,Math.min(20,Math.floor(67108864/(active.work.width*active.work.height*4)))))history.shift();drawing=true;last=null;stamp(e);showCursor(e)},true);
 canvas.addEventListener('pointermove',e=>{if(!active)return;if(hud){e.stopImmediatePropagation();const input=bar.querySelector('[type=range]');input.value=Math.max(+input.min,Math.min(+input.max,hud.size+(e.clientX-hud.x)/2));hardness=Math.max(0,Math.min(1,hud.hardness-(e.clientY-hud.y)/100));syncBrush();return}if(drawing){e.stopImmediatePropagation();stamp(e)}showCursor(e)},true);
 canvas.addEventListener('pointerup',e=>{if(!active)return;if(drawing||hud||e.altKey&&!navigating)e.stopImmediatePropagation();hud=null;drawing=false;navigating=false;last=null;controls.mouseButtons.LEFT=THREE.MOUSE.ROTATE;controls.enabled=true;showCursor(e)},true);
 canvas.addEventListener('pointercancel',()=>{drawing=false;navigating=false;last=null;controls.enabled=true;hideCursor()},true);
 canvas.addEventListener('pointerleave',hideCursor);
 window.addEventListener('blur',()=>{drawing=false;navigating=false;last=null;controls.enabled=true;hideCursor()});
 window.addEventListener('keydown',e=>{
  if(/INPUT|TEXTAREA|SELECT/.test(e.target.tagName))return;
  if(e.key.toLowerCase()==='b'&&!e.ctrlKey&&!e.altKey){e.preventDefault();if(!active)start();return}if(!active)return;
  if(e.code==='Space'){e.preventDefault();space=true;hideCursor();return}
  if((e.ctrlKey||e.metaKey)&&['z','y'].includes(e.key.toLowerCase())){e.preventDefault();bar.querySelector('[data-action='+((e.shiftKey||e.key.toLowerCase()==='y')?'redo':'undo')+']').click();return}
  if(e.key==='Alt'){hideCursor();canvas.style.cursor='crosshair'}
  if(e.code==='BracketLeft'||e.code==='BracketRight'){
   e.preventDefault();const direction=e.code==='BracketRight'?1:-1;
   if(e.shiftKey)hardness=Math.max(0,Math.min(1,hardness+direction*.25));else{const input=bar.querySelector('[type=range]');input.value=Math.max(+input.min,Math.min(+input.max,+input.value+direction*2))}syncBrush();
  }
  if(/^[0-9]$/.test(e.key)&&!e.ctrlKey&&!e.altKey){e.preventDefault();const now=performance.now();digits=now-lastDigitTime<500?(digits+e.key).slice(-2):e.key;lastDigitTime=now;opacity=(digits.length===1?(+digits||10)*10:(+digits||100))/100;syncBrush()}
 });
 window.addEventListener('keyup',e=>{if(e.code==='Space'){space=false;if(!navigating)controls.mouseButtons.LEFT=THREE.MOUSE.ROTATE}if(active&&hover&&!space)showCursor({...hover,clientX:hover.clientX,clientY:hover.clientY,altKey:e.altKey})});
 window.addEventListener('blur',()=>{space=false;hud=null;controls.mouseButtons.LEFT=THREE.MOUSE.ROTATE});
 canvas.addEventListener('contextmenu',e=>{if(active)e.preventDefault()});
 bar.addEventListener('click',e=>{
  const action=e.target.dataset.action;
  if(action==='start')start();
  if(action==='cancel'){finish();status.textContent='Paint cancelled.'}
  if(action==='undo'&&active&&history.length){redo.push(active.ctx.getImageData(0,0,active.work.width,active.work.height));active.ctx.putImageData(history.pop(),0,0);for(const x of active.targets)x.texture.needsUpdate=true;changed()}
  if(action==='redo'&&active&&redo.length){history.push(active.ctx.getImageData(0,0,active.work.width,active.work.height));active.ctx.putImageData(redo.pop(),0,0);for(const x of active.targets)x.texture.needsUpdate=true;changed()}
  if(action==='apply'&&active){
   const output=document.createElement('canvas');output.width=active.work.width;output.height=active.work.height;const ctx=output.getContext('2d');
   if(active.s.materialId==='2296875182504'&&!active.targets[0].map.flipY){ctx.translate(0,output.height);ctx.scale(1,-1)}
   ctx.drawImage(active.work,0,0);const key=active.s.key,png=output.toDataURL('image/png');finish();notify({type:'paint-applied',key,png});status.textContent='Paint sent to design.';
  }
 });
 return {get active(){return !!active},cancel:finish};
}
