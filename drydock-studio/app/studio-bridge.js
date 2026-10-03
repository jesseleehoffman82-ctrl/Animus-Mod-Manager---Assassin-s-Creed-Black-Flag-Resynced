import * as THREE from 'three';
import {GLTFLoader} from './vendor/stdlib/loaders/GLTFLoader.js';
import {setFinishColor,setFinishDesign,resetFinish,finishName,exportFinish} from './finish-editor.js';
const $=id=>document.getElementById(id), embedded=true;
const defaults={quality:'High',normals:true,shadows:false,aa:4,lighting:'Studio',exposure:1,wireframe:false,textures:true,focusFade:true};
let prefs={...defaults};const presets={Low:{normals:false,shadows:false,aa:4},Medium:{normals:true,shadows:false,aa:4},High:{normals:true,shadows:false,aa:4}};
let renderer,scene,camera,controls,canvas,root,selected,box,shared=false,bindings={},areas={},meshCount=0;
const selectionEdges=[],surfaces=new Map(),ray=new THREE.Raycaster(),pointer=new THREE.Vector2();
const clay=new THREE.MeshStandardMaterial({color:0x9a9e9f,roughness:.8,side:THREE.DoubleSide});
function notify(m){if(m.type==='ready')document.getElementById('status').textContent='3D Gen Studio | '+m.surfaces+' surfaces | Middle-drag: orbit | Right-drag: pan';if(m.type==='surface-selected')document.getElementById('status').textContent='Selected: '+m.label;window.chrome?.webview?.postMessage(m);window.__lastDrydockMessage=m}
function update(){
 renderer.toneMappingExposure=Number(prefs.exposure);renderer.shadowMap.enabled=!!prefs.shadows;
 window.__jackdawStudioStore.getState().setDpr(prefs.quality==='Low'?1:Math.min(devicePixelRatio,2));
 for(const s of surfaces.values()){s.current.normalMap=prefs.normals?s.normal:null;s.current.wireframe=!!prefs.wireframe;s.clay.wireframe=!!prefs.wireframe;s.mesh.material=prefs.textures?s.current:s.clay;s.current.needsUpdate=true;}
 scene.traverse(o=>{if(o.isLight&&o.userData.drydockIntensity!==undefined)o.intensity=o.userData.drydockIntensity*(prefs.lighting==='Overcast'?.65:prefs.lighting==='Daylight'?1.2:1)});
 for(const k of ['normals','shadows','wireframe','focusFade'])$(k).checked=!!prefs[k];for(const k of ['quality','aa','lighting','exposure'])$(k).value=prefs[k];$('textures').textContent=`Textures: ${prefs.textures?'On':'Off'}`;
}
function resize(){};
function fit(direction=new THREE.Vector3(1,.35,1)){if(!box)return;const center=box.getCenter(new THREE.Vector3()),d=direction.normalize(),right=new THREE.Vector3().crossVectors(camera.up,d).normalize(),up=new THREE.Vector3().crossVectors(d,right);let distance=0;const tangent=Math.tan(THREE.MathUtils.degToRad(camera.fov/2));for(const x of [box.min.x,box.max.x])for(const y of [box.min.y,box.max.y])for(const z of [box.min.z,box.max.z]){const v=new THREE.Vector3(x,y,z).sub(center);distance=Math.max(distance,v.dot(d)+Math.max(Math.abs(v.dot(up))/tangent,Math.abs(v.dot(right))/(tangent*camera.aspect)))}controls.target.copy(center);camera.position.copy(center).add(d.multiplyScalar(distance*1.08));camera.near=.05;camera.far=distance+box.getSize(new THREE.Vector3()).length()*8;camera.updateProjectionMatrix();controls.maxDistance=distance*8;controls.minDistance=.1;controls.update();}



function clearSelectionEdges(){for(const edge of selectionEdges){edge.removeFromParent();edge.geometry.dispose();edge.material.dispose()}selectionEdges.length=0}



function highlightPart(s){clearSelectionEdges();for(const surface of surfaces.values()){if(surface.groupRoot!==s.groupRoot)continue;const edges=new THREE.LineSegments(new THREE.EdgesGeometry(surface.mesh.geometry,25),new THREE.LineBasicMaterial({color:0xe8ba70,transparent:true,opacity:.95,depthTest:true,depthWrite:false,toneMapped:false}));edges.name='Selected part edges';edges.raycast=()=>{};edges.renderOrder=10;surface.mesh.add(edges);selectionEdges.push(edges)}}



function clearSelection(){selected=null;clearSelectionEdges();$('selection').replaceChildren();notify({type:'selection-cleared'});}



function selectSurface(s){

 selected=s;highlightPart(s);const record=bindings[s.materialId]||{};const panel=$('selection');panel.replaceChildren();

 const title=document.createElement('strong');title.textContent=s.area+' Â· '+finishName(record.label);panel.append(title);

 const hint=document.createElement('p');hint.textContent='Change the color or add a PNG. Surface detail stays in place.';panel.append(hint);

 const label=document.createElement('label');label.append('Color tint');const color=document.createElement('input');color.type='color';color.value=s.tint||'#ffffff';color.setAttribute('aria-label','Finish color');color.oninput=()=>tintSelected(color.value);label.append(color);panel.append(label);

 if(!embedded){const input=document.createElement('input');input.type='file';input.accept='image/png';input.setAttribute('aria-label','Import a PNG design');input.onchange=async()=>{const file=input.files[0];if(!file)return;const url=URL.createObjectURL(file);const id=s.id;try{await applyPNG({surfaceId:id,shared,url})}catch(e){notify({type:'edit-error',message:e.message});hint.textContent='Could not read that PNG. Your finish is unchanged.'}finally{URL.revokeObjectURL(url)}};panel.append(input)}

 const scope=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.checked=shared;check.onchange=()=>{shared=check.checked;notifySelection()};scope.append('Use on matching surfaces',check);panel.append(scope);

 const save=document.createElement('button');save.textContent='Save finish PNG';save.onclick=saveSelectedFinish;panel.append(save);

 const reset=document.createElement('button');reset.id='restore';reset.textContent='Reset this finish';reset.onclick=restoreSelected;panel.append(reset);

 const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent='Mesh information';details.append(summary);const stats=meshStats(s),info=document.createElement('p');info.textContent=`${stats.vertices.toLocaleString()} vertices Â· ${stats.triangles.toLocaleString()} triangles Â· ${stats.uvSets} UV sets Â· ${(record.size||[]).join(' Ã— ')}`;details.append(info);panel.append(details);notifySelection();

}

function saveSelectedFinish(){if(!selected)return;const data=exportFinish(selected),filename='Jackdaw-'+selected.area.replace(/[^a-z0-9]+/gi,'-')+'-finish.png';if(embedded)notify({type:'export-finish',filename,data});else{const a=document.createElement('a');a.href=data;a.download=filename;a.click()}}

function tintSelected(hex){if(!selected)return;for(const s of targetSurfaces(selected.id,shared))setFinishColor(s,hex);notify({type:'finish-color',hex});}



function meshStats(s){const group=[...surfaces.values()].filter(x=>x.groupRoot===s.groupRoot);return {vertices:group.reduce((n,x)=>n+x.mesh.geometry.attributes.position.count,0),triangles:group.reduce((n,x)=>n+(x.mesh.geometry.index?x.mesh.geometry.index.count:x.mesh.geometry.attributes.position.count)/3,0),uvSets:Math.max(...group.map(x=>Object.keys(x.mesh.geometry.attributes).filter(k=>/^uv\d*$/.test(k)).length))}}



function notifySelection(){if(!selected)return;notify({type:'surface-selected',surfaceId:selected.id,materialId:selected.materialId,textureId:bindings[selected.materialId]?.diffuse,label:selected.area+' Â· '+finishName(bindings[selected.materialId]?.label),tint:selected.tint||'#ffffff',previewDiffuse:bindings[selected.materialId]?.previewDiffuse,partName:selected.partName,...meshStats(selected),textureSize:bindings[selected.materialId]?.size||[],shared});}



function targetSurfaces(id,all){const s=surfaces.get(id);return s?(all?[...surfaces.values()].filter(x=>x.materialId===s.materialId):[...surfaces.values()].filter(x=>x.groupRoot===s.groupRoot&&x.materialId===s.materialId)):[]}



async function applyPNG(message){

 const targets=targetSurfaces(message.surfaceId,message.shared);if(!targets.length)return;

 const request=++editRequest;const texture=await new THREE.TextureLoader().loadAsync(message.url);

 try{if(request!==editRequest)return;for(const s of targets)setFinishDesign(s,texture);update();notify({type:'applied',count:targets.length});}

 finally{texture.dispose();}

}

let editRequest=0;

function restoreSelected(){if(!selected)return;++editRequest;for(const s of targetSurfaces(selected.id,shared))resetFinish(s);update();selectSurface(selected);notify({type:'restored'});}



window.jackdawViewer={setTextures(value){prefs.textures=!!value;update()},applyPNG,restoreSelected,tintSelected,fit,debug(){return {loaded:!!root,surfaces:surfaces.size,preferences:{...prefs},selected:selected?.id,triangles:renderer.info.render.triangles}},select(id){if(surfaces.has(id))selectSurface(surfaces.get(id))}};



window.chrome?.webview?.addEventListener('message',event=>{const m=event.data;if(m.type==='textures')window.jackdawViewer.setTextures(m.enabled);if(m.type==='apply')applyPNG(m).catch(e=>notify({type:'edit-error',message:e.message}));if(m.type==='tint')tintSelected(m.hex);if(m.type==='export-finish')saveSelectedFinish();if(m.type==='fit')fit();if(m.type==='clear-selection')clearSelection();if(m.type==='restore')restoreSelected();if(m.type==='scope')shared=!!m.shared;if(m.type==='settings')$('settings').open=!$('settings').open});



async function load(){const params=new URLSearchParams(location.search);const base='/ship-preview/';const manifestResponse=await fetch(base+'preview-manifest.json',{cache:'no-store'});if(!manifestResponse.ok)throw new Error('Current ship manifest is missing. Run the preview deployment.');const manifest=await manifestResponse.json();if(!/^[a-f0-9]{64}$/.test(manifest.sha256))throw new Error('Invalid ship revision');const revision='?v='+manifest.sha256;bindings=await (await fetch(base+'material-bindings.json'+revision,{cache:'no-store'})).json();const rawAreas=await (await fetch(base+'selection-areas.json'+revision,{cache:'no-store'})).json();areas=Object.fromEntries(Object.entries(rawAreas).map(([k,v])=>[THREE.PropertyBinding.sanitizeNodeName(k),v]));const gltf=await new GLTFLoader().loadAsync(base+manifest.file+revision,e=>{if(e.total)$('status').textContent=`Loading ship: ${Math.round(100*e.loaded/e.total)}%`});root=gltf.scene;root.traverse(o=>{if(!o.isMesh)return;const original=o.material;if(Array.isArray(original))throw new Error('Expected one glTF primitive per selectable surface');const id=String(meshCount++);const current=original.clone();let groupRoot=o;while(groupRoot.parent&&groupRoot.parent!==root&&!areas[groupRoot.name])groupRoot=groupRoot.parent;const meta=areas[groupRoot.name]||{};surfaces.set(id,{id,mesh:o,groupRoot,area:meta.area,partName:meta.area||groupRoot.name,clay:clay.clone(),original,current,normal:original.normalMap,materialId:original.userData.game_material_id||original.name.split(' :: ').at(-1)});o.userData.surfaceId=id;o.castShadow=true;o.receiveShadow=true;});scene.add(root);box=new THREE.Box3().setFromObject(root);update();fit();notify({type:'ready',surfaces:surfaces.size,revision:manifest.sha256,model:manifest.label,renderer:'3D Gen Studio / React Three Fiber'});if(params.has('selftest'))await studioSelfTest();}




let fadeTime=performance.now();function animate(){requestAnimationFrame(animate);const now=performance.now(),blend=1-Math.exp(-(now-fadeTime)/96);fadeTime=now;for(const s of surfaces.values()){const faded=!!(selected&&prefs.focusFade&&s.groupRoot!==selected.groupRoot);const target=faded?.18:1;const m=s.mesh.material;m.opacity=THREE.MathUtils.lerp(m.opacity,target,blend);const transparent=m.opacity<.995;if(m.transparent!==transparent){m.transparent=transparent;m.depthWrite=!transparent;m.needsUpdate=true}}}
async function studioSelfTest(){
 const assert=(v,m)=>{if(!v)throw Error(m)};
 assert(surfaces.size===663,'Current model surface count');
 const target=[...surfaces.values()].find(s=>s.area==='Cannons');const other=[...surfaces.values()].find(s=>s.groupRoot!==target.groupRoot);
 const matrices=[...surfaces.values()].map(s=>[s,s.mesh.matrixWorld.toArray()]);
 selectSurface(target);assert(selectionEdges.length>0&&selectionEdges.every(e=>e.isLineSegments),'Actual part edges');
 await new Promise(r=>setTimeout(r,1800));assert(other.mesh.material.opacity<.25&&target.mesh.material.opacity>.99,'Ghosting excludes selected part');
 prefs.textures=false;update();assert([...surfaces.values()].every(s=>s.mesh.material===s.clay),'Textures off');prefs.textures=true;update();
 tintSelected('#ad5544');assert(target.tint==='#ad5544','Tint');restoreSelected();assert(target.current.map===target.original.map,'Restore');
 for(const [s,m] of matrices)assert(m.every((v,i)=>v===s.mesh.matrixWorld.elements[i]),'Transforms preserved');
 clearSelection();await new Promise(r=>setTimeout(r,1800));assert(other.mesh.material.opacity>.99,'Ghosting clears');
 window.__drydockTest={pass:true,surfaces:surfaces.size,renderer:'3D Gen Studio',checks:['part edges','smooth ghosting','texture toggle','tint/reset','geometry unchanged']};notify({type:'selftest-pass',...window.__drydockTest});$('status').textContent='Verified: 3D Gen Studio Â· 663 surfaces Â· selection and ghosting';
}
async function init(){
 for(let i=0;i<600;i++){const state=window.__jackdawStudioStore?.getState();if(state?.controls&&state.camera?.isPerspectiveCamera){({gl:renderer,scene,camera,controls}=state);break}await new Promise(r=>setTimeout(r,100))}
 if(!renderer)throw Error('3D Gen Studio canvas did not initialize');
 canvas=renderer.domElement;canvas.setAttribute('aria-label','3D Gen Studio Jackdaw preview');
 // Preserve Studio's renderer, lighting, camera, and orbit controls; replace its merged editing proxy with the intact current GLB.
 scene.traverse(o=>{if(o.isMesh||o.isLineSegments)o.visible=false;if(o.isLight)o.userData.drydockIntensity=o.intensity});
 scene.background=null;renderer.setClearColor(0,0);
 const shell=document.querySelector('.mesh-editor-canvas-shell');canvas.addEventListener('pointerdown',e=>{if(e.button===0)e.stopPropagation()});canvas.addEventListener('pointerup',e=>{if(e.button===0)e.stopPropagation()});
 let down;canvas.addEventListener('pointerdown',e=>{down=[e.clientX,e.clientY]});canvas.addEventListener('pointerup',e=>{if(e.button!==0)return;if(!root||!down||Math.hypot(e.clientX-down[0],e.clientY-down[1])>5)return;pointer.set(e.clientX/innerWidth*2-1,1-e.clientY/innerHeight*2);ray.setFromCamera(pointer,camera);const hit=ray.intersectObject(root,true).find(h=>surfaces.get(h.object.userData.surfaceId)?.area);if(hit)selectSurface(surfaces.get(hit.object.userData.surfaceId));else clearSelection();});



$('fit').onclick=()=>fit();$('side').onclick=()=>fit(new THREE.Vector3(1,.05,0));$('deck').onclick=()=>{controls.target.set(0,5,3);camera.position.set(18,27,25);controls.update()};$('textures').onclick=()=>{prefs.textures=!prefs.textures;update();notify({type:'textures',enabled:prefs.textures})};



$('quality').onchange=e=>{prefs.quality=e.target.value;Object.assign(prefs,presets[prefs.quality]);update()};for(const k of ['normals','shadows','aa','lighting','exposure','wireframe','focusFade'])$(k).onchange=e=>{prefs[k]=e.target.type==='checkbox'?e.target.checked:e.target.value;if(['normals','shadows','aa'].includes(k))prefs.quality='Custom';update()};$('reset').onclick=()=>{prefs={...defaults};update()};window.addEventListener('resize',resize);



function fail(e){console.error(e);$('error').style.display='block';$('error').textContent='The high-detail preview could not load. '+e.message;notify({type:'error',message:e.message})}



canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();fail(new Error('Graphics context lost. Reopen the preview or choose a lower quality preset.'))});




 animate();await load();
}
init().catch(e=>{console.error(e);$('error').style.display='block';$('error').textContent=e.message;notify({type:'error',message:e.message})});
