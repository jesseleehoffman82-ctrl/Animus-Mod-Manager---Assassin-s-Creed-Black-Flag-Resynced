import * as THREE from 'three';

// Unique texel ownership prevents atlas reuse from painting a distant surface.
// Ambiguous/shared texels are deliberately unpaintable until their UVs are separated.
export function buildPaintBoundaries(targets,width,height) {
 const owner=new Int32Array(width*height);owner.fill(-1);const triangles=[];
 for(const target of targets){
  const g=target.s.mesh.geometry,uv=g.attributes.uv,pos=g.attributes.position,idx=g.index;
  target.s.mesh.updateWorldMatrix(true,false);target.texture.updateMatrix();
  for(let f=0;f<(idx?idx.count:pos.count);f+=3){
   const ids=[0,1,2].map(j=>idx?idx.getX(f+j):f+j);
   const t=ids.map(i=>{const p=new THREE.Vector2().fromBufferAttribute(uv,i);target.texture.transformUv(p);return p.multiply(new THREE.Vector2(width,height))});
   const world=ids.map(i=>new THREE.Vector3().fromBufferAttribute(pos,i).applyMatrix4(target.s.mesh.matrixWorld));
   const a=t[1].clone().sub(t[0]),b=t[2].clone().sub(t[0]),det=a.x*b.y-a.y*b.x;if(Math.abs(det)<1e-7)continue;
   const id=triangles.length;triangles.push({t,world,a,b,det});
   const x0=Math.max(0,Math.floor(Math.min(...t.map(p=>p.x)))),x1=Math.min(width-1,Math.ceil(Math.max(...t.map(p=>p.x))));
   const y0=Math.max(0,Math.floor(Math.min(...t.map(p=>p.y)))),y1=Math.min(height-1,Math.ceil(Math.max(...t.map(p=>p.y))));
   for(let y=y0;y<=y1;y++)for(let x=x0;x<=x1;x++){
    const dx=x+.5-t[0].x,dy=y+.5-t[0].y,u=(dx*b.y-dy*b.x)/det,v=(a.x*dy-a.y*dx)/det;
    if(u<0||v<0||u+v>1)continue;const k=y*width+x;owner[k]=owner[k]===-1?id:-2;
   }
  }
 }
 return {
  clip(ctx,x,y,r,hitPoint,worldRadius){
   ctx.beginPath();let count=0;
   for(let py=Math.max(0,Math.floor(y-r));py<Math.min(height,Math.ceil(y+r));py++){
    let start=-1;
    for(let px=Math.max(0,Math.floor(x-r));px<=Math.min(width,Math.ceil(x+r));px++){
     let safe=false;const id=px<width?owner[py*width+px]:-1;
     if(id>=0&&(px+.5-x)**2+(py+.5-y)**2<=r*r){
      const t=triangles[id],dx=px+.5-t.t[0].x,dy=py+.5-t.t[0].y,u=(dx*t.b.y-dy*t.b.x)/t.det,v=(t.a.x*dy-t.a.y*dx)/t.det;
      const p=t.world[0].clone().multiplyScalar(1-u-v).addScaledVector(t.world[1],u).addScaledVector(t.world[2],v);
      safe=p.distanceToSquared(hitPoint)<=worldRadius*worldRadius;
     }
     if(safe){count++;if(start<0)start=px}else if(start>=0){ctx.rect(start,py,px-start,1);start=-1}
    }
    if(start>=0)ctx.rect(start,py,Math.min(width,Math.ceil(x+r))-start,1);
   }
   ctx.clip();return count;
  },
  stats(){let shared=0;for(const n of owner)if(n===-2)shared++;return {shared,total:owner.length}}
 };
}

export function testPaintBoundaries(){
 const make=(offset=0)=>{const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute([offset,0,0,offset+1,0,0,offset,1,0],3));g.setAttribute('uv',new THREE.Float32BufferAttribute([.25,.25,.75,.25,.25,.75],2));const mesh=new THREE.Mesh(g);const texture=new THREE.Texture();texture.flipY=false;return {s:{mesh},texture}};
 const canvas=document.createElement('canvas');canvas.width=canvas.height=32;const ctx=canvas.getContext('2d');
 const draw=targets=>{ctx.clearRect(0,0,32,32);ctx.save();buildPaintBoundaries(targets,32,32).clip(ctx,16,16,20,new THREE.Vector3(.3,.3,0),3);ctx.fillStyle='red';ctx.fillRect(0,0,32,32);ctx.restore();return ctx.getImageData(0,0,32,32).data};
 const one=make(),single=draw([one]);if(!single[(10*32+10)*4+3]||single[(2*32+2)*4+3])throw Error('Selected UV boundary clipping failed');
 const duplicate=make(100),overlap=draw([one,duplicate]);if(overlap.some(x=>x))throw Error('Shared UV painted distant surface');
 return 'PASS: oversized brush stays inside selected UV triangle; overlapping distant UVs remain unchanged';
}
