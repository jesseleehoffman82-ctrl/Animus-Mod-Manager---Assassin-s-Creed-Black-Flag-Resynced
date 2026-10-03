import * as THREE from 'three';

// Edits own only the visible color layer. The material's other maps stay attached.
export function composeDesign(original, design) {
  const width=original?.image?.width||design.image.width;
  const height=original?.image?.height||design.image.height;
  const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
  const ctx=canvas.getContext('2d');
  if(original?.image)ctx.drawImage(original.image,0,0,width,height);
  else{ctx.fillStyle='#ffffff';ctx.fillRect(0,0,width,height)}
  ctx.drawImage(design.image,0,0,width,height);
  const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace;
  texture.flipY=false;
  if(original){texture.wrapS=original.wrapS;texture.wrapT=original.wrapT;texture.offset.copy(original.offset);texture.repeat.copy(original.repeat);texture.center.copy(original.center);texture.rotation=original.rotation;texture.channel=original.channel;texture.anisotropy=original.anisotropy}
  return texture;
}
export function setFinishColor(surface,hex){
  if(!/^#[0-9a-f]{6}$/i.test(hex))throw new Error('Choose a valid color.');
  surface.tint=hex;surface.current.color.copy(surface.original.color).multiply(new THREE.Color(hex));
}
export function setFinishDesign(surface,design){
  const next=composeDesign(surface.original.map,design);surface.designMap?.dispose();
  surface.designMap=next;surface.current.map=next;surface.current.needsUpdate=true;
}
export function resetFinish(surface){
  surface.designMap?.dispose();surface.designMap=null;surface.current.map=surface.original.map;
  setFinishColor(surface,'#ffffff');surface.current.needsUpdate=true;
}
export function finishName(label=''){
  if(/Sail|BaseAtlas|PT_Jackdaw/.test(label))return 'Canvas';
  if(/Carriage/.test(label))return 'Carriage wood';
  if(/Culverin|LongGun|Swivel/.test(label))return 'Gun metal';
  if(/Painted/.test(label))return 'Painted wood';
  if(/FloorDeck/.test(label))return 'Deck planks';
  if(/Wood|Ornate/.test(label))return 'Wood finish';
  if(/Rope/.test(label))return 'Rope';
  return 'Finish';
}

export function exportFinish(surface){
 const map=surface.current.map||surface.original.map;
 if(!map?.image)throw new Error('This finish has no color image to export.');
 const canvas=document.createElement('canvas');canvas.width=map.image.width;canvas.height=map.image.height;
 const ctx=canvas.getContext('2d');ctx.drawImage(map.image,0,0);
 const image=ctx.getImageData(0,0,canvas.width,canvas.height),a=image.data;
 const factors=[surface.current.color.r,surface.current.color.g,surface.current.color.b];
 const linear=x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4;
 const srgb=x=>x<=.0031308?x*12.92:1.055*x**(1/2.4)-.055;
 for(let i=0;i<a.length;i+=4)for(let c=0;c<3;c++)a[i+c]=Math.round(Math.min(1,Math.max(0,srgb(linear(a[i+c]/255)*factors[c])))*255);
 ctx.putImageData(image,0,0);return canvas.toDataURL('image/png');
}
