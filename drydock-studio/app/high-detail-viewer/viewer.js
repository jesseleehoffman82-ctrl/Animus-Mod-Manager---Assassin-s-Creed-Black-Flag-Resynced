import * as THREE from 'three';

import {setFinishColor,setFinishDesign,resetFinish,finishName,exportFinish} from './finish-editor.js';



import {OrbitControls} from './vendor/stdlib/controls/OrbitControls.js';



import {GLTFLoader} from './vendor/stdlib/loaders/GLTFLoader.js';



import {RoomEnvironment} from './vendor/stdlib/environments/RoomEnvironment.js';







const $=id=>document.getElementById(id), canvas=$('canvas');



const embedded=new URLSearchParams(location.search).has('embedded');if(embedded)document.body.classList.add('embedded');

const defaults={quality:'High',normals:true,shadows:true,aa:4,lighting:'Daylight',exposure:1.15,wireframe:false,textures:true,focusFade:true};



let prefs={...defaults};try{prefs={...defaults,...JSON.parse(localStorage.getItem('jackdaw-viewer-settings-v1')||'{}')}}catch{}



const presets={Low:{normals:false,shadows:false,aa:0},Medium:{normals:true,shadows:true,aa:2},High:{normals:true,shadows:true,aa:4}};



const renderer=new THREE.WebGLRenderer({canvas,antialias:false,alpha:true});renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;



const scene=new THREE.Scene();scene.background=null;renderer.setClearColor(0x000000,0);



const camera=new THREE.PerspectiveCamera(40,1,.1,1000), controls=new OrbitControls(camera,canvas);controls.enableDamping=true;



const pmrem=new THREE.PMREMGenerator(renderer),room=new RoomEnvironment();const environment=pmrem.fromScene(room,.04);scene.environment=environment.texture;room.dispose?.();pmrem.dispose();



const key=new THREE.DirectionalLight(0xfff1d5,2.5);key.position.set(35,65,30);key.castShadow=true;key.shadow.bias=-.0001;key.shadow.normalBias=.04;key.shadow.camera.left=-45;key.shadow.camera.right=45;key.shadow.camera.top=55;key.shadow.camera.bottom=-35;key.shadow.camera.far=160;scene.add(key);scene.add(key.target);



const fill=new THREE.HemisphereLight(0xdfeaff,0x6b4930,1.1);scene.add(fill);



const clay=new THREE.MeshStandardMaterial({color:0x9a9e9f,roughness:.8,side:THREE.DoubleSide});



let root,selected,box,shared=false,bindings={},areas={},meshCount=0,lastFrame=performance.now(),frames=0;

const selectionEdges=[];



const surfaces=new Map(),ray=new THREE.Raycaster(),pointer=new THREE.Vector2();



let renderTarget;



// A multisampled target allows changing anti-aliasing without replacing the WebGL context.



const quadScene=new THREE.Scene(),quadCamera=new THREE.OrthographicCamera(-1,1,1,-1,0,1);



const quadMaterial=new THREE.ShaderMaterial({uniforms:{image:{value:null}},vertexShader:'varying vec2 v; void main(){v=uv;gl_Position=vec4(position.xy,0.,1.);}',fragmentShader:'uniform sampler2D image;varying vec2 v;void main(){gl_FragColor=texture2D(image,v);\n#include <tonemapping_fragment>\n#include <colorspace_fragment>\n}',depthTest:false,depthWrite:false,transparent:true});quadScene.add(new THREE.Mesh(new THREE.PlaneGeometry(2,2),quadMaterial));



function resize(){const dpr=Math.min(devicePixelRatio,prefs.quality==='Low'?1:prefs.quality==='Medium'?1.5:2);renderer.setPixelRatio(dpr);renderer.setSize(innerWidth,innerHeight,false);camera.aspect=innerWidth/innerHeight;camera.updateProjectionMatrix();renderTarget?.dispose();renderTarget=new THREE.WebGLRenderTarget(Math.round(innerWidth*dpr),Math.round(innerHeight*dpr),{samples:Math.min(Number(prefs.aa),renderer.capabilities.maxSamples),type:THREE.HalfFloatType});renderTarget.texture.colorSpace=THREE.LinearSRGBColorSpace;quadMaterial.uniforms.image.value=renderTarget.texture;}



function notify(message){window.chrome?.webview?.postMessage(message)}



function save(){try{localStorage.setItem('jackdaw-viewer-settings-v1',JSON.stringify(prefs))}catch{}}



function update(){renderer.toneMappingExposure=Number(prefs.exposure);renderer.shadowMap.enabled=!!prefs.shadows;renderer.shadowMap.type=THREE.PCFSoftShadowMap;const shadowSize=prefs.quality==='High'||prefs.quality==='Custom'?2048:1024;if(key.shadow.mapSize.x!==shadowSize){key.shadow.mapSize.set(shadowSize,shadowSize);key.shadow.map?.dispose();key.shadow.map=null}key.shadow.needsUpdate=true;scene.environmentIntensity=prefs.lighting==='Studio'?1.1:.6;key.intensity=prefs.lighting==='Overcast'?1:2.5;fill.intensity=prefs.lighting==='Overcast'?1.5:1.1;clay.wireframe=!!prefs.wireframe;



for(const s of surfaces.values()){const normal=prefs.normals?s.normal:null;const changed=s.current.normalMap!==normal||s.current.wireframe!==!!prefs.wireframe;s.current.normalMap=normal;s.current.wireframe=!!prefs.wireframe;s.clay.wireframe=!!prefs.wireframe;s.mesh.material=prefs.textures?s.current:s.clay;if(changed)s.current.needsUpdate=true;for(const t of [s.current.map,s.normal])if(t){const a=Math.min(renderer.capabilities.getMaxAnisotropy(),prefs.quality==='Low'?1:prefs.quality==='Medium'?4:16);if(t.anisotropy!==a){t.anisotropy=a;t.needsUpdate=true}}}



for(const k of ['normals','shadows','wireframe','focusFade'])$(k).checked=!!prefs[k];for(const k of ['quality','aa','lighting','exposure'])$(k).value=prefs[k];$('textures').textContent=`Textures: ${prefs.textures?'On':'Off'}`;save();resize();}



function fit(direction=new THREE.Vector3(1,.35,1)){if(!box)return;const center=box.getCenter(new THREE.Vector3()),d=direction.normalize(),right=new THREE.Vector3().crossVectors(camera.up,d).normalize(),up=new THREE.Vector3().crossVectors(d,right);let distance=0;const tangent=Math.tan(THREE.MathUtils.degToRad(camera.fov/2));for(const x of [box.min.x,box.max.x])for(const y of [box.min.y,box.max.y])for(const z of [box.min.z,box.max.z]){const v=new THREE.Vector3(x,y,z).sub(center);distance=Math.max(distance,v.dot(d)+Math.max(Math.abs(v.dot(up))/tangent,Math.abs(v.dot(right))/(tangent*camera.aspect)))}controls.target.copy(center);camera.position.copy(center).add(d.multiplyScalar(distance*1.08));camera.near=.05;camera.far=distance+box.getSize(new THREE.Vector3()).length()*8;camera.updateProjectionMatrix();controls.update();}



function clearSelectionEdges(){for(const edge of selectionEdges){edge.removeFromParent();edge.geometry.dispose();edge.material.dispose()}selectionEdges.length=0}



function highlightPart(s){clearSelectionEdges();for(const surface of surfaces.values()){if(surface.groupRoot!==s.groupRoot)continue;const edges=new THREE.LineSegments(new THREE.EdgesGeometry(surface.mesh.geometry,25),new THREE.LineBasicMaterial({color:0xe8ba70,transparent:true,opacity:.95,depthTest:true,depthWrite:false,toneMapped:false}));edges.name='Selected part edges';edges.raycast=()=>{};edges.renderOrder=10;surface.mesh.add(edges);selectionEdges.push(edges)}}



function clearSelection(){selected=null;clearSelectionEdges();$('selection').replaceChildren();notify({type:'selection-cleared'});}



function selectSurface(s){

 selected=s;highlightPart(s);const record=bindings[s.materialId]||{};const panel=$('selection');panel.replaceChildren();

 const title=document.createElement('strong');title.textContent=s.area+' · '+finishName(record.label);panel.append(title);

 const hint=document.createElement('p');hint.textContent='Change the color or add a PNG. Surface detail stays in place.';panel.append(hint);

 const label=document.createElement('label');label.append('Color tint');const color=document.createElement('input');color.type='color';color.value=s.tint||'#ffffff';color.setAttribute('aria-label','Finish color');color.oninput=()=>tintSelected(color.value);label.append(color);panel.append(label);

 if(!embedded){const input=document.createElement('input');input.type='file';input.accept='image/png';input.setAttribute('aria-label','Import a PNG design');input.onchange=async()=>{const file=input.files[0];if(!file)return;const url=URL.createObjectURL(file);const id=s.id;try{await applyPNG({surfaceId:id,shared,url})}catch(e){notify({type:'edit-error',message:e.message});hint.textContent='Could not read that PNG. Your finish is unchanged.'}finally{URL.revokeObjectURL(url)}};panel.append(input)}

 const scope=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.checked=shared;check.onchange=()=>{shared=check.checked;notifySelection()};scope.append('Use on matching surfaces',check);panel.append(scope);

 const save=document.createElement('button');save.textContent='Save finish PNG';save.onclick=saveSelectedFinish;panel.append(save);

 const reset=document.createElement('button');reset.id='restore';reset.textContent='Reset this finish';reset.onclick=restoreSelected;panel.append(reset);

 const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent='Mesh information';details.append(summary);const stats=meshStats(s),info=document.createElement('p');info.textContent=`${stats.vertices.toLocaleString()} vertices · ${stats.triangles.toLocaleString()} triangles · ${stats.uvSets} UV sets · ${(record.size||[]).join(' × ')}`;details.append(info);panel.append(details);notifySelection();

}

function saveSelectedFinish(){if(!selected)return;const data=exportFinish(selected),filename='Jackdaw-'+selected.area.replace(/[^a-z0-9]+/gi,'-')+'-finish.png';if(embedded)notify({type:'export-finish',filename,data});else{const a=document.createElement('a');a.href=data;a.download=filename;a.click()}}

function tintSelected(hex){if(!selected)return;for(const s of targetSurfaces(selected.id,shared))setFinishColor(s,hex);notify({type:'finish-color',hex});}



function meshStats(s){const group=[...surfaces.values()].filter(x=>x.groupRoot===s.groupRoot);return {vertices:group.reduce((n,x)=>n+x.mesh.geometry.attributes.position.count,0),triangles:group.reduce((n,x)=>n+(x.mesh.geometry.index?x.mesh.geometry.index.count:x.mesh.geometry.attributes.position.count)/3,0),uvSets:Math.max(...group.map(x=>Object.keys(x.mesh.geometry.attributes).filter(k=>/^uv\d*$/.test(k)).length))}}



function notifySelection(){if(!selected)return;notify({type:'surface-selected',surfaceId:selected.id,materialId:selected.materialId,textureId:bindings[selected.materialId]?.diffuse,label:selected.area+' · '+finishName(bindings[selected.materialId]?.label),tint:selected.tint||'#ffffff',previewDiffuse:bindings[selected.materialId]?.previewDiffuse,partName:selected.partName,...meshStats(selected),textureSize:bindings[selected.materialId]?.size||[],shared});}



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



let down;canvas.addEventListener('pointerdown',e=>{down=[e.clientX,e.clientY]});canvas.addEventListener('pointerup',e=>{if(!root||!down||Math.hypot(e.clientX-down[0],e.clientY-down[1])>5)return;pointer.set(e.clientX/innerWidth*2-1,1-e.clientY/innerHeight*2);ray.setFromCamera(pointer,camera);const hit=ray.intersectObject(root,true).find(h=>surfaces.get(h.object.userData.surfaceId)?.area);if(hit)selectSurface(surfaces.get(hit.object.userData.surfaceId));else clearSelection();});



$('fit').onclick=()=>fit();$('side').onclick=()=>fit(new THREE.Vector3(1,.05,0));$('deck').onclick=()=>{controls.target.set(0,5,3);camera.position.set(18,27,25);controls.update()};$('textures').onclick=()=>{prefs.textures=!prefs.textures;update();notify({type:'textures',enabled:prefs.textures})};



$('quality').onchange=e=>{prefs.quality=e.target.value;Object.assign(prefs,presets[prefs.quality]);update()};for(const k of ['normals','shadows','aa','lighting','exposure','wireframe','focusFade'])$(k).onchange=e=>{prefs[k]=e.target.type==='checkbox'?e.target.checked:e.target.value;if(['normals','shadows','aa'].includes(k))prefs.quality='Custom';update()};$('reset').onclick=()=>{prefs={...defaults};update()};window.addEventListener('resize',resize);



function fail(e){console.error(e);$('error').style.display='block';$('error').textContent='The high-detail preview could not load. '+e.message;notify({type:'error',message:e.message})}



canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();fail(new Error('Graphics context lost. Reopen the preview or choose a lower quality preset.'))});



async function load(){const params=new URLSearchParams(location.search);const base=params.get('assets')||'./assets/';const manifestResponse=await fetch(base+'preview-manifest.json',{cache:'no-store'});if(!manifestResponse.ok)throw new Error('Current ship manifest is missing. Run the preview deployment.');const manifest=await manifestResponse.json();if(!/^[a-f0-9]{64}$/.test(manifest.sha256))throw new Error('Invalid ship revision');const revision='?v='+manifest.sha256;bindings=await (await fetch(base+'material-bindings.json'+revision,{cache:'no-store'})).json();const rawAreas=await (await fetch(base+'selection-areas.json'+revision,{cache:'no-store'})).json();areas=Object.fromEntries(Object.entries(rawAreas).map(([k,v])=>[THREE.PropertyBinding.sanitizeNodeName(k),v]));const gltf=await new GLTFLoader().loadAsync(base+manifest.file+revision,e=>{if(e.total)$('status').textContent=`Loading ship: ${Math.round(100*e.loaded/e.total)}%`});root=gltf.scene;root.traverse(o=>{if(!o.isMesh)return;const original=o.material;if(Array.isArray(original))throw new Error('Expected one glTF primitive per selectable surface');const id=String(meshCount++);const current=original.clone();let groupRoot=o;while(groupRoot.parent&&groupRoot.parent!==root&&!areas[groupRoot.name])groupRoot=groupRoot.parent;const meta=areas[groupRoot.name]||{};surfaces.set(id,{id,mesh:o,groupRoot,area:meta.area,partName:meta.area||groupRoot.name,clay:clay.clone(),original,current,normal:original.normalMap,materialId:original.userData.game_material_id||original.name.split(' :: ').at(-1)});o.userData.surfaceId=id;o.castShadow=true;o.receiveShadow=true;});scene.add(root);box=new THREE.Box3().setFromObject(root);key.target.position.copy(box.getCenter(new THREE.Vector3()));update();fit();notify({type:'ready',surfaces:surfaces.size,revision:manifest.sha256,model:manifest.label});if(params.has('selftest'))await selfTest(base);}



function animate(){requestAnimationFrame(animate);controls.update();for(const s of surfaces.values()){const faded=!!(selected&&prefs.focusFade&&s.groupRoot!==selected.groupRoot);const target=faded?.18:1;const m=s.mesh.material;m.opacity=THREE.MathUtils.lerp(m.opacity,target,.16);const transparent=m.opacity<.995;if(m.transparent!==transparent){m.transparent=transparent;m.depthWrite=!transparent;m.needsUpdate=true}}if(renderTarget){renderer.setRenderTarget(renderTarget);renderer.render(scene,camera);renderer.setRenderTarget(null);renderer.render(quadScene,quadCamera)}frames++;const now=performance.now();if(root&&now-lastFrame>1000){$('status').textContent=`${surfaces.size} surfaces · ${Math.round(frames*1000/(now-lastFrame))} FPS · Click a surface to select its texture`;lastFrame=now;frames=0}}



update();animate();load().catch(fail);





async function selfTest(base){

 const assert=(value,text)=>{if(!value)throw new Error('Self-test: '+text)};

 const baseCanvas=document.createElement('canvas');baseCanvas.width=2;baseCanvas.height=1;const bc=baseCanvas.getContext('2d');bc.fillStyle='rgb(20,40,80)';bc.fillRect(0,0,2,1);

 const designCanvas=document.createElement('canvas');designCanvas.width=2;designCanvas.height=1;const dc=designCanvas.getContext('2d');dc.fillStyle='rgb(200,60,30)';dc.fillRect(1,0,1,1);

 const baseMap=new THREE.CanvasTexture(baseCanvas),designMap=new THREE.CanvasTexture(designCanvas),original=new THREE.MeshStandardMaterial({map:baseMap});const sample={original,current:original.clone()};

 setFinishDesign(sample,designMap);let px=sample.current.map.image.getContext('2d').getImageData(0,0,2,1).data;

 assert(px[0]===20&&px[1]===40&&px[2]===80,'transparent PNG keeps default');assert(px[4]===200&&px[5]===60&&px[6]===30,'opaque PNG uses design');

 setFinishColor(sample,'#00ff00');const exported=await new THREE.TextureLoader().loadAsync(exportFinish(sample));const ec=document.createElement('canvas');ec.width=2;ec.height=1;ec.getContext('2d').drawImage(exported.image,0,0);px=ec.getContext('2d').getImageData(0,0,2,1).data;assert(px[4]===0&&px[5]===60&&px[6]===0,'saved PNG matches tint');exported.dispose();resetFinish(sample);baseMap.dispose();designMap.dispose();sample.current.dispose();original.dispose();

 const saved={...prefs};const originals=[...surfaces.values()].map(s=>({s,matrix:s.mesh.matrixWorld.toArray(),map:s.current.map,normal:s.normal}));

 prefs.textures=false;update();assert([...surfaces.values()].every(s=>s.mesh.material===s.clay),'all surfaces enter clay');

 const target=[...surfaces.values()].find(s=>s.area==='Cannons');assert(target,'cannon selectable');const untouched=[...surfaces.values()].find(s=>s!==target&&s.materialId===target.materialId);selectSurface(target);assert(selectionEdges.length>0&&selectionEdges.every(e=>e.isLineSegments&&e.geometry.attributes.position.count>0),'part geometry edges highlighted');

 await applyPNG({surfaceId:target.id,shared:false,url:base+bindings[target.materialId].diffuse+'.png'});

 assert(target.mesh.material===target.clay,'applying while textures off remains clay');assert(target.current.map!==target.original.map,'PNG applied');assert(target.normal===target.original.normalMap,'normal retained');assert(target.current.roughnessMap===target.original.roughnessMap&&target.current.metalnessMap===target.original.metalnessMap,'finish response retained');tintSelected('#ad5544');assert(target.tint==='#ad5544','color edit applied');assert(target.current.map!==target.original.map,'color edit keeps design');if(untouched)assert(untouched.current.map===untouched.original.map,'other cannon unchanged');

 prefs.textures=true;update();assert(target.mesh.material===target.current,'texture restored');shared=false;restoreSelected();assert(target.current.map===target.original.map,'default restored');assert(target.tint==='#ffffff'&&target.current.color.equals(target.original.color),'reset restores color');

 for(const [quality,settings] of Object.entries(presets)){prefs.quality=quality;Object.assign(prefs,settings);update();assert(renderTarget.samples===Math.min(settings.aa,renderer.capabilities.maxSamples),'AA preset');assert(renderer.shadowMap.enabled===settings.shadows,'shadow preset')}

 for(const row of originals)assert(row.matrix.every((v,i)=>v===row.s.mesh.matrixWorld.elements[i]),'geometry transforms retained');

 assert([...surfaces.values()].some(s=>!s.area),'small details not selectable');

 prefs=saved;clearSelection();update();const result=document.createElement('div');result.id='selftest-result';result.style='position:absolute;top:55px;left:12px;color:#9fe6ae';result.textContent='PASS: finish color, PNG transparency, saved PNG, preserved detail maps, reset, selection scope, texture toggle and geometry';document.body.append(result);notify({type:'selftest-pass',surfaces:surfaces.size});

}

