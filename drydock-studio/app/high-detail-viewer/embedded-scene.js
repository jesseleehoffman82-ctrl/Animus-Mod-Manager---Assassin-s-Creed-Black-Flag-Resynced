import {createSailMotion} from './sail-motion.js';
import {testPaintBoundaries} from './paint-boundaries.js';
import * as THREE from 'three';
import {createLanternLights} from './lantern-lights.js';
import {createSurfacePaint} from './surface-paint.js';
import {OrbitControls} from './vendor/stdlib/controls/OrbitControls.js';
import {GLTFLoader} from './vendor/stdlib/loaders/GLTFLoader.js';
import {RoomEnvironment} from './vendor/stdlib/environments/RoomEnvironment.js';
import {EffectComposer} from './vendor/stdlib/postprocessing/EffectComposer.js';
import {RenderPass} from './vendor/stdlib/postprocessing/RenderPass.js';
import {ShaderPass} from './vendor/stdlib/postprocessing/ShaderPass.js';
import {SSAOPass} from './vendor/stdlib/postprocessing/SSAOPass.js';
import {TemporalRefinementPass} from './TemporalRefinementPass.js';
import {FXAAShader} from './vendor/stdlib/shaders/FXAAShader.js';
import {OutlinePass} from './vendor/stdlib/postprocessing/OutlinePass.js';
const $=id=>document.getElementById(id),params=new URLSearchParams(location.search),base=params.get('assets')||'../user-data/ship-preview/';
if(params.has('embedded'))document.body.classList.add('embedded');
const notify=m=>window.chrome?.webview?.postMessage(m);
let lanternLights,sailMotion;let previousFrame=performance.now();
const defaults={sailMotion:true,lanterns:false,quality:'High',normals:true,shadows:true,occlusion:true,aa:4,aaMethod:'MSAA',shadowResolution:2048,aoStrength:.65,aoRadius:6,lighting:'Daylight',exposure:1,textures:true,wireframe:false,focusFade:true};
let prefs={...defaults};try{prefs={...defaults,...JSON.parse(localStorage.getItem('jackdaw-depth-settings')||'{}')}}catch{}
const renderer=new THREE.WebGLRenderer({canvas:$('canvas'),alpha:true,antialias:false});
renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.setClearColor(0,0);
renderer.shadowMap.type=THREE.PCFSoftShadowMap;renderer.shadowMap.autoUpdate=false;
const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(40,1,.1,1000),controls=new OrbitControls(camera,renderer.domElement);
controls.enableDamping=true;controls.dampingFactor=.09;controls.mouseButtons={LEFT:THREE.MOUSE.ROTATE,MIDDLE:THREE.MOUSE.DOLLY,RIGHT:THREE.MOUSE.PAN};
const pmrem=new THREE.PMREMGenerator(renderer),room=new RoomEnvironment();scene.environment=pmrem.fromScene(room,.08).texture;room.dispose?.();pmrem.dispose();
const key=new THREE.DirectionalLight(0xfff4e8,2.3),fill=new THREE.HemisphereLight(0xc8e0ff,0x71624e,.65);key.castShadow=true;scene.add(key,key.target,fill);
const target=new THREE.WebGLRenderTarget(1,1,{type:THREE.HalfFloatType,samples:4});
const composer=new EffectComposer(renderer,target);const beauty=new RenderPass(scene,camera),ao=new SSAOPass(scene,camera,1,1);
ao.ssaoMaterial.uniforms.aoStrength={value:.65};ao.ssaoMaterial.fragmentShader=ao.ssaoMaterial.fragmentShader.replace('uniform float kernelRadius;', 'uniform float kernelRadius; uniform float aoStrength;').replace('1.0 - occlusion','1.0 - occlusion * aoStrength');
ao.kernelRadius=6;ao.minDistance=.0008;ao.maxDistance=.018;ao.beautyRenderTarget.texture.type=THREE.HalfFloatType;
const outline=new OutlinePass(new THREE.Vector2(1,1),scene,camera);outline.visibleEdgeColor.set('#8fd8ff');outline.hiddenEdgeColor.set('#000000');outline.edgeStrength=1.3;outline.edgeGlow=.35;outline.edgeThickness=.65;outline.downSampleRatio=2;
const temporal=new TemporalRefinementPass(),fxaa=new ShaderPass(FXAAShader);let lastMotion=0;controls.addEventListener('change',()=>{temporal.reset();lastMotion=performance.now()});
const output=new ShaderPass({uniforms:{tDiffuse:{value:null}},vertexShader:'varying vec2 vUv;void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}',fragmentShader:'uniform sampler2D tDiffuse;varying vec2 vUv;void main(){gl_FragColor=texture2D(tDiffuse,vUv);\n#include <tonemapping_fragment>\n#include <colorspace_fragment>\n}'});
composer.addPass(beauty);composer.addPass(ao);composer.addPass(temporal);composer.addPass(outline);composer.addPass(output);composer.addPass(fxaa);
const selection=new Map();const surfaces=new Map(),byKey=new Map(),ray=new THREE.Raycaster(),pointer=new THREE.Vector2();let root,box,selected=null,revision=0,ready=false,pendingState=null;
function group(s){return s.materialId==='2296875182504'?'all-sails':s.part}
function groupSurfaces(s){return [...surfaces.values()].filter(x=>group(x)===group(s))}
function resize(){const dpr=Math.min(devicePixelRatio,prefs.quality==='Low'?1:1.5);renderer.setPixelRatio(dpr);renderer.setSize(innerWidth,innerHeight,false);camera.aspect=innerWidth/innerHeight;camera.updateProjectionMatrix();composer.setPixelRatio(dpr);composer.setSize(innerWidth,innerHeight);fxaa.uniforms.resolution.value.set(1/(innerWidth*dpr),1/(innerHeight*dpr));}
function update(){lanternLights?.setEnabled(prefs.lanterns);temporal.reset();ao.kernelRadius=+prefs.aoRadius;ao.ssaoMaterial.uniforms.aoStrength.value=+prefs.aoStrength;renderer.toneMappingExposure=+prefs.exposure;renderer.shadowMap.enabled=!!prefs.shadows;renderer.shadowMap.needsUpdate=true;scene.environmentIntensity=prefs.lighting==='Studio'?.7:.35;key.intensity=prefs.lighting==='Overcast'?1:2.3;fill.intensity=prefs.lighting==='Overcast'?1.15:.65;
 const size=+prefs.shadowResolution;if(key.shadow.mapSize.x!==size){key.shadow.mapSize.set(size,size);key.shadow.map?.dispose();key.shadow.map=null}
 for(const s of surfaces.values()){s.current.normalMap=prefs.normals?s.normal:null;s.current.wireframe=!!prefs.wireframe;s.current.needsUpdate=true;s.mesh.material=prefs.textures?s.current:s.clay;for(const t of [s.current.map,s.normal])if(t)t.anisotropy=Math.min(renderer.capabilities.getMaxAnisotropy(),prefs.quality==='Low'?2:8)}
 for(const k of ['sailMotion','lanterns','normals','shadows','occlusion','wireframe','focusFade'])$(k).checked=!!prefs[k];for(const k of ['quality','aa','aaMethod','shadowResolution','aoStrength','aoRadius','lighting','exposure'])$(k).value=prefs[k];$('textures').textContent=`Textures: ${prefs.textures?'On':'Off'}`;
 const samples=['MSAA','TAA'].includes(prefs.aaMethod)?Math.min(+prefs.aa,renderer.capabilities.maxSamples):0;composer.renderTarget1.samples=samples;composer.renderTarget2.samples=samples;ao.beautyRenderTarget.samples=samples;
 try{localStorage.setItem('jackdaw-depth-settings',JSON.stringify(prefs))}catch{}resize();}
function fit(direction=new THREE.Vector3(1,.4,1),bounds=box){if(!bounds)return;const center=bounds.getCenter(new THREE.Vector3()),d=direction.clone().normalize(),right=new THREE.Vector3().crossVectors(camera.up,d).normalize(),up=new THREE.Vector3().crossVectors(d,right);let distance=0;const tangent=Math.tan(THREE.MathUtils.degToRad(camera.fov/2));for(const x of [bounds.min.x,bounds.max.x])for(const y of [bounds.min.y,bounds.max.y])for(const z of [bounds.min.z,bounds.max.z]){const v=new THREE.Vector3(x,y,z).sub(center);distance=Math.max(distance,v.dot(d)+Math.max(Math.abs(v.dot(up))/tangent,Math.abs(v.dot(right))/(tangent*camera.aspect)))}controls.target.copy(center);camera.position.copy(center).addScaledVector(d,distance*1.08);camera.near=.05;camera.far=Math.max(distance*8,500);camera.updateProjectionMatrix();controls.update();}
function select(s,emit=true,additive=false){if(!additive)selection.clear();if(s){if(additive&&selection.has(s.key))selection.delete(s.key);else selection.set(s.key,s)}s=[...selection.values()].at(-1)||null;temporal.reset();lastMotion=performance.now()+500;selected=s;outline.selectedObjects=[...new Set([...selection.values()].flatMap(x=>groupSurfaces(x).map(y=>y.mesh)))];if(emit)notify(s?{type:'surface-selected',key:s.key,keys:[...selection.keys()],part:s.part,materialId:s.materialId}:{type:'selection-cleared'});}
function selectClick(s,additive=false){if(s?.materialId==='2296875182504')s=[...surfaces.values()].find(x=>x.materialId==='2296875182504');select(!additive&&selected&&s&&group(selected)===group(s)?null:s,true,additive)}
let down;renderer.domElement.addEventListener('pointerdown',e=>{down=[e.clientX,e.clientY,e.button]});renderer.domElement.addEventListener('pointerup',e=>{if(paint.active||!root||!down||down[2]!==0||Math.hypot(e.clientX-down[0],e.clientY-down[1])>4)return;pointer.set(e.clientX/innerWidth*2-1,1-e.clientY/innerHeight*2);ray.setFromCamera(pointer,camera);const hit=ray.intersectObject(root,true).find(h=>surfaces.get(h.object.userData.surfaceId)?.area);selectClick(hit?surfaces.get(hit.object.userData.surfaceId):null,e.ctrlKey||e.metaKey)});
function focus(mode){if(!root)return;if(mode==='ship'){fit();return}const allowed={cannon:[8],mortar:[10],swivel:[9],cabin:[3],deck:[1]};const b=new THREE.Box3();for(const s of surfaces.values())if(allowed[mode]?.includes(s.component))b.expandByObject(s.mesh);if(!b.isEmpty())fit(new THREE.Vector3(1,.75,1),b)}
async function setState(state){if(!ready){pendingState=state;return}const request=++revision,loaded=new Map();
 try{await Promise.all([...new Set(state.finishes.map(x=>x.url))].map(async url=>{const texture=await new THREE.TextureLoader().loadAsync(url);texture.colorSpace=THREE.SRGBColorSpace;texture.flipY=false;loaded.set(url,texture)}));if(request!==revision){for(const t of loaded.values())t.dispose();return}
 const entries=new Map(state.finishes.map(x=>[x.key,x]));for(const s of surfaces.values()){const entry=entries.get(s.key),previous=s.override;if(entry){const texture=loaded.get(entry.url).clone(),original=s.original.map;if(original){texture.wrapS=original.wrapS;texture.wrapT=original.wrapT;texture.offset.copy(original.offset);texture.repeat.copy(original.repeat);texture.rotation=original.rotation;texture.channel=original.channel}texture.flipY=!!entry.flipV;texture.needsUpdate=true;s.override=texture;s.current.map=texture;s.current.color.set(0xffffff)}else{s.override=null;s.current.map=s.original.map;s.current.color.copy(s.original.color)}previous?.dispose()}
 for(const t of loaded.values())t.dispose();update();notify({type:'state-applied',finishes:entries.size});
 }catch(e){for(const t of loaded.values())t.dispose();fail(e)}}
function receive(m){if(m.type==='state')setState(m);if(m.type==='select'&&!selection.has(m.key))select(byKey.get(m.key)||null,false);if(m.type==='clear-selection')select(null,false);if(m.type==='textures'){prefs.textures=!!m.enabled;update()}if(m.type==='settings')$('settings').open=!$('settings').open;if(m.type==='fit')fit();if(m.type==='focus')focus(m.mode);if(m.type==='fade'){prefs.focusFade=!!m.enabled;update()}}
window.addEventListener('keydown',e=>{if(e.key==='Escape')select(null)});
window.chrome?.webview?.addEventListener('message',e=>receive(e.data));
$('fit').onclick=()=>fit();$('side').onclick=()=>fit(new THREE.Vector3(1,.06,0));$('deck').onclick=()=>focus('deck');$('textures').onclick=()=>{prefs.textures=!prefs.textures;update();notify({type:'textures',enabled:prefs.textures})};
$('quality').onchange=e=>{prefs.quality=e.target.value;Object.assign(prefs,prefs.quality==='Low'?{occlusion:false,shadows:false,aa:0,aaMethod:'FXAA',shadowResolution:1024}:{occlusion:true,shadows:true,aa:prefs.quality==='High'?4:2,aaMethod:'MSAA',shadowResolution:2048});update()};for(const k of ['sailMotion','lanterns','normals','shadows','occlusion','aa','aaMethod','shadowResolution','aoStrength','aoRadius','lighting','exposure','wireframe','focusFade'])$(k).onchange=e=>{prefs[k]=e.target.type==='checkbox'?e.target.checked:e.target.value;update()};$('reset').onclick=()=>{prefs={...defaults};update()};window.addEventListener('resize',resize);
function fail(e){$('model-loader').hidden=true;console.error(e);$('error').style.display='block';$('error').textContent=e.message;notify({type:'error',message:e.message})}
function loading(stage,percent){$('model-stage').textContent=stage;const bar=$('model-progress');if(Number.isFinite(percent)){bar.value=Math.max(0,Math.min(100,percent));$('model-percent').textContent=Math.round(bar.value)+'%'}else{bar.removeAttribute('value');$('model-percent').textContent='Please wait'}}
 async function load(){loading('Reading model information…');const manifest=await(await fetch(base+'embedded-manifest.json',{cache:'no-store'})).json();const metadata=await(await fetch(base+'native-current-metadata.json',{cache:'no-store'})).json();if(metadata.source_sha256!==manifest.source_sha256)throw Error('Preview and editing model revisions do not match.');
 const parts=new Map();for(const [key,meta] of Object.entries(metadata.zones)){const name=THREE.PropertyBinding.sanitizeNodeName(meta.part);if(!parts.has(name))parts.set(name,new Map());parts.get(name).set(meta.material_id,{...meta,key})}
 const gltf=await new GLTFLoader().loadAsync(base+manifest.file+'?v='+manifest.sha256,e=>{loading(e.total&&e.loaded>=e.total?'Building ship surfaces…':'Loading ship model…',e.total?Math.min(85,85*e.loaded/e.total):undefined)});root=gltf.scene;loading('Preparing textures and materials…',90);
 root.traverse(o=>{if(!o.isMesh)return;let original=o.material;if(BigInt(original.userData.game_material_id||0)===2296875182504n){const fabric=new THREE.MeshPhysicalMaterial();THREE.MeshStandardMaterial.prototype.copy.call(fabric,original);fabric.sheen=.25;fabric.sheenColor.set('#b8ad99');fabric.sheenRoughness=.9;fabric.roughness=.82;original=fabric;o.material=fabric}const materialId=BigInt(original.userData.preview_material_id||original.userData.game_material_id).toString();let parent=o;while(parent&&!parts.has(parent.name))parent=parent.parent;const meta=parts.get(parent?.name)?.get(materialId);if(!meta)throw Error('Unmapped editable surface: '+o.name);const id=String(surfaces.size);const s={id,mesh:o,original,current:original.clone(),clay:new THREE.MeshStandardMaterial({color:0x9a9e9f,roughness:.75,side:THREE.DoubleSide}),normal:original.normalMap,materialId,...meta,component:+meta.key.split('/')[0]};if(!s.area&&s.original.metalnessMap)s.area='Metal fittings';surfaces.set(id,s);byKey.set(s.key,s);o.userData.surfaceId=id;o.castShadow=true;o.receiveShadow=true;});
 if(surfaces.size!==metadata.surfaces)throw Error('Ship surface count mismatch.');scene.add(root);box=new THREE.Box3().setFromObject(root);const center=box.getCenter(new THREE.Vector3()),extent=box.getSize(new THREE.Vector3()).length();key.position.copy(center).add(new THREE.Vector3(.5,.85,.4).multiplyScalar(extent));key.target.position.copy(center);key.shadow.camera.left=-extent*.55;key.shadow.camera.right=extent*.55;key.shadow.camera.top=extent*.55;key.shadow.camera.bottom=-extent*.55;key.shadow.camera.near=.1;key.shadow.camera.far=extent*3;key.shadow.normalBias=extent*.0004;key.shadow.bias=-.00003;key.shadow.camera.updateProjectionMatrix();const clothNormal=await new THREE.TextureLoader().loadAsync(base+'sail-cloth-normal-full.png');clothNormal.flipY=false;clothNormal.colorSpace=THREE.NoColorSpace;for(const s of surfaces.values())if(s.materialId==='2296875182504'){const old=s.normal;if(old){clothNormal.wrapS=old.wrapS;clothNormal.wrapT=old.wrapT;clothNormal.repeat.copy(old.repeat);clothNormal.offset.copy(old.offset)}s.normal=clothNormal;s.original.normalMap=clothNormal;s.current.normalMap=clothNormal;s.current.needsUpdate=true}
 loading('Preparing sails and lighting…',96);sailMotion=createSailMotion(surfaces,camera,controls);lanternLights=createLanternLights(surfaces,scene);ready=true;update();fit();loading('Ready',100);$('model-loader').hidden=true;notify({type:'ready',surfaces:surfaces.size,source_sha256:manifest.source_sha256});if(pendingState){setState(pendingState);pendingState=null}}
let frames=0,last=performance.now();function animate(){requestAnimationFrame(animate);controls.update();const now=performance.now(),dt=(now-previousFrame)/1000;previousFrame=now;if(sailMotion?.update(dt,prefs.sailMotion,paint.active)){temporal.reset();lastMotion=now;renderer.shadowMap.needsUpdate=true}for(const s of surfaces.values()){const faded=selected&&prefs.focusFade&&![...selection.values()].some(x=>group(x)===group(s)),m=s.mesh.material;const target=faded?.18:1;m.opacity=THREE.MathUtils.lerp(m.opacity,target,.17);const transparent=m.opacity<.995||s.original.transparent;if(m.transparent!==transparent){m.transparent=transparent;m.depthWrite=!transparent;m.needsUpdate=true}}
 ao.enabled=ready&&prefs.occlusion&&!selected;beauty.enabled=!ao.enabled;outline.enabled=!!selected;fxaa.enabled=prefs.aaMethod==='FXAA';temporal.enabled=prefs.aaMethod==='TAA'&&performance.now()-lastMotion>180;
 if(temporal.enabled){const offsets=[[-.375,-.375],[.125,-.125],[-.125,.375],[.375,.125],[-.375,.125],[.125,.375],[-.125,-.125],[.375,-.375]],j=offsets[temporal.count%8];const size=renderer.getDrawingBufferSize(new THREE.Vector2());camera.setViewOffset(size.x,size.y,j[0],j[1],size.x,size.y)}else temporal.reset();
 ao.ssaoMaterial.uniforms.cameraProjectionMatrix.value.copy(camera.projectionMatrix);ao.ssaoMaterial.uniforms.cameraInverseProjectionMatrix.value.copy(camera.projectionMatrixInverse);composer.render();if(temporal.enabled)camera.clearViewOffset();if(ready&&performance.now()-last>1500){$('status').textContent=`${Math.round(frames*1000/(performance.now()-last))} FPS Â· Drag to rotate Â· Right-drag to pan Â· Ctrl-click to add parts Â· Esc to clear`;frames=0;last=performance.now()}frames++}
window.jackdawViewer={debug:()=>({loaderHidden:document.getElementById('model-loader').hidden,sailMotion:sailMotion?.debug(),clothNormalSize:[...surfaces.values()].find(s=>s.materialId==='2296875182504')?.normal?.image?.width,lanterns:lanternLights?.debug(),ready,surfaces:surfaces.size,keys:byKey.size,selected:selected?.key,selectionCount:outline.selectedObjects.length,shadows:renderer.shadowMap.enabled,occlusion:ao.enabled,normalMaps:[...surfaces.values()].filter(s=>s.normal).length,metalMaps:[...surfaces.values()].filter(s=>s.original.metalnessMap).length,temporalSamples:temporal.count,preferences:prefs}),selectKey:key=>select(byKey.get(key)),clickKey:key=>selectClick(byKey.get(key)),receive,focus};
const paint=createSurfacePaint({canvas:renderer.domElement,controls,camera,root:()=>root,surface:o=>surfaces.get(o.userData.surfaceId),selected:()=>selected,group:groupSurfaces,notify,changed:()=>{temporal.reset();renderer.shadowMap.needsUpdate=true}});
window.jackdawViewer.testSails=()=>sailMotion.test();
window.jackdawViewer.testPaint=()=>{
 testPaintBoundaries();
 // Isolated uniquely mapped fixture exercises editing independently of the game's reused UVs.
 const fixtureImage=document.createElement('canvas');fixtureImage.width=fixtureImage.height=64;fixtureImage.getContext('2d').fillStyle='#ffffff';fixtureImage.getContext('2d').fillRect(0,0,64,64);
 const fixtureMap=new THREE.CanvasTexture(fixtureImage);fixtureMap.flipY=false;
 const fixtureMaterial=new THREE.MeshStandardMaterial({map:fixtureMap,side:THREE.DoubleSide});
 const fixture=new THREE.Mesh(new THREE.PlaneGeometry(2,2),fixtureMaterial);fixture.quaternion.copy(camera.quaternion);fixture.position.copy(camera.position).addScaledVector(camera.getWorldDirection(new THREE.Vector3()),3);root.add(fixture);fixture.updateWorldMatrix(true,false);
 const hit={id:'paint-test',key:'paint-test',part:'paint-test',materialId:'paint-test',mesh:fixture,current:fixtureMaterial,original:fixtureMaterial,area:'Paint test'},xy=[innerWidth/2,innerHeight/2];
 fixture.userData.surfaceId=hit.id;surfaces.set(hit.id,hit);select(hit,false);
 const original=hit.current.map;document.querySelector('[data-action=start]').click();
 const canvas=hit.current.map.image,before=canvas.toDataURL();
 renderer.domElement.dispatchEvent(new PointerEvent('pointermove',{clientX:xy[0],clientY:xy[1],bubbles:true}));
 const brushCursor=document.querySelector('[data-paint-cursor]');
 if(brushCursor.style.display!=='block'||!brushCursor.firstElementChild.getAttribute('d'))throw Error('Brush footprint cursor did not appear');
 renderer.domElement.dispatchEvent(new PointerEvent('pointerdown',{clientX:xy[0],clientY:xy[1],button:0,pointerId:0,bubbles:true}));
 renderer.domElement.dispatchEvent(new PointerEvent('pointerup',{clientX:xy[0],clientY:xy[1],button:0,pointerId:0,bubbles:true}));
 if(canvas.toDataURL()===before)throw Error('Stroke did not change texture pixels: '+hit.part);
 const painted=canvas.toDataURL();window.dispatchEvent(new KeyboardEvent('keydown',{key:'z',ctrlKey:true}));if(canvas.toDataURL()!==before)throw Error('Ctrl+Z failed');
 window.dispatchEvent(new KeyboardEvent('keydown',{key:'z',ctrlKey:true,shiftKey:true}));if(canvas.toDataURL()!==painted)throw Error('Ctrl+Shift+Z failed');
 window.dispatchEvent(new KeyboardEvent('keydown',{key:'z',ctrlKey:true}));if(canvas.toDataURL()!==before)throw Error('Repeated undo failed');
 const element=renderer.domElement,setCapture=element.setPointerCapture,releaseCapture=element.releasePointerCapture;
 element.setPointerCapture=()=>{};element.releasePointerCapture=()=>{};
 try {
  for(const button of [0,2]){
   if(button===0)window.dispatchEvent(new KeyboardEvent('keydown',{code:'Space',key:' ',ctrlKey:true}));
   const position=camera.position.clone(),target=controls.target.clone();
   element.dispatchEvent(new PointerEvent('pointerdown',{clientX:xy[0],clientY:xy[1],button,buttons:button===0?1:2,ctrlKey:button===0,pointerType:'mouse',pointerId:17,bubbles:true}));
   element.dispatchEvent(new PointerEvent('pointermove',{clientX:xy[0]+60,clientY:xy[1]+30,button,buttons:button===0?1:2,ctrlKey:button===0,pointerType:'mouse',pointerId:17,bubbles:true}));
   element.dispatchEvent(new PointerEvent('pointerup',{clientX:xy[0]+60,clientY:xy[1]+30,button,buttons:0,ctrlKey:button===0,pointerType:'mouse',pointerId:17,bubbles:true}));controls.update();if(button===0)window.dispatchEvent(new KeyboardEvent('keyup',{code:'Space',key:' '}));
   if(position.distanceTo(camera.position)<1e-5&&target.distanceTo(controls.target)<1e-5)throw Error(button===0?'Paint orbit failed':'Paint pan failed');
   if(canvas.toDataURL()!==before)throw Error('Navigation painted texture');
   if(selected!==hit)throw Error('Navigation changed selection');
  }
  const distance=camera.position.distanceTo(controls.target);
  element.dispatchEvent(new WheelEvent('wheel',{deltaY:-120,clientX:xy[0],clientY:xy[1],bubbles:true,cancelable:true}));controls.update();
  if(Math.abs(camera.position.distanceTo(controls.target)-distance)<1e-5)throw Error('Paint zoom failed');
 } finally {element.setPointerCapture=setCapture;element.releasePointerCapture=releaseCapture}
 document.querySelector('[data-action=cancel]').click();if(hit.current.map!==original)throw Error('Paint cancel failed');select(null,false);root.remove(fixture);surfaces.delete(hit.id);fixture.geometry.dispose();fixtureMaterial.dispose();fixtureMap.dispose();
 return 'PASS: UV boundary and overlap guards; Ctrl+Z undo and Ctrl+Shift+Z redo; brush footprint visible; painting and undo work; Ctrl+Space orbit, right-pan and wheel zoom work without painting or changing selection; cancel restores original';
};
update();animate();load().catch(fail);
