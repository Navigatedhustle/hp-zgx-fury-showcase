'use strict';
/* Original local Canvas sphere. Speech deformation follows the actual Web Audio signal. */
window.AtlasOrb=class {
 constructor(canvas){
  this.canvas=canvas;this.ctx=canvas.getContext('2d');this.state='idle';this.enabled=true;this.paused=false;this.analyser=null;this.bands=new Uint8Array(128);this.waveform=new Uint8Array(256);this.level=0;this.energy=0;this.last=0;this.frames=0;this.raf=null;
  this.reduced=matchMedia('(prefers-reduced-motion: reduce)');this.points=Array.from({length:850},(_,i)=>{const y=1-2*(i+.5)/850,a=i*Math.PI*(3-Math.sqrt(5)),r=Math.sqrt(1-y*y);return [Math.cos(a)*r,y,Math.sin(a)*r]});
  document.addEventListener('visibilitychange',()=>this.draw(performance.now(),true));this.reduced.addEventListener('change',()=>this.draw(performance.now(),true));
  this.resize=new ResizeObserver(()=>this.draw(performance.now(),true));this.resize.observe(canvas);
  this.visible=true;this.intersection=new IntersectionObserver(entries=>{this.visible=entries[0].isIntersecting;this.draw(performance.now(),true)});this.intersection.observe(canvas);
  this.theme=new MutationObserver(()=>this.draw(performance.now(),true));this.theme.observe(document.documentElement,{attributes:true,attributeFilter:['class','data-hp-theme']});this.theme.observe(document.body,{attributes:true,attributeFilter:['class']});this.draw(performance.now(),true);
 }
 setState(state){this.state=state;this.paused=false;this.changedAt=performance.now();this.stage({idle:'Ready · hold to ask',listening:'Listening · speak now',thinking:'Thinking · checking your data',speaking:'Speaking · local voice'}[state]||state);this.canvas.dataset.state=state;this.canvas.parentElement.setAttribute('aria-label',state==='speaking'?'Voice orb speaking. Hold to interrupt and ask.':'Hold the voice orb to ask Atlas');this.draw(performance.now(),true)}
 setPaused(paused){this.paused=paused;if(this.state==='speaking')this.stage(paused?'Audio paused':'Speaking · local voice');this.draw(performance.now(),true)}
 attachSpeech(context,node,output=context.destination){if(!this.speechAnalyser){this.speechAnalyser=context.createAnalyser();this.speechAnalyser.fftSize=256;this.speechAnalyser.smoothingTimeConstant=.65;this.speechAnalyser.connect(output)}node.connect(this.speechAnalyser);this.analyser=this.speechAnalyser;this.draw(performance.now(),true);return this.speechAnalyser}
 attach(context,node){this.analyser=context.createAnalyser();this.analyser.fftSize=256;this.analyser.smoothingTimeConstant=.55;node.connect(this.analyser);this.draw(performance.now(),true);return this.analyser}
 stage(label){const node=document.getElementById('orb-stage');if(node)node.textContent=label.toUpperCase()}
 schedule(){if(!this.reduced.matches&&!this.paused&&!document.hidden&&this.enabled&&this.visible)this.raf=requestAnimationFrame(t=>this.draw(t))}
 draw(now,immediate=false){
  if(this.raf!==null){cancelAnimationFrame(this.raf);this.raf=null}
  if(document.hidden||!this.enabled||!this.visible)return;
  const w=this.canvas.clientWidth,h=this.canvas.clientHeight;if(w<1||h<1)return;
  const active=['speaking','listening'].includes(this.state),fps=active?40:this.state==='thinking'?24:12;
  if(!immediate&&now-this.last<1000/fps){this.schedule();return}this.last=now;this.frames++;
  const dpr=Math.min(devicePixelRatio,2);if(this.canvas.width!==Math.round(w*dpr)||this.canvas.height!==Math.round(h*dpr)){this.canvas.width=Math.round(w*dpr);this.canvas.height=Math.round(h*dpr)}
  const c=this.ctx;c.setTransform(dpr,0,0,dpr,0,0);c.clearRect(0,0,w,h);
  let energy=0,low=0,high=0;
  if(this.analyser&&active&&!this.paused){this.analyser.getByteFrequencyData(this.bands);this.analyser.getByteTimeDomainData(this.waveform);let squares=0;for(let i=0;i<128;i++){low+=i<24?this.bands[i]:0;high+=i>64?this.bands[i]:0}for(const value of this.waveform)squares+=((value-128)/128)**2;energy=Math.min(1,Math.sqrt(squares/this.waveform.length)*2.2);low/=24*255;high/=63*255}
  this.level=energy;this.energy+=(energy-this.energy)*.3;
  const motion=this.reduced.matches?0:1,t=now*.00018*motion,e=this.paused?0:this.energy,thinking=this.state==='thinking';
  const radius=Math.min(w,h)*.345*(1+e*.16),angle=t*(thinking?1.8:1),dark=document.documentElement.classList.contains('dark'),ink=dark?'237,244,255':'2,74,216';
  const points=this.points.map(([x,y,z],i)=>{const a=angle+y*.18,xx=x*Math.cos(a)+z*Math.sin(a),zz=z*Math.cos(a)-x*Math.sin(a),wave=e*(Math.sin(y*11+t*10)*.17+Math.cos(x*9-t*8)*high*.3)+low*.075;return {x:w/2+xx*radius*(1+wave),y:h/2+(y+Math.sin(xx*4+t*3)*e*.09)*radius*(1+wave),z:zz,i}}).sort((a,b)=>a.z-b.z);
  c.strokeStyle=`rgba(${ink},${.11+e*.13})`;c.lineWidth=.7;
  for(let lat=-2;lat<=2;lat++){const y=lat*.31,r=Math.sqrt(1-y*y);c.beginPath();for(let n=0;n<=72;n++){const a=n*Math.PI/36+angle,xx=Math.cos(a)*r,zz=Math.sin(a)*r,wave=e*Math.sin(a*4+y*8+t*7)*.07,x=w/2+xx*radius*(1+wave),yy=h/2+(y+zz*.16)*radius;if(n===0)c.moveTo(x,yy);else c.lineTo(x,yy)}c.stroke()}
  for(const p of points){const front=(p.z+1)/2;c.fillStyle=`rgba(${ink},${.14+front*.78})`;c.beginPath();c.arc(p.x,p.y,(.55+front*1.1)*(1+e*.45),0,Math.PI*2);c.fill()}
  c.beginPath();c.strokeStyle=`rgba(${ink},${active?.3:.14})`;c.lineWidth=1;c.setLineDash(thinking?[2,5]:[]);c.ellipse(w/2,h/2,radius*1.21,radius*1.21,0,0,Math.PI*2);c.stroke();c.setLineDash([]);
  this.schedule();
 }
};
