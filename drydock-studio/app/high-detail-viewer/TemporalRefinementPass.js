import {WebGLRenderTarget,HalfFloatType,ShaderMaterial,NoBlending} from 'three';
import {Pass,FullScreenQuad} from './vendor/stdlib/postprocessing/Pass.js';
// Static-view temporal supersampling. Reset on camera/content changes rather
// than reprojecting history without the motion vectors used by game TAA.
export class TemporalRefinementPass extends Pass {
 constructor(){super();this.count=0;this.history=new WebGLRenderTarget(1,1,{type:HalfFloatType});this.material=new ShaderMaterial({uniforms:{current:{value:null},history:{value:this.history.texture},weight:{value:1}},vertexShader:'varying vec2 v;void main(){v=uv;gl_Position=vec4(position.xy,0.,1.);}',fragmentShader:'uniform sampler2D current;uniform sampler2D history;uniform float weight;varying vec2 v;void main(){gl_FragColor=mix(texture2D(history,v),texture2D(current,v),weight);}',depthTest:false,depthWrite:false,blending:NoBlending});this.quad=new FullScreenQuad(this.material);}
 reset(){this.count=0}
 setSize(w,h){this.history.setSize(w,h);this.reset()}
 render(renderer,write,read){this.material.uniforms.current.value=read.texture;this.material.uniforms.weight.value=1/(Math.min(this.count,7)+1);renderer.setRenderTarget(write);this.quad.render(renderer);this.material.uniforms.current.value=write.texture;this.material.uniforms.weight.value=1;renderer.setRenderTarget(this.history);this.quad.render(renderer);this.count++;}
 dispose(){this.history.dispose();this.material.dispose();this.quad.dispose()}
}
