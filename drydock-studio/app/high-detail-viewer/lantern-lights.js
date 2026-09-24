import * as THREE from 'three';

// Anchor each light to the actual glass mesh, not an approximate hull position.
export function createLanternLights(surfaces,scene) {
 const lamps=[];
 for(const s of surfaces.values()) {
  const small=s.part.includes('2221220301775')&&s.materialId===String(BigInt('0x0000021824035F8B'));
  const large=s.part.includes('2254219731646')&&s.materialId==='2284948083835';
  if(!small&&!large)continue;
  const bounds=new THREE.Box3().setFromObject(s.mesh),center=bounds.getCenter(new THREE.Vector3());
  const size=bounds.getSize(new THREE.Vector3()).length();
  const light=new THREE.PointLight(0xffbd75,large?18:9,large?6:4,2);
  light.position.copy(center);light.castShadow=false;light.visible=false;scene.add(light);
  lamps.push({surface:s,light,emissive:s.current.emissive.clone(),intensity:s.current.emissiveIntensity,size});
 }
 return {
  setEnabled(enabled){for(const lamp of lamps){lamp.light.visible=!!enabled;lamp.surface.current.emissive.copy(enabled?new THREE.Color(0xffb66b):lamp.emissive);lamp.surface.current.emissiveIntensity=enabled?1.6:lamp.intensity}},
  debug(){return {count:lamps.length,enabled:lamps.filter(x=>x.light.visible).length,positions:lamps.map(x=>x.light.position.toArray())}}
 };
}
