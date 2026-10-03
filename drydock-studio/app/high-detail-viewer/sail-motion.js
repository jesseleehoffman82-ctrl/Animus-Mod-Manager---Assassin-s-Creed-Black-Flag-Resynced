import * as THREE from 'three';

export function createSailMotion(surfaces,camera,controls){
 const sails=[];let previousDirection=camera.position.clone().sub(controls.target).normalize(),accumulator=0,energy=0;
 for(const s of surfaces.values()){
  if(s.materialId!=='2296875182504')continue;
  const geometry=s.mesh.geometry.clone();s.mesh.geometry=geometry;
  const rest=geometry.attributes.position.array.slice(),normal=geometry.attributes.normal.array.slice(),count=rest.length/3;
  geometry.computeBoundingBox();const size=geometry.boundingBox.getSize(new THREE.Vector3()),axes=[0,1,2].sort((a,b)=>size.getComponent(b)-size.getComponent(a));
  const weights=new Float32Array(count),direction=new THREE.Vector3();
  for(let i=0;i<count;i++){const n=new THREE.Vector3().fromArray(normal,i*3);if(n.getComponent(axes[2])<0)n.negate();direction.add(n)}direction.normalize();
  const unique=new Map(),weld=[],points=[],edges=new Map(),adj=[];
  for(let i=0;i<count;i++){const key=[0,1,2].map(j=>Math.round(rest[i*3+j]*100000)).join(',');if(!unique.has(key)){unique.set(key,points.length);points.push(i);adj.push(new Set())}weld.push(unique.get(key))}
  const index=geometry.index,indices=index?index.array:Array.from({length:count},(_,i)=>i);
  for(let i=0;i<indices.length;i+=3)for(let j=0;j<3;j++){const a=weld[indices[i+j]],b=weld[indices[i+(j+1)%3]];if(a===b)continue;const key=a<b?`${a}/${b}`:`${b}/${a}`;edges.set(key,(edges.get(key)||0)+1);adj[a].add(b);adj[b].add(a)}
  const distances=new Int32Array(points.length);distances.fill(-1);const queue=[];
  for(const [key,n] of edges)if(n===1)for(const id of key.split('/').map(Number))if(distances[id]<0){distances[id]=0;queue.push(id)}
  for(let i=0;i<queue.length;i++)for(const n of adj[queue[i]])if(distances[n]<0){distances[n]=distances[queue[i]]+1;queue.push(n)}
  let max=1;for(const d of distances)max=Math.max(max,d);
  for(let i=0;i<count;i++){
   const u=(rest[i*3+axes[0]]-geometry.boundingBox.min.getComponent(axes[0]))/Math.max(size.getComponent(axes[0]),1e-6),v=(rest[i*3+axes[1]]-geometry.boundingBox.min.getComponent(axes[1]))/Math.max(size.getComponent(axes[1]),1e-6);
   weights[i]=queue.length?Math.max(0,distances[weld[i]])/max:Math.sin(Math.PI*u)*Math.sin(Math.PI*v);
  }
  sails.push({s,geometry,rest,normal,weights,direction,amplitude:Math.min(.22,size.getComponent(axes[1])*.035),position:0,velocity:0});
 }
 function restore(){for(const sail of sails){sail.geometry.attributes.position.array.set(sail.rest);sail.geometry.attributes.normal.array.set(sail.normal);sail.geometry.attributes.position.needsUpdate=true;sail.geometry.attributes.normal.needsUpdate=true;sail.position=sail.velocity=0;sail.geometry.computeBoundingSphere()}energy=0}
 return {
  update(dt,enabled,painting){
   const dir=camera.position.clone().sub(controls.target).normalize(),turn=previousDirection.angleTo(dir),sign=Math.sign(previousDirection.clone().cross(dir).y)||1;previousDirection.copy(dir);
   if(!enabled||painting){if(energy)restore();return false}
   const impulse=turn<.3?Math.min(turn*12,1.5)*sign:0;
   if(!energy&&!impulse)return false;
   for(const sail of sails)sail.velocity+=impulse;
   accumulator+=Math.min(dt,.05);if(accumulator<1/30)return false;const step=Math.min(accumulator,.05);accumulator=0;
   energy=0;for(const sail of sails){
    sail.velocity+=(-22*sail.position-5.5*sail.velocity)*step;sail.position=Math.max(-1,Math.min(1,sail.position+sail.velocity*step));
    energy=Math.max(energy,Math.abs(sail.position)+Math.abs(sail.velocity));
    const pos=sail.geometry.attributes.position.array;
    for(let i=0;i<sail.weights.length;i++){const displacement=sail.position*sail.amplitude*sail.weights[i];for(let j=0;j<3;j++)pos[i*3+j]=sail.rest[i*3+j]+sail.direction.getComponent(j)*displacement}
    sail.geometry.attributes.position.needsUpdate=true;sail.geometry.computeVertexNormals();sail.geometry.computeBoundingSphere();
   }
   if(energy<.0001){restore();return false}return true;
  },
  debug(){return {panels:sails.length,energy,vertices:sails.reduce((n,s)=>n+s.weights.length,0),pinned:sails.reduce((n,s)=>n+s.weights.filter(w=>w===0).length,0)}},
  test(){const uvs=sails.map(s=>s.geometry.attributes.uv.array.slice());for(const s of sails)s.velocity=1;energy=1;for(let i=0;i<10;i++)this.update(1/30,true,false);if(!energy)throw Error('No sail spring response');if(!sails.some(s=>s.geometry.attributes.position.array.some((v,i)=>Math.abs(v-s.rest[i])>.0001)))throw Error('No visible vertex displacement');for(let j=0;j<sails.length;j++){const s=sails[j];for(let i=0;i<s.weights.length;i++)if(s.weights[i]===0)for(let k=0;k<3;k++)if(s.geometry.attributes.position.array[i*3+k]!==s.rest[i*3+k])throw Error('Pinned edge moved');if(!s.geometry.attributes.uv.array.every((v,i)=>v===uvs[j][i]))throw Error('Sail UV changed')}this.update(1/30,true,true);if(energy)throw Error('Paint did not pause sails');return 'PASS: spring response, pinned edges, UV preservation, and paint pause'}
 };
}
